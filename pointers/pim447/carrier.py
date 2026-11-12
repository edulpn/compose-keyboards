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
import cadquery as cq
from shapely.geometry import box, Point
from shapely.ops import unary_union
from compose import params as PR
from compose.geom import poly_prism, cyl, union, big_box
from compose.pointer import std as S
from compose.pointer.device import pose_fn, tilt_map
from pointers.pim447.module import DEVICE as D

POSE = {"slot": (90.0, -3.0, 0.0), "bay30": (-90.0, 0.0, 0.0)}    # device frame -> footprint frame (turn, then shift)
USES = {"slot": (2, 3), "bay30": (0, 1, 2, 3)}                   # which of std.points(fp) it screws to
BASE_T = {"slot": 1.5, "bay30": 2.0}                             # base thickness above the seat
BOARD_Z = {"slot": 3.5, "bay30": 3.5}                            # the board's underside above the plate top
TILT = {"slot": (0.0, 0.0), "bay30": (15.0, 0.0)}          # (angle deg, azimuth deg in the footprint frame): see above
BOSS_R = 2.5
EDGE = 0.25                                                  # the base stays this far inside the window


def tilt_of(fp, override=None):
    """(angle, azimuth) of the board's tilt on footprint fp; `override` (degrees) replaces the angle."""
    ang, az = TILT.get(fp, (0.0, 0.0))
    return (ang if override is None else float(override)), az


def pivot(fp):
    """The turn's centre (footprint frame, z from the plate top): the device frame's origin on the board's top face."""
    x, y = pose_fn(POSE[fp])(0.0, 0.0)
    return (x, y, BOARD_Z[fp] + D.pcb_t)


def tilt_fn(fp, tilt=None):
    ang, az = tilt_of(fp, tilt)
    return tilt_map(pivot(fp), ang, az)


def _under(fp, tilt, pts):
    """Device-frame points (x, y) -> footprint-frame (x, y, z) on the board's underside, tilted."""
    f, T = pose_fn(POSE[fp]), tilt_fn(fp, tilt)
    return [T(*f(*p), BOARD_Z[fp]) for p in pts]


def holes(fp, tilt=None):
    """The board's mounting holes on its underside (footprint frame, top view), tilted."""
    return [(x, y) for x, y, _ in _under(fp, tilt, D.holes)]


def pads(fp, tilt=None):
    return [(x, y) for x, y, _ in _under(fp, tilt, [(x, y) for _, x, y in D.pads])]


def pad_points(fp, tilt=None):
    """The cable pads on the board's underside: (x, y, z) in the footprint frame, tilted."""
    return _under(fp, tilt, [(x, y) for _, x, y in D.pads])


def normal(fp, tilt=None):
    """Unit normal of the board (footprint frame): +z turned by the tilt."""
    T = tilt_fn(fp, tilt)
    px, py, pz = pivot(fp)
    q = T(px, py, pz + 1.0)
    return (q[0] - px, q[1] - py, q[2] - pz)


def board_low(fp, tilt=None):
    """Height (above the plate top) of the board's underside at its lowest corner."""
    return min(z for _, _, z in _under(fp, tilt, [(x, y) for x0, y0, x1, y1 in
                                                  [r for r in D.rects] for x, y in
                                                  ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]))


def insert_depth(fp, tilt=None):
    """Depth of the carrier's insert holes (along the board's normal): the old rule (4.5, or the room up to the seat),
    less what the tilted board's low side leaves above POINTER_INSERT_FLOOR of base."""
    z0, zb = S.seat_z(fp), BOARD_Z[fp]
    if tilt_of(fp, tilt)[0] == 0.0:
        return min(zb - z0, PR.M2_PLATE_INSERT_L + 1.0)
    n = normal(fp, tilt)
    low = min(z for _, _, z in _under(fp, tilt, D.holes))
    return min(zb - z0, PR.M2_PLATE_INSERT_L + 1.0, (low - (z0 + PR.POINTER_INSERT_FLOOR)) / n[2])


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


def outline(fp, tilt=None):
    """The carrier's top view (footprint frame): base and bosses."""
    x0, y0, x1, y1 = S.window(fp)
    base = box(x0 + EDGE, y0 + EDGE, x1 - EDGE, y1 - EDGE).difference(_cuts(fp, tilt))
    return unary_union([base] + [Point(p).buffer(BOSS_R) for p in holes(fp, tilt)])


def solid(fp, tilt=None):
    """The carrier (footprint frame, z from the plate top). Tilted: a wedge, the bosses ending on the board's tilted
    underside, the insert holes along its normal."""
    z0 = S.seat_z(fp)
    z1 = z0 + BASE_T[fp]
    zb = BOARD_Z[fp]
    x0, y0, x1, y1 = S.window(fp)
    base = poly_prism(box(x0 + EDGE, y0 + EDGE, x1 - EDGE, y1 - EDGE).difference(_cuts(fp, tilt)), z0, z1)
    ang, az = tilt_of(fp, tilt)
    hs = holes(fp, tilt)
    if ang == 0.0:
        bosses = union([cyl(x, y, BOSS_R, z1 - 0.1, zb) for x, y in hs])
    else:
        px, py, pz = pivot(fp)
        phi = math.radians(az)
        below = big_box(-60, 60, -60, 60, z0 - 1.0, zb).rotate(                  # everything under the tilted underside
            cq.Vector(px, py, pz), cq.Vector(px - math.sin(phi), py + math.cos(phi), pz), ang)
        bosses = union([cyl(x, y, BOSS_R, z1 - 0.1, zb + 12.0) for x, y in hs]).intersect(below)
    c = union([base, bosses])
    pts = S.points(fp)
    c = c.cut(union([cyl(*pts[i], S.screw_clear(fp) / 2, z0 - 1.0, z1 + 1.0) for i in USES[fp]]))   # footprint screws
    depth = insert_depth(fp, tilt)
    if ang == 0.0:
        c = c.cut(union([cyl(x, y, PR.M2_INSERT_D / 2, zb - depth, zb + 1.0) for x, y in hs]))      # board's inserts
    else:
        n = cq.Vector(*normal(fp, tilt))
        cuts = [cq.Solid.makeCylinder(PR.M2_INSERT_D / 2, depth + 1.0, cq.Vector(x, y, z) - n * depth, n)
                for x, y, z in _under(fp, tilt, D.holes)]
        c = c.cut(union(cuts))
    return c.clean()
