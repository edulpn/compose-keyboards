"""
Printed carrier for the PIM447, for both footprints of the pointer mount standard (compose/pointer/std.py). Footprint
frame, z up from the plate's top face. It prints flat on its base, bosses up: the insert holes open upward, nothing
overhangs.

slot  the board turned 90 deg (header tab toward the footprint's +x) and moved 3 mm toward -x, so the 22 mm board
      fills the 22.5 mm window. A 1.5 mm base on the plate keeps the switch hole open, screws to the two slot inserts
      beside the tab (the other two sit under the -x bosses, unused), and has a channel from the pads to the switch
      hole for the cable.
bay30 the board turned the other way (header tab toward the footprint's -x, the keys' side: the tab is the high end
      of the tilted board and its pads sit next to the wall hole) and centred: the ball sits over the bay's centre. A
      2 mm base on the four posts, screwed (M3) to all four (the heads clear the board's bosses by 1.5 mm), with a
      channel from the pads out past the -x edge: there the cable drops into the pocket.

Four bosses take the board's M2 screws in M2 heat-set inserts; the board's underside sits BOARD_Z above the plate
top, so the ball top is 3.5 + 1.6 + 7.9 = 13.0 above it.

Tilt (TILT): the bay30 board is turned 15 deg about the footprint's y axis through the ball so its normal leans
outward, toward +x and away from the keys (so the -x end, with the header tab, is the high one): the thumb meets the
ball with the pad of the thumb, not the side. The base stays flat on the
posts; the bosses end on the tilted underside (a wedge), their insert holes follow its normal. The ball top is then
3.5 + 1.6 + 7.9 cos 15 = 12.7 above the plate top. The slot isn't tilted: its base is 1.5 mm on the plate and the
board's low side would meet it. C58_POINTER_TILT=<deg> overrides the angle (0 = flat, as before).
"""
import math
import sys
import cadquery as cq
from shapely.geometry import box, Point
from shapely.ops import unary_union
from compose import params as PR
from compose.geom import poly_prism, cyl, union, big_box
from compose.pointer import std as S
from compose.pointer import device as D_
from compose.pointer.device import pose_fn
from pointers.pim447.module import DEVICE as D

POSE = {"slot": (90.0, -3.0, 0.0), "bay30": (-90.0, 0.0, 0.0)}    # device frame -> footprint frame (turn, then shift)
USES = {"slot": (2, 3), "bay30": (0, 1, 2, 3)}                   # which of std.points(fp) it screws to
BASE_T = {"slot": 1.5, "bay30": 2.0}                             # base thickness above the seat
BOARD_Z = {"slot": 3.5, "bay30": 3.5}                            # the board's underside above the plate top
TILT = {"slot": (0.0, 0.0), "bay30": (15.0, 0.0)}          # (angle deg, azimuth deg in the footprint frame): see above
BOSS_R = 2.5
EDGE = 0.25                                                  # the base stays this far inside the window


_ME = sys.modules[__name__]


def holes(fp, tilt=None):
    """The board's mounting holes on its underside (footprint frame, top view), tilted."""
    return D_.holes(D, _ME, fp, tilt)


def pads(fp, tilt=None):
    return D_.pads(D, _ME, fp, tilt)


def _cuts(fp, tilt=None):
    """What the base leaves open: the switch hole (slot) and the cable's way."""
    xs, ys = [x for x, _ in pads(fp, tilt)], [y for _, y in pads(fp, tilt)]
    x0, y0, x1, y1 = S.window(fp)
    if sum(xs) / len(xs) >= 0:                                               # under the pads, out past the edge they face
        channel = box(min(xs) - 2.0, min(ys) - 1.5, x1 + 1.0, max(ys) + 1.5)
    else:
        channel = box(x0 - 1.0, min(ys) - 1.5, max(xs) + 2.0, max(ys) + 1.5)
    if S.kind(fp) == "slot":                                                 # and on to the switch hole, kept open
        h = PR.SWITCH_HOLE / 2
        return unary_union([box(-h, -h, h, h), channel, box(h - 1.0, min(ys) - 1.5, x1, max(ys) + 1.5)])
    return channel


def _boss_axes(fp, tilt=None):
    """[(point on the board's underside, unit axis)] of the four bosses: each runs along the board's normal."""
    n = D_.normal(D, _ME, fp, tilt)
    return [((x, y, z), n) for x, y, z in D_.under(D, _ME, fp, tilt, D.holes)]


def _boss_feet(fp, tilt=None):
    """Top view of each boss: its radius where it meets the board, swept along the tilted axis down to the base."""
    z0 = S.seat_z(fp)
    r = BOSS_R / max(math.cos(math.radians(tilt_of(fp, tilt)[0])), 0.5)
    out = []
    for (x, y, z), n in _boss_axes(fp, tilt):
        t = (z - z0) / n[2]
        out.append(unary_union([Point(x, y).buffer(r), Point(x - n[0] * t, y - n[1] * t).buffer(r)]).convex_hull)
    return out


def tilt_of(fp, override=None):
    return D_.tilt_of(_ME, fp, override)


def insert_depth(fp, tilt=None):
    return D_.insert_depth(D, _ME, fp, tilt)


def outline(fp, tilt=None):
    """The carrier's top view (footprint frame): base and bosses."""
    x0, y0, x1, y1 = S.window(fp)
    base = box(x0 + EDGE, y0 + EDGE, x1 - EDGE, y1 - EDGE).difference(_cuts(fp, tilt))
    return unary_union([base] + _boss_feet(fp, tilt))


def solid(fp, tilt=None):
    """The carrier (footprint frame, z from the plate top). Tilted: a wedge, the bosses running along the board's normal
    up to its tilted underside, the insert holes coaxial with them."""
    z0 = S.seat_z(fp)
    z1 = z0 + BASE_T[fp]
    zb = BOARD_Z[fp]
    x0, y0, x1, y1 = S.window(fp)
    base = poly_prism(box(x0 + EDGE, y0 + EDGE, x1 - EDGE, y1 - EDGE).difference(_cuts(fp, tilt)), z0, z1)
    ang, az = tilt_of(fp, tilt)
    if ang == 0.0:
        bosses = union([cyl(x, y, BOSS_R, z1 - 0.1, zb) for x, y in holes(fp, tilt)])
    else:
        px, py, pz = D_.pivot(D, _ME, fp)
        phi = math.radians(az)
        below = big_box(-60, 60, -60, 60, z0 - 80.0, zb).rotate(                  # everything under the tilted underside
            cq.Vector(px, py, pz), cq.Vector(px - math.sin(phi), py + math.cos(phi), pz), ang)
        cyls = []
        for (x, y, z), n in _boss_axes(fp, tilt):
            t = (z - z0) / n[2]                                           # the axis down to the base's underside
            cyls.append(cq.Solid.makeCylinder(BOSS_R, t + 8.0, cq.Vector(x - n[0] * t, y - n[1] * t, z - n[2] * t),
                                              cq.Vector(*n)))
        # trimmed flat at the base's underside (the cylinders' own end faces are tilted) and at the board's underside
        bosses = union(cyls).intersect(below).intersect(big_box(-60, 60, -60, 60, z0, zb + 40.0))
    c = union([base, bosses])
    pts = S.points(fp)
    c = c.cut(union([cyl(*pts[i], S.screw_clear(fp) / 2, z0 - 1.0, z1 + 1.0) for i in USES[fp]]))   # footprint screws
    depth = insert_depth(fp, tilt)
    if ang == 0.0:
        c = c.cut(union([cyl(x, y, PR.M2_INSERT_D / 2, zb - depth, zb + 1.0) for x, y in holes(fp, tilt)]))   # board's inserts
    else:
        cuts = [cq.Solid.makeCylinder(PR.M2_INSERT_D / 2, depth + 1.0, cq.Vector(x - n[0] * depth, y - n[1] * depth,
                                                                              z - n[2] * depth), cq.Vector(*n))
                for (x, y, z), n in _boss_axes(fp, tilt)]
        c = c.cut(union(cuts))
    return c.clean()
