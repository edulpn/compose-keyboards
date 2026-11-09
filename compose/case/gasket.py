"""
Rev 2 printed parts: gasket mount, one-piece tub, controller rev 2 in the middle (C58_REV=2).

  plate2_local()   left plate, local frame (right = mirror): core with the switches + a thin perimeter
                   flange, notched around the frame screws
  frame2_local()   left frame, local frame: bevelled ring over the flange, skirt down to the case wall,
                   trim lip over the case's reveal, M3 inserts; stops at the bridge (the cover takes over)
  case2_world()    the tub: walls + pad ledge per half, open middle, bridge back/front walls, inner pad seats,
                   front cover posts, controller bosses, USB opening, feet
  cover2_P()       middle cover (P frame), flush with the frames, overlapping the plates' inner bands
                   without touching them; hooked under the back wall, two screws at the front

Gasket stack (local z): pad seat LEDGE_TOP | pad | flange FLANGE_Z0..+FLANGE_T | pad | frame FRAME_LIP_Z.
"""
import math
import numpy as np
import cadquery as cq
from shapely.geometry import Point, LineString, Polygon, box as sbox
from shapely.ops import unary_union
from shapely.geometry.polygon import orient as _orient
from compose import params as PR
from compose import geom as G
from compose.geom import prism, poly_prism, cyl, union, ring, loft, big_box

L = G.LAYOUT
TH = PR.PLATE_T
DEEP = -200.0
W = PR.WALL_T
O_PLATE = G.OUTLINE                                       # plate outline (flange edge)
O_WALL_IN = G.OUTLINE.buffer(PR.FLOAT_GAP, join_style="round")
_R_OUT = PR.BEZEL_BEVEL + 0.5                              # outer corners rounder than the bevel's inset, so the
O_OUTER = (G.OUTLINE.buffer(PR.FLOAT_GAP + W, join_style="round")   # bevel's top ring never turns inside out
           .buffer(-_R_OUT, join_style="round").buffer(_R_OUT, join_style="round").simplify(0.01))
O_OUTER = _orient(O_OUTER, 1.0)                                # CCW: miter_offset insets a CCW ring
O_CORE = G.OUTLINE.buffer(-PR.FLANGE_W, join_style="round")


# ================================================================ layout of screws and pads
def _perimeter_path():
    """The plate outline as an open path that skips the straight inner edge along the bridge (local)."""
    yb, yf = G.bridge_stretch_local()
    ax = G.ANCHOR[0]
    pts = list(O_PLATE.exterior.coords)[:-1]
    on_bridge = [abs(x - ax) < 0.6 and yf - 0.5 <= y <= yb + 0.5 for x, y in pts]
    n = len(pts)
    # start right after the bridge stretch, walk the ring once
    start = next(i for i in range(n) if on_bridge[i - 1] and not on_bridge[i])
    path = []
    for k in range(n):
        i = (start + k) % n
        if on_bridge[i]:
            break
        path.append(pts[i])
    return LineString(path)


def _inward(path, d):
    """Unit inward normal of the outline at distance d along path."""
    a, b = path.interpolate(max(d - 0.5, 0)), path.interpolate(min(d + 0.5, path.length))
    t = np.array([b.x - a.x, b.y - a.y])
    t /= np.linalg.norm(t)
    n = np.array([-t[1], t[0]])
    p = np.array([path.interpolate(d).x, path.interpolate(d).y])
    return n if O_PLATE.contains(Point(*(p + n * 1.0))) else -n, t, p


def _local_y_at_P(xl, y_P, zl):
    """Local y whose point (xl, y, zl) lands at P-frame y = y_P."""
    import scipy.optimize as so
    return so.brentq(lambda yl: G.apply(G.M_LP, (xl, yl, zl))[1] - y_P, -300, 300)


def gasket_layout():
    """Frame screws (local xy), outer pad pairs (centre, tangent, inward), inner bottom pads (centre)."""
    from types import SimpleNamespace
    s = SimpleNamespace()
    path = _perimeter_path()
    Ln = path.length
    end = 14.0                                     # keep screws/pads off the path ends next to the bridge
    s.screws, s.tabs = [], []
    for i in range(PR.FRAME_SCREWS):
        d = end + (Ln - 2 * end) * (i + 0.5) / PR.FRAME_SCREWS
        n, t, p = _inward(path, d)
        s.screws.append(tuple(p + n * PR.FRAME_SCREW_IN))
    band = O_PLATE.buffer(-0.25, join_style="round").difference(O_PLATE.buffer(-(PR.PCB_INSET - 0.25), join_style="round"))
    cand = []                                   # every position along the edge where a pad fits in the band
    for d in np.arange(0.5, Ln - 0.5, 0.5):
        n, t, p = _inward(path, d)
        c = np.array(p) + n * (0.3 + PR.GK_PAD_W / 2)
        if min(Point(*c).distance(Point(*sc)) for sc in s.screws) < PR.NOTCH_R + PR.GK_PAD_L / 2 + 1.0:
            continue
        if band.contains(pad_poly(c, t, n)):
            cand.append((d, tuple(c), tuple(t), tuple(n)))
    chosen = []
    for i in range(PR.GK_TABS):                 # evenly spaced targets, nearest free candidate to each
        d0 = end * 0.5 + (Ln - end) * (i + 0.5) / PR.GK_TABS
        ok = [q for q in cand if abs(q[0] - d0) <= Ln / PR.GK_TABS / 2
              and all(abs(q[0] - o[0]) >= PR.GK_PAD_L + 2.0 for o in chosen)]
        if ok:
            chosen.append(min(ok, key=lambda q: abs(q[0] - d0)))
    s.tabs = [q[1:] for q in sorted(chosen)]
    s.tab_d = [q[0] for q in sorted(chosen)]
    # inner edge (along the bridge): no screws; a pad pair at each end of the stretch, on seats that stand
    # straight up from the floor (P-vertical, so they don't lean into the controller), the frame's inner
    # rail holds the upper pad. Pads are given by local (x, y) centre with the long side along local y.
    ax = G.ANCHOR[0]
    s.inner = []
    for y0, y1 in PR.INNER_SEATS_P:
        yc = 0.5 * (y0 + y1)
        yl = _local_y_at_P(ax, yc, PR.LEDGE_TOP)
        s.inner.append((ax - 0.3 - PR.GK_PAD_W / 2, yl))
    s.screws_all = list(s.screws)
    s.path = path
    return s



def pad_poly(c, t, n, L_=None, W_=None):
    L_ = L_ or PR.GK_PAD_L
    W_ = W_ or PR.GK_PAD_W
    c, t, n = np.array(c), np.array(t), np.array(n)
    pts = [c + t * a * L_ / 2 + n * b * W_ / 2 for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return Polygon(pts)


def inner_seat_local(c):
    """Seat footprint (local) under an inner pad: from the plate edge INNER_SEAT_IN into the plate."""
    ax = G.ANCHOR[0]
    h = PR.GK_PAD_L / 2 + 0.4
    return Polygon([(ax, c[1] - h), (ax - PR.INNER_SEAT_IN, c[1] - h), (ax - PR.INNER_SEAT_IN, c[1] + h), (ax, c[1] + h)])


def inner_seat_P(c):
    """Left inner seat in the P frame: local cap (LEDGE_T thick, top at LEDGE_TOP) + a P-vertical column
    under it whose footprint is the cap's plan view, topped just under the cap's lowest top point."""
    fp = inner_seat_local(c)
    cap = _run_LP(poly_prism(fp, PR.LEDGE_TOP - PR.LEDGE_T, PR.LEDGE_TOP))
    pts_b = [G.apply(G.M_LP, (x, y, PR.LEDGE_TOP - PR.LEDGE_T)) for x, y in fp.exterior.coords[:-1]]
    pts_t = [G.apply(G.M_LP, (x, y, PR.LEDGE_TOP)) for x, y in fp.exterior.coords[:-1]]
    hull = unary_union([Point(p[0], p[1]) for p in pts_b + pts_t]).convex_hull
    inner = Polygon([(p[0], p[1]) for p in pts_b]).intersection(Polygon([(p[0], p[1]) for p in pts_t]))
    ztop = min(p[2] for p in pts_t) - 0.3
    col = poly_prism(inner.buffer(-0.35, join_style="mitre"), DEEP, ztop)   # a little inside the cap: clear of the half board
    return cap.fuse(col).clean()


def _run_LP(shape):
    return G._run(shape, G.OPS_LP)


def inner_pad_poly(c):
    return Polygon([(c[0] - PR.GK_PAD_W / 2, c[1] - PR.GK_PAD_L / 2), (c[0] + PR.GK_PAD_W / 2, c[1] - PR.GK_PAD_L / 2),
                    (c[0] + PR.GK_PAD_W / 2, c[1] + PR.GK_PAD_L / 2), (c[0] - PR.GK_PAD_W / 2, c[1] + PR.GK_PAD_L / 2)])


GL = gasket_layout()


# ================================================================ plate
def plate2_local():
    from compose.case import sandwich as PT
    core = prism(ring(O_CORE), 0.0, TH)
    flange = prism(ring(O_PLATE), PR.FLANGE_Z0, PR.FLANGE_Z0 + PR.FLANGE_T)
    plate = core.fuse(flange).clean()
    cut = PT._switch_cutter()
    cutters = [cut.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), k.rot).translate(cq.Vector(k.x, k.y, 0))
               for k in L.keys]
    plate = plate.cut(cq.Compound.makeCompound(cutters))
    # the half board (compose/pcb/rev2_half.py) hangs from the plate on four M2 screws into inserts, and the
    # diodes' top-side solder joints sit in shallow pockets (one plan for all four board variants)
    from compose.pcb import rev2_half as H2
    hb = H2.plan()
    plate = plate.cut(union([cyl(x, y, PR.M2_INSERT_D / 2, -0.01, PR.M2_PLATE_INSERT_L) for x, y in hb.posts]))
    plate = plate.cut(poly_prism(hb.pockets, -1.0, PR.JOINT_POCKET_D))
    plate = plate.cut(union([cyl(x, y, PR.NOTCH_R, -1.0, TH + 1.0) for x, y in GL.screws_all]))
    return plate.clean()


# ================================================================ frame
def _key_opening():
    from compose.case import sandwich as PT
    return PT.key_opening()


def middle_side_local(gap):
    """Local-frame block on the middle side of the inner edge along the bridge stretch, from `gap` past
    the interface plane (the frame's inner rail ends there; the cover sits beyond)."""
    return G.bridge_zone_local(reach=-gap, z0=-60.0, z1=60.0)


def frame2_local():
    """Full ring around the key field (rev 1's bevelled look): skirt + trim lip down to the case wall on the
    outer edges; along the bridge an inner rail that ends at the interface plane (the cover continues it)."""
    outer = ring(O_OUTER)
    bevel = loft(outer, TH, G.miter_offset(outer, PR.BEZEL_BEVEL), PR.FRAME_TOP_Z)     # rev 1's bevel, from the plate top
    env = bevel.fuse(prism(outer, PR.SEAM_Z - PR.TRIM_LIP_H - 1.0, TH))                # the frame's outside, nothing pokes out
    body = bevel
    # skirt and trim lip from the exact outer ring the bevel starts from (no simplification), so their outer
    # faces are the bevel's own: no zero-thickness slivers between them
    skirt = prism(outer, PR.SEAM_Z, TH).cut(prism(ring(O_WALL_IN), PR.SEAM_Z - 1, TH + 1))
    lip = prism(outer, PR.SEAM_Z - PR.TRIM_LIP_H, PR.SEAM_Z + 0.3).cut(
        prism(ring(O_OUTER.buffer(-PR.TRIM_LIP_T, join_style="round")), PR.SEAM_Z - PR.TRIM_LIP_H - 1, PR.SEAM_Z + 1))
    body = union([body, skirt, lip])
    body = body.cut(prism(ring(O_WALL_IN), TH - 1.0, PR.FRAME_LIP_Z))                    # clear of the plate + top pads
    bosses = union([cyl(x, y, PR.FRAME_BOSS_R, PR.SEAM_Z, PR.FRAME_LIP_Z + 0.5) for x, y in GL.screws_all])
    body = body.fuse(bosses.intersect(env))
    body = body.cut(poly_prism(_key_opening(), PR.FRAME_LIP_Z - 1, PR.FRAME_TOP_Z + 1))
    body = body.cut(union([cyl(x, y, PR.M3_INSERT_D / 2, PR.SEAM_Z - 0.5, PR.SEAM_Z + PR.M3_INSERT_L) for x, y in GL.screws_all]))
    # the inner rail ends FLOAT_GAP short of the interface plane, square at the bridge's back and front faces:
    # one cut with the bridge's own block in the P frame (a second, local-frame cut along the same plane left
    # micro-slivers in the mesh)
    blk = _bridge_block_P(PR.FIT_GAP, -PR.BRIDGE_LEN - PR.FIT_GAP, G.Z0 - 40, G.Z0 + 40, -PR.FLOAT_GAP)
    body = body.cut(G.P2L(blk))
    return body.clean()


# ================================================================ controller placement (P frame)
def _ctrl():
    from types import SimpleNamespace
    from compose.controller import rev2_std as CS
    c = SimpleNamespace()
    c.cover_under = G.Z0 + PR.FRAME_LIP_Z                     # cover underside (flat, P frame)
    c.cover_top = G.Z0 + PR.FRAME_TOP_Z
    c.board_top = c.cover_under - CS.COVER_BOSS_H - CS.STANDOFF_L     # set by the standoffs
    c.pico_top = c.board_top + CS.STACK_ABOVE_BOARD
    c.pico_gap = c.cover_under - c.pico_top
    c.board_bot = c.board_top - CS.PCB_T
    c.pico_bot = c.pico_top - PR.PICO_T
    c.y_pc = -PR.BRIDGE_WALL_T - PR.CTRL_BACK_CLEAR + CS.Y_BACK
    c.to_P = lambda x, y: (x, c.y_pc - y)
    c.mounts = [c.to_P(x, y) for x, y in CS.STANDOFF_HOLES]
    from shapely.affinity import scale as _sc, translate as _tr
    c.outline_P = _tr(_sc(CS.outline(), 1.0, -1.0, origin=(0, 0)), 0.0, c.y_pc)
    return c


CT = _ctrl()


def cover_screws_P():
    """The cover screws onto the two front standoffs."""
    return list(CT.mounts)


# ================================================================ case
def _bridge_block_P(y_back, y_front, z0, z1, reach):
    w = 300.0
    blk = prism([(-w, y_back), (w, y_back), (w, y_front), (-w, y_front)], z0, z1)
    return blk.cut(G.half_space_P(-1, -reach)).cut(G.half_space_P(1, -reach))


def _both(local_solid):
    w = G.L2W(local_solid)
    return w, w.mirror("YZ")


def _dbg(lab, b):
    import os
    if os.environ.get('C2DBG'):
        print(lab, round(b.Volume()), len(b.Solids()), flush=True)


def case2_world():
    from compose.controller import rev2_std as CS
    yb, yf = 0.0, -PR.BRIDGE_LEN
    BW = PR.BRIDGE_WALL_T
    rv_w, rv_h = PR.TRIM_LIP_T + PR.REVEAL_SIDE_GAP, PR.TRIM_LIP_H + PR.REVEAL_SHADOW
    # ---- half tubs (local): wall up to the seam, reveal rebate on the outside, open inside
    tub = prism(ring(O_OUTER), DEEP, PR.SEAM_Z)
    rebate = poly_prism(O_OUTER.buffer(1.0).difference(O_OUTER.buffer(-rv_w, join_style="round")), PR.SEAM_Z - rv_h, PR.SEAM_Z + 1)
    # where the rebate runs into the bridge walls (the only thing above the seam), the wall would hang over it:
    # the cut carries on above as a 60-degree chamfer back out to the outline, so the wall slopes over the notch
    # (the sloped face runs on past the cutter's outer edge, so it ends on a clean crossing, not a knife edge)
    r0 = O_OUTER.buffer(-rv_w, join_style="round").simplify(0.05, preserve_topology=True)
    r1 = O_OUTER.buffer(1.0, join_style="round")
    over = rv_w + 3.0
    r2 = O_OUTER.buffer(-rv_w + over, join_style="round").simplify(0.05, preserve_topology=True)
    zc0 = PR.SEAM_Z + 1
    zc2 = zc0 + over * math.tan(math.radians(PR.LEDGE_CHAMFER_DEG))
    wire = lambda poly, z: cq.Wire.makePolygon([cq.Vector(x, y, z) for x, y in poly.exterior.coords], close=True)
    rebate = rebate.fuse(poly_prism(r1, zc0, zc2).cut(cq.Solid.makeLoft([wire(r0, zc0), wire(r2, zc2)], True)))
    cav = prism(ring(O_WALL_IN), DEEP, PR.SEAM_Z + 1)
    tubL, tubR = _both(tub)
    cavL, cavR = _both(cav)
    # ---- middle (P): back/front walls up to the cover underside, open between the plates' inner edges
    bridge = G.P2W(_bridge_block_P(yb, yf, DEEP, CT.cover_under, -PR.FLOAT_GAP))
    interior = G.P2W(_bridge_block_P(yb - BW, yf + BW, DEEP, CT.cover_under + 1, W + PR.FLOAT_GAP + 1.0))
    top = big_box(-500, 500, -500, 500, 0, 500)
    body = union([tubL, tubR, bridge]).intersect(top)
    hollow = union([cavL, cavR, interior]).intersect(big_box(-500, 500, -500, 500, PR.FLOOR_T, 500))
    body = body.cut(hollow)
    # ---- pad ledge (local) round each half, except along the bridge (the middle is open there)
    # the tub prints floor down: the ledge is a shelf off the wall, so under its flat top a smooth chamfer runs
    # back to the wall at LEDGE_CHAMFER_DEG instead of hanging over air (each print layer then moves a fraction
    # of a line width; a staircase of 0.6 mm steps would leave an unsupported perimeter on every step)
    wall_b = O_WALL_IN.buffer(0.5, join_style="round")                  # 0.5 into the wall: a real overlap to fuse
    z_b = PR.LEDGE_TOP - PR.LEDGE_T                                       # underside of the flat part
    grow = PR.LEDGE_W + PR.FLOAT_GAP + 1.5                                 # the chamfer reaches past wall_b
    dz = grow * math.tan(math.radians(PR.LEDGE_CHAMFER_DEG))
    inner = O_PLATE.buffer(-PR.LEDGE_W, join_style="round").simplify(0.05, preserve_topology=True)
    outer = inner.buffer(grow, join_style="round").simplify(0.05, preserve_topology=True)
    under = cq.Solid.makeLoft([cq.Wire.makePolygon([cq.Vector(x, y, z_b) for x, y in inner.exterior.coords], close=True),
                               cq.Wire.makePolygon([cq.Vector(x, y, z_b - dz) for x, y in outer.exterior.coords], close=True)],
                              True)                                       # the space under the chamfer
    ledge = poly_prism(wall_b.difference(inner), z_b - dz, PR.LEDGE_TOP).cut(under)
    ledge = ledge.cut(middle_side_local(-PR.LEDGE_W - 1.0))
    # frame-screw bosses (local): from the floor to the seam, counterbored from below
    fb = union([cyl(x, y, PR.FRAME_BOSS_R, DEEP, PR.SEAM_Z) for x, y in GL.screws])
    # inner seats: a local cap under each inner pad, on a P-vertical column from the floor
    pil = [inner_seat_P(c_) for c_ in GL.inner]
    loc = union([ledge, fb])
    locL, locR = _both(loc)
    seats = union(pil)
    seatsW = G.P2W(seats)
    locL = locL.fuse(seatsW)
    locR = locR.fuse(seatsW.mirror("YZ"))
    # ---- middle (P): posts under the standoffs (from the floor to the board's underside)
    posts = union([cyl(x, y, CS.POST_R, DEEP, CT.board_bot) for x, y in CT.mounts])
    body = body.fuse(union([locL, locR, G.P2W(posts)]).intersect(top)).clean()
    rbL, rbR = _both(rebate)               # reveal rebate last, so the frame-screw bosses don't fill it
    body = body.cut(rbL).cut(rbR)
    _dbg('fuse', body)
    # ---- holes
    cb = [cyl(x, y, PR.M3_CBORE_D / 2, DEEP - 10, PR.SEAM_Z - PR.SHELF_T) for x, y in GL.screws]
    cb += [cyl(x, y, PR.M3_CLEAR / 2, PR.SEAM_Z - PR.SHELF_T - 1, PR.SEAM_Z + 1) for x, y in GL.screws]
    cbL, cbR = _both(union(cb))
    body = body.cut(cbL).cut(cbR)
    _dbg('cb', body)
    hp = [cyl(x, y, PR.M3_INSERT_D / 2, CT.board_bot - PR.M3_INSERT_L, CT.board_bot + 1) for x, y in CT.mounts]
    usb_z = CT.pico_bot - PR.USB_NOTCH_BELOW_PCB
    hp.append(big_box(-PR.USB_NOTCH_W / 2, PR.USB_NOTCH_W / 2, -BW - 3.0, 3.0, usb_z, CT.cover_top + 10))
    # the controller's envelope stays clear (underside parts, everything above), except its posts; the
    # back wall is left alone (only the slots above go into it)
    env = CT.outline_P.buffer(0.45, join_style="mitre").intersection(sbox(-100, -200, 100, -BW))
    keep = prism(list(env.exterior.coords)[:-1], CT.board_bot - CS.BOTTOM_PARTS_H - 0.6, CT.cover_under + 1)
    keep = keep.cut(posts)
    body = body.cut(G.P2W(union(hp + [keep]))).clean()
    _dbg('hp', body)
    # ---- feet
    feet = []
    for x, y in L.feet:
        p = G.apply(G.M_LW, (x, y, 0))
        feet += [cyl(p[0], p[1], PR.FOOT_D / 2, -1, PR.FOOT_DEPTH), cyl(-p[0], p[1], PR.FOOT_D / 2, -1, PR.FOOT_DEPTH)]
    for sx in (-1, 1):
        y = yf + 8.0
        p = G.apply(G.M_PW, (sx * (abs(G.interface_x(y, G.Z0)) - 8.0), y, 0))
        feet.append(cyl(p[0], p[1], PR.FOOT_D / 2, -1, PR.FOOT_DEPTH))
    body = body.cut(union(feet)).clean()
    _dbg('feet', body)
    sol = body.Solids()
    if len(sol) > 1:
        big = max(sol, key=lambda s_: s_.Volume())
        assert all(s_.Volume() < 2.0 for s_ in sol if s_ is not big), "case splits into real pieces"
        body = big
    return body


# ================================================================ cover
def cover2_P():
    """Flat slab between the frames' inner rails, flush with their tops, bevelled back and front like rev 1.
    Window over the Pico (open to the back for the USB plug); drops straight onto the four controller
    standoffs, four M3 screws."""
    from compose.case import sandwich as PT
    z0 = CT.cover_under
    gap = PR.FLOAT_GAP + PR.FIT_GAP
    yb, yf = 0.0, -PR.BRIDGE_LEN
    w = 200.0
    bot = [(-w, yb), (w, yb), (w, yf), (-w, yf)]
    bev = PR.BEZEL_BEVEL * (CT.cover_top - z0) / PR.BEZEL_H                # the frames' bevel angle (56 deg)
    tp = [(-w, yb - bev), (w, yb - bev), (w, yf + bev), (-w, yf + bev)]
    body = loft(bot, z0, tp, CT.cover_top)
    body = body.cut(G.half_space_P(-1, gap)).cut(G.half_space_P(1, gap))
    hw = PR.PICO_W / 2 - PR.WINDOW_EDGE_OVER_PCB
    body = body.cut(big_box(-hw, hw, CT.y_pc - PR.PICO_L / 2 - PR.WINDOW_FRONT_MARGIN, 20.0, z0 - 1, CT.cover_top + 1))
    from compose.controller import rev2_std as CS
    bosses = union([cyl(x, y, CS.COVER_BOSS_R, z0 - CS.COVER_BOSS_H, z0 + 0.01) for x, y in cover_screws_P()])   # sits on the hex top
    body = body.fuse(bosses)
    body = body.cut(union([cyl(x, y, CS.M_CLEAR / 2, z0 - 5, CT.cover_top + 1) for x, y in cover_screws_P()]))
    body = body.cut(union([cyl(x, y, PR.M3_CBORE_D / 2, CT.cover_top - PR.M3_HEAD_H - 0.2, CT.cover_top + 1)
                           for x, y in cover_screws_P()]))
    return body.clean()


def export_print(out):
    """Printable STLs in print orientation: the tub on its floor; plates switch side down (flange flat on the
    bed, clip pockets open upward); frames and cover upside down (their visible tops on the bed)."""
    import os
    d = os.path.join(out, "print")
    os.makedirs(d, exist_ok=True)
    tol = dict(tolerance=0.02, angularTolerance=0.1)
    flip = lambda s: s.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 180)
    def save(shape, name):
        bb = shape.BoundingBox()
        shape = shape.translate(cq.Vector(-bb.center.x, -bb.center.y, -bb.zmin))
        cq.exporters.export(cq.Workplane().add(shape), os.path.join(d, name), **tol)
    save(case2_world(), "rev2_case.stl")
    pl, fr = plate2_local(), frame2_local()
    save(flip(pl), "rev2_plate_left.stl"); save(flip(pl.mirror("YZ")), "rev2_plate_right.stl")   # switch side down
    save(flip(fr), "rev2_frame_left.stl"); save(flip(fr.mirror("YZ")), "rev2_frame_right.stl")
    save(flip(cover2_P()), "rev2_cover.stl")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        export_print(sys.argv[1])
    print("screws", np.round(GL.screws_all, 1).tolist())
    print("tabs", len(GL.tabs), "inner", GL.inner)
