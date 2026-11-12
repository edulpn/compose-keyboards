"""
CadQuery solids for pointer modules, left local frame (z = 0 plate underside, PLATE_T plate top).

Footprint features (compose/pointer/std.py; they depend on the layout, never on a device): the slot's inserts in the
plate and its relief in the frame; the bay's posts, the lid's opening and the cable's hole in the half's wall.
Device parts (they depend on the device): the device as the checks see it, its screws and the carrier's, and the
carrier itself (pointers/<name>/carrier.py), mapped from its footprint frame.
"""
import math
import cadquery as cq
from shapely.geometry import Point
from shapely.ops import unary_union
from compose import params as PR
from compose.geom import poly_prism, cyl, union
from compose.pointer import std as S
from compose.pointer import place as PL
from compose.pointer import device as D


# ---------------------------------------------------------------- footprint features
def slot_seat(fr, fp):
    """The slot's insert holes, from the plate's top face."""
    f = S.get(fp)
    z0 = PR.PLATE_T - f.insert_l
    return union([cyl(x, y, f.insert_d / 2, z0, PR.PLATE_T + 0.5) for x, y in PL.points(fp, fr)])


def slot_relief(fr, fp):
    """Extra key-opening area for the frame over the slot (left local polygon): the window, KEY_OPENING_GAP round."""
    return PL.window(fp, fr).buffer(PR.KEY_OPENING_GAP, join_style="mitre")


def bay_posts(fr, fp):
    """The bay's posts, from far below (the case cuts them at its floor) up to the seat, each with an insert hole from
    the top."""
    f = S.get(fp)
    zt = PR.PLATE_T + f.seat_z
    pts = PL.points(fp, fr)
    p = union([cyl(x, y, f.post_r, -200.0, zt) for x, y in pts])
    return p.cut(union([cyl(x, y, f.insert_d / 2, zt - f.insert_l, zt + 1.0) for x, y in pts]))


def lid_opening(fr, fp):
    """Through the frame's lid over the bay: the window, KEY_OPENING_GAP round, from below the seam to above the top."""
    return poly_prism(PL.lid_opening(fr, fp), PR.SEAM_Z - 1.0, PR.FRAME_TOP_Z + 1.0)


def wall_hole_z():
    """Local z of the cable's centre through the wall: below the case ledge's chamfer where it meets the wall."""
    t = math.tan(math.radians(PR.LEDGE_CHAMFER_DEG))
    z_wall = PR.LEDGE_TOP - PR.LEDGE_T - (PR.LEDGE_W + PR.FLOAT_GAP) * t
    return z_wall - PR.POINTER_CABLE_D / 2 - 1.0


def wall_hole_frame(fr):
    """(point on the wall's inner face, unit normal into the pocket, unit tangent), left local 2D: the spot on the
    half's wall nearest the bay's centre, slid along the wall until it's clear of the frame-screw bosses."""
    import numpy as np
    from shapely.geometry import Point as P_
    from compose.case import gasket as C
    ring_ = C.O_WALL_IN.exterior
    d0 = ring_.project(P_(fr[0], fr[1]))
    keep = PR.FRAME_BOSS_R + PR.BAY_WALL_HOLE / 2 + 1.0
    for k in sorted(range(-60, 61), key=abs):
        d = (d0 + 0.5 * k) % ring_.length
        q = ring_.interpolate(d)
        if all(q.distance(P_(s)) >= keep for s in C.GL.screws_all):
            break
    else:
        raise ValueError(f"no spot on the half's wall within {0.5 * 60:g} mm of the bay's nearest point clears the "
                         f"frame-screw bosses by {keep:.1f} mm: move the bay or the frame screws")
    a, b = ring_.interpolate(d - 0.5), ring_.interpolate(d + 0.5)
    t = np.array([b.x - a.x, b.y - a.y]); t /= np.linalg.norm(t)
    n = np.array([t[1], -t[0]])
    if C.O_WALL_IN.contains(P_(q.x + n[0], q.y + n[1])):
        n = -n
    return (q.x, q.y), (float(n[0]), float(n[1])), (float(t[0]), float(t[1]))


def wall_hole(fr):
    """The cable's hole through the wall between the half and the pocket: a diamond whose faces lean
    LEDGE_CHAMFER_DEG from horizontal (prints without support), BAY_WALL_HOLE wide, along the wall's normal."""
    (x, y), n, t = wall_hole_frame(fr)
    z = wall_hole_z()
    w = PR.BAY_WALL_HOLE / 2
    h = w * math.tan(math.radians(PR.LEDGE_CHAMFER_DEG))
    span = PR.WALL_T + PR.BAY_POCKET_GAP + 4.0
    o = cq.Vector(x - 2.0 * n[0], y - 2.0 * n[1], z)
    pl_ = cq.Plane(origin=o, xDir=cq.Vector(t[0], t[1], 0), normal=cq.Vector(n[0], n[1], 0))
    return cq.Workplane(pl_).polyline([(w, 0), (0, h), (-w, 0), (0, -h)]).close().extrude(span).val()


# ---------------------------------------------------------------- device parts
def module_solid(pl):
    """The board (with its mounting holes), the housing and ball envelope above it, the parts' envelope under it."""
    d = pl.device
    zb = pl.board_bot_z
    zt = zb + d.pcb_t
    holes = unary_union([Point(p).buffer(d.hole_d / 2) for p in pl.holes])
    board = poly_prism(pl.board.difference(holes), zb, zt)
    top = poly_prism(pl.top, zt, zt + d.top_h)
    back = poly_prism(pl.back, zb - d.back_h, zb)
    return union([board, top, back])


def screws_solid(pl):
    """The board's M2 button-head screws (heads on its top face, into the carrier's inserts) and the carrier's
    screws into the footprint (heads on the carrier's base)."""
    fp = pl.footprint
    car = D.carrier(pl.device.name)
    zt = pl.board_bot_z + pl.device.pcb_t
    sol = []
    if pl.dev_screw:
        L = pl.dev_screw[0]
        sol += [cyl(x, y, PR.M2_HEAD_D / 2, zt, zt + PR.M2_HEAD_H) for x, y in pl.holes]
        sol += [cyl(x, y, 1.0, zt - L, zt) for x, y in pl.holes]
    if pl.fp_screw:
        L = pl.fp_screw[0]
        zh = PR.PLATE_T + S.seat_z(fp) + car.BASE_T[fp]
        hd, hh = S.screw_head(fp)
        r = S.get(fp).shank_d / 2
        sol += [cyl(x, y, hd / 2, zh, zh + hh) for x, y in pl.uses]
        sol += [cyl(x, y, r, zh - L, zh) for x, y in pl.uses]
    return union(sol)


def carrier_solid(pl):
    """The device's printed carrier, left local (pointers/<name>/carrier.py solid(), in its footprint frame)."""
    x, y, rot = pl.frame
    c = D.carrier(pl.device.name).solid(pl.footprint)
    return c.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), rot).translate(cq.Vector(x, y, PR.PLATE_T))
