import os as _os
"""
Every design parameter lives here. Edit a value, run `python3 -m compose build`, and every part
is regenerated from it. Units: millimetres and degrees.

Naming: *_T = thickness, *_H = height, *_R = radius, *_D = diameter,
*_GAP = clearance between mating parts.
"""

# ---------------------------------------------------------------- revision
# C58_REV=2 builds the rev 2 case around the controller rev 2 board (compose/controller/rev2_std.py): wider back gap, 64 mm bridge,
# corner bosses + M3 standoffs carrying the board and the cover, research-based default angles (README).
REV = int(_os.environ.get("C58_REV", "1"))
_D = (lambda r1, r2: r2 if REV == 2 else r1)          # per-revision default (env vars still override)

# ---------------------------------------------------------------- layout
LAYOUT = "lily58"            # key layout: layouts/<name>/layout.py
KEY_PITCH = 19.05            # 1u
KEYCAP_SIZE = 18.0           # 1u cap footprint (used for spacing checks/renders)
MX_STEM_TOP = 10.44          # MX stem top above the plate surface at rest (Cherry MX 3D model, kiswitch library)
MX_TRAVEL = 4.0              # total travel
PLATE_MARGIN = 10.0          # key cell edge -> outer edge of plate/case
OUTLINE_CONVEX_R = 6.0       # outline corner rounding (>= BEZEL_BEVEL + 2)
OUTLINE_CONCAVE_R = 3.0

# ---------------------------------------------------------------- ergonomics
SPLAY_DEG = float(_os.environ.get("C58_SPLAY", 10.0))           # each half rotated toward the centre (top view)
TENT_DEG = float(_os.environ.get("C58_TENT", _D(6.0, 12.0)))    # gable tent: inner edges raised
TILT_DEG = float(_os.environ.get("C58_TILT", _D(5.0, 0.0)))     # typing tilt: back raised (negative = front raised)
GAP_TOP = float(_os.environ.get("C58_GAP_TOP", 34.0))          # distance between the halves' inner edges at the back

# ---------------------------------------------------------------- switch plate
PLATE_T = 5.0                # MX bottom housing sits inside the plate
SWITCH_HOLE = 14.0
SWITCH_CLIP_LIP = 1.5        # top skin the MX clips latch under
CLIP_NOTCH_W = 5.5           # relief for the clips below the lip (N and S walls)
CLIP_NOTCH_D = 0.8
PLATE_HOLE_CHAMFER = 0.3     # bed-side chamfer on switch holes (elephant foot)
PLATE_EDGE_CHAMFER = 0.5     # bed-side chamfer on the outer edge
TRIM_LIP_T = 1.2             # trim lip under the plate edge, hides the case's
TRIM_LIP_H = 2.2             #   stair-stepped top edge (prints upward)

# ---------------------------------------------------------------- case
FLOOR_T = 2.5
WALL_T = 3.0
WIRE_DEPTH = 7.0             # minimum space between plate underside and floor
REVEAL_SIDE_GAP = 0.4        # trim lip -> case step, sideways
REVEAL_SHADOW = 0.3          # gap under the trim lip (shadow line)
SCREW_EDGE_INSET = 6.0       # sandwich screw centre -> outer edge
SHELF_T = 3.0                # case material under the plate at each M3 boss
BOSS_R = 4.0                 # M3 sandwich boss radius
POST_R = 3.25                # M2 plate-support post radius
POST_SHELF_T = 2.5           # material under the plate at each M2 post
# middle supports: M2 screws from under the case through each post and the board into the plate
FLOOR_RIB_T = 1.2            # hex rib lattice on the inside of the floor
FLOOR_RIB_H = 3.0
FLOOR_RIB_CELL = 16.0        # flat-to-flat
POST_FLARE = 3.0             # 45-degree flare at the base of every post
WIRE_KEEPOUT = 7.3           # floor details stay this far below the plate
FOOT_D = 10.5                # rubber bumpon recesses
FOOT_DEPTH = 1.0

# ---------------------------------------------------------------- bevel frame (bezel)
BEZEL_H = 6.0                # above the plate top
BEZEL_BEVEL = 4.0            # horizontal inset of the bevel over BEZEL_H
KEY_OPENING_GAP = 0.5        # opening beyond the key cells
KEY_OPENING_CLOSE_R = 3.0    # fills slivers between differently rotated keys
KEY_OPENING_CORNER_R = 1.0

# ---------------------------------------------------------------- centre section
BRIDGE_LEN = float(_os.environ.get("C58_BRIDGE_LEN", 62.0))   # depth of the centre section (back face at y = 0)
BRIDGE_WALL_T = _D(3.0, 2.5)   # back and front walls of the bay
COVER_H = BEZEL_H            # cover top sits flush with the frames
COVER_BEVEL = BEZEL_BEVEL
COVER_SCREW_Y = (-22.0, -50.0)   # cover screw rows (y in the bridge frame)
PILLAR_R = 4.5               # cover screw pillars
CLAMP_TAB_OVERLAP = 1.0      # cover tab over the Pico's front edge
CLAMP_GAP = 0.8              # Pico top -> cover underside (foam pad on the tab)
WINDOW_EDGE_OVER_PCB = 0.5   # cover window stops this far over each long PCB edge
WINDOW_FRONT_MARGIN = 1.5    # window ends this far past the Pico's front edge

# ---------------------------------------------------------------- controller + socket
PICO_W, PICO_L, PICO_T = 21.0, 51.0, 1.0
PICO_PIN_PITCH = 2.54
PICO_PINS_PER_SIDE = 20
PICO_PIN_ROW_X = 8.89        # pin rows at +-x from the board centre
PICO_PIN1_FROM_END = 1.61    # first pin centre from the USB end
PICO_BACK_Y = -3.5           # y of the board's USB end (bridge back face is y = 0)
USB_RECEPT_W, USB_RECEPT_L, USB_RECEPT_H = 7.6, 5.0, 2.6
USB_RECEPT_OVERHANG = 1.3    # receptacle sticks out past the board edge
USB_NOTCH_W = 13.0           # opening in the back wall for the cable's overmold
USB_NOTCH_BELOW_PCB = 2.5    # opening starts this far below the board underside
MALE_HEADER_SPACER = 2.54    # plastic spacer of the Pico's male headers
FEMALE_HEADER_H = 8.5
FEMALE_HEADER_W = 2.5
HEADER_TAIL = 2.8            # female header pins below the perfboard
PERF_T = 1.6
PERF_PITCH = 2.54
PERF_COLS, PERF_ROWS = 8, 20
CARRIER_SCREW_GRID = (1.5, 7.5)  # carrier screw holes at (+-x, +-y) pitches from its centre
CARRIER_POST_R = 2.75

# ---------------------------------------------------------------- hardware
M3_CLEAR = 3.4
M3_HEAD_D = 5.7              # button head
M3_HEAD_H = 1.65
M3_CBORE_D = 6.4             # counterbore for the head
M3_INSERT_D = 4.6            # hole for M3 x 5 x 4 heat-set inserts
M3_INSERT_L = 5.0            # hole depth for M3 x 5 x 4 inserts (insert length + ~1 mm)
M2_CLEAR = 2.4
M2_HEAD_D = 3.5
M2_HEAD_H = 1.3
M2_CBORE_D = 4.2
M2_INSERT_D = 3.2
M2_INSERT_L = 4.0            # in the case
M2_PLATE_INSERT_L = 3.5      # in the 5 mm plate
STANDARD_SCREW_LENGTHS = (4, 5, 6, 8, 10, 12, 14, 16, 20, 25)

# ---------------------------------------------------------------- fits
FIT_GAP = 0.3                # between printed parts that meet (cover/frames, bridge/plate)

# ---------------------------------------------------------------- printer
BED_X, BED_Y = 350.0, 350.0
BED_MARGIN = 5.0

# ---------------------------------------------------------------- PCB build (vs handwired)
MATRIX = "pcb"               # "pcb": reversible half PCBs + controller PCB; "handwire": copper wire matrix
PCB_T = 1.6
PCB_EDGE_GAP = 0.5           # half board edge to the case cavity wall / interface plane
PCB_UNDER_H = 2.4            # tallest part under a half board (Kailh socket 1.85, DO-35 body 1.9 + leads)
PCB_UNDER_CLEAR = 1.0
UNDER_PLATE = PCB_T if MATRIX == "pcb" else 0.0    # what's sandwiched between plate and case bosses
if MATRIX == "pcb":
    WIRE_DEPTH = PCB_T + PCB_UNDER_H + PCB_UNDER_CLEAR
    WIRE_KEEPOUT = WIRE_DEPTH + 0.3
    POST_SHELF_T = 2.4               # so the M2 post screw lands on a standard length with the board in the stack
    COVER_SCREW_Y = (-21.0, -51.0)   # leaves room between the pillars for the controller's cable connectors
# perimeter M3 points: the sandwich screw clamps case boss -> board -> plate -> frame insert solid
# (rev 1 is a fully screwed sandwich mount)
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
HALF_CONN_PITCH, HALF_CONN_PINS = 1.25, 12        # Molex PicoBlade 53047 vertical (half) / 53048 right angle (controller)
HALF_CONN_INSET = 6.0        # pin row distance in from the half's inner edge
CONN_BODY_UNDER = 4.3        # vertical connector height under the half board
CTRL_CONN_X = 14.0           # controller connector pin rows at +-x (P frame), courtyards clear of the Pico headers
CTRL_MARGIN = 1.0            # controller board to pillars / interface plane
RENDER_PCB_VARIANT = "hotswap"   # which half board the 3D model, renders and checks show ("hotswap" / "solder")
TRACE_W, CLEARANCE = 0.25, 0.2
VIA_D, VIA_DRILL = 0.6, 0.3

# ---------------------------------------------------------------- board art / naming
BOARD_NAME = "Compose58"
HANDLE = "edulpn"
REVISION = "rev 1"
YEAR = 2026
TAGLINE = {"F": "static func ∘ (lhs: Half, rhs: Half) -> Keyboard",     # Swift on one face...
           "B": "@Composable fun Keyboard(lhs: Half, rhs: Half)"}         # ...Kotlin Compose on the other
CREDIT = "layout: Lily58 by kata0510"
HALF_NAMES = ("lhs", "rhs")      # left / right half, as in operator overloading
ART_TITLE_FONT = ("DejaVu Sans", "bold")
ART_CODE_FONT = ("DejaVu Sans Mono", "normal")
ART_TEXT_FONT = ("DejaVu Sans", "normal")
ART_HEX_CELL = 6.0               # silkscreen hex lattice (flat-to-flat, mm)
ART_LINE_W = 0.2                 # silkscreen line width (JLC min ~0.15)
ART_MIN_TEXT_EM = 1.2            # smallest silkscreen font size (em, mm)
ART_COPPER_KEEPOUT = 0.6         # traces kept this far from the exposed-copper title

# ---------------------------------------------------------------- rev 2 controller (rev 2 board on standoffs)
CONTROLLER = "rev2" if REV == 2 else "rev1"
CTRL_BACK_CLEAR = 0.5            # board's back edge to the bridge's back wall
STANDOFF_LENGTHS = (10, 12, 15, 20, 25)   # stock M3 male-female hex standoffs
STANDOFF_MIN_GAP = 0.5           # Pico top -> cover underside, at least
CTRL_BOSS_R = 3.6                # case post under each standoff (M3 heat-set insert)

# ---------------------------------------------------------------- rev 2: gasket mount (compose/case/gasket.py)
# Local half frame: z = 0 plate underside, PLATE_T plate top. The plate's outer FLANGE_W is a thin flange
# (FLANGE_Z0..+FLANGE_T) pinched between foam pads: a case ledge below, the frame above. Nothing screws
# through the plate or the half board; the frame screws to the case and bottoms out on it, so the pad
# squeeze is set by geometry, not torque.
FLOAT_GAP = 0.6                  # plate edge to case wall / frame skirt (sideways float)
FLANGE_W = 6.0                   # flange width inward from the plate outline
FLANGE_T = 2.0
FLANGE_Z0 = PLATE_T - FLANGE_T   # flange underside (local z): flush with the plate's top face, so the plate prints
                                 # switch side down (like rev 1) with the flange flat on the bed - no overhang
# pads = slices of off-the-shelf self-adhesive foam weatherstrip tape (closed-cell EPDM or neoprene sponge,
# 1/8 in / 3 mm thick, 3/8 in / 10 mm wide), cut across into GK_PAD_W slices with scissors
GK_T = 3.0                       # tape thickness, free (3.0-3.2 mm: 30-34 % squeeze, fine for EPDM sponge)
GK_SQUEEZE = 0.30                # designed squeeze
GK_C = GK_T * (1 - GK_SQUEEZE)   # installed thickness
GK_PAD_L, GK_PAD_W = 10.0, 4.0   # pad: tape width along the edge (9.5-10) x slice length inward
LEDGE_W = 4.5                    # case ledge under the flange, inward from the outline
LEDGE_T = 1.0                    # flat part of the ledge; under it a 60-degree stepped chamfer back to the wall
LEDGE_CHAMFER_DEG = 60.0         # from horizontal, local frame (the tent tilts it by up to 12 deg: 48 deg worst, printable)
LEDGE_TOP = FLANGE_Z0 - GK_C     # pad seat (local z)
FRAME_LIP_Z = FLANGE_Z0 + FLANGE_T + GK_C   # frame underside over the flange (local z)
SEAM_Z = FLANGE_Z0               # case wall top = frame bottom (local z)
FRAME_TOP_Z = PLATE_T + BEZEL_H  # frame top (local z), same as rev 1
FRAME_SCREWS = 6                 # per half, M3 from below into frame inserts
FRAME_BOSS_R = 4.0
FRAME_SCREW_IN = 0.5             # screw centre inside the plate outline (the plate is notched around it)
NOTCH_R = FRAME_BOSS_R + FLOAT_GAP
GK_TABS = 18                     # pad pairs per half (outer edges)
INNER_SEATS_P = ((-3.0, -13.0), (-48.5, -58.5))   # inner-edge pad pairs: P-frame y spans (back, front)
INNER_SEAT_IN = 4.5              # inner seat width under the flange, from the plate edge
PCB_INSET = LEDGE_W + 0.5        # half board outline inside the plate outline
FFC_CABLE_L = 50.0               # rev 2 controller <-> half ribbon (20-pin 1.0 mm type B): slack hangs in a U in the bay
FFC_CABLE_L_MAX = 60.0           # longest that still hangs clear of the floor (checked)
FFC_STIFFENER = 5.0              # rigid stiffener at each cable end: >= 5 mm (Molex 200528 drawing); 4 mm goes in
COVER_UPSTOP = 1.0               # cover over the plates' inner flange: clear of it by this (it doesn't clamp)
# middle (controller rev 2): the board drops onto four case posts and is clamped by four M3 male-female
# standoffs; the cover drops onto the standoffs and takes four M3 x 6 screws (nothing slides or hooks).
# Same M3 x 6 screws and M3 x 5 x 4 inserts as the frames (M3_INSERT_D / M3_INSERT_L / M3_HEAD_H / M3_CBORE_D).
