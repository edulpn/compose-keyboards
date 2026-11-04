"""
Rev 2 electronics as 3D models for the renders, placed from the routed boards and the half-board plan:

  half board (left local frame, the fitted B face, under the board):
    Kailh MX hotswap socket   body + metal solder tabs on its two pads
    1N4148 DO-35 diode        glass body with its cathode band, leads bent down to the holes and through the board
    SK6812 MINI-E             reverse mount: white body through the cutout, four leads on the pads
    100 nF 1206               ceramic body, metal end caps on the pads
    Molex 200528-0200         housing from the footprint's body outline, flip-lock actuator, the flex slot in the
                              cable face, 20 tails on the pads, the two side nails
    M2 screw heads
  controller (bridge frame P, top face):
    Molex 52610-2072          vertical housing from the footprint's body outline, slider on top, the flex slot,
                              tails on both pad rows
Dimensions from the parts' datasheets (Molex 200528 / 52610 drawings, Kailh CPG151101S11, OPSCO SK6812MINI-E,
DO-35, EIA 1206). Returns {material: [solids]}; the render colours each material.
"""
import math
import numpy as np
import cadquery as cq
from shapely.geometry import Polygon

from compose import params as PR
from compose import geom as G


def _box(x0, x1, y0, y1, z0, z1):
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _prism(poly, z0, z1):
    z0, z1 = sorted((z0, z1))
    pts = [cq.Vector(x, y, z0) for x, y in list(poly.exterior.coords)[:-1]]
    w = cq.Wire.makePolygon(pts + [pts[0]])
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(w), cq.Vector(0, 0, z1 - z0))


def _cyl(a, b, r):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    return cq.Solid.makeCylinder(r, float(np.linalg.norm(d)), cq.Vector(*a), cq.Vector(*(d / np.linalg.norm(d))))


def _oriented_box(c, u, L, W, z0, z1):
    """Box centred at c (xy), length L along unit u, width W across, z0..z1."""
    u = np.asarray(u, float) / np.linalg.norm(u)
    v = np.array([-u[1], u[0]])
    q = [c + u * a * L / 2 + v * b * W / 2 for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return _prism(Polygon(q), z0, z1)


def half_local(board_path):
    """The left half's fitted parts (hotswap + RGB build), left local frame: {material: [solids]}."""
    import pcbnew
    from compose.pcb import rev2_half as H2
    from compose.pcb import layout as PL
    from compose.pcb import kicad as PK
    s = H2.plan("hotswap", True)
    L = G.LAYOUT
    zb = -PR.PCB_T                                      # the B face (the parts hang below it)
    out = {k: [] for k in ("hsock", "hmetal", "hdiode", "hband", "hled", "hcap", "hffc", "hact", "hhead")}
    # ---- hotswap sockets: body between the two tabs, metal tabs on the pads
    for k in L.keys:
        rects = []
        for (c, (w, h)) in (PR.HS_PAD2, PR.HS_PAD1):
            r = Polygon([PL.fp2local(k, c[0] + dx * w / 2, c[1] + dy * h / 2) for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
            rects.append(r)
            out["hmetal"].append(_prism(r.buffer(-0.15), zb, zb - 0.25))
        from shapely.ops import unary_union
        body = unary_union(rects).convex_hull.buffer(-0.6)
        out["hsock"].append(_prism(body, zb - 0.05, zb - PR.HS_HEIGHT))
        for p in (PR.MX_PIN1, PR.MX_PIN2):                # the two pin receptacles
            x, y = PL.fp2local(k, *p)
            out["hsock"].append(cq.Solid.makeCylinder(1.6, PR.HS_HEIGHT + 0.2, cq.Vector(x, y, zb - PR.HS_HEIGHT - 0.2)))
    # ---- DO-35 diodes: body against the board, band at the cathode, leads to the holes and through the board
    Ld, Dd = PR.DIODE_BODY
    for ks in s.keys:
        ca, an = np.array(ks.cathode, float), np.array(ks.anode, float)
        u = (an - ca) / np.linalg.norm(an - ca)
        mid = (ca + an) / 2
        zc = zb - Dd / 2 - 0.05
        b0, b1 = mid - u * Ld / 2, mid + u * Ld / 2
        out["hdiode"].append(_cyl((*(b0 + u * 0.7), zc), (*b1, zc), Dd / 2))
        out["hband"].append(_cyl((*b0, zc), (*(b0 + u * 0.7), zc), Dd / 2 + 0.02))
        for end, hole in ((b0, ca), (b1, an)):
            out["hmetal"].append(_cyl((*end, zc), (*hole, zc), 0.25))
            out["hmetal"].append(_cyl((*hole, zc), (*hole, 0.6), 0.25))
    # ---- SK6812 MINI-E, reverse mount: body through the cutout, leads on the B pads
    for i in range(len(L.keys)):
        cut = s.ledcut[i] if i < len(s.ledcut) else None
        if cut is None:
            continue
        mr = cut.minimum_rotated_rectangle
        q = list(mr.exterior.coords)[:4]
        c = np.mean(q, axis=0)
        e1, e2 = np.subtract(q[1], q[0]), np.subtract(q[2], q[1])
        u = e1 if np.linalg.norm(e1) >= np.linalg.norm(e2) else e2
        out["hled"].append(_oriented_box(c, u, 3.2, 2.8, zb - 0.94, zb + 0.84))
        for poly in H2.led_pads(k=L.keys[i], face="B").values():
            out["hmetal"].append(_prism(poly.buffer(-0.12), zb, zb - 0.2))
    # ---- 1206 capacitors on the fitted face: body between the pads, metal end caps
    for i in s.caps:
        pa, pb = (np.array(p, float) for p in H2.cap_pads(L.keys[i], "B"))
        u = pb - pa
        c = (pa + pb) / 2
        out["hcap"].append(_oriented_box(c, u, 2.2, 1.55, zb - 0.05, zb - 1.0))
        un = u / np.linalg.norm(u)
        for sg in (-1, 1):
            out["hmetal"].append(_oriented_box(c + un * sg * 1.35, u, 0.5, 1.6, zb - 0.02, zb - 1.02))
    # ---- M2 screw heads
    for x, y in s.posts:
        out["hhead"].append(cq.Solid.makeCylinder(PR.M2_HEAD_D / 2, PR.M2_HEAD_H, cq.Vector(x, y, zb - PR.M2_HEAD_H)))
    # ---- Molex 200528-0200 from the routed board's J1B footprint
    b = pcbnew.LoadBoard(board_path)
    J = next(f for f in b.GetFootprints() if f.GetReference() == "J1B")
    mm = pcbnew.ToMM
    loc = lambda X, Y: (X - PK.OX, PK.OY - Y)
    pads = [p for p in J.Pads() if p.GetNumber() != "MP"]
    nails = [p for p in J.Pads() if p.GetNumber() == "MP"]
    xs = [loc(mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in pads]
    row_x = float(np.mean([x for x, _ in xs]))
    y0, y1 = min(y for _, y in xs), max(y for _, y in xs)
    yc = (y0 + y1) / 2
    fab = [g.GetBoundingBox() for g in J.GraphicalItems() if g.GetLayer() == pcbnew.B_Fab and g.GetClass() != "MTEXT"
           and "TEXT" not in g.GetClass()]
    fx1 = max(mm(bb.GetRight()) for bb in fab) - PK.OX            # cable face (toward the bridge)
    fx0 = row_x + 0.2                                                # the housing's back, just past the tails
    H = 1.9
    half_len = 11.85                                                 # 23.7 mm body between the nail blocks
    out["hffc"].append(_box(fx0, fx1 - 0.12, yc - half_len, yc + half_len, zb, zb - H))
    out["hffc"].append(_box(fx0 - 0.35, fx1 - 1.4, yc - 12.65, yc - half_len, zb, zb - H))   # nail blocks
    out["hffc"].append(_box(fx0 - 0.35, fx1 - 1.4, yc + half_len, yc + 12.65, zb, zb - H))
    act = _box(fx0 + 0.2, fx1 - 0.25, yc - half_len + 0.3, yc + half_len - 0.3, zb - H + 0.4, zb - H - 0.02)
    out["hact"].append(act)                                          # flip-lock actuator, the face away from the board
    slot = _box(fx1 - 3.6, fx1 + 0.1, yc - 10.7, yc + 10.7, zb - 0.85, zb - 1.15)
    out["hffc"] = [s_.cut(slot) for s_ in out["hffc"]]
    for (x, y) in xs:                                               # tails: on the pad, up into the housing
        out["hmetal"].append(_box(x - 0.5, x + 0.35, y - 0.15, y + 0.15, zb, zb - 0.15))
        out["hmetal"].append(_box(x + 0.2, x + 0.35, y - 0.15, y + 0.15, zb, zb - 0.9))
    for p in nails:
        x, y = loc(mm(p.GetPosition().x), mm(p.GetPosition().y))
        out["hmetal"].append(_box(x - 0.6, x + 0.6, y - 0.9, y + 0.9, zb, zb - 0.2))
        out["hmetal"].append(_box(x - 0.6, x + 0.6, y - 0.12 * np.sign(y - yc) - 0.1, y - 0.12 * np.sign(y - yc) + 0.1, zb, zb - 1.5))
    return {k: v for k, v in out.items() if v}


def controller_P(board_path):
    """The controller's two Molex 52610 vertical connectors, bridge frame P: {material: [solids]}."""
    import pcbnew
    from compose.case import gasket as C
    from compose.controller import rev2 as CR
    from compose.controller import rev2_std as CS
    CT = C.CT
    bt = CT.board_top
    mm = pcbnew.ToMM
    b = pcbnew.LoadBoard(board_path)
    out = {"cffc": [], "cslide": [], "cmetal": []}
    toP = lambda X, Y: CT.to_P(X - CR.CX, Y - CR.CY)
    for ref in ("JL", "JR"):
        J = next(f for f in b.GetFootprints() if f.GetReference() == ref)
        fab = [g.GetBoundingBox() for g in J.GraphicalItems() if g.GetLayer() == pcbnew.F_Fab and "TEXT" not in g.GetClass()]
        X0, X1 = min(mm(bb.GetLeft()) for bb in fab), max(mm(bb.GetRight()) for bb in fab)
        Y0, Y1 = min(mm(bb.GetTop()) for bb in fab), max(mm(bb.GetBottom()) for bb in fab)
        (px0, py0), (px1, py1) = toP(X0 + 0.05, Y1 - 0.05), toP(X1 - 0.05, Y0 + 0.05)
        sx = -1.0 if ref == "JL" else 1.0
        slot_x = sx * CS.VFFC_SLOT_X
        _, sy = toP(CR.CX, CR.CY + CS.VFFC_Y0)
        h0, H = CS.VFFC_H - 1.4, CS.VFFC_H
        slot = _box(slot_x - 0.3, slot_x + 0.3, sy - 10.75, sy + 10.75, bt + H - 4.6, bt + H + 0.1)
        out["cffc"].append(_box(px0, px1, py0, py1, bt, bt + h0).cut(slot))
        out["cslide"].append(_box(px0 + 0.1, px1 - 0.1, py0 + 0.6, py1 - 0.6, bt + h0, bt + H).cut(slot))
        for p in J.Pads():
            X, Y = mm(p.GetPosition().x), mm(p.GetPosition().y)
            x, y = toP(X, Y)
            Lp = mm(max(p.GetSize().x, p.GetSize().y))
            out["cmetal"].append(_box(x - Lp / 2 + 0.1, x + Lp / 2 - 0.1, y - 0.15, y + 0.15, bt, bt + 0.15))
    return out


def controller_parts_P(board_path):
    """Every other part on the controller, bridge frame P, from the routed board's footprints: the Pico (board,
    RP2040, flash, micro-USB, on its male headers in the two female sockets), the OLED/AUX pin headers, the Qwiic
    JST SH, and underneath the 74HCT125 DIP-14, the axial resistors, the ceramic disc and electrolytic capacitors
    and the standing polyfuse. {material: [solids]}."""
    import pcbnew
    from compose.case import gasket as C
    from compose.controller import rev2 as CR
    from compose.controller import rev2_std as CS
    CT = C.CT
    bt, bb = CT.board_top, CT.board_bot
    mm = pcbnew.ToMM
    b = pcbnew.LoadBoard(board_path)
    toP = lambda X, Y: np.array(CT.to_P(X - CR.CX, Y - CR.CY))
    out = {k: [] for k in ("cpico", "cchip", "cusb", "chdr", "cpin", "cjst", "cdip", "cres", "ccer", "celec",
                           "cfuse", "cmetal")}
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        pads = [toP(mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in fp.Pads()]
        if not pads:
            continue
        P_ = np.array(pads)
        lo, hi = P_.min(axis=0), P_.max(axis=0)
        mid = (lo + hi) / 2
        if ref.startswith("U1"):                                # female sockets, 8.5 mm
            out["chdr"].append(_box(lo[0] - 1.27, hi[0] + 1.27, lo[1] - 1.27, hi[1] + 1.27, bt, bt + 8.5))
        elif ref in ("J4", "J6"):                               # pin headers: base + square pins
            out["chdr"].append(_box(lo[0] - 1.27, hi[0] + 1.27, lo[1] - 1.27, hi[1] + 1.27, bt, bt + 2.5))
            for x, y in P_:
                out["cpin"].append(_box(x - 0.32, x + 0.32, y - 0.32, y + 0.32, bt - 3.0, bt + 8.5))
        elif ref == "J5":                                       # JST SH 4-pin, top entry
            out["cjst"].append(_box(mid[0] - 3.0, mid[0] + 3.0, mid[1] - 2.1, mid[1] + 2.1, bt, bt + 4.25))
        elif ref == "U2":                                       # DIP-14 under the board
            u = (hi - lo)
            along = 0 if u[0] > u[1] else 1
            L_, W_ = 19.0, 6.35
            sx, sy = (L_, W_) if along == 0 else (W_, L_)
            out["cdip"].append(_box(mid[0] - sx / 2, mid[0] + sx / 2, mid[1] - sy / 2, mid[1] + sy / 2, bb - 0.5, bb - 3.8))
            for x, y in P_:
                out["cmetal"].append(_box(x - 0.25, x + 0.25, y - 0.25, y + 0.25, bb - 2.0, bt + 0.8))
        elif ref.startswith("R"):                               # axial DIN0207, lying under the board
            a, c = P_[0], P_[-1]
            u = (c - a) / np.linalg.norm(c - a)
            m = (a + c) / 2
            z = bb - 1.35
            out["cres"].append(_cyl((*(m - u * 3.15), z), (*(m + u * 3.15), z), 1.25))
            for e, h in ((m - u * 3.15, a), (m + u * 3.15, c)):
                out["cmetal"].append(_cyl((*e, z), (*h, z), 0.25))
                out["cmetal"].append(_cyl((*h, z), (*h, bt + 0.8), 0.25))
        elif ref == "C1":                                       # ceramic disc, standing
            a, c = P_[0], P_[-1]
            u = (c - a) / np.linalg.norm(c - a)
            m = (a + c) / 2
            n = np.array([-u[1], u[0]])
            out["ccer"].append(_cyl((*(m - n * 0.8), bb - 3.6), (*(m + n * 0.8), bb - 3.6), 2.0))
            for h in (a, c):
                out["cmetal"].append(_cyl((*h, bb - 2.0), (*h, bt + 0.8), 0.25))
        elif ref == "C2":                                       # radial electrolytic, standing under the board
            out["celec"].append(cq.Solid.makeCylinder(2.5, 11.0, cq.Vector(mid[0], mid[1], bb - 11.3)))
            for h in P_:
                out["cmetal"].append(_cyl((*h, bb - 0.3), (*h, bt + 0.8), 0.25))
        elif ref == "F1":                                       # MF-RHT050 disc, standing
            a, c = P_[0], P_[-1]
            u = (c - a) / np.linalg.norm(c - a)
            out["cfuse"].append(_oriented_box(mid, u, 7.4, 3.0, bb - 2.5, bb - 12.5))
            for h in (a, c):
                out["cmetal"].append(_cyl((*h, bb - 2.5), (*h, bt + 0.8), 0.3))
    # the Pico on its male headers: board, RP2040, flash, micro-USB at the back end
    yc = CT.y_pc
    out["chdr"] += [_box(sx * CS.PICO_X - 1.25, sx * CS.PICO_X + 1.25, yc - 25.4, yc + 25.4, bt + 8.5, CT.pico_bot)
                    for sx in (-1, 1)]
    out["cpico"].append(_box(-PR.PICO_W / 2, PR.PICO_W / 2, yc - PR.PICO_L / 2, yc + PR.PICO_L / 2, CT.pico_bot,
                             CT.pico_bot + PR.PICO_T))
    zt = CT.pico_bot + PR.PICO_T
    out["cchip"].append(_box(-3.5, 3.5, yc - 3.5, yc + 3.5, zt, zt + 0.9))                 # RP2040, centred
    out["cchip"].append(_box(-2.6, 2.6, yc + 8.0, yc + 12.0, zt, zt + 1.0))                # flash, toward USB
    out["cusb"].append(_box(-4.0, 4.0, yc + PR.PICO_L / 2 - 4.2, yc + PR.PICO_L / 2 + 1.3, zt, zt + 2.7))
    for sx in (-1, 1):                                       # castellated pads along both long edges
        for i in range(20):
            y = yc - 24.13 + i * 2.54
            out["cpin"].append(_box(sx * PR.PICO_W / 2 - sx * 1.6 - 0.6, sx * PR.PICO_W / 2 - sx * 1.6 + 0.6,
                                    y - 0.6, y + 0.6, zt, zt + 0.05))
    return {k: v for k, v in out.items() if v}
