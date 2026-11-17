"""Is this board the same board as that one?

    python3 .github/ci/sameboard.py <a.kicad_pcb> <b.kicad_pcb> [name=<label>] [was="routed at <commit>"]

KiCad gives every item a new id each time a board is built and saves the items in the order of those ids, so
two builds of the same board never compare equal as files. This reads both boards, drops the ids and compares
what is left as a set of items: every footprint with its pads and position, every track and via, every zone
with its fill, every drawing, the nets, the layers and the rules. Nothing else is left out, so "the same" means
the same copper, the same parts in the same places and the same silkscreen.

Prints the verdict and, if the boards differ, how many items of each kind are only in one of them, with an
example of each. Writes same=true|false to $GITHUB_OUTPUT and a line to the job summary. Exits 0 either way:
whether a difference is a mistake depends on the change (a design change moves copper on purpose; a
reorganisation must not), so the caller decides.
"""
import collections
import os
import re
import sys

IDS = ("tstamp", "uuid")             # per-build ids (KiCad 7 writes tstamp, later versions uuid)
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
    ia, ib = items(a), items(b)
    only_a, only_b = ia - ib, ib - ia
    if not only_a and not only_b:
        return True, [f"{sum(ia.values())} items, all the same apart from the ids KiCad gives on every build"]
    lines = []
    kinds = sorted({label(i)[0] for i in list(only_a) + list(only_b)})
    for k in kinds:
        xa = [i for i in only_a.elements() if label(i)[0] == k]
        xb = [i for i in only_b.elements() if label(i)[0] == k]
        eg = label((xa or xb)[0])[1]
        lines.append(f"{k}: {len(xa)} only in the first, {len(xb)} only in the second (e.g. {eg})")
    return False, lines


def main():
    a, b = sys.argv[1:3]
    kv = dict(x.split("=", 1) for x in sys.argv[3:])
    name = kv.get("name") or os.path.basename(b).split(".")[0]
    was = f"the one {kv['was']}" if kv.get("was") else "the other"
    same, lines = compare(a, b)
    head = f"{name}: the same board as {was}" if same else f"{name}: differs from {was}"
    print(head)
    for ln in lines:
        print("  " + ln)
    if not same and os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title={name} changed::{head}: " + "; ".join(ln.split(" (e.g.")[0] for ln in lines))
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as o:
        o.write(f"same={'true' if same else 'false'}\n")
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as o:
        o.write(f"**{head}**" + ("" if same else "\n\n" + "\n".join("- " + ln for ln in lines)) + "\n\n")


if __name__ == "__main__":
    main()
