"""
Pointer devices as data. Each lives in its own folder, pointers/<name>/ (like layouts/<name>/):

    module.py    DEVICE = Device(...): the part's numbers, each with its source, and how it connects
    carrier.py   its printed carrier for each footprint it supports (compose/pointer/std.py): POSE, USES, BASE_T,
                 BOARD_Z, optionally TILT, and outline(fp, tilt=None), solid(fp, tilt=None) (tilt: the angle in
                 degrees, or None for the carrier's own; a carrier that never tilts ignores it)
    pcb.py       (optional) a board of its own, generated like compose/pcb/*

Device frame: origin at the touch point's centre (the ball) on the board's top face, +y toward the board edge away
from the header, z up. A right-half device is the left-half one mirrored with its half (compose/case/gasket.py,
compose/pointer/place.py), so a device and its carrier must be mirror-symmetric about the device's own y axis (x -> -x),
or the right half's solids won't match the real part. A carrier may tilt the board: TILT[fp] = (angle, azimuth)
turns the board about the horizontal axis through the device frame's origin so its normal leans `angle` degrees
toward `azimuth` (degrees, footprint frame: 0 = toward +x, the bay's outer side away from the keys; 180 = toward them). The carrier is then a wedge: its
base stays flat on the footprint, its bosses end on the tilted underside. `measured` stays False until a real part has been measured
(pointer-checks warns until then).
"""
import os
import math
import importlib
import sys
from dataclasses import dataclass
from shapely.geometry import box
from shapely.ops import unary_union
from compose import REPO_ROOT


@dataclass(frozen=True)
class Device:
    name: str
    title: str
    footprints: tuple   # the std footprints its carrier supports, by name: "slot", "bay30", ...
    rects: tuple        # board outline as rectangles (x0, y0, x1, y1); rects[0] is the main body
    holes: tuple        # mounting hole centres (x, y)
    hole_d: float
    pads: tuple         # cable pads (signal, x, y)
    pcb_t: float
    top_rect: tuple     # envelope above the board (x0, y0, x1, y1): housing and ball
    top_h: float        # board top -> touch surface (ball top)
    back_rect: tuple    # envelope of the parts under the board (x0, y0, x1, y1)
    back_h: float       # their height
    bus: str            # how it connects: "i2c" (the firmware generator's only one so far)
    address: int        # I2C address
    driver: str         # QMK POINTING_DEVICE_DRIVER
    qmk_defines: tuple  # extra config.h defines (name, value)
    measured: bool
    sources: tuple      # (what, source) pairs


def outline(d):
    return unary_union([box(*r) for r in d.rects])


def tilt_map(pivot, angle, azimuth):
    """Point map (x, y, z) -> (x, y, z): a turn of `angle` degrees about the horizontal axis through `pivot` that leans
    the +z normal toward `azimuth` (degrees, from +x toward +y)."""
    if not angle:
        return lambda x, y, z: (x, y, z)
    a, phi = math.radians(angle), math.radians(azimuth)
    kx, ky = -math.sin(phi), math.cos(phi)
    c, s = math.cos(a), math.sin(a)

    def f(x, y, z):
        px, py, pz = x - pivot[0], y - pivot[1], z - pivot[2]
        d = (kx * px + ky * py) * (1.0 - c)                       # Rodrigues, the axis (kx, ky, 0)
        return (px * c + ky * pz * s + kx * d + pivot[0],
                py * c - kx * pz * s + ky * d + pivot[1],
                pz * c + (kx * py - ky * px) * s + pivot[2])
    return f


def pose_fn(pose):
    """Point map device frame -> footprint frame for a carrier's pose (turn in degrees, then shift)."""
    rot, dx, dy = pose
    a = math.radians(rot)
    c, s = math.cos(a), math.sin(a)
    return lambda x, y: (c * x - s * y + dx, s * x + c * y + dy)


# ---- the board on its carrier, tilted: the carrier module `car` gives POSE, BOARD_Z and (optionally) TILT; `dev` the
# ---- Device. Footprint frame, z up from the plate's top face.
def tilt_of(car, fp, override=None):
    """(angle, azimuth) of the board's tilt on footprint fp; `override` (degrees) replaces the angle. A carrier with
    no TILT, or none for this footprint, is flat."""
    ang, az = getattr(car, "TILT", {}).get(fp, (0.0, 0.0))
    return (ang if override is None else float(override)), az


def pivot(dev, car, fp):
    """The turn's centre: the device frame's origin on the board's top face."""
    x, y = pose_fn(car.POSE[fp])(0.0, 0.0)
    return (x, y, car.BOARD_Z[fp] + dev.pcb_t)


def tilt_fn(dev, car, fp, tilt=None):
    ang, az = tilt_of(car, fp, tilt)
    return tilt_map(pivot(dev, car, fp), ang, az)


def under(dev, car, fp, tilt, pts, dz=0.0):
    """Device-frame points (x, y) -> footprint-frame (x, y, z) at height dz above the board's underside, tilted."""
    f, T = pose_fn(car.POSE[fp]), tilt_fn(dev, car, fp, tilt)
    return [T(*f(*p), car.BOARD_Z[fp] + dz) for p in pts]


def holes(dev, car, fp, tilt=None):
    """The board's mounting holes on its underside (footprint frame, top view), tilted."""
    return [(x, y) for x, y, _ in under(dev, car, fp, tilt, dev.holes)]


def pads(dev, car, fp, tilt=None):
    return [(x, y) for x, y, _ in under(dev, car, fp, tilt, [(x, y) for _, x, y in dev.pads])]


def pad_points(dev, car, fp, tilt=None):
    """The cable pads on the board's underside: (x, y, z) in the footprint frame, tilted."""
    return under(dev, car, fp, tilt, [(x, y) for _, x, y in dev.pads])


def normal(dev, car, fp, tilt=None):
    """Unit normal of the board (footprint frame): +z turned by the tilt."""
    px, py, pz = pivot(dev, car, fp)
    q = tilt_fn(dev, car, fp, tilt)(px, py, pz + 1.0)
    return (q[0] - px, q[1] - py, q[2] - pz)


def board_low(dev, car, fp, tilt=None):
    """Height (above the plate top) of the lowest point under the board: its underside's corners and the parts'
    envelope beneath it, tilted."""
    pts = [(x, y) for x0, y0, x1, y1 in dev.rects for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    bx0, by0, bx1, by1 = dev.back_rect
    back = [(x, y) for x, y in ((bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1))]
    return min(min(z for _, _, z in under(dev, car, fp, tilt, pts)),
               min(z for _, _, z in under(dev, car, fp, tilt, back, -dev.back_h)))


def insert_depth(dev, car, fp, tilt=None, insert_d=None, insert_l=None, floor=None):
    """Depth of the carrier's insert holes along the board's normal: the flat rule (4.5, or the room up to the seat), less
    what a tilted board's low side leaves: the hole's bottom face, its lowest rim point included, keeps `floor` of base."""
    from compose import params as PR
    from compose.pointer import std as S
    insert_d = PR.M2_INSERT_D if insert_d is None else insert_d
    floor = PR.POINTER_INSERT_FLOOR if floor is None else floor
    z0, zb = S.seat_z(fp), car.BOARD_Z[fp]
    flat = min(zb - z0, PR.M2_PLATE_INSERT_L + 1.0)
    ang = tilt_of(car, fp, tilt)[0]
    if ang == 0.0:
        return flat
    n = normal(dev, car, fp, tilt)
    low = min(z for _, _, z in under(dev, car, fp, tilt, dev.holes))
    rim = (insert_d / 2) * math.sin(math.radians(abs(ang)))
    return min(flat, (low - rim - (z0 + floor)) / n[2])


def _import(name, part):
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    return importlib.import_module(f"pointers.{name}.{part}")


def names():
    """Every device folder in pointers/ (one with a module.py)."""
    root = os.path.join(REPO_ROOT, "pointers")
    return sorted(n for n in os.listdir(root) if os.path.isfile(os.path.join(root, n, "module.py")))


def get(name):
    """The Device in pointers/<name>/module.py; KeyError when there's no such folder."""
    if name not in names():
        raise KeyError(f"unknown pointer device {name!r}: one of {', '.join(names())} (pointers/)")
    return _import(name, "module").DEVICE


def carrier(name):
    """The device's carrier module (pointers/<name>/carrier.py)."""
    return _import(name, "carrier")
