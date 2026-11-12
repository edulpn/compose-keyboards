"""
Pointer mount standard (rev 2): what a plate or case gives a pointing device, and what the device's printed carrier
must fit (docs/pointer-modules.md). Like compose/controller/rev2_std.py: the plate and the case are built from this
file alone, never from a device, so one print takes any device that meets it. Each device in pointers/<name>/ brings
a carrier for the footprints it supports. The standard fixes the mechanical footprint only: how a device connects
(I2C, PS/2, SPI, ...) is the device's business.

Footprints are named entries in FOOTPRINTS, of two kinds, each in its own frame: x, y in mm, z up from the plate's
top face (z = 0 is the plate top).

  slot  on the plate, in place of a 1.5u thumb key. Frame: the key's centre; x along its 1u side, y along its 1.5u
        side (the key's own turn). The key's switch hole stays open: the cable goes down it and through the half
        board's MX centre hole.
  bay   on the case, in the thumb bay (compose/case/bay.py). Frame: the centre and turn the layout declares for that
        bay (Layout.bays). The cable goes down into the pocket and through the diamond hole in the half's wall.

A carrier stays inside its footprint's window (top view) and below its top, screw heads included, and fixes to at
least MIN_POINTS of the footprint's points with the footprint's screws, heads on the carrier.

Growing the standard: a new size is a new entry (say "bay40"); an entry never changes once parts are printed against
it. Plates and cases depend only on the footprint a build uses, devices name the footprints their carriers fit, and
layouts declare a position per bay, so a new entry changes nothing that's already there.
"""
from dataclasses import dataclass
from compose import params as PR

MIN_POINTS = 2                 # a carrier screws to at least this many of the footprint's points


@dataclass(frozen=True)
class Footprint:
    name: str
    kind: str                  # "slot" (plate, in place of the 1.5u thumb key) or "bay" (case, in the thumb bay)
    w: float                   # window (x by y), centred on the frame: a device and its carrier stay inside it
    l: float
    top: float                 # ... and below this, above the plate top
    points: tuple              # fixing points (x, y), in the frame
    seat_z: float              # carriers sit here (above the plate top)
    insert_d: float            # the points' heat-set insert holes: diameter ...
    insert_l: float            # ... and depth
    screw: str                 # "M2" / "M3", button head
    thread: tuple              # (min, max) thread in the insert
    head: tuple                # (diameter, height) of the screw heads
    shank_d: float             # the screws' shank
    clear: float               # clearance hole through a carrier
    post_r: float = 0.0        # bay: the posts' radius (from the pocket floor up to the seat)


SLOT = Footprint(
    name="slot", kind="slot", w=22.5, l=28.5, top=16.0,                 # top: the stand-in keycap's top, fully up
    points=((-8.0, -11.0), (-8.0, 11.0), (8.0, -11.0), (8.0, 11.0)),     # M2 inserts in the plate's top face
    seat_z=0.0,                                                          # carriers sit on the plate top
    insert_d=PR.M2_INSERT_D, insert_l=PR.M2_PLATE_INSERT_L,              # 3.2, 3.5 deep in the 5 mm plate
    screw="M2", thread=(2.5, PR.M2_PLATE_INSERT_L - 0.2),                # the hole is blind
    head=(PR.M2_HEAD_D, PR.M2_HEAD_H), shank_d=2.0, clear=PR.M2_CLEAR)

BAY30 = Footprint(
    name="bay30", kind="bay", w=30.0, l=30.0, top=16.0,
    points=((-12.0, -12.0), (-12.0, 12.0), (12.0, -12.0), (12.0, 12.0)),  # posts; M3 heads stay inside the window
    seat_z=-3.0,                                                         # post tops, 3 mm below the plate top
    insert_d=PR.M3_INSERT_D, insert_l=PR.M3_INSERT_L,                    # 4.6, 5.0 deep (M3 x 5 x 4 inserts)
    screw="M3", thread=(2.5, PR.M3_INSERT_L - 1.0),                      # thread in the 4 mm insert
    head=(PR.M3_HEAD_D, PR.M3_HEAD_H), shank_d=3.0, clear=PR.M3_CLEAR,
    post_r=3.5)                                                          # 1.2 mm of wall round the insert

FOOTPRINTS = {f.name: f for f in (SLOT, BAY30)}       # add new sizes here; never change an entry once printed


def get(fp):
    """The Footprint named fp; KeyError when the standard has none."""
    if fp not in FOOTPRINTS:
        raise KeyError(f"no footprint {fp!r} in the pointer mount standard: one of {', '.join(FOOTPRINTS)}")
    return FOOTPRINTS[fp]


def bays():
    """The names of the standard's bay footprints."""
    return [n for n, f in FOOTPRINTS.items() if f.kind == "bay"]


def kind(fp):
    return get(fp).kind


def points(fp):
    return get(fp).points


def seat_z(fp):
    return get(fp).seat_z


def top(fp):
    return get(fp).top


def window(fp):
    """(x0, y0, x1, y1) of the footprint's window, in its frame."""
    f = get(fp)
    return (-f.w / 2, -f.l / 2, f.w / 2, f.l / 2)


def thread(fp):
    return get(fp).thread


def screw_head(fp):
    """(diameter, height) of the footprint's button-head screws."""
    return get(fp).head


def screw_clear(fp):
    return get(fp).clear
