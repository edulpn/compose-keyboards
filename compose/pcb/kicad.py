"""
Build the KiCad boards:  python3 -m compose pcb [outdir]

  half_hotswap  reversible half board, Kailh MX hotswap sockets  (order 5: 2 per keyboard)
  half_solder   reversible half board, switches soldered in
  controller    Pico socket + two cable connectors, replaces the perfboard carrier

For each: place from compose.pcb.layout -> autoroute (Freerouting) -> DRC (KiCad) ->
Gerbers + drill zipped for JLCPCB, SVG previews. Needs KiCad 7 (pcbnew) and
java + tools/freerouting.jar.
"""
import os
import sys
import math
import pcbnew
from compose import params as PR
from compose.case import sandwich as PT
from compose.pcb import layout as PL
from compose.pcb.toolbox import (PCB_OUT, MM, V, DEG, OX, OY, K, new_board, Nets, outline, text, add_poly, switch_fp, lib_fp,
                                 place_by_pads, hole_fp, add_art_half, make)


# ---------------------------------------------------------------- half board
def build_half(variant):
    plan = PL.plan_half()
    b = new_board()
    b.kb2_outline = (plan.outline, OX, OY)
    net = Nets(b)
    outline(b, plan.outline, OX, OY)
    for ks in plan.keys:
        k = ks.k
        dnet = net(f"D{ks.i + 1}")
        fp = switch_fp(b, variant, ks.ref, net(f"COL{ks.col}"), dnet)
        fp.SetOrientation(DEG(k.rot))
        fp.SetPosition(V(*K((k.x, k.y))))
        b.Add(fp)
        exp = K(PL.fp2local(k, *(PR.MX_PIN2 if variant == "solder" else PR.HS_PAD2[0])))
        assert any(math.dist(exp, g) < 1e-3 for g in [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in fp.Pads() if p.GetNumber() == "2"]), "switch frame"
        d = lib_fp(b, "Diode_THT", "D_DO-35_SOD27_P7.62mm_Horizontal")
        d.SetReference(ks.dref)
        d.Reference().SetVisible(False)
        d.Value().SetVisible(False)
        d.Flip(d.GetPosition(), False)                         # body on the B face (left half)
        place_by_pads(d, "1", K(ks.cathode), "2", K(ks.anode))
        for p in d.Pads():
            p.SetNet(net(f"ROW{ks.row}") if p.GetNumber() == "1" else dnet)
        b.Add(d)
        # F-side silkscreen for the right half: diode outline with the cathode band
        c, a = K(ks.cathode), K(ks.anode)
        ux, uy = (a[0] - c[0]) / PR.DIODE_PITCH, (a[1] - c[1]) / PR.DIODE_PITCH
        nx, ny = -uy, ux
        h0, h1, r = 1.8, PR.DIODE_PITCH - 1.8, 0.95
        corner = lambda t, s: (c[0] + ux * t + nx * s, c[1] + uy * t + ny * s)
        sh = pcbnew.PCB_SHAPE(b)
        for t0, s0, t1, s1 in ((h0, -r, h1, -r), (h1, -r, h1, r), (h1, r, h0, r), (h0, r, h0, -r), (h0 + 0.6, -r, h0 + 0.6, r)):
            sh = pcbnew.PCB_SHAPE(b)
            sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
            sh.SetStart(V(*corner(t0, s0)))
            sh.SetEnd(V(*corner(t1, s1)))
            sh.SetLayer(pcbnew.F_SilkS)
            sh.SetWidth(MM(0.12))
            b.Add(sh)
    # cable connector (vertical PicoBlade) on the B face, pad 1 at the back end
    j = lib_fp(b, "Connector_Molex", "Molex_PicoBlade_53047-1210_1x12_P1.25mm_Vertical")
    j.SetReference("J1")
    j.Flip(j.GetPosition(), False)
    place_by_pads(j, "1", K(plan.conn_pins[0]), "12", K(plan.conn_pins[-1]))
    for p in j.Pads():
        p.SetNet(net(PL.half_nets()[int(p.GetNumber())]))
    b.Add(j)
    for i, (x, y) in enumerate(plan.holes_m3):
        hole_fp(b, f"H{i + 1}", K((x, y)), PR.M3_CLEAR)
    for i, (x, y) in enumerate(plan.holes_m2):
        hole_fp(b, f"H{i + 20}", K((x, y)), PR.M2_CLEAR)
    # labels + art (pcb_art): exposed-copper title, taglines, build labels, hex lattice
    from compose.pcb import art as pcb_art
    art = pcb_art.plan_half_art(plan, variant)
    add_art_half(b, art, OX, OY)
    c1, c12 = K(plan.conn_pins[0]), K(plan.conn_pins[-1])
    lhs, rhs = PR.HALF_NAMES
    text(b, f"{lhs}: pin 1", (c1[0] - 4.4, c1[1]), pcbnew.B_SilkS, 0.9, mirror=True)
    text(b, f"{rhs}: pin 1", (c12[0] - 4.4, c12[1]), pcbnew.F_SilkS, 0.9)
    return b


# ---------------------------------------------------------------- controller board
COX, COY = 60.0, 30.0           # P-frame (x, y) -> KiCad (x + COX, COY - y)


def build_ctrl():
    st = PT.Stack
    plan = PL.plan_ctrl(st, PT.pillar_positions())
    b = new_board()
    b.kb2_outline = (plan.outline, COX, COY)
    net = Nets(b)
    KC = lambda p: K(p, COX, COY)
    outline(b, plan.outline, COX, COY)
    pin_net = {pin: f"GP{g}" for pin, g in PL.PICO_PIN_GPIO.items()}
    pin_net.update({pin: "GND" for pin in PL.PICO_GND_PINS})
    for side, first, last in (("L", 1, 20), ("R", 40, 21)):
        h = lib_fp(b, "Connector_PinSocket_2.54mm", "PinSocket_1x20_P2.54mm_Vertical")
        h.SetReference(f"U1{side}")
        place_by_pads(h, "1", KC(PL.pico_pin_xy(first, st)), "20", KC(PL.pico_pin_xy(last, st)))
        for p in h.Pads():
            n_ = int(p.GetNumber())
            pin = first + (n_ - 1) * (1 if side == "L" else -1)
            p.SetNet(net(pin_net.get(pin)))
        b.Add(h)
    for side in ("L", "R"):
        j = lib_fp(b, "Connector_Molex", "Molex_PicoBlade_53048-1210_1x12_P1.25mm_Horizontal")
        j.SetReference(f"J{side}")
        j.Reference().SetVisible(False)                 # the lhs/rhs art labels name them
        pins = plan.conn[side]
        place_by_pads(j, "1", KC(pins[0]), "12", KC(pins[-1]))
        # body must open outward (toward its half); if not, mirror the pad order
        bb = j.GetCourtyard(pcbnew.F_CrtYd).BBox() if hasattr(j, "GetCourtyard") else j.GetBoundingBox(False, False)
        cxm = pcbnew.ToMM((bb.GetLeft() + bb.GetRight()) // 2) - COX
        if (cxm > PR.CTRL_CONN_X) != (side == "R"):
            place_by_pads(j, "12", KC(pins[0]), "1", KC(pins[-1]))
        cn = PL.ctrl_conn_nets(side)
        for p in j.Pads():
            p.SetNet(net(cn[int(p.GetNumber())]))
        b.Add(j)
    for i, (x, y) in enumerate(st.carrier_holes):
        hole_fp(b, f"H{i + 1}", KC((x, y)), PR.M2_CLEAR)
    lhs, rhs = PR.HALF_NAMES
    from compose.pcb import art as pcb_art
    art = pcb_art.plan_ctrl_art(plan, st)
    for f, lay in (("F", pcbnew.F_SilkS), ("B", pcbnew.B_SilkS)):
        for g in art.silk[f]:
            add_poly(b, g, lay, COX, COY)
    return b



def main(which=None):
    os.makedirs(PCB_OUT, exist_ok=True)
    jobs = {"half_hotswap": lambda: build_half("hotswap"), "half_solder": lambda: build_half("solder"),
            "controller": build_ctrl}
    res = {}
    for n, f in jobs.items():
        if which and n not in which:
            continue
        res[n] = make(n, f)
    return res


if __name__ == "__main__":
    main(sys.argv[2:] or None)
