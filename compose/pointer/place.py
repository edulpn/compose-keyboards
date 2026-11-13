"""
Where a pointer device goes and whether it fits, in 2D and numbers (no CadQuery), so `pointer-checks --fast` runs in
seconds. Two sets of questions:

  layout  does this layout give the footprint (compose/pointer/std.py)? slot: the window clear of the other keycaps
          and inside the plate core, the inserts clear of switch holes and of what's cut into the plate from below.
          bay: compose/case/bay.py, the posts inside the pocket, the lid's opening clear of the plate.
  device  does the device on its carrier (pointers/<name>/carrier.py) fit the footprint? inside the window and under
          its top, screwed to enough of its points, screw lengths, the cable's way down.

Frames: footprint frame -> left local, the plate frame (z = 0 plate underside, PLATE_T plate top). A right-half
device is placed on the left local footprint and mirrored with its half, as the right plate itself is.
"""
import math
from dataclasses import dataclass
from functools import lru_cache
from shapely.geometry import MultiPoint, Point, Polygon, box
from shapely import affinity as A
from shapely.ops import unary_union
from compose import params as PR
from compose import geom as G
from compose.pointer import std as S
from compose.pointer import device as D
from compose.case import bay as B


@dataclass
class Placement:
    device: D.Device
    side: str
    footprint: str         # the standard's footprint: "slot", or a bay such as "bay30"
    kind: str              # its kind: "slot" or "bay"
    key_index: object      # the 1.5u key it replaces (slot), None in the bay
    frame: tuple           # (x, y, rot) of the footprint's frame, left local
    window: Polygon        # the footprint's window, left local
    points: list           # the footprint's points (inserts or posts), left local
    uses: list             # the ones the carrier screws to, left local
    board: Polygon         # the device's board outline, left local
    top: Polygon           # its envelope above the board, left local
    back: Polygon          # its envelope of the parts under the board, left local
    holes: list            # its mounting holes, left local
    pads: list             # its cable pads [(signal, x, y)], left local
    carrier: Polygon       # the carrier's top view, left local
    board_bot_z: float     # the board's underside, local z
    ball_top: float        # the touch surface above the plate top
    dev_screw: tuple       # (length, thread) of the board's M2 screws into the carrier's inserts, or None
    fp_screw: tuple        # (length, thread) of the carrier's screws into the footprint, or None
    tilt: float = 0.0      # the board's tilt (degrees) about the horizontal axis through `pivot` (positive: outward, away from the keys)
    pivot: tuple = None    # that axis's point: the device frame's origin on the board's top face (left local x, y, z)
    axis: tuple = None     # the axis's direction (x, y), left local
    rot: object = None     # point map (x, y, z) -> (x, y, z) of that turn, left local
    pad_pt: tuple = None   # middle of the cable pads on the board's underside, tilted (left local x, y, z)
    base_clear: float = 0.0   # the board's lowest underside point above the carrier's base top
    top_z: float = 0.0     # the device's highest point above the plate top
    # (board, top, back, holes and pads above are the untilted device: the solids are built flat and then turned)


# ---------------------------------------------------------------- frames
def frame(fp):
    """(key index or None, (x, y, rot)): the footprint's frame on this layout, left local."""
    if S.kind(fp) == "slot":
        i, k = B.thumb_key()
        return i, (k.x, k.y, k.rot)
    b = B.solve(fp)
    return None, (b.x, b.y, b.rot)


def to_local(fr):
    """Point map footprint frame -> left local."""
    x0, y0, rot = fr
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    return lambda x, y: (x0 + c * x - s * y, y0 + s * x + c * y)


def poly_to_local(poly, f):
    return Polygon([f(x, y) for x, y in poly.exterior.coords])


def geom_to_local(g, f):
    return unary_union([poly_to_local(p, f) for p in getattr(g, "geoms", [g])])


def window(fp, fr):
    return poly_to_local(box(*S.window(fp)), to_local(fr))


def points(fp, fr):
    f = to_local(fr)
    return [f(*p) for p in S.points(fp)]


# ---------------------------------------------------------------- the slot on this layout
def switch_hole(k):
    """The plate's switch hole at key k with its clip notches (compose/case/sandwich.py _switch_cutter), left local."""
    h, w, d = PR.SWITCH_HOLE / 2, PR.CLIP_NOTCH_W / 2, PR.CLIP_NOTCH_D + 0.1
    p = unary_union([box(-h, -h, h, h), box(-w, h - 0.1, w, h + d), box(-w, -h - d, w, -h + 0.1)])
    return A.translate(A.rotate(p, k.rot, origin=(0, 0)), k.x, k.y)


def keycaps(skip=None):
    """Every other key's keycap square (KEYCAP_SIZE), left local (skip: index of the replaced key, or None)."""
    return unary_union([G.key_poly(k, size=PR.KEYCAP_SIZE) for i, k in enumerate(G.LAYOUT.keys) if i != skip])


@lru_cache(maxsize=1)
def core():
    """The plate's 5 mm core (the outline less the flange)."""
    return G.OUTLINE.buffer(-PR.FLANGE_W, join_style="round")


@lru_cache(maxsize=1)
def _switch_holes():
    return unary_union([switch_hole(k) for k in G.LAYOUT.keys])


@lru_cache(maxsize=1)
def underside():
    """What's cut into the plate from below: [(polygon, depth from the underside)]; the frame-screw notches go
    through. Same sources as compose/case/gasket.py plate2_local()."""
    from compose.pcb import rev2_half as H2
    from compose.case import gasket as C
    hb = H2.plan()
    cuts = [(hb.pockets, PR.JOINT_POCKET_D)]
    cuts += [(Point(p).buffer(PR.M2_INSERT_D / 2), PR.M2_PLATE_INSERT_L) for p in hb.posts]
    cuts += [(Point(p).buffer(PR.NOTCH_R), PR.PLATE_T) for p in C.GL.screws_all]
    return tuple(cuts)


def insert_problems(holes, fp="slot"):
    """[(check id, message)] for slot insert holes that are too close to something; [] when all are fine.
    S4: walls to every switch hole (with notches) and to the core's edge. S5: material between the insert's bottom
    and anything cut from below, unless they're far enough apart sideways."""
    r = S.get(fp).insert_d / 2
    z_bot = PR.PLATE_T - S.get(fp).insert_l
    out = []
    for x, y in holes:
        c = Point(x, y)
        d = c.distance(_switch_holes()) - r
        if d < PR.POINTER_INSERT_WALL:
            out.append(("S4", f"insert ({x:.1f}, {y:.1f}) {d:.2f} mm from a switch hole"))
        e = c.distance(core().exterior) - r if core().contains(c) else -r
        if e < PR.POINTER_INSERT_WALL:
            out.append(("S4", f"insert ({x:.1f}, {y:.1f}) {e:.2f} mm from the core's edge"))
        for poly, depth in underside():
            if z_bot - depth >= PR.POINTER_INSERT_UNDER:
                continue
            d = c.distance(poly) - r
            if d < PR.POINTER_INSERT_UNDER:
                out.append(("S5", f"insert ({x:.1f}, {y:.1f}) {d:.2f} mm beside and {z_bot - depth:.2f} mm above "
                                  f"a cut from below"))
    return out


def slot_problems(fp="slot"):
    """[(check id, message)] for the slot on this layout: S2 window vs the other keycaps, S3 window inside the plate
    core, S4/S5 the inserts. S1 (a 1.5u thumb key) raises ValueError in frame()."""
    i, fr = frame(fp)
    w = window(fp, fr)
    out = []
    g = w.distance(keycaps(i))
    if g < PR.POINTER_ENV_CLR:
        out.append(("S2", f"window {g:.2f} mm from another key's keycap"))
    if not core().contains(w):
        out.append(("S3", f"window {w.difference(core()).area:.1f} mm2 outside the plate core"))
    return out + insert_problems(points(fp, fr), fp)


def lid_opening(fr, fp):
    """The frame lid's opening over the bay (top view), left local: the window, KEY_OPENING_GAP round."""
    return window(fp, fr).buffer(PR.KEY_OPENING_GAP, join_style="mitre")


def bay_problems(fp=None):
    """[(check id, message)] for the bay's footprint features on this layout (fp: the active bay by default): B6 the
    posts inside the pocket, B7 the lid's opening clear of the plate's cavity and BAY_FRAME_RIM inside the case's
    outer edge."""
    fp = fp or B.active()
    b = B.solve(fp)
    _, fr = frame(fp)
    out = []
    posts = unary_union([Point(p).buffer(S.get(fp).post_r) for p in points(fp, fr)])
    if not b.pocket.buffer(0.05).contains(posts):
        out.append(("B6", f"{posts.difference(b.pocket).area:.1f} mm2 of the posts outside the pocket"))
    o = lid_opening(fr, fp)
    over = o.intersection(G.OUTLINE.buffer(PR.FLOAT_GAP, join_style="round")).area
    if over > 1e-3:
        out.append(("B7", f"the lid's opening reaches {over:.1f} mm2 over the plate"))
    if not b.outer.buffer(-PR.BAY_FRAME_RIM).contains(o):
        out.append(("B7", f"the lid's opening comes within {PR.BAY_FRAME_RIM} mm of the case's outer edge"))
    return out


# ---------------------------------------------------------------- the device on its carrier
def tilted(pl, poly, z0, z1):
    """Top view of the board's `poly` between heights z0 and z1 above its underside, with the tilt applied: the
    hull of the turned corners (the poly itself when there's no tilt)."""
    if not pl.tilt:
        return poly
    pts = [pl.rot(x, y, pl.board_bot_z + z)[:2] for x, y in poly.exterior.coords[:-1] for z in (z0, z1)]
    return MultiPoint(pts).convex_hull


def screws(dev, car, fp, tilt=None):
    """((length, thread) of the board's M2 screws into the carrier's inserts, (length, thread) of the carrier's
    screws into the footprint's points); None where no standard length fits. The board's screws take 2.5 mm up to the
    insert hole's depth less 0.1; the carrier's take the footprint's thread range (std.thread)."""
    z0 = S.seat_z(fp)
    depth = D.insert_depth(dev, car, fp, tilt)                          # the carrier's insert holes
    dev_s = next(((L, round(L - dev.pcb_t, 2)) for L in PR.STANDARD_SCREW_LENGTHS
                  if 2.5 <= L - dev.pcb_t <= depth - 0.1), None)
    lo, hi = S.thread(fp)
    fp_s = next(((L, round(L - car.BASE_T[fp], 2)) for L in PR.STANDARD_SCREW_LENGTHS
                 if lo <= L - car.BASE_T[fp] <= hi), None)
    return dev_s, fp_s


@lru_cache(maxsize=8)
def place(cfg):
    """The Placement for a PointerConfig (cached: the case, the checks and the firmware all ask). Raises KeyError for
    an unknown device or footprint, ValueError when the device has no carrier for the footprint or the layout lacks
    it."""
    dev = D.get(cfg.device)
    S.get(cfg.mount)
    if cfg.mount not in dev.footprints:
        raise ValueError(f"{dev.name} has no carrier for the {cfg.mount} footprint (it has: {', '.join(dev.footprints)})")
    car = D.carrier(cfg.device)
    i, fr = frame(cfg.mount)
    f = to_local(fr)
    g = D.pose_fn(car.POSE[cfg.mount])
    fl = lambda x, y: f(*g(x, y))                       # device frame -> left local
    zb = car.BOARD_Z[cfg.mount]
    tl = getattr(cfg, "tilt", None)
    ang, az = D.tilt_of(car, cfg.mount, tl)
    dev_s, fp_s = screws(dev, car, cfg.mount, tl)
    pts = points(cfg.mount, fr)
    ox, oy = fl(0.0, 0.0)
    phi = math.radians(az + fr[2])                      # the lean's direction, left local
    pivot = (ox, oy, PR.PLATE_T + zb + dev.pcb_t)
    rot = D.tilt_map(pivot, ang, az + fr[2])
    px, py, pz = (sum(c) / len(dev.pads) for c in zip(*D.pad_points(dev, car, cfg.mount, tl)))   # tilted pads' middle
    pad_pt = (*f(px, py), PR.PLATE_T + pz)
    return Placement(device=dev, side=cfg.side, footprint=cfg.mount, kind=S.kind(cfg.mount), key_index=i, frame=fr,
                     window=window(cfg.mount, fr), points=pts, uses=[pts[j] for j in car.USES[cfg.mount]],
                     board=poly_to_local(D.outline(dev), fl), top=poly_to_local(box(*dev.top_rect), fl),
                     back=poly_to_local(box(*dev.back_rect), fl), holes=[fl(*h) for h in dev.holes],
                     pads=[(n, *fl(x, y)) for n, x, y in dev.pads],
                     carrier=geom_to_local(car.outline(cfg.mount, tl), f), board_bot_z=PR.PLATE_T + zb,
                     ball_top=round(zb + dev.pcb_t + dev.top_h * math.cos(math.radians(ang)), 2), dev_screw=dev_s,
                     fp_screw=fp_s, tilt=ang, pivot=pivot, axis=(-math.sin(phi), math.cos(phi)), rot=rot, pad_pt=pad_pt,
                     base_clear=round(D.board_low(dev, car, cfg.mount, tl) - (S.seat_z(cfg.mount) + car.BASE_T[cfg.mount]), 3),
                     top_z=round(max(rot(*fl(x, y), PR.PLATE_T + zb + dev.pcb_t + dev.top_h)[2]
                                     for x, y in box(*dev.top_rect).exterior.coords) - PR.PLATE_T, 3))


def pads_centre(pl):
    """Middle of the device's cable pads (left local, top view, tilted): where its cable leaves."""
    return pl.pad_pt[0], pl.pad_pt[1]


def device_problems(pl):
    """[(check id, message)] for the device on its carrier: M2 inside the window (screw heads too) and under the
    footprint's top, M3 screwed to enough of the footprint's points, M4 standard screws, M5 the cable's way down."""
    out = []
    fp = pl.footprint
    w = pl.window.buffer(0.01)
    heads = unary_union([Point(p).buffer(S.screw_head(fp)[0] / 2) for p in pl.uses])
    d = pl.device
    for what, g in (("board", tilted(pl, pl.board, 0.0, d.pcb_t)),
                    ("device's housing", tilted(pl, pl.top, d.pcb_t, d.pcb_t + d.top_h)),
                    ("carrier", pl.carrier), ("carrier's screw heads", heads)):
        if not w.contains(g):
            out.append(("M2", f"the {what} reaches {g.difference(pl.window).area:.1f} mm2 outside the window"))
    if pl.top_z > S.top(fp):
        out.append(("M2", f"the device's top {pl.top_z:.1f} mm above the plate (the footprint allows {S.top(fp)})"))
    if pl.tilt and pl.base_clear < PR.POINTER_BOARD_BASE_CLR:   # a carrier that tilts: the turn lowers a side; a flat carrier keeps its own seat
        out.append(("M2", f"the board's low side {pl.base_clear:.2f} mm above the carrier's base (>= {PR.POINTER_BOARD_BASE_CLR})"))
    if len(set(pl.uses)) < S.MIN_POINTS:
        out.append(("M3", f"screwed to {len(set(pl.uses))} of the footprint's points (at least {S.MIN_POINTS})"))
    if pl.dev_screw is None:
        out.append(("M4", "no standard M2 length for the board's screws into the carrier"))
    if pl.fp_screw is None:
        out.append(("M4", f"no standard {S.get(fp).screw} length for the carrier's screws into the footprint"))
    c = Point(pads_centre(pl))
    r = PR.POINTER_CABLE_D / 2
    if pl.carrier.buffer(-0.01).intersects(c.buffer(r)):
        out.append(("M5", "the carrier covers the pads: the cable can't drop"))
    if S.kind(fp) == "slot" and not pl.window.contains(c):
        out.append(("M5", "the pads are outside the window"))
    if S.kind(fp) == "bay" and not B.solve(fp).pocket.buffer(-(r + 0.5)).contains(c):
        out.append(("M5", "the pads aren't over the pocket"))
    return out
