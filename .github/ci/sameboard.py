"""Is this board the same board as that one?

    python3 .github/ci/sameboard.py <a.kicad_pcb> <b.kicad_pcb> [name=<label>] [was="routed at <commit>"] [at=<commit>]

KiCad gives every item a new id each time a board is built and saves the items in the order of those ids, so
two builds of the same board never compare equal as files. This reads both boards, drops the ids and compares
what is left as a set of items: every footprint with its pads and position, every track and via, every zone
with its fill, every drawing, the nets, the layers and the rules. Nothing else is left out, so "the same" means
the same copper, the same parts in the same places and the same silkscreen.

A routed board has three files beside it: the job the router was handed (<board>.dsn), what it gave back
(<board>.ses) and its log (<board>_freerouting.log, which compose/pcb/toolbox.py starts with the way the router
was called). Where both boards have them, a difference is traced to where it comes from, because one kind of
difference is not a change: Freerouting 2.5.0 routes the same job the same way every time, pass for pass, but
its optimizer can then finish that routing in more than one way (seen on 18 Nov 2026: one junction of one net,
a quarter of a millimetre of track). The verdicts:

  the same board           every item the same
  the same routing         the same job (.dsn and call), the routing stage the same pass for pass in both logs,
                           and the optimizer ending on another board in one of its passes; only tracks and vias
                           differ, and only on nets where the router's two results differ
  differs                  anything else, with the reason: another job, another routing, more than the router's
                           own tracks, or the same result from the router and another board made from it

Prints the verdict and what differs. Writes same=true|false and verdict=same|routing|differs to $GITHUB_OUTPUT
and a line to the job summary. Exits 0 either way: whether a difference is a mistake depends on the change (a
design change moves copper on purpose; a reorganisation must not), so the caller decides.
"""
import collections
import math
import os
import re
import sys

IDS = ("tstamp", "uuid")             # per-build ids (KiCad 7 writes tstamp, later versions uuid)
ROUTED = ("segment", "via", "arc")   # the kinds of item a router lays
UNORDERED = ("kicad_pcb", "footprint", "zone")    # their children are saved in id order; elsewhere order is content
TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text):
    """The file as nested lists: ["kicad_pcb", ["version", "20221018"], ...]."""
    stack, cur = [], []
    for t in TOKEN.findall(text):
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(t)
    if stack or len(cur) != 1:
        raise ValueError("not one complete s-expression")
    return cur[0]


def canon(node):
    """A node as text without its ids; the children of the kinds in UNORDERED sorted."""
    if not isinstance(node, list):
        return node
    if not node:
        return "()"
    kept = [c for c in node[1:] if not (isinstance(c, list) and c and c[0] in IDS)]
    if node[0] in UNORDERED:
        body = [c for c in kept if not isinstance(c, list)] + sorted(canon(c) for c in kept if isinstance(c, list))
    else:
        body = [canon(c) for c in kept]
    return "(" + " ".join([canon(node[0])] + body) + ")"


def items(path):
    """The board's top-level items, canonical, as a multiset."""
    tree = parse(open(path, encoding="utf-8").read())
    if not tree or tree[0] != "kicad_pcb":
        raise ValueError(f"{path}: not a KiCad board")
    return collections.Counter(canon(c) for c in tree[1:])


def label(item):
    """A short name for an item: its kind, and for a part its reference and position."""
    kind = item[1:].split(" ", 1)[0].rstrip(")")
    if kind == "footprint":
        ref = re.search(r'\(fp_text reference ("[^"]*"|\S+)', item)
        at = re.search(r"\(at ([-\d.]+ [-\d.]+)", item)
        return kind, f"{ref.group(1) if ref else '?'} at {at.group(1) if at else '?'}"
    if kind in ("segment", "via", "arc"):
        return kind, item[:110]
    return kind, item[:80]


def compare(a, b):
    """(same?, lines): the items only in a or only in b, counted by kind."""
    same, lines, _, _ = _compare(a, b)
    return same, lines


def _compare(a, b):
    ia, ib = items(a), items(b)
    only_a, only_b = ia - ib, ib - ia
    if not only_a and not only_b:
        return True, [f"{sum(ia.values())} items, all the same apart from the ids KiCad gives on every build"], ia, ib
    lines = []
    kinds = sorted({label(i)[0] for i in list(only_a) + list(only_b)})
    for k in kinds:
        xa = [i for i in only_a.elements() if label(i)[0] == k]
        xb = [i for i in only_b.elements() if label(i)[0] == k]
        eg = label((xa or xb)[0])[1]
        lines.append(f"{k}: {len(xa)} only in the first, {len(xb)} only in the second (e.g. {eg})")
    return False, lines, ia, ib


# ---------------------------------------------------------------- where a routed board's difference comes from
def beside(pcb):
    """The router's files beside a board: (job, result, log), or None if one is missing."""
    stem = pcb[:-len(".kicad_pcb")] if pcb.endswith(".kicad_pcb") else pcb
    files = (stem + ".dsn", stem + ".ses", stem + "_freerouting.log")
    return files if all(os.path.isfile(f) for f in files) else None


def router_log(path):
    """What a Freerouting 2.5 log says was done: how the router was called (the line toolbox.py writes first), the
    board after every routing pass, the board the optimizer started from and the board after each of its passes.
    Boards are the router's own fingerprints of them."""
    t = open(path, encoding="utf-8", errors="replace").read()
    call = re.search(r"^compose: (.*)$", t, re.M)
    start = re.search(r"Optimization stage started on board '(\w+)'", t)
    return dict(
        call=call.group(1).strip() if call else None,
        routing=re.findall(r"Auto-routing pass #(\d+) on board '(\w+)' was completed in \S+ seconds with score ([\d.]+) "
                           r"\((\d+) unrouted", t),
        start=start.group(1) if start else None,
        optimizer=re.findall(r"Optimizer pass #(\d+) on board '(\w+)' was completed in \S+ seconds with the score of ([\d.]+)", t))


def routed_nets(path):
    """{net: its wires and vias} in what the router gave back (.ses)."""
    out = {}

    def walk(node):
        if not isinstance(node, list) or not node:
            return
        if node[0] == "network_out":
            for c in node[1:]:
                if isinstance(c, list) and len(c) > 1 and c[0] == "net":
                    out[c[1].strip('"')] = tuple(sorted(canon(x) for x in c[2:]))
            return
        for c in node[1:]:
            walk(c)
    walk(parse(open(path, encoding="utf-8").read()))
    return out


def net_names(board_items):
    """{number: name} from a board's net table."""
    out = {}
    for i in board_items:
        m = re.fullmatch(r'\(net (\d+) ("(?:[^"\\]|\\.)*"|\S+)\)', i)
        if m:
            out[m.group(1)] = m.group(2).strip('"')
    return out


def tracks(only, names):
    """{net name: (segments, vias, mm of track)} for the routed items among `only`."""
    out = collections.defaultdict(lambda: [0, 0, 0.0])
    for i in only.elements():
        kind = label(i)[0]
        net = re.search(r"\(net (\d+)\)", i)
        row = out[names.get(net.group(1), "net " + net.group(1)) if net else "?"]
        if kind == "via":
            row[1] += 1
        else:
            row[0] += 1
            m = re.search(r"\(start ([-\d.]+) ([-\d.]+)\).*?\(end ([-\d.]+) ([-\d.]+)\)", i)
            if m:
                x1, y1, x2, y2 = map(float, m.groups())
                row[2] += math.dist((x1, y1), (x2, y2))
    return out


def job(a, b):
    """(the router was handed the same job? None if it cannot be told, why not): the same .dsn, and called the
    same way."""
    (dsn_a, _, log_a), (dsn_b, _, log_b) = beside(a), beside(b)
    ca, cb = router_log(log_a)["call"], router_log(log_b)["call"]
    if open(dsn_a, "rb").read() != open(dsn_b, "rb").read():
        return False, "the router's job (.dsn) is not the same"
    if ca is None or cb is None:
        return None, "the job (.dsn) is the same, but one of the two logs does not say how the router was called"
    if ca != cb:
        return False, f"the job (.dsn) is the same but the router was called another way: {ca} / {cb}"
    return True, ""


def trace(a, b, ia, ib):
    """Two routed boards that differ, with the router's files beside both and the same job: (the same routing?,
    lines saying where the difference comes from)."""
    (_, ses_a, log_a), (_, ses_b, log_b) = beside(a), beside(b)
    la, lb = router_log(log_a), router_log(log_b)
    if not la["routing"] or la["start"] is None or lb["start"] is None:
        return False, ["the router's log does not show its passes, so the difference cannot be traced"]
    if la["routing"] != lb["routing"] or la["start"] != lb["start"]:
        n = next((x[0] for x, y in zip(la["routing"], lb["routing"]) if x != y), "the last")
        return False, [f"the router routed the same job another way, from auto-routing pass {n} on"]
    if la["optimizer"] == lb["optimizer"]:
        return False, ["the router ended on the same board both times: the difference was made after it"]
    only_a, only_b = ia - ib, ib - ia
    other = sorted({label(i)[0] for i in list(only_a) + list(only_b)} - set(ROUTED))
    if other:
        return False, ["the router's optimizer ended on another board, but more than its tracks differ: " + ", ".join(other)]
    na, nb = routed_nets(ses_a), routed_nets(ses_b)
    moved = {n for n in set(na) | set(nb) if na.get(n) != nb.get(n)}
    ta, tb = tracks(only_a, net_names(ia)), tracks(only_b, net_names(ib))
    stray = sorted((set(ta) | set(tb)) - moved)
    if stray:
        return False, ["tracks differ on " + ", ".join(stray) + ", where the router's two results are the same"]
    k = next((i for i, (x, y) in enumerate(zip(la["optimizer"], lb["optimizer"])) if x != y), min(len(la["optimizer"]), len(lb["optimizer"])))
    x = la["optimizer"][k] if k < len(la["optimizer"]) else None
    y = lb["optimizer"][k] if k < len(lb["optimizer"]) else None
    before = {0: "", 1: ", and so is optimizer pass 1"}.get(k, f", and so are optimizer passes 1 to {k}")
    lines = [f"the {len(la['routing'])} routing passes are the same in both logs{before}"
             + f"; optimizer pass {k + 1} ended on another board (score {x[2] if x else 'none'} before, {y[2] if y else 'none'} now)"]
    for n in sorted(set(ta) | set(tb)):
        (sa, va, da), (sb, vb, db) = ta.get(n, (0, 0, 0.0)), tb.get(n, (0, 0, 0.0))
        lines.append(f"{n}: {sa} segments, {va} vias, {da:.3f} mm before; {sb} segments, {vb} vias, {db:.3f} mm now")
    return True, lines


def judge(a, b, name, was="the other", at="for the other"):
    """("same" | "routing" | "differs", the verdict's lines, what differs)."""
    same, lines, ia, ib = _compare(a, b)
    verdict, heads = "same" if same else "differs", []
    if beside(a) and beside(b):
        handed, why_not = job(a, b)
        heads.append({True: f"{name}: the router was handed the same job as {at}",
                      False: f"{name}: the router was not handed the same job as {at}",
                      None: f"{name}: it cannot be told whether the router was handed the same job as {at}"}[handed])
        if not same and handed:
            routing, why = trace(a, b, ia, ib)
            verdict = "routing" if routing else "differs"
            lines = why + ([] if routing else lines)
        elif not handed:
            lines = [why_not] + ([] if same else lines)
    heads.append({"same": f"{name}: the same board as {was}",
                  "routing": f"{name}: the same routing as {was}, finished another way by the router's optimizer",
                  "differs": f"{name}: differs from {was}"}[verdict])
    return verdict, heads, lines


def main():
    a, b = sys.argv[1:3]
    kv = dict(x.split("=", 1) for x in sys.argv[3:])
    name = kv.get("name") or os.path.basename(b).split(".")[0]
    verdict, heads, lines = judge(a, b, name, f"the one {kv['was']}" if kv.get("was") else "the other",
                                  f"at {kv['at']}" if kv.get("at") else "for the other")
    same = verdict == "same"
    for h in heads:
        print(h)
    for ln in lines:
        print("  " + ln)
    if verdict == "differs" and os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title={name} changed::{heads[-1]}: " + "; ".join(ln.split(" (e.g.")[0] for ln in lines))
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as o:
        o.write(f"same={'true' if same else 'false'}\nverdict={verdict}\n")
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as o:
        o.write("".join(f"**{h}**\n\n" for h in heads) + ("" if verdict == "same" else "\n".join("- " + ln for ln in lines) + "\n\n"))


if __name__ == "__main__":
    main()
