"""
Printed carrier for the PIM447, for both footprints of the pointer mount standard (compose/pointer/std.py). Footprint
frame, z up from the plate's top face. It prints flat on its base, bosses up: the insert holes open upward, nothing
overhangs.

slot  the board turned 90 deg (header tab toward the footprint's +x) and moved 3 mm toward -x, so the 22 mm board
      fills the 22.5 mm window. A 1.5 mm base on the plate keeps the switch hole open, screws to the two slot inserts
      beside the tab (the other two sit under the -x bosses, unused), and has a channel from the pads to the switch
      hole for the cable.
bay30 the board turned the same way and centred: the ball sits over the bay's centre. A 2 mm base on the four posts,
      screwed (M3) to all four (the heads clear the board's bosses by 1.5 mm), with the same channel from the pads:
      there the cable drops into the pocket.

Four bosses take the board's M2 screws in M2 heat-set inserts; the board's underside sits BOARD_Z above the plate
top, so the ball top is 3.5 + 1.6 + 7.9 = 13.0 above it.
"""
from shapely.geometry import box, Point
from shapely.ops import unary_union
from compose import params as PR
from compose.geom import poly_prism, cyl, union
from compose.pointer import std as S
from compose.pointer.device import pose_fn
from pointers.pim447.module import DEVICE as D

POSE = {"slot": (90.0, -3.0, 0.0), "bay30": (90.0, 0.0, 0.0)}    # device frame -> footprint frame (turn, then shift)
USES = {"slot": (2, 3), "bay30": (0, 1, 2, 3)}                   # which of std.points(fp) it screws to
BASE_T = {"slot": 1.5, "bay30": 2.0}                             # base thickness above the seat
BOARD_Z = {"slot": 3.5, "bay30": 3.5}                            # the board's underside above the plate top
BOSS_R = 2.5
EDGE = 0.25                                                  # the base stays this far inside the window


def holes(fp):
    f = pose_fn(POSE[fp])
    return [f(*h) for h in D.holes]


def pads(fp):
    f = pose_fn(POSE[fp])
    return [f(x, y) for _, x, y in D.pads]


def _cuts(fp):
    """What the base leaves open: the switch hole (slot) and the cable's way."""
    xs, ys = [x for x, _ in pads(fp)], [y for _, y in pads(fp)]
    x0, y0, x1, y1 = S.window(fp)
    channel = box(min(xs) - 2.0, min(ys) - 1.5, x1 + 1.0, max(ys) + 1.5)    # under the pads, out past the +x edge
    if S.kind(fp) == "slot":                                                 # and on to the switch hole, kept open
        h = PR.SWITCH_HOLE / 2
        return unary_union([box(-h, -h, h, h), channel, box(h - 1.0, min(ys) - 1.5, x1, max(ys) + 1.5)])
    return channel


def outline(fp):
    """The carrier's top view (footprint frame): base and bosses."""
    x0, y0, x1, y1 = S.window(fp)
    base = box(x0 + EDGE, y0 + EDGE, x1 - EDGE, y1 - EDGE).difference(_cuts(fp))
    return unary_union([base] + [Point(p).buffer(BOSS_R) for p in holes(fp)])


def solid(fp):
    """The carrier (footprint frame, z from the plate top)."""
    z0 = S.seat_z(fp)
    z1 = z0 + BASE_T[fp]
    zb = BOARD_Z[fp]
    x0, y0, x1, y1 = S.window(fp)
    base = poly_prism(box(x0 + EDGE, y0 + EDGE, x1 - EDGE, y1 - EDGE).difference(_cuts(fp)), z0, z1)
    bosses = union([cyl(x, y, BOSS_R, z1 - 0.1, zb) for x, y in holes(fp)])
    c = union([base, bosses])
    pts = S.points(fp)
    c = c.cut(union([cyl(*pts[i], S.screw_clear(fp) / 2, z0 - 1.0, z1 + 1.0) for i in USES[fp]]))   # footprint screws
    depth = min(zb - z0, PR.M2_PLATE_INSERT_L + 1.0)
    c = c.cut(union([cyl(x, y, PR.M2_INSERT_D / 2, zb - depth, zb + 1.0) for x, y in holes(fp)]))  # board's inserts
    return c.clean()
