"""
Copper-level simulation of the rev 2 half boards with controller rev 2:
    C58_REV=2 python3 -m compose sim-half-rev2 OUT      (after `half-rev2` and `controller`)

Independent of the net names the boards were built with:
  1. Copper connectivity of every routed board is rebuilt from geometry (pads, tracks, vias that touch).
  2. Parts are fitted the way a builder would, per half: the left half is the board switch-side-up (sockets,
     LEDs, capacitors and connector on the bottom face B), the right half the same board flipped (all of that
     on F), and only copper on that face counts. Positions come from the plan and the parts' datasheets, not
     from pad nets:
       switch      contacts at the MX pin positions (solder) or the Kailh socket's nominal tabs (hotswap)
       diode       cathode = the band end (the square pad), anode = the other
       FFC         contacts at the physical slots: slot 1 = the back-most contact
       MINI-E      what each of its four leads carries is read from the copper under the part's own lead
                   positions (5 V, GND, the chain's data in and out) and compared with where the SK6812 MINI-E
                   has VDD, DOUT, VSS and DIN, seen from its pad side (MINI_E_PADSIDE, from two published
                   footprints, not from the board plan's LED_PINS)
  3. Per board: each key is a switch between its column's slot and its diode, the diode's cathode on its row's
     slot (COL2ROW); unused slots touch nothing; RGB boards: one unbroken chain slot 3 -> 29 LEDs -> slot 18 on
     the fitted face, every LED and capacitor across slot 2/19 (5 V) and 1/4/20 (GND), the unfitted face's
     copies harmless; plain boards: slot 3 wired straight to slot 18 and nothing else on 1-4 / 18-20.
  4. The flex jumper (`flex-jumper`, one part for both sides): copper rebuilt from its board, every half-end finger joined to
     exactly one controller-end finger; then the flat cut-out folded along the solved path (compose.pcb.jumper)
     puts each finger against a connector contact: at the half's 200528 the conductor side faces up (bottom
     contact, connector on the half's underside), at the controller's 52610 it faces inboard (the contact face,
     checked by sim-controller). Each finger must land within 0.25 mm of a contact, so the slot k <-> slot k'
     map comes from geometry, not from the jumper's net names.
  5. End to end: the controller rev 2 copper, the two jumpers and the two real halves; the QMK COL2ROW scan
     with the rev 2 pin config reads every key alone at its keymap position, 1000 random chords exactly, and no
     ghosting.
  6. Negative controls: a cut column track, a diode fitted backwards, a jumper with its fingers in reverse
     order and a half connector 0.5 mm off along its row are caught.
  7. RGB boards: the 5 V rail's resistance, read from its copper as a resistor network (1 oz copper, as
     board_facts() in compose/sim/controller_spice.py): from the fitted connector's slots 2 and 19 to the
     farthest fitted LED. A rail the layout pre-routes on that board (layouts/<layout>/preroute.py) is held to
     RAIL_R_MAX, the figure the power simulation assumes; an autorouted one is reported. Negative control: the
     same copper read at the signal width is over the limit.
"""
import os
import sys
import random
import itertools
import numpy as np
import pcbnew

OUT = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
CTRL_OUT = os.environ.get("CTRL_OUT", "out")
sys.argv = sys.argv[:1] + [OUT]
from compose import params as PR
from compose import geom as G
from compose.pcb import layout as PL
from compose.pcb import rev2_half as H
from compose.pcb import preroute as PRE
from compose.sim import matrix as SP
from compose.sim import controller_copper as CC
from compose.pcb import jumper as J

ToMM = pcbnew.ToMM
FAIL = []
OX, OY = 40.0, 60.0
L = G.LAYOUT
F, B = pcbnew.F_Cu, pcbnew.B_Cu
KAILH_TAB1, KAILH_TAB2 = (5.842, -5.08), (-7.085, -2.54)   # Kailh hotswap socket: its tab beside MX pin 1 / pin 2,
                                                            #   footprint coords (the values compose/sim/matrix.py uses)
# SK6812 MINI-E, reverse-mounted, seen from the side its pads are on (x right, y down): which lead sits at which
# corner. Taken from two published footprints, not from this repo's board plan (rev2_half.LED_PINS):
#   ebastler/marbastlib  LED_6028R with its SK6812MINI-E symbol: VDD (2.725, -0.75), DOUT (2.725, 0.75),
#                        DIN (-2.725, -0.75), VSS (-2.725, 0.75)
#   foostan/kbd          YS-SK6812MINI-E: pads 1-4 (VDD, DOUT, VSS, DIN) at (2.8, -0.7), (2.8, 0.7), (-2.8, 0.7),
#                        (-2.8, -0.7)
MINI_E_PADSIDE = {"VDD": (1, -1), "DOUT": (1, 1), "VSS": (-1, 1), "DIN": (-1, -1)}
MINI_E_LEAD = (2.75, 0.75)                                  # lead centres from the LED's centre (x, y), mm
RAIL_R_MAX = 0.15                                           # ohm, a half's 5 V rail from its connector to the farthest
                                                            #   LED: what compose/sim/controller_spice.py (E2) allows for
                                                            #   the half's rail and its return


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
        """Copper group at a plate-local point, on the fitted (bottom) face unless a layer is given. The other
        face doesn't count: a part whose pads are only there can't be soldered where the builder fits it."""
        return self.cu.node_at(K(local_xy), layer if layer is not None else self.bottom)

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

    def connector_gap(self):
        """(distance, part) from the fitted connector's pads to the nearest other pad on the same face."""
        from shapely.geometry import Polygon as SP_
        ref = "J1B" if self.side == "L" else "J1F"

        def poly(p):
            o = p.GetEffectivePolygon().Outline(0)
            return SP_([(ToMM(o.CPoint(i).x), ToMM(o.CPoint(i).y)) for i in range(o.PointCount())])
        mine = [poly(p) for p in self.fp[ref].Pads() if p.IsOnLayer(self.bottom)]
        best = (1e9, None)
        for r, f in self.fp.items():
            if r.startswith("J1"):
                continue
            for p in f.Pads():
                if p.IsOnLayer(self.bottom):
                    q = poly(p)
                    d = min(q.distance(m) for m in mine)
                    if d < best[0]:
                        best = (d, f"{r} pad {p.GetNumber()}")
        return best

    def keys(self):
        """[(key index, row, col, switch contact a, contact b, diode anode, diode cathode)] as copper groups."""
        out = []
        for ks in self.s.keys:
            k = ks.k
            if self.variant == "hotswap":
                # socket tabs on the bottom face, at the Kailh socket's nominal tab positions (as in the rev 1
                # simulation), not at the pads' own centres: a pad moved off its tab fails. On the flipped board
                # they're the mirrored copies
                c1, c2 = KAILH_TAB1, KAILH_TAB2
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

    def leds(self, layer=None):
        """Fitted LEDs in chain order: [(VDD, DOUT, GND, DIN)] groups, located by the plan's pad positions for
        the fitted face, not by pad number. layer: read the copper on that layer instead (negative control)."""
        face = "B" if self.side == "L" else "F"
        out = []
        for i in self.s.led_order:
            k = L.keys[i]
            pads = H.led_pads(k, face)               # plan: pin -> pad polygon on that face
            g = {pin: self.at(poly.centroid.coords[0], layer) for pin, poly in pads.items()}
            out.append((g["1"], g["2"], g["3"], g["4"]))
        return out

    def led_leads(self, light_side=False):
        """Fitted LEDs in chain order: {(sx, sy): copper group} under each of the four leads, the corner named as
        it's seen from the pad side of the fitted face (x right, y down). Positions are the part's own lead
        positions about the LED's centre, not the plan's pads. light_side: name the corners as seen from the other
        side instead, i.e. the part mirrored (negative control)."""
        X, Y = MINI_E_LEAD
        mir = (self.bottom == B) != light_side          # footprint coords are drawn from F: B's own view is mirrored
        out = []
        for i in self.s.led_order:
            k = L.keys[i]
            out.append({(-sx if mir else sx, sy): self.at(H.fp2local(k, H.LED_AT[0] + sx * X, H.LED_AT[1] + sy * Y))
                        for sx in (-1, 1) for sy in (-1, 1)})
        return out

    def caps(self, layer=None):
        face = "B" if self.side == "L" else "F"
        return [tuple(self.at(p, layer) for p in H.cap_pads(L.keys[i], face)) for i in self.s.caps]

    def rail(self, width=None):
        """The 5 V rail as a resistor network (compose.pcb.preroute.rail_resistance): every track and via in
        the copper group of the fitted connector's slot 2, whatever its net is called. Returns (worst resistance
        from slots 2 + 19 to a fitted LED's 5 V pad, that LED's place in the chain, the far LED's drop per ampere
        of total current when every LED draws the same). width: read the tracks at that width instead."""
        face = "B" if self.side == "L" else "F"
        ref = "J1B" if self.side == "L" else "J1F"
        cp = sorted((p for p in self.fp[ref].Pads() if p.GetNumber() != "MP"), key=lambda p: p.GetPosition().y)
        xy = lambda p: (ToMM(p.GetPosition().x), ToMM(p.GetPosition().y))
        vdd = self.slots()[2]
        name = {F: "F", B: "B"}
        items = self.cu.items
        k = next(i for i, it in enumerate(items) if it[2] in ("via", "track"))       # Copper lists pads, then tracks
        segs, vias = [], []
        for t in self.b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                assert items[k][2] == "via"
                if self.cu.find(k) == vdd:
                    vias.append(xy(t))
                k += 2
            else:
                assert items[k][2] == "track"
                if self.cu.find(k) == vdd:
                    a, c = t.GetStart(), t.GetEnd()
                    segs.append(((ToMM(a.x), ToMM(a.y)), (ToMM(c.x), ToMM(c.y)), ToMM(t.GetWidth()), name[t.GetLayer()]))
                k += 1
        pads = [(s, name[lay]) for i, (s, lay, lab) in enumerate(items)
                if lab not in ("via", "track", "zone") and self.cu.find(i) == vdd]
        loads = [(K(H.led_pads(L.keys[i], face)["1"].centroid.coords[0]), face) for i in self.s.led_order]
        worst, far, _, shared = PRE.rail_resistance(segs, vias, pads, [(xy(cp[1]), face), (xy(cp[18]), face)], loads,
                                                    PR.VIA_D, PR.VIA_DRILL, board_t=PR.PCB_T, width=width)
        return worst, far, shared


def joined_slots(sl, rgb):
    """Connector slots that share copper and shouldn't: GND 1/4/20 and 5 V 2/19 may, and on a board without LEDs
    the pass-through 3/18. With LEDs, 3 joined to 18 shorts the chain out."""
    groups = {}
    for k_, g in sl.items():
        groups.setdefault(g, []).append(k_)
    allowed = [{1, 4, 20}, {2, 19}] + ([] if rgb else [{3, 18}])
    return [v for v in groups.values() if len(v) > 1 and set(v) not in allowed]


def led_lead_problems(leads, sl):
    """What each LED lead carries, read from the copper (5 V, GND, the chain's data in; the fourth is data out),
    against where the SK6812 MINI-E has them (MINI_E_PADSIDE). A LED can sit either way round (turned 180
    degrees), never mirrored. Returns the problems found."""
    gnd, vdd, cur, bad = sl[1], sl[2], sl[3], []
    turned = {f: (-x, -y) for f, (x, y) in MINI_E_PADSIDE.items()}
    for j, c in enumerate(leads):
        at = {}
        for xy, n in c.items():
            f = None if n is None else "VDD" if n == vdd else "VSS" if n == gnd else "DIN" if n == cur else "DOUT"
            at.setdefault(f, []).append(xy)
        if sorted(at, key=str) != ["DIN", "DOUT", "VDD", "VSS"] or any(len(v) != 1 for v in at.values()):
            bad.append(f"LED {j + 1}: its leads don't read as one each of VDD, DOUT, VSS, DIN "
                       f"({ {str(f): v for f, v in at.items()} })")
            break                                        # the chain can't be followed past it
        got = {f: v[0] for f, v in at.items()}
        if got != MINI_E_PADSIDE and got != turned:
            bad.append(f"LED {j + 1}: {got}")
        cur = c[got["DOUT"]]
    return bad


def board_checks(h):
    name = f"{h.variant}{' rgb' if h.rgb else ''} as {'lhs' if h.side == 'L' else 'rhs'}"
    print(f"\n== {name}")
    sl = h.slots()
    ok(all(v is not None for v in sl.values()), "every connector contact is on copper")
    gap = h.connector_gap()
    ok(gap[0] >= 0.6 - 1e-3, f"jumper connector's pads >= 0.6 mm from every other part's pad on its face "
                             f"(both hand-soldered): {gap[0]:.2f} mm, nearest {gap[1]}")
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
    if h.variant == "hotswap":                                   # a tab 2.1 mm further out is past its pad's end
        off = (KAILH_TAB1[0] + 2.1, KAILH_TAB1[1])
        bare = sum(h.at(PL.fp2local(ks.k, *(mirror(off) if h.side == "R" else off))) is None for ks in h.s.keys)
        ok(bare >= len(keys) // 2, f"negative control: a socket tab just off its pad is caught ({bare} of {len(keys)} "
                                   f"land on bare board; the tab test isn't trivially true)")
    used = {5 + c for c in {k.col for k in L.keys}} | {12 + r for r in {k.row for k in L.keys}}
    spare = [k for k in range(5, 18) if k not in used]
    shared = joined_slots(sl, h.rgb)
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
    bad = led_lead_problems(h.led_leads(), sl)
    ok(not bad, "every LED's leads, seen from its pad side, are VDD, DOUT, VSS, DIN where the SK6812 MINI-E has them "
                "(from published footprints, not from this board's plan), either way round" + (f": {bad[:2]}" if bad else ""))
    # negative controls: each of these broken readings must be caught
    ok(bool(led_lead_problems(h.led_leads(light_side=True), sl)),
       "negative control: the LEDs' leads read mirrored (the part seen from its light side) are caught")
    other = F if h.bottom == B else B
    ok(not all(l_[0] == vdd and l_[2] == gnd for l_ in h.leds(other)),
       "negative control: the LEDs' pads read on the other face aren't their 5 V and GND")
    ok(not all(set(c_) == {vdd, gnd} for c_ in h.caps(other)),
       "negative control: the capacitors' pads read on the other face aren't across 5 V / GND")
    ok(bool(joined_slots({**sl, 18: sl[3]}, True)), "negative control: slot 3 joined to slot 18 on a board with LEDs is caught")
    worst, far, shared = h.rail()
    msg = (f"5 V rail, slots 2 + 19 to the farthest LED (chain position {far + 1}): {worst * 1e3:.0f} mohm of copper "
           f"(with every LED drawing the same, the far LED drops {shared * 1e3:.0f} mV per ampere of the half's total)")
    name = next(n for n, v in H.BOARDS.items() if v == (h.variant, h.rgb))
    laid = H.laid(name)[1]
    if laid is not None and "+5V" in laid.nets():
        ok(worst <= RAIL_R_MAX, f"{msg}; limit {RAIL_R_MAX * 1e3:.0f} mohm, as the power simulation assumes")
        thin = h.rail(width=PR.TRACE_W)[0]
        ok(thin > RAIL_R_MAX, f"negative control: the same rail read at the signal width ({PR.TRACE_W} mm) is over the limit "
                              f"({thin * 1e3:.0f} mohm)")
    else:
        print(f"  note  {msg}; autorouted, so not held to the {RAIL_R_MAX * 1e3:.0f} mohm the power simulation assumes "
              f"(the layout's preroute.py doesn't lay this board's rail)")


# ---------------------------------------------------------------- the flex jumpers
class Jumper:
    """The flex jumper fitted on one side: {half slot: controller slot}, from the jumper's copper and the
    folded geometry. It's one part for both sides; on the right it's bent as the mirror image of the left, so
    its fingers are placed through the left geometry with w negated, against the right half's and right
    connector's contacts mirrored back."""

    def __init__(self, path, side, g, half, ctrl_board, shift=0.0):
        self.cu = SP.Copper(path)
        self.side = side
        sg = 1.0 if side == "L" else -1.0
        f = J.flat(g, side)
        cl, length = f["centre"], f["length"]
        pts = np.array([c[0] for c in cl])
        Z = np.array([0.0, 0.0, 1.0])
        # where a conductor at offset w (left of the centre line seen from the conductor side) lands, measured
        # along each connector's slot axis: the strip's own width direction at each end, carried through the
        # three bends by the solved path (conductor side up at the half, inboard at the controller)
        lh, lc = g.left_half @ g.a1, g.left_ctrl @ g.a2
        fingers = {"H": [], "C": []}
        for fp in self.cu.b.GetFootprints():
            for p in fp.Pads():
                X, Y = ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)
                q = np.array([X - 50.0, 50.0 - Y])                        # jumper board: flex (x, y) -> (x + 50, 50 - y)
                i = int(np.argmin(np.linalg.norm(pts - q, axis=1)))
                h = cl[i][1]
                w = float((q - pts[i]) @ np.array([-h[1], h[0]]))
                end = "H" if cl[i][2] < length / 2 else "C"
                fingers[end].append((sg * w, self.cu.node_at((X, Y), pcbnew.F_Cu)))
        self.n_fingers = (len(fingers["H"]), len(fingers["C"]))
        # contacts along the slot axis: half (fitted connector, slot 1 = the back-most), controller (52610)
        ref = "J1B" if side == "L" else "J1F"
        hp = sorted([p for p in half.fp[ref].Pads() if p.GetNumber() != "MP"], key=lambda p: p.GetPosition().y)
        zf = -PR.PCB_T
        hc = []
        for p in hp:
            lx, ly = ToMM(p.GetPosition().x) - OX, OY - ToMM(p.GetPosition().y)
            hc.append(float((np.array(G.apply(G.M_LP, (lx, ly, zf))) - g.half.face) @ g.a1) + shift)
        from compose.case import gasket as C
        from compose.controller import rev2 as CR
        cp = ctrl_board.fp["J" + side].Pads()
        ys = sorted({round(ToMM(p.GetPosition().y), 2) for p in cp})
        cc = [float((C.CT.y_pc - (y - CR.CY)) - g.ctrl.top[1]) for y in ys]   # controller: P y = y_pc - (KiCad y - CY)
        self.miss, self.worst = [], {"half": 0.0, "controller": 0.0}

        def slot_of(c, contacts, what):
            d = [abs(c - x) for x in contacts]
            k = int(np.argmin(d))
            self.worst[what] = max(self.worst[what], d[k])
            if d[k] > 0.25:
                self.miss.append(f"{what} finger at {c:+.2f} mm off every contact ({d[k]:.2f})")
            return k + 1
        hs = {node: slot_of(w * lh, hc, "half") for w, node in fingers["H"]}
        cs = {}
        for w, node in fingers["C"]:
            cs.setdefault(node, []).append(slot_of(w * lc, cc, "controller"))
        self.map, self.bad = {}, []
        for node, k in hs.items():
            to = cs.get(node, [])
            if len(to) != 1:
                self.bad.append(f"half slot {k} reaches {len(to)} controller fingers")
            else:
                self.map[k] = to[0]
        if len(set(hs.values())) != len(hs):
            self.bad.append("two half-end fingers on one contact or one copper group")


# ---------------------------------------------------------------- end to end
def assemble(pins, halves, jumpers, cable_rev=None, cut=None, diode_flip=None):
    edges = {}

    def link(a, b):
        edges.setdefault(a, set()).add(b)
        edges.setdefault(b, set()).add(a)
    keys, diodes = [], []
    for side, h in halves.items():
        sl = h.slots()
        for hk, ck in jumpers[side].map.items():
            if cable_rev == side:
                ck = 21 - ck
            if sl[hk] is not None:
                link(("C", pins[("ffc" + side, ck)]), (side, sl[hk]))
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


def run(pins, halves, jumpers, quiet=False, **kw):
    edges, keys, diodes = assemble(pins, halves, jumpers, **kw)
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
    # ... and each key by itself: its legend and the half it's drawn on (left or right of the middle) against the
    # matrix position of the key with that legend on that half; along each main row the columns rise with x
    lay = fw["layouts"]["LAYOUT"]["layout"]
    mid = (min(e["x"] for e in lay) + max(e["x"] for e in lay)) / 2
    got = {("L" if e["x"] < mid else "R", e["label"]): e["matrix"] for e in lay}
    want = {(s_, ks.k.label_l if s_ == "L" else ks.k.label_r): exp_m[(s_, ks.i)] for s_ in ("L", "R") for ks in H.plan().keys}
    ok(len(got) == len(lay) and got == want,
       "keyboard.json: every key, by its legend and the half it's drawn on, has the matrix position the scan reads it at"
       + ("" if got == want else f": {sorted(k for k in set(got) | set(want) if got.get(k) != want.get(k))[:4]}"))
    rows_ok = all([e["matrix"][1] for e in sorted((e for e in lay if e["matrix"][0] == r), key=lambda e: e["x"])]
                  == sorted(e["matrix"][1] for e in lay if e["matrix"][0] == r) for r in range(4))
    ok(rows_ok, "keyboard.json: along each of the four main rows the matrix columns rise with x")
    a_, b_ = sorted(got)[:2]
    swapped = {**got, a_: got[b_], b_: got[a_]}
    ok(swapped != want, "negative control: two keys' matrix positions swapped in keyboard.json are caught")
    pcb = os.path.join(OUT, "pcb")
    jpath = lambda s_: os.path.join(pcb, "jumper_rev2.kicad_pcb")         # one part, both sides
    g = J.solve()
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
        print(f"\n== {name}: flex jumpers (copper of {os.path.basename(jpath('L'))}, folded along the solved path, left and mirrored right)")
        jumpers = {}
        for s_ in ("L", "R"):
            jm = Jumper(jpath(s_), s_, g, halves[s_], CB)
            jumpers[s_] = jm
            ok(jm.n_fingers == (20, 20), f"jumper {s_}: 20 fingers at each end ({jm.n_fingers[0]} / {jm.n_fingers[1]})")
            ok(not jm.miss, f"jumper {s_}: every finger lands on a connector contact (within 0.25 mm; worst {jm.worst['half']:.2f} at the half, "
               f"{jm.worst['controller']:.2f} at the controller)" + (f" {jm.miss[:2]}" if jm.miss else ""))
            ok(not jm.bad and len(jm.map) == 20, f"jumper {s_}: each half-end finger joined to exactly one controller-end finger"
               + (f" {jm.bad[:2]}" if jm.bad else ""))
            ok(all(jm.map.get(k) == k for k in range(1, 21)), f"jumper {s_}: half slot k meets controller slot k, all 20")
        jm = Jumper(jpath("L"), "L", g, halves["L"], CB, shift=0.5)
        ok(bool(jm.miss), f"negative control: a half connector 0.5 mm off along its row is caught ({len(jm.miss)} fingers off a contact)")
        print(f"\n== {name}: QMK COL2ROW scan, controller rev 2 + two flex jumpers + both halves")
        run(pins, halves, jumpers)
        k0 = halves["L"].s.keys[7]
        s_, _ = run(pins, halves, jumpers, quiet=True, cut=("L", k0.i))
        ok(("L", k0.i) in s_, f"negative control: a cut column connection kills key {k0.k.label_l} ... and the scan sees it")
        s_, _ = run(pins, halves, jumpers, quiet=True, diode_flip=("R", 3))
        ok(("R", 3) in s_, "negative control: a diode fitted backwards is caught")
        s_, w_ = run(pins, halves, jumpers, quiet=True, cable_rev="L")
        ok(len(s_) > 0, f"negative control: a left jumper with its fingers in reverse order scrambles the left half ({len(s_)} keys wrong)")
    print("\n" + ("SIMULATION PASSED" if not FAIL else f"{len(FAIL)} SIMULATION CHECK(S) FAILED"))
    return len(FAIL)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
