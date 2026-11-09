"""
Rev 2 flex jumpers: the custom flex PCB that joins each half board's cable connector (Molex 200528,
right-angle, on the half's bottom face) to the controller's (Molex 52610, vertical, top face).

The controller's connectors sit square to its edges at fixed positions (controller rev 2 standard), so the
controller never depends on a layout's angles; the jumper absorbs them. It is one straight, symmetric strip,
the same part on both sides: the right jumper is bent as the mirror image of the left. From the half end:
  1 mm of stiffener out of the half's connector (along the cable's own direction, tilted by the tent),
  a bend up, a straight climb, a bend over, a straight, a bend down, a straight drop,
  1 mm of stiffener above the controller's slot.
Each bend is a plain cylindrical bend whose bend line crosses the strip a few degrees off square: those
skews turn the strip by the splay (10 deg in plan), so nothing twists and the flat strip needs no curve.
The bends' angles and skews and the straights are solved so the path meets both ends.

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
SLACK = 0.5              # the strip is this much longer than the solved path: it eases the bends while the controller
                         #   end is lifted 4.1 mm to go into its slot (flex-sim: copper strain 3.0 -> 2.3 %)
SKEW_MAX = math.radians(12.0)   # bend lines at most this far off square across the strip
Z = np.array([0.0, 0.0, 1.0])
SIGNS = (1, -1, -1)             # the climb bends toward the conductor side, the other two away from it


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


def _rod(a, th):
    a = _unit(a)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


def _bend(p, F, phi, beta, sg, r, n=12):
    """A cylindrical bend of a flat strip. F = columns (t along the strip, w across it, n the conductor side's
    normal). The bend line crosses the strip at `beta` off square, i.e. the cylinder axis is
    e = sin(beta) t + cos(beta) w; sg = +1 bends toward n. The centre line is a helix on the cylinder (radius r,
    wrapped by phi). Returns the end point, the end frame and [(point, frame)] samples along the bend."""
    t, w, nn = F.T
    e = math.sin(beta) * t + math.cos(beta) * w
    a, c = -sg * e, p + sg * r * nn
    out = []
    for th in np.linspace(0.0, phi, n + 1):
        R = _rod(a, th)
        out.append((c + R @ (p - c) + r * math.tan(beta) * th * e, R @ F))
    return out[-1][0], out[-1][1], out


def _walk3(p0, F0, bends, Ls, r, n=12):
    """Straight Ls[0], bend 1, straight Ls[1], bend 2, straight Ls[2], bend 3, straight Ls[3].
    bends = [(phi, beta)] * 3. Returns the end point, the end frame and the bends' samples."""
    p, F, samples = np.array(p0, float), np.array(F0, float), []
    for i, (phi, beta) in enumerate(bends):
        p = p + Ls[i] * F[:, 0]
        p, F, smp = _bend(p, F, phi, beta, SIGNS[i], r, n)
        samples.append((smp, beta))
    return p + Ls[3] * F[:, 0], F, samples


def _frames(r=BEND_R, s_out=STIFF_OUT):
    half, ctrl = ends()
    t0 = -half.ins
    w0 = _unit(half.axis - (half.axis @ t0) * t0)
    F0 = np.column_stack([t0, w0, np.cross(t0, w0)])         # conductor side up (n has +z)
    assert F0[2, 2] > 0
    p0 = half.face - half.ins * s_out                        # end of the half's stiffener
    e_top = ctrl.top + Z * s_out                             # top of the controller's stiffener
    return half, ctrl, F0, p0, e_top


def solve(rise_deg=None, r=BEND_R, s_out=STIFF_OUT, drop_min=DROP_MIN, free_shift=False):
    """Solve the left jumper: a straight strip from the half connector's stiffener to the controller's, bent
    three times (up, over, down), each bend line at most SKEW_MAX off square. The skews take up the splay, so
    the flat strip is straight and symmetric: the right jumper is the same part, bent as the mirror image.
    rise_deg = the climb's angle above horizontal; None = the gentlest that works (90 down to RISE_DEG,
    1 deg steps). The bends' angles and skews and the four straights are solved (least total skew), each
    straight long enough that neighbouring bend lines never meet on the strip. free_shift: also slide the
    half connector along its row (to find where a layout should put it); the shift is returned.
    ValueError if there's no path."""
    from scipy.optimize import minimize
    half, ctrl, F0, p0, e_top = _frames(r, s_out)
    key = (rise_deg, r, s_out, drop_min, free_shift, tuple(np.round(p0, 9)), tuple(np.round(e_top, 9)), tuple(np.round(F0, 9).ravel()))
    if key in _SOLVED:
        return _SOLVED[key]
    W = PR.JUMPER_W
    tilt = math.degrees(math.asin(F0[2, 0]))
    sm = lambda b: math.sqrt(math.tan(b) ** 2 + 1e-10)

    def attempt(climb, z0):
        p1 = math.radians(climb - tilt)
        bends = lambda z: [(p1, z[0]), (z[1], z[2]), (z[3], z[4])]
        start = lambda z: p0 + (z[9] * F0[:, 1] if free_shift else 0.0)
        end = lambda z: _walk3(start(z), F0, bends(z), z[5:9], r, n=2)
        cons = [{"type": "eq", "fun": lambda z: np.array([end(z)[1][0, 0], end(z)[1][1, 0], end(z)[1][0, 1]])},
                {"type": "eq", "fun": lambda z: end(z)[0] - e_top},
                {"type": "ineq", "fun": lambda z: z[5] - W / 2 * sm(z[0])},
                {"type": "ineq", "fun": lambda z: z[6] - W / 2 * (sm(z[0]) + sm(z[2]))},
                {"type": "ineq", "fun": lambda z: z[7] - W / 2 * (sm(z[2]) + sm(z[4]))},
                {"type": "ineq", "fun": lambda z: z[8] - W / 2 * sm(z[4]) - drop_min}]
        bnd = [(-SKEW_MAX, SKEW_MAX), (0.0, 2.2), (-SKEW_MAX, SKEW_MAX), (0.3, 2.6), (-SKEW_MAX, SKEW_MAX)] \
            + [(0.0, 40.0)] * 4 + [(-6.0, 6.0) if free_shift else (0.0, 0.0)]
        res = minimize(lambda z: z[0] ** 2 + z[2] ** 2 + z[4] ** 2, z0, method="SLSQP", constraints=cons, bounds=bnd,
                       options=dict(maxiter=600, ftol=1e-13))
        z = res.x
        pe, Fe, _ = end(z)
        ok = (np.abs(pe - e_top).max() < 1e-6 and np.linalg.norm(Fe[:, 0] + Z) < 1e-6 and Fe[1, 1] > 0.999
              and all(c_["fun"](z) >= -1e-7 for c_ in cons[2:]))
        return (z, bends(z), start(z)) if ok else None

    climbs = [float(rise_deg)] if rise_deg is not None else [float(a) for a in np.arange(90.0, RISE_DEG - 0.01, -1.0)]
    seeds = [np.radians([-3.0, 80.0, 3.0, 100.0, -4.0]).tolist() + [1.3, 2.6, 4.3, 1.3, 0.0],
             np.radians([3.0, 80.0, -3.0, 100.0, 4.0]).tolist() + [1.3, 2.6, 4.3, 1.3, 0.0]]
    found, prev = None, None
    for climb in climbs:                                     # continuation: each solve starts from the last one
        got = None
        for z0 in ([prev] if prev is not None else []) + seeds:
            z0 = np.array(z0, float)
            z0[1] = math.radians(climb) if prev is None else z0[1]
            got = attempt(climb, z0)
            if got:
                break
        if got is None:
            if found is not None:
                break                                        # gentler climbs than this don't fit either
            continue
        found, prev = (climb, got), got[0]
    if found is None:
        raise ValueError("no jumper path: no straight strip reaches the controller's slot from this half connector")
    climb, (z, bends, start) = found
    Ls = [float(v) for v in z[5:9]]
    pe, Fe, samples = _walk3(start, F0, bends, Ls, r)
    arcs = [phi * r / math.cos(beta) for phi, beta in bends]
    _SOLVED[key] = SimpleNamespace(half=half, ctrl=ctrl, F0=F0, p0=start, Fe=Fe, e_top=e_top, bends=bends, Ls=Ls, r=r,
                           s_out=s_out, rise_deg=climb, skews=[b for _, b in bends], samples=samples,
                           shift=float(z[9]) if free_shift else 0.0, arcs=arcs,
                           path_length=STIFF_HALF + sum(Ls) + sum(arcs) + STIFF_CTRL,
                           length=STIFF_HALF + sum(Ls) + sum(arcs) + STIFF_CTRL + SLACK,
                           z_max=float(max(q[2] for smp, _ in samples for q, _ in smp)),
                           left_half=F0[:, 1], left_ctrl=Fe[:, 1], a1=half.axis, a2=ctrl.axis)
    return _SOLVED[key]


_SOLVED = {}


# ---------------------------------------------------------------- the jumper as a solid (case checks)
T_SOLID = 0.3                                                # modelled at the stiffened thickness everywhere


def solid_P(g=None):
    """The left jumper as a cadquery solid, bridge frame P, from the half connector's face down to the
    controller's slot opening (the parts inside the connectors are left out). The strip is ruled: in a bend
    the straight lines across it run along the bend line (the cylinder's axis), so it's lofted through thin
    rectangles along those lines; the flat pieces between them are planar."""
    import cadquery as cq
    g = g or solve()
    W, T = PR.JUMPER_W, T_SOLID

    def section(p, along, nrm, half_len):
        q = [p + a * half_len * along + b * T / 2 * nrm for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        return cq.Wire.makePolygon([cq.Vector(*v) for v in q] + [cq.Vector(*q[0])])
    F0 = g.F0
    secs = [section(g.half.face, F0[:, 1], F0[:, 2], W / 2)]
    for smp, beta in g.samples:
        for q, F in smp:
            e = math.sin(beta) * F[:, 0] + math.cos(beta) * F[:, 1]
            secs.append(section(q, e, F[:, 2], W / 2 / math.cos(beta)))
    Fe = g.Fe
    secs.append(section(g.e_top, Fe[:, 1], Fe[:, 2], W / 2))
    secs.append(section(g.ctrl.top, Fe[:, 1], Fe[:, 2], W / 2))
    return cq.Solid.makeLoft(secs, True)


# ---------------------------------------------------------------- the flat pattern and the flex board
INS_HALF, INS_CTRL = 4.0, 4.1     # flex inside each connector (Molex 200528 / 52610 drawings)
FINGER_L, FINGER_W = 3.5, 0.7     # exposed contacts from each tip (200528: 3.5 +-0.3; 52610: >= 2.7), width
FINGER_PULLBACK = 0.3             # copper starts this far in from the cut edge
TRACE_W = 0.5
EAR = (1.1, 1.5, 2.2, 0.55)       # 200528 retention ears: slope from 1.1, full from 1.5 to 2.2, 0.55 proud of each edge
CHAMFER_CTRL = 0.3                # 52610 end: 2 x C0.3
STIFF_HALF, STIFF_CTRL = INS_HALF + STIFF_OUT, INS_CTRL + STIFF_OUT


def flat_segments(g, side="L"):
    """The flat pattern's centre line as turtle steps from the half end's tip: one straight (the strip is straight
    and the same for both sides)."""
    return [("S", g.length)]


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
    Left jumper: left = the back (slot 1); right jumper (the same part, bent as the mirror image): left = the
    front, so conductor k carries slot k on the left and slot 21 - k on the right."""
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


def build_board(g=None):
    """KiCad board of the jumper (one part for both sides; conductors numbered as on the left jumper): single-sided (F.Cu), fingers as pads, traces as tracks; User.1 = the PI
    stiffener areas (on the back, under the fingers: 0.3 mm total there); F.Mask = the coverlay openings."""
    import pcbnew
    from compose.pcb import kicad as PK
    f = flat(g, "L")
    b = PK.new_board()
    ds = b.GetDesignSettings()
    ds.m_CopperEdgeClearance = PK.MM(FINGER_PULLBACK - 0.05)

    net = PK.Nets(b)
    ox, oy = 50.0, 50.0
    PK.outline(b, f["outline"], ox, oy)
    fp = pcbnew.FOOTPRINT(b)
    fp.SetFPID(pcbnew.LIB_ID("compose", "FlexJumper"))
    fp.SetReference("JMP")
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
                       net=net(f"C{k}"))
    b.Add(fp)
    for k, pts in f["cond"].items():
        s = f["s"]
        sel = [q for q, sv in zip(pts, s) if FINGER_L - 0.3 <= sv <= f["length"] - FINGER_L + 0.3]
        for a, c in zip(sel[:-1], sel[1:]):
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(PK.V(*PK.K((float(a[0]), float(a[1])), ox, oy)))   # pcbnew.FromMM rejects numpy floats
            t.SetEnd(PK.V(*PK.K((float(c[0]), float(c[1])), ox, oy)))
            t.SetWidth(PK.MM(TRACE_W)); t.SetLayer(pcbnew.F_Cu); t.SetNet(net(f"C{k}"))
            b.Add(t)
    for poly in f["cover_open"]:
        PK.add_poly(b, poly.intersection(f["outline"].buffer(0.05)), pcbnew.F_Mask, ox, oy)
    for poly in f["stiff"]:
        PK.add_poly(b, poly, pcbnew.User_1, ox, oy)
    return b, f


def plot_flat(path, g=None):
    """Drawing of the flat pattern (conductor side up), as cut, with fingers, stiffeners and slot numbers."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MP
    g = g or solve()
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    f = flat(g, "L")
    ax.add_patch(MP(list(f["outline"].exterior.coords), fc="#e9b44c", ec="#7a5200", lw=1.0, alpha=0.55))
    for poly in f["stiff"]:
        ax.add_patch(MP(list(poly.exterior.coords), fc="none", ec="#555", lw=0.8, ls="--", hatch="///"))
    for k, pts in f["cond"].items():
        sel = [q for q, sv in zip(pts, f["s"]) if FINGER_L - 0.3 <= sv <= f["length"] - FINGER_L + 0.3]
        xs, ys = zip(*[(q[0], q[1]) for q in sel])
        ax.plot(xs, ys, color="#b5651d", lw=1.4, solid_capstyle="butt")
    for k, (a, b) in f["fingers"].items():
        for poly in (a, b):
            ax.add_patch(MP(list(poly.exterior.coords), fc="#d4af37", ec="#8a6d00", lw=0.5))
    for k, txt in ((1, "slot 1 on the left jumper, 20 on the right"), (20, "slot 20 on the left jumper, 1 on the right")):
        ax.annotate(txt, (f["length"] / 2, (PR.JUMPER_W / 2 + 0.5) * (1 if k == 1 else -1)), ha="center",
                    va="bottom" if k == 1 else "top", fontsize=7)
    W = PR.JUMPER_W
    ax.annotate("half end\n(Molex 200528)", (FINGER_L / 2, -W / 2 - 1.2), ha="center", va="top", fontsize=8)
    ax.annotate("controller end\n(Molex 52610)", (f["length"] - FINGER_L / 2, -W / 2 - 1.2), ha="center", va="top", fontsize=8)
    bb = f["outline"].bounds
    ax.set_xlim(bb[0] - 3, bb[2] + 3); ax.set_ylim(bb[1] - 5, bb[3] + 2.5)
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(f"jumper_rev2: {f['length']:.1f} x {W:.0f} mm, flat, conductor side up (one part, both sides)", fontsize=9)
    sk = ", ".join(f"{abs(math.degrees(b)):.1f}" for b in g.skews)
    fig.text(0.5, 0.04, "hatched: polyimide stiffener on the back (0.3 mm total at the fingers)\n"
             f"bent: climb {g.rise_deg:.0f} deg, three bends r {g.r:.0f} mm with their bend lines {sk} deg off square",
             ha="center", fontsize=8)
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


EXPORT = dict(layers="F.Cu,B.Cu,F.Mask,B.Mask,Edge.Cuts,User.1", drill=False,
              rename={"-User_1.gbr": "-Stiffener_PI_bottom.gbr"})


def describe(g):
    sk = " / ".join(f"{math.degrees(b):+.1f}" for b in g.skews)
    bd = " / ".join(f"{math.degrees(p):.0f}" for p, _ in g.bends)
    return (f"climb {g.rise_deg:.0f} deg; bends {bd} deg (r {g.r:.0f} mm), bend lines {sk} deg off square; "
            f"straights {' / '.join(f'{v:.2f}' for v in g.Ls)} mm; {g.length:.1f} mm long ({g.path_length:.1f} + "
            f"{SLACK} slack); top at z {g.z_max:.2f}")


def main(out=None):
    import os
    import sys
    import pcbnew
    from compose.pcb import kicad as PK
    out = out or (sys.argv[1] if len(sys.argv) > 1 else "out_r2t")
    PK.PCB_OUT = os.path.join(out, "pcb")
    os.makedirs(PK.PCB_OUT, exist_ok=True)
    g = solve()
    print("jumper path: " + describe(g))
    name = "jumper_rev2"
    b, f = build_board(g)
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
    # conductors on one side; ordered as JLCPCB's 2-layer flex (much cheaper than 1-layer there): the back copper
    # is empty and its coverlay unbroken. Front copper, both coverlays (mask: the front one open over the finger
    # fields), outline and the PI stiffener areas (User.1)
    z = PK.export(path, name, **EXPORT)
    bb = f["outline"].bounds
    print(f"{name}: {f['length']:.1f} mm long, outline {bb[2] - bb[0]:.1f} x {bb[3] - bb[1]:.1f} mm | "
          f"DRC {err} errors, {warn} warnings, {unc} unconnected (+{bridges} finger-field mask bridges, by design) | "
          f"{os.path.basename(z)} (order 2 per keyboard: one part for both sides)")
    png = os.path.join(out, "png")
    os.makedirs(png, exist_ok=True)
    plot_flat(os.path.join(png, "jumper_rev2_flat.png"), g)
    print(f"flat pattern: {os.path.join(png, 'jumper_rev2_flat.png')}")


if __name__ == "__main__":
    main()
