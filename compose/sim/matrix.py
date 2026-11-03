"""
Electrical simulation of the routed boards:  python3 -m compose sim [outdir]

Independent of the net names used to build the boards:
  1. Copper connectivity is rebuilt from geometry (pad/track/via shapes that
     touch on a shared layer), so a short or a break shows up as such.
  2. Physical parts are placed the way a builder would:
       switch    the real MX pin positions (standard orientation, pins to the back)
                 on the face the silkscreen says, for each half
       socket    a Kailh contact joins a pin to its tab at the NOMINAL tab position
                 (so a nudged pad that no longer covers the tab fails)
       diode     anode -> cathode, cathode = the end with the band
       connector physical pin 1 where the silkscreen says ("L: pin 1" / "R: pin 1")
       cable     straight through, pin k to pin k
       Pico      datasheet pinout at its mechanical pin positions
     The right half is the same board flipped: switches and sockets enter from
     the other face, so their pins land on the mirrored positions.
  3. The QMK COL2ROW scan runs with the pins from out/firmware/keyboard.json:
     every key alone, then random multi-key chords (ghosting).
"""
import os
import sys
import json
import random
import itertools
import pcbnew
from shapely.geometry import Point, LineString, Polygon
from shapely.strtree import STRtree
from compose import params as PR
from compose import geom as G
from compose.case import sandwich as PT
from compose.pcb import layout as PL

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
PCB = os.path.join(OUT, "pcb")
ToMM = pcbnew.ToMM
FAIL = []
OX, OY, COX, COY = 40.0, 60.0, 60.0, 30.0       # same frames as compose/pcb/kicad.py


def ok(cond, msg):
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        FAIL.append(msg)


# ---------------------------------------------------------------- copper connectivity (geometry only)
class Copper:
    def __init__(self, path):
        self.b = pcbnew.LoadBoard(path)
        self.items = []                                   # (shape, layers, label)
        for fp in self.b.GetFootprints():
            for p in fp.Pads():
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    continue
                for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                    if not p.IsOnLayer(lay):
                        continue
                    ps = p.GetEffectivePolygon()
                    ol = ps.Outline(0)
                    pts = [(ToMM(ol.CPoint(i).x), ToMM(ol.CPoint(i).y)) for i in range(ol.PointCount())]
                    self.items.append((Polygon(pts).buffer(0), lay, f"{fp.GetReference()}.{p.GetNumber()}"))
        for t in self.b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                shp = Point(ToMM(q.x), ToMM(q.y)).buffer(ToMM(t.GetWidth()) / 2)
                for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                    self.items.append((shp, lay, "via"))
            else:
                a, c = t.GetStart(), t.GetEnd()
                shp = LineString([(ToMM(a.x), ToMM(a.y)), (ToMM(c.x), ToMM(c.y))]).buffer(ToMM(t.GetWidth()) / 2)
                self.items.append((shp, t.GetLayer(), "track"))
        # a PTH pad / via is one conductor on both layers: join its two layer entries
        self.parent = list(range(len(self.items)))
        key = {}
        for i, (s, lay, lab) in enumerate(self.items):
            if lab != "track":
                k = (lab, round(s.centroid.x, 3), round(s.centroid.y, 3))
                if k in key:
                    self.union(i, key[k])
                key[k] = i
        for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
            idx = [i for i, it in enumerate(self.items) if it[1] == lay]
            tree = STRtree([self.items[i][0] for i in idx])
            for n, i in enumerate(idx):
                for m in tree.query(self.items[i][0], predicate="intersects"):
                    self.union(i, idx[int(m)])

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def node_at(self, xy, layer):
        """Conductor group of the copper covering point xy on a layer (None if bare)."""
        p = Point(xy)
        hits = [i for i, (s, lay, lab) in enumerate(self.items) if lay == layer and lab != "track" and s.contains(p)]
        return self.find(hits[0]) if hits else None


def K(p, ox, oy):
    return (p[0] + ox, oy - p[1])


# ---------------------------------------------------------------- half board model
def half_model(variant, side):
    """Returns (edges, diodes, conn_pin_nodes) for one half as a builder would assemble it."""
    cu = Copper(os.path.join(PCB, f"half_{variant}.kicad_pcb"))
    plan = PL.plan_half()
    mir = side == "R"
    bottom = pcbnew.F_Cu if mir else pcbnew.B_Cu        # face the sockets/diodes sit on
    # standard MX pins seen from the switch side; on the flipped board they land mirrored
    pin_a, pin_b = PR.MX_PIN2, PR.MX_PIN1                # (-3.81,-2.54) and (2.54,-5.08)
    tab_a, tab_b = (-7.085, -2.54), (5.842, -5.08)        # Kailh nominal tabs for those contacts
    m = (lambda p: PL.mirror_fp(p)) if mir else (lambda p: p)
    switches = []
    for ks in plan.keys:
        k = ks.k
        loc = lambda p: K(PL.fp2local(k, *m(p)), OX, OY)
        if variant == "hotswap":
            a, b = cu.node_at(loc(tab_a), bottom), cu.node_at(loc(tab_b), bottom)
        else:
            a, b = cu.node_at(loc(pin_a), pcbnew.F_Cu), cu.node_at(loc(pin_b), pcbnew.F_Cu)
        switches.append((side, k, a, b))
    diodes = []
    for fp in cu.b.GetFootprints():
        if fp.GetReference().startswith("D"):
            pads = {p.GetNumber(): p for p in fp.Pads()}
            pc, pa = pads["1"].GetPosition(), pads["2"].GetPosition()     # pad 1 = cathode (band)
            diodes.append((cu.node_at((ToMM(pa.x), ToMM(pa.y)), pcbnew.F_Cu),
                           cu.node_at((ToMM(pc.x), ToMM(pc.y)), pcbnew.F_Cu)))
    n = PR.HALF_CONN_PINS
    order = plan.conn_pins if not mir else list(reversed(plan.conn_pins))   # physical pin 1 per silkscreen
    conn = {i + 1: cu.node_at(K(order[i], OX, OY), pcbnew.F_Cu) for i in range(n)}
    return cu, switches, diodes, conn


def ctrl_model():
    cu = Copper(os.path.join(PCB, "controller.kicad_pcb"))
    st = PT.Stack
    pico = {pin: cu.node_at(K(PL.pico_pin_xy(pin, st), COX, COY), pcbnew.F_Cu) for pin in range(1, 41)}
    conn = {}
    for sd in ("L", "R"):
        fp = [f for f in cu.b.GetFootprints() if f.GetReference() == f"J{sd}"][0]
        for p in fp.Pads():
            q = p.GetPosition()
            conn[(sd, int(p.GetNumber()))] = cu.node_at((ToMM(q.x), ToMM(q.y)), pcbnew.F_Cu)
    return cu, pico, conn


# ---------------------------------------------------------------- circuit + scan
def run(variant, kb):
    print(f"\n== {variant} half boards + controller")
    graph = {}                                        # undirected adjacency between global nodes

    def link(a, b):
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)

    diodes, switches = [], []
    cuc, pico, cconn = ctrl_model()
    gnode = lambda board, n: (board, n)
    for side in ("L", "R"):
        cu, sw, di, hconn = half_model(variant, side)
        tag = f"{side}"
        bad_sw = [s for s in sw if s[2] is None or s[3] is None]
        ok(not bad_sw, f"{side}: every switch terminal lands on copper ({len(sw) - len(bad_sw)}/{len(sw)})")
        bad_d = [d for d in di if d[0] is None or d[1] is None]
        ok(not bad_d, f"{side}: every diode lead lands on copper ({len(di) - len(bad_d)}/{len(di)})")
        for (s, k, a, b) in sw:
            switches.append((s, k, gnode(tag, a), gnode(tag, b)))
        for an, ca in di:
            diodes.append((gnode(tag, an), gnode(tag, ca)))
        for pin, node in hconn.items():               # cable: physical pin k to controller pin k
            link(gnode(tag, node), gnode("C", cconn[(side, pin)]))
    gpio_node = {}
    for pin, g in PL.PICO_PIN_GPIO.items():
        gpio_node[f"GP{g}"] = gnode("C", pico[pin])
    # shorts: two different GPIOs (or a GPIO and GND) in one copper group
    groups = {}
    for name, nd in gpio_node.items():
        groups.setdefault(nd, []).append(name)
    gnd = {gnode("C", pico[p]) for p in PL.PICO_GND_PINS}
    shorted = [v for v in groups.values() if len(v) > 1] + [[n] for n, nd in gpio_node.items() if nd in gnd]
    ok(not shorted, f"no GPIO shorted to another GPIO or to GND {shorted if shorted else ''}")

    rows = kb["matrix_pins"]["rows"]
    cols = kb["matrix_pins"]["cols"]

    def scan(pressed):
        """QMK COL2ROW: drive one row low, a column reads low if current can flow
        column -> switch -> diode (anode->cathode) -> row."""
        adj = {a: set(b) for a, b in graph.items()}
        for (s, k, a, b) in pressed:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        dir_adj = {}
        for an, ca in diodes:
            dir_adj.setdefault(an, set()).add(ca)
        found = set()
        for ci, cname in enumerate(cols):
            start = gpio_node[cname]
            seen, stack = {start}, [start]
            while stack:
                u = stack.pop()
                for v in itertools.chain(adj.get(u, ()), dir_adj.get(u, ())):
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
            for ri, rname in enumerate(rows):
                if gpio_node[rname] in seen:
                    found.add((ri, ci))
        return found

    # expected matrix position per physical key, from keyboard.json (label + which half)
    xs = [e["x"] for e in kb["layouts"]["LAYOUT"]["layout"]]
    mid = (min(xs) + max(xs)) / 2
    expect = {}
    for e in kb["layouts"]["LAYOUT"]["layout"]:
        expect[("L" if e["x"] < mid else "R", e["label"])] = tuple(e["matrix"])
    single_bad, seen_pos = [], {}
    for sw in switches:
        s, k, a, b = sw
        lab = k.label_l if s == "L" else k.label_r
        got = scan([sw])
        want = expect.get((s, lab))
        if got != {want}:
            single_bad.append((s, lab, sorted(got), want))
        seen_pos[(s, lab)] = got
    ok(not single_bad, f"every key alone is read at its keyboard.json position ({len(switches) - len(single_bad)}/{len(switches)})"
       + (f": {single_bad[:4]}" if single_bad else ""))
    ok(scan([]) == set(), "nothing reads as pressed with no key down")
    random.seed(1)
    ghosts = 0
    for n in (2, 3, 4, 6):
        for _ in range(150):
            chord = random.sample(switches, n)
            want = {expect[(s, k.label_l if s == "L" else k.label_r)] for s, k, a, b in chord}
            if scan(chord) != want:
                ghosts += 1
    ok(ghosts == 0, f"600 random 2/3/4/6-key chords read exactly the keys pressed (no ghosting): {ghosts} wrong")
    # the classic ghosting square: three corners of a row/col rectangle on one half
    sq = [sw for sw in switches if sw[0] == "L" and (sw[1].row, sw[1].col) in ((0, 0), (0, 1), (1, 0))]
    want = {expect[("L", s[1].label_l)] for s in sq}
    ok(scan(sq) == want, "3 corners of a matrix rectangle do not ghost the 4th (diodes block it)")
    # polarity check: the same boards with every diode reversed must NOT work
    saved = list(diodes)
    diodes[:] = [(c, a) for a, c in saved]
    rev_ok = sum(1 for sw in switches if scan([sw]) == {expect[(sw[0], sw[1].label_l if sw[0] == 'L' else sw[1].label_r)]})
    diodes[:] = saved
    ok(rev_ok == 0, f"negative control: with diodes reversed no key reads ({rev_ok} still read) - the scan is polarity-aware")


def negative_controls(kb):
    """Deliberately broken builds must fail, or the simulation is blind."""
    global half_model
    print("\n== negative controls (each must FAIL inside, PASS here)")
    import copy
    orig, saved_fail = half_model, list(FAIL)

    def quiet(variant, kbx):
        import io, contextlib
        FAIL.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            run(variant, kbx)
        return bool(FAIL)

    def wrong_conn(variant, side):
        cu, sw, di, conn = orig(variant, side)
        return cu, sw, di, ({PR.HALF_CONN_PINS + 1 - k: v for k, v in conn.items()} if side == "R" else conn)
    half_model = wrong_conn
    r1 = quiet("hotswap", kb)
    half_model = orig
    kb2 = copy.deepcopy(kb)
    c = kb2["matrix_pins"]["cols"]
    c[1], c[2] = c[2], c[1]
    r2 = quiet("solder", kb2)
    cu = Copper(os.path.join(PCB, "half_hotswap.kicad_pcb"))
    plan = PL.plan_half()
    no_mirror = sum(cu.node_at(K(PL.fp2local(ks.k, -7.085, -2.54), OX, OY), pcbnew.F_Cu) is not None for ks in plan.keys)
    off_pad = sum(cu.node_at(K(PL.fp2local(ks.k, 7.95, -5.08), OX, OY), pcbnew.B_Cu) is not None for ks in plan.keys)
    FAIL[:] = saved_fail
    ok(r1, "right connector read from the wrong end is caught")
    ok(r2, "two column pins swapped in the firmware is caught")
    ok(no_mirror == 0, "right-half sockets need the mirrored pads (standard spots on that face are bare)")
    ok(off_pad == 0, "a socket tab just off its pad is caught (the tab test is not trivially true)")


def main():
    kb = json.load(open(os.path.join(OUT, "firmware", "keyboard.json")))
    for variant in ("hotswap", "solder"):
        run(variant, kb)
    negative_controls(kb)
    print("\n" + ("SIMULATION PASSED" if not FAIL else f"{len(FAIL)} SIMULATION CHECK(S) FAILED"))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
