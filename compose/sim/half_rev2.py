"""
Copper-level simulation of the rev 2 half boards with controller rev 2:
    C58_REV=2 python3 -m compose sim-half-rev2 OUT      (after `half-rev2` and `controller`)

Independent of the net names the boards were built with:
  1. Copper connectivity of every routed board is rebuilt from geometry (pads, tracks, vias that touch).
  2. Parts are fitted the way a builder would, per half: the left half is the board switch-side-up (sockets,
     LEDs, capacitors and connector on the bottom face B), the right half the same board flipped (all of that
     on F). Positions come from the plan and the parts' datasheets, not from pad nets:
       switch      contacts at the MX pin positions (solder) or the socket tabs beside them (hotswap)
       diode       cathode = the band end (the square pad), anode = the other
       FFC         contacts at the physical slots: slot 1 = the back-most contact
       MINI-E      pins 1-4 = VDD, DOUT, GND, DIN at their datasheet corners, seen from the pad side
  3. Per board: each key is a switch between its column's slot and its diode, the diode's cathode on its row's
     slot (COL2ROW); unused slots touch nothing; RGB boards: one unbroken chain slot 3 -> 29 LEDs -> slot 18 on
     the fitted face, every LED and capacitor across slot 2/19 (5 V) and 1/4/20 (GND), the unfitted face's
     copies harmless; plain boards: slot 3 wired straight to slot 18 and nothing else on 1-4 / 18-20.
  4. End to end: the controller rev 2 copper, two straight type B FFCs (same physical slot order at both
     ends) and the two real halves; the QMK COL2ROW scan with the rev 2 pin config reads every key alone at
     its keymap position, 1000 random chords exactly, and no ghosting.
  5. Negative controls: a cut column track, a diode fitted backwards and a cable reversed are caught.
"""
import os
import sys
import random
import itertools
import pcbnew

OUT = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
CTRL_OUT = os.environ.get("CTRL_OUT", "out")
sys.argv = sys.argv[:1] + [OUT]
from compose import params as PR
from compose import geom as G
from compose.pcb import layout as PL
from compose.pcb import rev2_half as H
from compose.sim import matrix as SP
from compose.sim import controller_copper as CC

ToMM = pcbnew.ToMM
FAIL = []
OX, OY = 40.0, 60.0
L = G.LAYOUT
F, B = pcbnew.F_Cu, pcbnew.B_Cu


def ok(cond, msg):
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        FAIL.append(msg)
    return cond


def K(p):
    return (p[0] + OX, OY - p[1])


def mirror(p):
    return PL.mirror_fp(p)


class Half:
    """One routed board fitted as one half: copper groups of every part pin."""

    def __init__(self, path, variant, rgb, side):
        self.cu = SP.Copper(path)
        self.b = self.cu.b
        self.fp = {f.GetReference(): f for f in self.b.GetFootprints()}
        self.variant, self.rgb, self.side = variant, rgb, side
        self.bottom = B if side == "L" else F
        self.s = H.plan(variant, rgb)

    def at(self, local_xy, layer=None):
        n = self.cu.node_at(K(local_xy), layer if layer is not None else self.bottom)
        if n is None and layer is None:
            n = self.cu.node_at(K(local_xy), F if self.bottom == B else B)
        return n

    def pad_nodes(self, ref, layer):
        out = []
        for p in self.fp[ref].Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            q = (ToMM(p.GetPosition().x), ToMM(p.GetPosition().y))
            out.append((p, self.cu.node_at(q, layer)))
        return out

    def slots(self):
        """Fitted connector (the bottom face's): slot -> group. Slot 1 = the back-most contact (smallest KiCad
        y on either face: flipping the board over mirrors x only)."""
        ref = "J1B" if self.side == "L" else "J1F"
        pads = [p for p in self.fp[ref].Pads() if p.GetNumber() != "MP"]
        pads.sort(key=lambda p: p.GetPosition().y)
        return {k + 1: self.cu.node_at((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)), self.bottom)
                for k, p in enumerate(pads)}

    def keys(self):
        """[(key index, row, col, switch contact a, contact b, diode anode, diode cathode)] as copper groups."""
        out = []
        for ks in self.s.keys:
            k = ks.k
            if self.variant == "hotswap":
                # socket tabs on the bottom face; on the flipped board they're the mirrored copies
                (c2, _), (c1, _) = PR.HS_PAD2, PR.HS_PAD1
                if self.side == "R":
                    c1, c2 = mirror(c1), mirror(c2)
                sa, sb = self.at(PL.fp2local(k, *c1)), self.at(PL.fp2local(k, *c2))
            else:
                p1, p2 = PR.MX_PIN1, PR.MX_PIN2
                if self.side == "R":
                    p1, p2 = mirror(p1), mirror(p2)
                sa, sb = self.at(PL.fp2local(k, *p1), F), self.at(PL.fp2local(k, *p2), F)
            d = self.fp[ks.dref]
            square = (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT)
            sq = [p for p in d.Pads() if p.GetShape() in square]       # (SWIG pad objects don't compare equal)
            rd = [p for p in d.Pads() if p.GetShape() not in square]
            xy = lambda p: (ToMM(p.GetPosition().x), ToMM(p.GetPosition().y))
            cath, an = self.cu.node_at(xy(sq[0]), F), self.cu.node_at(xy(rd[0]), F)
            out.append((ks.i, ks.row, ks.col, sa, sb, an, cath))
        return out

    def leds(self):
        """Fitted LEDs in chain order: [(VDD, DOUT, GND, DIN)] groups, located by plan position and datasheet
        corner (pad-side view), not by pad number."""
        face = "B" if self.side == "L" else "F"
        out = []
        for i in self.s.led_order:
            k = L.keys[i]
            pads = H.led_pads(k, face)               # plan: pin -> pad polygon on that face
            g = {pin: self.at(poly.centroid.coords[0]) for pin, poly in pads.items()}
            out.append((g["1"], g["2"], g["3"], g["4"]))
        return out

    def caps(self):
        face = "B" if self.side == "L" else "F"
        return [tuple(self.at(p) for p in H.cap_pads(L.keys[i], face)) for i in self.s.caps]


def board_checks(h):
    name = f"{h.variant}{' rgb' if h.rgb else ''} as {'lhs' if h.side == 'L' else 'rhs'}"
    print(f"\n== {name}")
    sl = h.slots()
    ok(all(v is not None for v in sl.values()), "every connector contact is on copper")
    keys = h.keys()
    ok(all(None not in k[3:] for k in keys), f"every switch contact and diode lead is on copper ({len(keys)} keys)")
    col = {c: sl[5 + c] for c in range(7)}
    row = {r: sl[12 + r] for r in range(6)}
    bad = []
    for i, r, c, sa, sb, an, cath in keys:
        if sb != col[c] and sa != col[c]:
            bad.append(f"key {i}: no contact on COL{c} (slot {5 + c})")
        other = sa if sb == col[c] else sb
        if other != an:
            bad.append(f"key {i}: switch not wired to its diode's anode")
        if cath != row[r]:
            bad.append(f"key {i}: diode cathode not on ROW{r} (slot {12 + r})")
    ok(not bad, "every key: column slot -> switch -> diode anode, cathode -> row slot" + (f" ({bad[:3]})" if bad else ""))
    used = {5 + c for c in {k.col for k in L.keys}} | {12 + r for r in {k.row for k in L.keys}}
    spare = [k for k in range(5, 18) if k not in used]
    groups = {}
    for k_, g in sl.items():
        groups.setdefault(g, []).append(k_)
    shared = [v for v in groups.values() if len(v) > 1 and set(v) not in ({1, 4, 20}, {2, 19}, {3, 18})]
    ok(not shared, f"no two connector slots joined except GND 1/4/20, 5 V 2/19{' and the pass-through 3/18' if not h.rgb else ''}"
       + (f" ({shared})" if shared else ""))
    anods = {k[5] for k in keys}
    live = {sl[k_] for k_ in used}
    for k_ in spare:
        ok(sl[k_] not in anods and sl[k_] not in live,
           f"spare slot {k_} ({CC.SLOTS[k_]}) touches nothing of the matrix")
    if not h.rgb:
        ok(sl[3] == sl[18], "no LEDs: slot 3 (RGB in) wired straight to slot 18 (RGB back)")
        mat = live | anods
        ok(not ({sl[1], sl[2], sl[4], sl[19], sl[20]} & mat), "GND / 5 V slots don't touch the matrix")
        return
    leds = h.leds()
    ok(all(None not in l_ for l_ in leds), f"every fitted LED pad is on copper ({len(leds)} LEDs)")
    gnd, vdd = sl[1], sl[2]
    ok(sl[4] == gnd and sl[20] == gnd and sl[19] == vdd and gnd != vdd, "GND on slots 1/4/20, 5 V on 2/19, apart")
    ok(all(l_[0] == vdd and l_[2] == gnd for l_ in leds), "every LED: VDD on 5 V, GND on GND")
    cur, chain = sl[3], 0
    for vd, do, gn, di in leds:
        if di != cur:
            break
        chain += 1
        cur = do
    ok(chain == len(leds) and cur == sl[18],
       f"one chain: slot 3 -> DIN ... DOUT -> slot 18 through all {len(leds)} LEDs (unbroken for {chain})")
    douts = [l_[1] for l_ in leds]
    ok(len(set(douts)) == len(douts), "no two LED outputs on one line")
    ok(not ({l_[1] for l_ in leds} | {l_[3] for l_ in leds}) & (live | anods | {gnd, vdd}),
       "LED data lines touch nothing of the matrix or power")
    cps = h.caps()
    ok(all(set(c_) == {vdd, gnd} for c_ in cps), f"every capacitor across 5 V / GND ({len(cps)}, one per {H.CAP_EVERY} LEDs)")


# ---------------------------------------------------------------- end to end
def assemble(pins, halves, cable_rev=None, cut=None, diode_flip=None):
    edges = {}

    def link(a, b):
        edges.setdefault(a, set()).add(b)
        edges.setdefault(b, set()).add(a)
    keys, diodes = [], []
    for side, h in halves.items():
        sl = h.slots()
        for k in range(1, 21):
            hk = 21 - k if cable_rev == side else k
            if sl[hk] is not None:
                link(("C", pins[("ffc" + side, k)]), (side, sl[hk]))
        for i, r, c, sa, sb, an, cath in h.keys():
            colside = sb if sb == sl[5 + c] else sa
            other = sa if colside == sb else sb
            if cut == (side, i):
                colside = ("cut", side, i)
            keys.append(((side, i), (side, colside), (side, other)))
            a, c_ = (side, an), (side, cath)
            if diode_flip == (side, i):
                a, c_ = c_, a
            diodes.append((a, c_))
            if other != an:
                link((side, other), (side, an))
    return edges, keys, diodes


def run(pins, halves, quiet=False, **kw):
    edges, keys, diodes = assemble(pins, halves, **kw)
    scan = CC.scanner(pins, edges, keys, diodes, CC.QMK_V2)
    meta = {(s, ks.i): (ks.row, ks.col) for s, h in halves.items() for ks in h.s.keys}
    exp = lambda k: (meta[k][0], meta[k][1] if k[0] == "L" else 13 - meta[k][1])
    allk = [k for k, _, _ in keys]
    single = [k for k in allk if scan([k]) != {exp(k)}]
    random.seed(11)
    wrong = 0
    for n in (2, 3, 4, 6, 10):
        for _ in range(200):
            ch = random.sample(allk, n)
            if scan(ch) != {exp(k) for k in ch}:
                wrong += 1
    if not quiet:
        ok(not single, f"every key alone reads at its keymap position ({len(allk) - len(single)}/{len(allk)})")
        ok(scan([]) == set(), "nothing reads with no key down")
        ok(wrong == 0, f"1000 random 2/3/4/6/10-key chords read exactly the keys pressed: {wrong} wrong")
        bl = [k for k in allk if k[0] == "L"]
        sq = None
        for a, b_, c in itertools.combinations(bl, 3):
            ra, ca = meta[a]
            rb, cb = meta[b_]
            rc, cc = meta[c]
            if ra == rb and ca == cc and rb != rc and ca != cb:
                d = [k for k in bl if meta[k] == (rc, cb)]
                if d:
                    sq = [a, b_, c]
                    break
        if sq:
            ok(scan(sq) == {exp(k) for k in sq}, "3 corners of a matrix rectangle don't ghost the 4th")
    return single, wrong


def main():
    ctrl = os.path.join(CTRL_OUT, "pcb", "controller_rev2.kicad_pcb")
    print(f"== controller rev 2 copper: {ctrl}")
    CB = CC.Board(ctrl)
    pins = CC.place_parts(CB)
    from compose import firmware_rev2 as FW
    fw = FW.board(True)
    ok(fw["matrix_pins"] == CC.QMK_V2["matrix_pins"] and fw["diode_direction"] == CC.QMK_V2["diode_direction"]
       and fw["ws2812"]["pin"] == CC.QMK_V2["ws2812"]["pin"], "firmware-rev2 keyboard.json pins = the pin config scanned here")
    exp_m = {(s_, ks.i): [ks.row, ks.col if s_ == "L" else 13 - ks.col] for s_ in ("L", "R") for ks in H.plan().keys}
    ok(sorted(e["matrix"] for e in fw["layouts"]["LAYOUT"]["layout"]) == sorted(exp_m.values()),
       "keyboard.json lists every key at the matrix position the scan reads it")
    pcb = os.path.join(OUT, "pcb")
    only = [a for a in sys.argv[2:]] or os.environ.get("SIM_BOARDS", "").split() or list(H.BOARDS)
    for name, (variant, rgb) in H.BOARDS.items():
        if name not in only:
            continue
        path = os.path.join(pcb, name + ".kicad_pcb")
        if not os.path.exists(path):
            ok(False, f"{name}: not built")
            continue
        halves = {s: Half(path, variant, rgb, s) for s in ("L", "R")}
        for h in halves.values():
            board_checks(h)
        print(f"\n== {name}: QMK COL2ROW scan, controller rev 2 + two FFCs + both halves")
        run(pins, halves)
        k0 = halves["L"].s.keys[7]
        s_, _ = run(pins, halves, quiet=True, cut=("L", k0.i))
        ok(("L", k0.i) in s_, f"negative control: a cut column connection kills key {k0.k.label_l} ... and the scan sees it")
        s_, _ = run(pins, halves, quiet=True, diode_flip=("R", 3))
        ok(("R", 3) in s_, "negative control: a diode fitted backwards is caught")
        s_, w_ = run(pins, halves, quiet=True, cable_rev="L")
        ok(len(s_) > 0, f"negative control: a reversed left cable scrambles the left half ({len(s_)} keys wrong)")
    print("\n" + ("SIMULATION PASSED" if not FAIL else f"{len(FAIL)} SIMULATION CHECK(S) FAILED"))
    return len(FAIL)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
