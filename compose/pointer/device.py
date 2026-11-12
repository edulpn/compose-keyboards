"""
Pointer devices as data. Each lives in its own folder, pointers/<name>/ (like layouts/<name>/):

    module.py    DEVICE = Device(...): the part's numbers, each with its source, and how it connects
    carrier.py   its printed carrier for each footprint it supports (compose/pointer/std.py): POSE, USES, BASE_T,
                 BOARD_Z, TILT, outline(fp), solid(fp)
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
