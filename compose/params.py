import os as _os
"""
Every design parameter lives here. Edit a value, run the commands again (`python3 -m compose --help`),
and every part is regenerated from it. Units: millimetres and degrees.

Naming: *_T = thickness, *_H = height, *_R = radius, *_D = diameter,
*_GAP = clearance between mating parts.
"""

# ---------------------------------------------------------------- the keyboard this run builds
# One keyboard a run. Its layout comes from the command line (compose/__main__.py: --layout) and is carried
# here as COMPOSE_LAYOUT. The controller rev 2's commands build no keyboard (it is one board under every
# layout), and in such a run the values that belong to a keyboard do not exist: see the end of this file.
_RENAMED = {"C58_SPLAY": "COMPOSE_SPLAY", "C58_TENT": "COMPOSE_TENT", "C58_TILT": "COMPOSE_TILT", "C58_GAP_TOP": "COMPOSE_GAP_TOP",
            "C58_BRIDGE_LEN": "COMPOSE_BRIDGE_LEN", "C58_PREROUTE": "COMPOSE_PREROUTE"}
for _n in sorted(n for n in _os.environ if n.startswith("C58_")):       # an old name must not be passed over in silence
    raise SystemExit(f"{_n} is set, and nothing reads it any more. " + (
        f"It is {_RENAMED[_n]} now." if _n in _RENAMED else
        "There is one rev, and nothing to set." if _n == "C58_REV" else
        "There is no setting of that name.") + " Unset it and run the command again.")
LAYOUT = _os.environ.get("COMPOSE_LAYOUT") or None       # key layout: layouts/<name>/layout.py

# What the layout says about its keyboard: layouts/<name>/keyboard.py, plain constants (its name, the credit for its
# key layout, its angles, its USB ids). Read only when a run builds a keyboard.
_KB_NAMES = ("NAME", "CREDIT", "TENT_DEG", "TILT_DEG", "USB_VID", "USB_PID", "USB_PID_RGB")
_KB = None
if LAYOUT is not None:
    import importlib as _importlib
    try:
        _KB = _importlib.import_module(f"layouts.{LAYOUT}.keyboard")
    except ModuleNotFoundError as _e:
        if _e.name != f"layouts.{LAYOUT}.keyboard":
            raise
        raise SystemExit(f"layouts/{LAYOUT}/keyboard.py is missing: a layout says there what its keyboard is called, and its "
                         f"angles and USB ids. layouts/compose58/keyboard.py shows what goes in it.") from None
    _missing = [_n for _n in _KB_NAMES if not hasattr(_KB, _n)]
    if _missing:
        raise SystemExit(f"layouts/{LAYOUT}/keyboard.py does not say {', '.join(_missing)}. layouts/compose58/keyboard.py shows "
                         f"what goes in it.")
    for _n in ("TENT_DEG", "TILT_DEG"):
        if isinstance(getattr(_KB, _n), bool) or not isinstance(getattr(_KB, _n), (int, float)):
            raise SystemExit(f"layouts/{LAYOUT}/keyboard.py: {_n} has to be a number of degrees, and is {getattr(_KB, _n)!r}.")
_K = (lambda name: getattr(_KB, name) if _KB else None)      # a value of the keyboard's; None in a run that builds none

# ---------------------------------------------------------------- layout
KEY_PITCH = 19.05            # 1u
KEYCAP_SIZE = 18.0           # 1u cap footprint (used for spacing checks/renders)
PLATE_MARGIN = 10.0          # key cell edge -> outer edge of plate/case
OUTLINE_CONVEX_R = 6.0       # outline corner rounding (>= BEZEL_BEVEL + 2)
OUTLINE_CONCAVE_R = 3.0

# ---------------------------------------------------------------- ergonomics
SPLAY_DEG = float(_os.environ.get("COMPOSE_SPLAY", 10.0))           # each half rotated toward the centre (top view)
if _KB:                                                              # the keyboard's own: layouts/<name>/keyboard.py
    TENT_DEG = float(_os.environ.get("COMPOSE_TENT", _KB.TENT_DEG))    # gable tent: inner edges raised
    TILT_DEG = float(_os.environ.get("COMPOSE_TILT", _KB.TILT_DEG))    # typing tilt: back raised (negative = front raised)
GAP_TOP = float(_os.environ.get("COMPOSE_GAP_TOP", 34.0))          # distance between the halves' inner edges at the back

# ---------------------------------------------------------------- switch plate
PLATE_T = 5.0                # MX bottom housing sits inside the plate
SWITCH_HOLE = 14.0
SWITCH_CLIP_LIP = 1.5        # top skin the MX clips latch under
CLIP_NOTCH_W = 5.5           # relief for the clips below the lip (N and S walls)
CLIP_NOTCH_D = 0.8
PLATE_HOLE_CHAMFER = 0.3     # bed-side chamfer on switch holes (elephant foot)
TRIM_LIP_T = 1.2             # trim lip under the plate edge, hides the case's
TRIM_LIP_H = 2.2             #   stair-stepped top edge (prints upward)

# ---------------------------------------------------------------- case
FLOOR_T = 2.5
WALL_T = 3.0
REVEAL_SIDE_GAP = 0.4        # trim lip -> case step, sideways
REVEAL_SHADOW = 0.3          # gap under the trim lip (shadow line)
SHELF_T = 3.0                # case material under the plate at each M3 boss
FOOT_D = 10.5                # rubber bumpon recesses
FOOT_DEPTH = 1.0

# ---------------------------------------------------------------- bevel frame (bezel)
BEZEL_H = 6.0                # above the plate top
BEZEL_BEVEL = 4.0            # horizontal inset of the bevel over BEZEL_H
KEY_OPENING_GAP = 0.5        # opening beyond the key cells
KEY_OPENING_CLOSE_R = 3.0    # fills slivers between differently rotated keys
KEY_OPENING_CORNER_R = 1.0

# ---------------------------------------------------------------- centre section
BRIDGE_LEN = float(_os.environ.get("COMPOSE_BRIDGE_LEN", 62.0))   # depth of the centre section (back face at y = 0)
BRIDGE_WALL_T = 2.5          # back and front walls of the bay
WINDOW_EDGE_OVER_PCB = 0.5   # cover window stops this far over each long PCB edge
WINDOW_FRONT_MARGIN = 1.5    # window ends this far past the Pico's front edge

# ---------------------------------------------------------------- controller + socket
PICO_W, PICO_L, PICO_T = 21.0, 51.0, 1.0
USB_NOTCH_W = 13.0           # opening in the back wall for the cable's overmold
USB_NOTCH_BELOW_PCB = 2.5    # opening starts this far below the board underside

# ---------------------------------------------------------------- hardware
M3_CLEAR = 3.4
M3_HEAD_H = 1.65
M3_CBORE_D = 6.4             # counterbore for the head
M3_INSERT_D = 4.6            # hole for M3 x 5 x 4 heat-set inserts
M3_INSERT_L = 5.0            # hole depth for M3 x 5 x 4 inserts (insert length + ~1 mm)
M2_CLEAR = 2.4
M2_HEAD_D = 3.5
M2_HEAD_H = 1.3
M2_INSERT_D = 3.2
M2_PLATE_INSERT_L = 3.5      # in the 5 mm plate

# ---------------------------------------------------------------- fits
FIT_GAP = 0.3                # between printed parts that meet (cover/frames, bridge/plate)

# ---------------------------------------------------------------- half boards
PCB_T = 1.6
PCB_UNDER_H = 2.4            # tallest part under a half board (Kailh socket 1.85, DO-35 body 1.9 + leads)
PCB_UNDER_CLEAR = 1.0
WIRE_DEPTH = PCB_T + PCB_UNDER_H + PCB_UNDER_CLEAR      # minimum space between plate underside and floor
# switches: MX pins in footprint coords (KiCad, y down), mirrored copies make the board reversible
MX_PIN1 = (2.54, -5.08)      # -> diode anode
MX_PIN2 = (-3.81, -2.54)     # -> column
MX_CENTER_D = 4.0
MX_PEG_D = 1.75
MX_PEG_X = 5.08
MX_PTH_DRILL, MX_PTH_PAD = 1.5, 2.2              # solder version
HS_HOLE_D = 3.05                                   # hotswap: socket-post holes (merged into slots when mirrored)
HS_PAD2 = ((-7.085, -2.54), (2.55, 2.5))          # socket tab next to MX_PIN2: centre, size
HS_PAD1 = ((6.35, -5.08), (2.2, 2.0))      # next to MX_PIN1 (moved out and shortened to clear the mirrored slot)
HS_BODY = (-7.0, 7.0, -7.2, -0.6)                 # socket body box (x0, x1, y0, y1), both orientations combined
HS_HEIGHT = 2.0                                   # socket height under the board incl. its 0.3 mm feet (Kailh CPG151101S11 model)
DIODE_PITCH = 7.62
DIODE_BODY = (4.0, 2.0)                            # length, diameter (DO-35)
JOINT_POCKET_R = 1.5         # plate-underside pockets over top-side solder joints
JOINT_POCKET_D = 1.2
TRACE_W, CLEARANCE = 0.25, 0.2
VIA_D, VIA_DRILL = 0.6, 0.3

# ---------------------------------------------------------------- board art / naming
BOARD_NAME = _K("NAME")          # the keyboard's name: layouts/<name>/keyboard.py
HANDLE = "edulpn"
REVISION = "rev 2"               # the platform's generation, as the boards print it
YEAR = 2026
TAGLINE = {"F": "static func ∘ (lhs: Half, rhs: Half) -> Keyboard",     # Swift on one face...
           "B": "@Composable fun Keyboard(lhs: Half, rhs: Half)"}         # ...Kotlin Compose on the other
CREDIT = _K("CREDIT")            # whose key layout it is: layouts/<name>/keyboard.py
HALF_NAMES = ("lhs", "rhs")      # left / right half, as in operator overloading
ART_TITLE_FONT = ("DejaVu Sans", "bold")
ART_CODE_FONT = ("DejaVu Sans Mono", "normal")
ART_TEXT_FONT = ("DejaVu Sans", "normal")
ART_HEX_CELL = 6.0               # silkscreen hex lattice (flat-to-flat, mm)
ART_LINE_W = 0.2                 # silkscreen line width (JLC min ~0.15)
ART_MIN_TEXT_EM = 1.2            # smallest silkscreen font size (em, mm)
ART_COPPER_KEEPOUT = 0.6         # traces kept this far from the exposed-copper title

# ---------------------------------------------------------------- rev 2 controller (rev 2 board on standoffs)
CTRL_BACK_CLEAR = 0.5            # board's back edge to the bridge's back wall
STANDOFF_MIN_GAP = 0.5           # Pico top -> cover underside, at least

# ---------------------------------------------------------------- rev 2: gasket mount (compose/case/gasket.py)
# Local half frame: z = 0 plate underside, PLATE_T plate top. The plate's outer FLANGE_W is a thin flange
# (FLANGE_Z0..+FLANGE_T) pinched between foam pads: a case ledge below, the frame above. Nothing screws
# through the plate or the half board; the frame screws to the case and bottoms out on it, so the pad
# squeeze is set by geometry, not torque.
FLOAT_GAP = 0.6                  # plate edge to case wall / frame skirt (sideways float)
FLANGE_W = 6.0                   # flange width inward from the plate outline
FLANGE_T = 2.0
FLANGE_Z0 = PLATE_T - FLANGE_T   # flange underside (local z): flush with the plate's top face, so the plate prints
                                 # switch side down with the flange flat on the bed - no overhang
# pads = slices of off-the-shelf self-adhesive foam weatherstrip tape (closed-cell EPDM or neoprene sponge,
# 1/8 in / 3 mm thick, 3/8 in / 10 mm wide), cut across into GK_PAD_W slices with scissors
GK_T = 3.0                       # tape thickness, free (3.0-3.2 mm: 30-34 % squeeze, fine for EPDM sponge)
GK_SQUEEZE = 0.30                # designed squeeze
GK_C = GK_T * (1 - GK_SQUEEZE)   # installed thickness
GK_PAD_L, GK_PAD_W = 10.0, 4.0   # pad: tape width along the edge (9.5-10) x slice length inward
LEDGE_W = 4.5                    # case ledge under the flange, inward from the outline
LEDGE_T = 1.0                    # flat part of the ledge; under it a smooth 60-degree chamfer back to the wall
LEDGE_CHAMFER_DEG = 60.0         # from horizontal, local frame (the tent tilts it by up to 12 deg: 48 deg worst, printable)
LEDGE_TOP = FLANGE_Z0 - GK_C     # pad seat (local z)
FRAME_LIP_Z = FLANGE_Z0 + FLANGE_T + GK_C   # frame underside over the flange (local z)
SEAM_Z = FLANGE_Z0               # case wall top = frame bottom (local z)
FRAME_TOP_Z = PLATE_T + BEZEL_H  # frame top (local z)
FRAME_SCREWS = 6                 # per half, M3 from below into frame inserts
FRAME_BOSS_R = 4.0
FRAME_SCREW_IN = 0.5             # screw centre inside the plate outline (the plate is notched around it)
NOTCH_R = FRAME_BOSS_R + FLOAT_GAP
GK_TABS = 18                     # pad pairs per half (outer edges)
INNER_SEATS_P = ((-3.0, -13.0), (-48.5, -58.5))   # inner-edge pad pairs: P-frame y spans (back, front)
INNER_SEAT_IN = 4.5              # inner seat width under the flange, from the plate edge
PCB_INSET = LEDGE_W + 0.5        # half board outline inside the plate outline
JUMPER_W = 21.0                  # rev 2 flex jumper width (20 x 1.0 mm pitch + 1 mm margins: both connectors' N+1)
# middle (controller rev 2): the board drops onto four case posts and is clamped by four M3 male-female
# standoffs; the cover drops onto the standoffs and takes four M3 x 6 screws (nothing slides or hooks).
# Same M3 x 6 screws and M3 x 5 x 4 inserts as the frames (M3_INSERT_D / M3_INSERT_L / M3_HEAD_H / M3_CBORE_D).


# ---------------------------------------------------------------- firmware
USB_VID, USB_PID, USB_PID_RGB = _K("USB_VID"), _K("USB_PID"), _K("USB_PID_RGB")     # layouts/<name>/keyboard.py


# ---------------------------------------------------------------- a run that builds no keyboard
# What belongs to a keyboard (its layout and what the layout says of it) has no value in a run that builds
# none: the controller rev 2's commands, or a module started without python3 -m compose. Reading one stops the
# run and says so.
_KEYBOARD = ("LAYOUT", "TENT_DEG", "TILT_DEG", "BOARD_NAME", "CREDIT", "USB_VID", "USB_PID", "USB_PID_RGB")
if LAYOUT is None:
    del LAYOUT, BOARD_NAME, CREDIT, USB_VID, USB_PID, USB_PID_RGB


def __getattr__(name):
    if name in _KEYBOARD:
        raise AttributeError(f"compose.params.{name} belongs to a keyboard (its layout, or what the layout says of it), and this run builds none. A "
                             f"keyboard's command sets it (python3 -m compose --help); the controller rev 2's commands have none.")
    raise AttributeError(f"module 'compose.params' has no attribute {name!r}")
