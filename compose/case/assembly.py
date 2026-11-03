"""
Full assembly (CadQuery Assembly -> STEP): printed parts plus simplified
switches, keycaps, Pico, socket headers and carrier, all in world position.
"""
import math
import cadquery as cq
from compose import params as PR
from compose import geom as G
from compose.case import sandwich as PT

TH = PR.PLATE_T
P = PR.KEY_PITCH


def switch_shape():
    bottom = cq.Workplane("XY").rect(13.9, 13.9).extrude(TH)
    top = (cq.Workplane("XY").workplane(offset=TH).rect(15.6, 15.6)
           .workplane(offset=5.6).rect(11.6, 11.0).loft())
    stem = (cq.Workplane("XY").workplane(offset=TH + 5.6).rect(4.1, 1.3).extrude(3.8)
            .union(cq.Workplane("XY").workplane(offset=TH + 5.6).rect(1.3, 4.1).extrude(3.8)))
    pins = (cq.Workplane("XY").workplane(offset=-3.3).pushPoints([(-3.81, 2.54), (2.54, 5.08)])
            .circle(0.5).extrude(3.3))
    return bottom.union(top).union(stem).union(pins).val()


def keycap_shape(w_u, h_u):
    W, H = w_u * P - (P - PR.KEYCAP_SIZE), h_u * P - (P - PR.KEYCAP_SIZE)
    return (cq.Workplane("XY").workplane(offset=TH + 5.3).rect(W, H)
            .workplane(offset=7.6).rect(W - 5.2, H - 5.2).loft().val())


def _safe(s):
    rep = {"`": "grave", "'": "quote", ";": "semicolon", ",": "comma", ".": "period", "/": "slash",
           "-": "minus", "[": "lbracket", "]": "rbracket", "\\": "backslash", "=": "equal"}
    return "".join(rep.get(c, c) for c in s)


def build(world):
    a = cq.Assembly(name="keyboard")
    case_c, plate_c = cq.Color(0.23, 0.25, 0.43), cq.Color(0.55, 0.57, 0.72)
    for n, s in world.items():
        a.add(s, name=n, color=plate_c if n.startswith("plate") else case_c)
    sw = switch_shape()
    caps = {}
    swa, capa = cq.Assembly(name="switches"), cq.Assembly(name="keycaps")
    for side, lab in ((-1, "label_l"), (1, "label_r")):
        for i, k in enumerate(G.LAYOUT.keys):
            key = (k.w, k.h)
            if key not in caps:
                caps[key] = keycap_shape(k.w, k.h)
            place = lambda s: G.L2W(s.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), k.rot).translate(cq.Vector(k.x, k.y, 0)))
            s, c = place(sw), place(caps[key])
            if side == 1:
                s, c = s.mirror("YZ"), c.mirror("YZ")
            nm = f"{'L' if side < 0 else 'R'}_{_safe(getattr(k, lab))}_{i}"
            swa.add(s, name="sw_" + nm, color=cq.Color(0.15, 0.15, 0.17))
            capa.add(c, name="cap_" + nm, color=cq.Color(0.30, 0.30, 0.32))
    a.add(swa)
    a.add(capa)

    st = PT.Stack
    box = lambda x0, x1, y0, y1, z0, z1: G.P2W(G.big_box(x0, x1, y0, y1, z0, z1))
    a.add(box(-PR.PICO_W / 2, PR.PICO_W / 2, st.pico_front, st.pico_back, st.pico_bot, st.pico_top),
          name="pico", color=cq.Color(0.06, 0.48, 0.23))
    uy = st.pico_back + PR.USB_RECEPT_OVERHANG
    a.add(box(-PR.USB_RECEPT_W / 2, PR.USB_RECEPT_W / 2, uy - PR.USB_RECEPT_L, uy, st.pico_top, st.pico_top + PR.USB_RECEPT_H),
          name="pico_usb", color=cq.Color(0.77, 0.77, 0.77))
    a.add(box(-st.carrier_hw, st.carrier_hw, st.carrier_front, st.carrier_back, st.carrier_bot, st.carrier_top),
          name="perfboard_carrier", color=cq.Color(0.12, 0.42, 0.23))
    y0, y1 = st.pin_ys[-1] - PR.PICO_PIN_PITCH / 2, st.pin_ys[0] + PR.PICO_PIN_PITCH / 2
    hw = PR.FEMALE_HEADER_W / 2
    for sx, nm in ((-1, "left"), (1, "right")):
        x = sx * PR.PICO_PIN_ROW_X
        a.add(box(x - hw, x + hw, y0, y1, st.carrier_top, st.female_top), name=f"female_header_{nm}",
              color=cq.Color(0.08, 0.08, 0.08))
        a.add(box(x - hw, x + hw, y0, y1, st.female_top, st.pico_bot), name=f"male_header_{nm}",
              color=cq.Color(0.08, 0.08, 0.08))
    if PR.MATRIX == "pcb":
        add_pcbs(a)
    return a


def add_pcbs(a):
    """Half boards (left, and the same board flipped for the right) and the
    controller board, with simplified sockets, diodes and connectors."""
    from compose.pcb import layout as PLY
    from shapely.geometry import Point
    from shapely.ops import unary_union
    green, white, black = cq.Color(0.10, 0.36, 0.20), cq.Color(0.92, 0.90, 0.85), cq.Color(0.08, 0.08, 0.08)
    hp = PLY.plan_half()
    holes = [Point(x, y).buffer(PR.M3_CLEAR / 2) for x, y in hp.holes_m3]
    holes += [Point(x, y).buffer(PR.M2_CLEAR / 2) for x, y in hp.holes_m2]
    for k in G.LAYOUT.keys:
        holes += PLY.key_holes(k, PR.RENDER_PCB_VARIANT)
    board = G.poly_prism(hp.outline.difference(unary_union(holes)), -PR.PCB_T, 0.0)
    parts = [board]
    x0, x1, y0, y1 = PR.HS_BODY
    for ks in hp.keys:
        k = ks.k
        for (cx, cy), (w, h) in (((x0 + 2.35, -2.9), (4.7, 3.8)), ((0.4, y0 + 2.2), (9.8, 4.4))):
            pc = PLY.fp2local(k, cx, cy)
            parts.append(cq.Workplane("XY").box(w, h, PR.HS_HEIGHT).val().rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), k.rot)
                         .translate(cq.Vector(pc[0], pc[1], -PR.PCB_T - PR.HS_HEIGHT / 2)))
        c, an = ks.cathode, ks.anode
        mid = ((c[0] + an[0]) / 2, (c[1] + an[1]) / 2)
        ang = math.degrees(math.atan2(an[1] - c[1], an[0] - c[0]))
        parts.append(cq.Workplane("YZ").circle(0.95).extrude(3.7).val().translate(cq.Vector(-1.85, 0, 0))
                     .rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), ang).translate(cq.Vector(mid[0], mid[1], -PR.PCB_T - 1.05)))
    b = hp.conn_body.bounds
    parts.append(G.big_box(b[0], b[2], b[1], b[3], -PR.PCB_T - PR.CONN_BODY_UNDER, -PR.PCB_T))
    half = cq.Compound.makeCompound(parts)
    a.add(G.L2W(half), name="pcb_left (reversible half board)", color=green)
    a.add(G.R2W(half), name="pcb_right (same board, flipped)", color=green)
    st = PT.Stack
    cp = PLY.plan_ctrl(st, PT.pillar_positions())
    ch = unary_union([Point(x, y).buffer(PR.M2_CLEAR / 2) for x, y in st.carrier_holes])
    ctrl = [G.poly_prism(cp.outline.difference(ch), st.carrier_bot, st.carrier_top)]
    n = PR.HALF_CONN_PINS
    for sd, pins in cp.conn.items():
        sx = -1 if sd == "L" else 1
        ym = (pins[0][1] + pins[-1][1]) / 2
        L_ = (n - 1) * PR.HALF_CONN_PITCH + 3.2
        xa, xb = sorted((sx * (PR.CTRL_CONN_X - 1.55), sx * (PR.CTRL_CONN_X + 4.95)))
        ctrl.append(G.big_box(xa, xb, ym - L_ / 2, ym + L_ / 2, st.carrier_top, st.carrier_top + 3.6))
    a.add(G.P2W(cq.Compound.makeCompound(ctrl)), name="pcb_controller", color=green)
