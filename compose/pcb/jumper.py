"""
Rev 2 flex jumpers: the custom flex PCB that joins each half board's cable connector (Molex 200528,
right-angle, on the half's bottom face) to the controller's (Molex 52610, vertical, top face).

The controller's connectors sit square to its edges at fixed positions (controller rev 2 standard), so the
controller never depends on a layout's angles; the jumper absorbs them. Its centre line, from the half end:
  1 mm of stiffener out of the half's connector (along the cable's own direction, tilted by the tent),
  a bend up, a straight climb, a bend over to horizontal                    (rise: bends about the half's slot axis)
  a flat top: straight, a flat ring segment that turns it in plan by the splay, straight
  a bend down, a straight drop, 1 mm of stiffener above the controller's slot  (drop: bends about the controller's)
Every piece is flat or bent about one axis, so the jumper is a flat cut-out bent into shape: nothing twists.
The free lengths (the climb, the two flat-top straights, the drop) are solved so the path meets both ends.

Frames: everything here is in the bridge frame P (compose.geom), left jumper; the right one is its mirror.
"""
import math
from types import SimpleNamespace
import numpy as np

from compose import params as PR

STIFF_OUT = 1.0          # rigid stiffener past each connector's entry
BEND_R = 2.0             # every bend (centre line); flex static bends want >= ~1.4 mm for 2 layers
RISE_DEG = 45.0          # gentlest climb tried (steeper ones up to vertical if that doesn't fit)
DROP_MIN = 0.5           # shortest straight above the controller's stiffener
RING_EXTRA = 1.0         # flat top ring: inner edge radius (the ring's inner side turns about this)
Z = np.array([0.0, 0.0, 1.0])


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def ends():
    """(half end, controller end) frames, bridge frame P, left side:
    half:  face = cable face centre of the half's connector, ins = into it, axis = its slot axis (width)
    ctrl:  top  = slot opening centre of the controller's connector, ins = into it (down), axis = its slot axis"""
    from compose import geom as G
    from compose.case import gasket as C
    from compose.controller import rev2_std as CS
    from compose.pcb import rev2_half as H2
    s = H2.plan()
    face_x = max(x for x, _ in s.ffc.body.exterior.coords)
    R = G.M_LP[:3, :3]
    half = SimpleNamespace(face=np.array(G.apply(G.M_LP, (face_x + 0.2, s.ffc.c[1], -PR.PCB_T - CS.FFC_ENTRY_H))),
                           ins=_unit(R @ np.array([-1.0, 0, 0])), axis=_unit(R @ np.array([0, 1.0, 0])))
    CT = C.CT
    ctrl = SimpleNamespace(top=np.array([-CS.VFFC_SLOT_X, CT.y_pc - CS.VFFC_Y0, CT.board_top + CS.VFFC_H]),
                           ins=-Z, axis=np.array([0.0, 1.0, 0.0]))
    return half, ctrl


def _arc(p, hd, r, to, n=16):
    """Points along an arc in a (u, z) plane from p at heading hd (deg) to heading `to`; left turn if to > hd."""
    sg = 1.0 if to > hd else -1.0
    c = p + sg * r * np.array([-math.sin(math.radians(hd)), math.cos(math.radians(hd))])
    return [c - sg * r * np.array([-math.sin(math.radians(a)), math.cos(math.radians(a))])
            for a in np.linspace(hd, to, n + 1)[1:]]


def solve(rise_deg=None, r=BEND_R, s_out=STIFF_OUT, drop_min=DROP_MIN):
    """Solve the left jumper's centre line: the gentlest climb (RISE_DEG up to vertical, 1 deg steps) and the
    smallest sideways jog that reach the controller's slot with every straight >= 0. Returns a namespace with
    the pieces (for the solid and the flat pattern); ValueError if there's no such path."""
    if rise_deg is None:                                     # the smallest jog wins, then the gentlest climb
        sols, err = [], None
        for a in np.arange(RISE_DEG, 90.01, 1.0):
            try:
                sols.append(solve(float(a), r, s_out, drop_min))
            except ValueError as e:
                err = e
        if not sols:
            raise err
        return min(sols, key=lambda g: (round(abs(g.jog), 6), g.rise_deg))
    half, ctrl = ends()
    a1, a2 = half.axis, ctrl.axis
    u1 = _unit(np.cross(a1, Z))                              # horizontal, perpendicular to the half's slot axis
    if u1 @ (ctrl.top - half.face) < 0:
        u1 = -u1                                             # ... pointing inward (toward the controller)
    u2 = _unit(np.cross(a2, Z))
    if u2 @ (ctrl.top - half.face) < 0:
        u2 = -u2
    p0 = half.face - half.ins * s_out                       # end of the half's stiffener (3D)
    d0 = math.degrees(math.atan2(-half.ins @ Z, -half.ins @ u1))   # its heading in the rise plane (tent tilt)
    e_top = ctrl.top + Z * s_out                             # top of the controller's stiffener
    z_top = e_top[2] + drop_min + r                          # flat top height (centre line)
    # rise in the plane (u1, Z) from p0
    A1 = _arc(np.zeros(2), d0, r, rise_deg)
    A2s = _arc(np.zeros(2), rise_deg, r, 0.0)
    L1 = (z_top - p0[2] - A1[-1][1] - A2s[-1][1]) / max(math.sin(math.radians(rise_deg)), 1e-9)
    if L1 < 0:
        raise ValueError(f"no climb: L1 {L1:.2f}")
    pb = A1[-1] + L1 * np.array([math.cos(math.radians(rise_deg)), math.sin(math.radians(rise_deg))])
    rise = [np.zeros(2)] + A1 + [pb] + [pb + q for q in A2s]
    top0 = p0 + u1 * rise[-1][0] + Z * rise[-1][1]           # start of the flat top (3D)
    # flat top in plan: Lb along u1, an S of two ring segments (turn + jog, then -jog: net = the in-plan turn
    # between the two slot axes; the jog shifts the jumper sideways), La along u2, then the drop's bend (r)
    turn = math.atan2(np.cross(u1, u2)[2], u1 @ u2)          # signed in-plan turn (+ = left)
    Rc = PR.JUMPER_W / 2 + RING_EXTRA
    best = None
    for jog in sorted(np.radians(np.arange(-40.0, 40.01, 0.25)), key=abs):
        rings = [(turn + jog, Rc), (-jog, Rc)]
        pos, hd = np.zeros(3), u1.copy()
        for ang, rad in rings:
            if abs(ang) < 1e-9:
                continue
            side = math.copysign(1.0, ang)
            left = np.cross(Z, hd)
            pos = pos + rad * (math.sin(abs(ang)) * hd + (1 - math.cos(abs(ang))) * side * left)
            c_, s_ = math.cos(ang), math.sin(ang)
            hd = np.array([hd[0] * c_ - hd[1] * s_, hd[0] * s_ + hd[1] * c_, 0.0])
        rhs = (e_top - top0 - pos - u2 * r)[:2]
        Lb, La = np.linalg.solve(np.array([u1[:2], u2[:2]]).T, rhs)
        if Lb >= -1e-6 and La >= -1e-6:
            best = (jog, rings, max(Lb, 0.0), max(La, 0.0), pos)
            break
    if best is None:
        raise ValueError("no flat top: the jumper can't reach the controller's slot from this half connector")
    jog, rings, Lb, La, ring = best
    top1 = top0 + u1 * Lb + ring + u2 * La                   # end of the flat top (3D), heading u2
    D = _arc(np.zeros(2), 0.0, r, -90.0)
    L2 = (top1[2] + D[-1][1]) - e_top[2]
    drop = [np.zeros(2)] + D + [np.array([D[-1][0], D[-1][1] - L2])]
    seg = lambda pts: float(sum(np.linalg.norm(np.diff(np.array(pts), axis=0), axis=1)))
    return SimpleNamespace(half=half, ctrl=ctrl, u1=u1, u2=u2, a1=a1, a2=a2, p0=p0, top0=top0, top1=top1,
                           rise=rise, drop=drop, Lb=float(Lb), La=float(La), L1=float(L1), L2=float(L2),
                           turn=turn, jog=float(jog), rings=rings, Rc=Rc, r=r, s_out=s_out, z_top=float(top0[2]),
                           rise_deg=float(rise_deg),
                           len_rise=seg(rise), len_top=float(Lb + sum(abs(a) * rr for a, rr in rings) + La),
                           len_drop=seg(drop))


# ---------------------------------------------------------------- the jumper as a solid (case checks)
T_SOLID = 0.3                                                # modelled at the stiffened thickness everywhere


def _band(pts, t):
    from shapely.geometry import LineString
    return list(LineString([tuple(p) for p in pts]).buffer(t / 2, cap_style=2, join_style=2).exterior.coords)[:-1]


def solid_P(g=None):
    """The left jumper as a cadquery compound, bridge frame P: half stiffener out of its connector, rise, flat
    top, drop, controller stiffener down to its slot opening. The parts inside the connectors are left out."""
    import cadquery as cq
    g = g or solve()
    W, T = PR.JUMPER_W, T_SOLID

    def slab(origin, udir, wdir, pts2d):
        q = _band(pts2d, T)
        to3 = lambda uz, off: origin + udir * uz[0] + Z * uz[1] + wdir * off
        ws = [cq.Wire.makePolygon([cq.Vector(*to3(p, o)) for p in q] + [cq.Vector(*to3(q[0], o))]) for o in (-W / 2, W / 2)]
        return cq.Solid.makeLoft(ws, True)
    d0 = np.array([-g.half.ins @ g.u1, -g.half.ins @ Z])
    rise = [-d0 * g.s_out] + g.rise                          # from the half connector's face
    pieces = [slab(g.p0, g.u1, g.a1, rise)]
    plan = flat_top_plan(g)
    ring = [tuple(p[:2]) for p in plan["left"]] + [tuple(p[:2]) for p in plan["right"][::-1]]
    wire = cq.Wire.makePolygon([cq.Vector(x, y, g.z_top - T / 2) for x, y in ring] +
                               [cq.Vector(ring[0][0], ring[0][1], g.z_top - T / 2)])
    pieces.append(cq.Solid.extrudeLinear(cq.Face.makeFromWires(wire), cq.Vector(0, 0, T)))
    drop = g.drop + [g.drop[-1] + np.array([0.0, -g.s_out])]  # down to the slot opening
    pieces.append(slab(g.top1, g.u2, g.a2, drop))
    return cq.Compound.makeCompound(pieces)


def flat_top_plan(g, n=12):
    """Plan polylines (3D points at the flat top's height) of the flat top's centre line and both edges,
    from top0 (heading u1) to top1 (heading u2)."""
    W = PR.JUMPER_W
    pts, hd = [g.top0.copy()], g.u1.copy()
    pos = g.top0.copy()
    pos = pos + hd * g.Lb
    pts.append(pos.copy())
    for ang, rad in g.rings:
        if abs(ang) < 1e-9:
            continue
        side = math.copysign(1.0, ang)
        c = pos + side * rad * np.cross(Z, hd)
        v0 = pos - c
        for k in range(1, n + 1):
            a = ang * k / n
            ca, sa = math.cos(a), math.sin(a)
            pts.append(c + np.array([v0[0] * ca - v0[1] * sa, v0[0] * sa + v0[1] * ca, 0.0]))
        pos = pts[-1].copy()
        ca, sa = math.cos(ang), math.sin(ang)
        hd = np.array([hd[0] * ca - hd[1] * sa, hd[0] * sa + hd[1] * ca, 0.0])
    pts.append(pos + hd * g.La)
    # edges: offset along the local left normal; headings from the polyline
    left, right = [], []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]; b = pts[min(i + 1, len(pts) - 1)]
        t = _unit(b - a); nl = np.cross(Z, t)
        left.append(p + nl * W / 2); right.append(p - nl * W / 2)
    return dict(centre=pts, left=left, right=right)


# ---------------------------------------------------------------- the flat pattern and the flex board
INS_HALF, INS_CTRL = 4.0, 4.1     # flex inside each connector (Molex 200528 / 52610 drawings)
FINGER_L, FINGER_W = 3.5, 0.7     # exposed contacts from each tip (200528: 3.5 +-0.3; 52610: >= 2.7), width
FINGER_PULLBACK = 0.3             # copper starts this far in from the cut edge
TRACE_W = 0.5
EAR = (1.1, 1.5, 2.2, 0.55)       # 200528 retention ears: slope from 1.1, full from 1.5 to 2.2, 0.55 proud of each edge
CHAMFER_CTRL = 0.3                # 52610 end: 2 x C0.3
STIFF_HALF, STIFF_CTRL = INS_HALF + STIFF_OUT, INS_CTRL + STIFF_OUT


def flat_segments(g, side="L"):
    """The flat pattern's centre line as turtle steps from the half end's tip: ("S", length) or
    ("A", angle (rad, + = left seen from the conductor side), radius). Right jumper: the mirror (angles negated)."""
    sg = 1.0 if side == "L" else -1.0
    segs = [("S", STIFF_HALF + g.len_rise + g.Lb)]
    segs += [("A", sg * a, rr) for a, rr in g.rings if abs(a) > 1e-9]
    segs += [("S", g.La + g.len_drop + STIFF_CTRL)]
    return segs


def _walk(segs, step=0.25):
    """Densely sampled centre line: list of (point, heading unit vector, arc length)."""
    out, p, h, s = [], np.zeros(2), np.array([1.0, 0.0]), 0.0
    out.append((p.copy(), h.copy(), 0.0))
    for seg in segs:
        if seg[0] == "S":
            n = max(1, int(math.ceil(seg[1] / step)))
            for k in range(1, n + 1):
                out.append((p + h * seg[1] * k / n, h.copy(), s + seg[1] * k / n))
            p, s = p + h * seg[1], s + seg[1]
        else:
            ang, rad = seg[1], seg[2]
            nl = np.array([-h[1], h[0]])
            c = p + math.copysign(1, ang) * rad * nl
            n = max(2, int(math.ceil(abs(ang) * rad / step)))
            for k in range(1, n + 1):
                a = ang * k / n
                ca, sa = math.cos(a), math.sin(a)
                v = p - c
                q = c + np.array([v[0] * ca - v[1] * sa, v[0] * sa + v[1] * ca])
                hk = np.array([h[0] * ca - h[1] * sa, h[0] * sa + h[1] * ca])
                out.append((q, hk, s + abs(ang) * rad * k / n))
            p = out[-1][0].copy(); h = out[-1][1].copy(); s += abs(ang) * rad
    return out


def conductor_w(k, side="L"):
    """Offset across the flex (+ = left of the centre line seen from the conductor side) of slot k's conductor.
    Left jumper: left = the back (slot 1); right jumper: left = the front."""
    w = 9.5 - (k - 1)
    return w if side == "L" else -w


def flat(g=None, side="L"):
    """Flat pattern (flex frame, mm, conductor side up): outline polygon, conductor polylines, finger and
    stiffener rectangles. x runs from the half end's tip."""
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    from shapely.affinity import rotate, translate
    g = g or solve()
    W = PR.JUMPER_W
    cl = _walk(flat_segments(g, side))
    L = cl[-1][2]
    off = lambda w: [p + w * np.array([-h[1], h[0]]) for p, h, _ in cl]
    left, right = off(W / 2), off(-W / 2)
    body = Polygon([tuple(q) for q in left] + [tuple(q) for q in right[::-1]]).buffer(0)
    # half end (tip at x = 0, straight along +x): retention ears, small corner rounds
    e0, e1, e2, ep = EAR
    for sg in (1, -1):
        ear = Polygon([(e0, sg * W / 2), (e1, sg * (W / 2 + ep)), (e2, sg * (W / 2 + ep)), (e2, sg * W / 2)])
        body = unary_union([body, ear])
        body = body.difference(Polygon([(-0.01, sg * (W / 2 + 0.01)), (0.2, sg * (W / 2 + 0.01)), (-0.01, sg * (W / 2 - 0.2))]))
    # controller end: chamfers in the tip's own frame
    pe, he = cl[-1][0], cl[-1][1]
    ang = math.degrees(math.atan2(he[1], he[0]))
    for sg in (1, -1):
        tri = Polygon([(0.01, sg * (W / 2 + 0.01)), (-CHAMFER_CTRL, sg * (W / 2 + 0.01)), (0.01, sg * (W / 2 - CHAMFER_CTRL))])
        body = body.difference(translate(rotate(tri, ang, origin=(0, 0)), pe[0], pe[1]))
    in_tip = lambda poly: translate(rotate(poly, ang, origin=(0, 0)), pe[0], pe[1])   # tip frame: x <= 0 inward
    cond = {k: off(conductor_w(k, side)) for k in range(1, 21)}
    fingers = {}
    for k in range(1, 21):
        w = conductor_w(k, side)
        fingers[k] = (box(FINGER_PULLBACK, w - FINGER_W / 2, FINGER_L, w + FINGER_W / 2),
                      in_tip(box(-FINGER_L, w - FINGER_W / 2, -FINGER_PULLBACK, w + FINGER_W / 2)))
    stiff = (box(0, -W / 2 - EAR[3], STIFF_HALF, W / 2 + EAR[3]).intersection(body),
             in_tip(box(-STIFF_CTRL, -W / 2, 0, W / 2)).intersection(body))
    cover_open = (box(-0.1, -W / 2 - 1, FINGER_L, W / 2 + 1), in_tip(box(-FINGER_L, -W / 2 - 1, 0.1, W / 2 + 1)))
    s_of = np.array([c[2] for c in cl])
    return dict(outline=body, centre=cl, length=L, cond=cond, s=s_of, fingers=fingers, stiff=stiff,
                cover_open=cover_open, side=side)


def build_board(side="L", g=None):
    """KiCad board of one jumper: single-sided (F.Cu), fingers as pads, traces as tracks; User.1 = the PI
    stiffener areas (on the back, under the fingers: 0.3 mm total there); F.Mask = the coverlay openings."""
    import pcbnew
    from compose.pcb import kicad as PK
    f = flat(g, side)
    b = PK.new_board()
    ds = b.GetDesignSettings()
    ds.m_CopperEdgeClearance = PK.MM(FINGER_PULLBACK - 0.05)

    net = PK.Nets(b)
    ox, oy = 50.0, 50.0
    PK.outline(b, f["outline"], ox, oy)
    fp = pcbnew.FOOTPRINT(b)
    fp.SetFPID(pcbnew.LIB_ID("compose", f"FlexJumper_{side}"))
    fp.SetReference(f"JMP{side}")
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    for k, ends_ in f["fingers"].items():
        for e, poly in enumerate(ends_):
            # rectangular finger as a custom-shape-free rect pad: centre + size + rotation
            mr = poly.minimum_rotated_rectangle
            cx, cy = mr.centroid.x, mr.centroid.y
            xs = list(mr.exterior.coords)[:4]
            d1 = math.dist(xs[0], xs[1]); d2 = math.dist(xs[1], xs[2])
            a = math.degrees(math.atan2(xs[1][1] - xs[0][1], xs[1][0] - xs[0][0]))
            ln, wd = (d1, d2) if d1 >= d2 else (d2, d1)
            if d2 > d1:
                a += 90.0
            X, Y = PK.K((cx, cy), ox, oy)
            PK.add_pad(fp, f"{k}{'H' if e == 0 else 'C'}", "smd", "rect", (X, Y), (ln, wd), angle=a,
                       layers=pcbnew.LSET(pcbnew.F_Cu).AddLayer(pcbnew.F_Mask) if hasattr(pcbnew.LSET(pcbnew.F_Cu), "AddLayer") else None,
                       net=net(f"S{k}"))
    b.Add(fp)
    for k, pts in f["cond"].items():
        s = f["s"]
        sel = [q for q, sv in zip(pts, s) if FINGER_L - 0.3 <= sv <= f["length"] - FINGER_L + 0.3]
        for a, c in zip(sel[:-1], sel[1:]):
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(PK.V(*PK.K((float(a[0]), float(a[1])), ox, oy)))   # pcbnew.FromMM rejects numpy floats
            t.SetEnd(PK.V(*PK.K((float(c[0]), float(c[1])), ox, oy)))
            t.SetWidth(PK.MM(TRACE_W)); t.SetLayer(pcbnew.F_Cu); t.SetNet(net(f"S{k}"))
            b.Add(t)
    for poly in f["cover_open"]:
        PK.add_poly(b, poly.intersection(f["outline"].buffer(0.05)), pcbnew.F_Mask, ox, oy)
    for poly in f["stiff"]:
        PK.add_poly(b, poly, pcbnew.User_1, ox, oy)
    return b, f


def main(out=None):
    import os
    import sys
    import pcbnew
    from compose.pcb import kicad as PK
    out = out or (sys.argv[1] if len(sys.argv) > 1 else "out_r2t")
    PK.PCB_OUT = os.path.join(out, "pcb")
    os.makedirs(PK.PCB_OUT, exist_ok=True)
    g = solve()
    print(f"jumper path: climb {g.rise_deg:.0f} deg, flat top at z {g.z_top:.2f} (turn {math.degrees(g.turn):.1f} deg, "
          f"jog {math.degrees(g.jog):.1f}), bends r {g.r}")
    for side in ("L", "R"):
        name = f"jumper_rev2_{side}"
        b, f = build_board(side, g)
        path = os.path.join(PK.PCB_OUT, name + ".kicad_pcb")
        pcbnew.SaveBoard(path, b)
        b = pcbnew.LoadBoard(path)
        err, warn, unc, rep = PK.drc(b, name)
        # the coverlay is open across each finger field (Molex: the whole contact area bare), so that one aperture
        # exposes all 20 nets by design: KiCad's "solder mask bridge" check doesn't apply to a cable end. KiCad 7's
        # Python DRC ignores the project's rule severities, so those entries are taken out of the count here
        import re
        bridges = len(re.findall(r"\[solder_mask_bridge\]", open(rep).read()))
        err -= bridges
        z = PK.export(path, name)
        bb = f["outline"].bounds
        print(f"{name}: {f['length']:.1f} mm long, outline {bb[2] - bb[0]:.1f} x {bb[3] - bb[1]:.1f} mm | "
              f"DRC {err} errors, {warn} warnings, {unc} unconnected (+{bridges} finger-field mask bridges, by design) | "
              f"{os.path.basename(z)}")


if __name__ == "__main__":
    main()
