"""
Thumb bay (rev 2): a pocket added to the case beside a half's thumb keys, where a pointer device stands on posts from
the pocket floor (compose/pointer/). Its size is one of the standard's bay footprints (compose/pointer/std.py, e.g.
"bay30"). The layout says where each size goes (Layout.bays: {footprint: (x, y, rot)}, the centre and turn of its
square, left local), and the case grows the bay only when it's on: with a bay device (C58_POINTER=…:bay30), or empty
with C58_THUMB_BAY=bay30 (both lids closed, for a case printed ahead of the device). A layout that declares no
position for that size takes no such bay.

Only the case and the frames change: the frame covers the pocket as a lid (opened over the module on its side);
plates, gaskets, frame screws and half boards are the same as without the bay. Both halves get the pocket, so the
case and frames stay mirror images apart from the module's opening.

For a new layout or a new size, `pointer-checks --suggest-bay` proposes a position (suggest()): the square turns round the thumb
arc from its anchor key (the 1.5u thumb key, else the innermost key of the last row), starting at that key's own angle
and stepping BAY_ANGLE_STEP further round; at each angle it moves out from the key until the pocket clears the half's
own wall. The first angle that leaves BAY_WALL_GAP between the two halves' outer walls and to the bridge wins.
"""
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient
from shapely import affinity as A
from shapely.ops import unary_union
from compose import params as PR
from compose import geom as G
from compose.pointer import std as S
from compose.pointer import OFF

_R_OUT = PR.BEZEL_BEVEL + 0.5          # same rounding as compose/case/gasket.py O_OUTER


def active():
    """The bay footprint the case is built with, or None: a bay device's (C58_POINTER=…:bay30), else C58_THUMB_BAY.
    Raises ValueError when C58_THUMB_BAY names no bay of the standard."""
    parts = os.environ.get("C58_POINTER", "").split(":")
    v = os.environ.get("C58_THUMB_BAY", "")
    if len(parts) == 3 and parts[2] in S.bays():
        if v not in OFF and v != parts[2]:
            raise ValueError(f"C58_POINTER={':'.join(parts)!r} brings its own bay, but C58_THUMB_BAY={v!r} asks for "
                             f"another: unset C58_THUMB_BAY or make them the same")
        return parts[2]
    if v in OFF:
        return None
    if v not in S.bays():
        raise ValueError(f"C58_THUMB_BAY={v!r}: one of the standard's bays: {', '.join(S.bays())}")
    return v


def enabled():
    return active() is not None


def thumb_key():
    """(index, Key) of the layout's 1.5u thumb key (the innermost, if several): where a key-mount module goes. A
    layout without one raises ValueError."""
    keys = G.LAYOUT.keys
    row = max(k.row for k in keys)
    c = [(i, k) for i, k in enumerate(keys) if k.row == row and abs(max(k.w, k.h) - 1.5) < 1e-6]
    if not c:
        raise ValueError(f"layout {G.LAYOUT.name!r} has no 1.5u thumb key: the key mount needs one "
                         f"(the bay mount doesn't)")
    return max(c, key=lambda t: t[1].x)


def arc_anchor():
    """(index, Key) suggest() starts from: the 1.5u thumb key, else the innermost key of the last row."""
    try:
        return thumb_key()
    except ValueError:
        keys = G.LAYOUT.keys
        row = max(k.row for k in keys)
        return max(((i, k) for i, k in enumerate(keys) if k.row == row), key=lambda t: t[1].x)


@lru_cache(maxsize=1)
def plate_outer():
    """The case's outer outline without the bay (compose/case/gasket.py O_OUTER), left local."""
    o = (G.OUTLINE.buffer(PR.FLOAT_GAP + PR.WALL_T, join_style="round")
         .buffer(-_R_OUT, join_style="round").buffer(_R_OUT, join_style="round").simplify(0.01))
    return orient(o, 1.0)


def _outer_with(pocket):
    """The case's outer outline with the pocket's wall added, rounded like O_OUTER, CCW."""
    lobe = pocket.buffer(PR.WALL_T, join_style="round")
    r = PR.BAY_JOIN_R
    o = unary_union([plate_outer(), lobe]).buffer(r, join_style="round").buffer(-r, join_style="round")
    o = o.buffer(-_R_OUT, join_style="round").buffer(_R_OUT, join_style="round").simplify(0.01)
    return orient(o, 1.0)


def _to_P(poly):
    return Polygon([G.apply(G.M_LP, (x, y, 0.0))[:2] for x, y in poly.exterior.coords])


def wall_gap(outer):
    """P-frame gap between a half's outer outline and its mirror (the other half), top view."""
    o = _to_P(outer)
    return o.distance(Polygon([(-x, y) for x, y in o.exterior.coords]))


@dataclass(frozen=True)
class Bay:
    name: str              # its footprint in the standard
    x: float               # square centre, left local
    y: float
    rot: float             # square's turn (deg), left local
    square: Polygon        # where the module's board and posts stand (top view)
    pocket: Polygon        # the pocket's cavity, top view
    outer: Polygon         # the case's outer outline with the bay
    wall_gap: float        # between the two halves' outer walls (P frame)


def build(fp, x, y, rot):
    """The Bay of footprint fp with its square centred at (x, y), turned by rot (left local)."""
    f = S.get(fp)
    sq = A.translate(A.rotate(box(-f.w / 2, -f.l / 2, f.w / 2, f.l / 2), rot, origin=(0, 0)), x, y)
    pocket = sq.buffer(PR.BAY_POCKET_GAP, join_style="round")
    outer = _outer_with(pocket)
    return Bay(fp, x, y, rot, sq, pocket, outer, wall_gap(outer))


@lru_cache(maxsize=8)
def solve(fp=None):
    """The Bay the layout declares for footprint fp (default: the active one); ValueError when it declares none."""
    fp = fp or active()
    if fp is None:
        raise ValueError("no thumb bay is on (C58_POINTER=…:bay30 or C58_THUMB_BAY=bay30)")
    if fp not in G.LAYOUT.bays:
        raise ValueError(f"layout {G.LAYOUT.name!r} declares no {fp} thumb bay (Layout.bays): "
                         f"`pointer-checks --suggest-bay` proposes one")
    return build(fp, *G.LAYOUT.bays[fp])


def bridge_gap(b):
    """P-frame distance from the pocket's outer wall to the bridge (top view)."""
    ix0, ix1 = G.interface_x(0.0, G.Z0), G.interface_x(-PR.BRIDGE_LEN, G.Z0)
    bridge = Polygon([(ix0, 0.0), (-ix0, 0.0), (-ix1, -PR.BRIDGE_LEN), (ix1, -PR.BRIDGE_LEN)])
    return _to_P(b.pocket.buffer(PR.WALL_T, join_style="round")).distance(bridge)


def suggest(fp):
    """A Bay of footprint fp for a layout that has none yet (positions rounded to 0.01 mm, ready for Layout.bays);
    ValueError when no angle round the arc works."""
    _, k = arc_anchor()
    f = S.get(fp)
    s = max(f.w, f.l) / 2
    po = plate_outer()
    for j in range(int(round(90.0 / PR.BAY_ANGLE_STEP)) + 1):
        th = k.rot - j * PR.BAY_ANGLE_STEP
        a = math.radians(th)
        for i in range(400):
            d = 10.0 + 0.25 * i
            cx, cy = k.x + d * math.cos(a), k.y + d * math.sin(a)
            sq = A.translate(A.rotate(box(-s, -s, s, s), th, origin=(0, 0)), cx, cy)
            if sq.distance(po) >= PR.BAY_POCKET_GAP + 0.01:          # + 0.01: still clear after rounding
                break
        b = build(fp, round(cx, 2), round(cy, 2), th)
        if b.wall_gap >= PR.BAY_WALL_GAP and bridge_gap(b) >= PR.BAY_WALL_GAP:
            return b
    raise ValueError(f"no {fp} position round the arc leaves {PR.BAY_WALL_GAP} mm to the other half and the bridge")
