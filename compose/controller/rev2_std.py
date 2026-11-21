"""
Controller rev 2 mechanical standard (no KiCad needed): what a case must know about the board.

Board frame: origin at the Pico centre, x to the right, y toward the FRONT (KiCad's y-down), z up from the
board's top face. A case places it with the USB end at the back:  P_x = x,  P_y = y_pico_P - y.
"""
W2 = 21.5                                  # half width (43 mm)
Y_BACK, Y_FRONT = -26.0, 30.0              # board edges (56 mm); back edge at the Pico socket courtyard
CORNER_R = 2.0
PCB_T = 1.6
PICO_X, PICO_Y = 8.89, 24.13               # socket rows at x = +-8.89, pins 1/20 at y = -+24.13
# cable connectors: two Molex PicoBlade 53048-2010 (1.25 mm, 20 pos, right angle, through hole), top face, along the
# side edges with their openings outward, at fixed positions: each layout's 20-pin PicoBlade cables take up its
# angles. Slot order by physical position, slot 1 at the back. Body sizes as rev 1 modelled the 12-pin 53048 and
# 53047, its length grown with the pin count.
PB_N, PB_PITCH = 20, 1.25
PB_ROW_X = 13.0                            # |x| of the pin row
PB_Y0 = 2.0                                # centre of the row (y): the body's front end clears the front standoffs
PB_BODY_IN, PB_BODY_OUT = 1.55, 4.95       # body from the pin row toward the Pico / outward to its opening
PB_L = (PB_N - 1) * PB_PITCH + 3.2         # body length (along the row)
PB_H = 3.6                                 # body height above the board
PB_PLUG_OUT = 7.5                          # the mated plug (~3 mm past the opening) and its cable's first bend: kept clear
# the halves' connector (Molex PicoBlade 53047-2010, vertical, through hole, on each half's bottom face)
HALF_PB_UNDER = 4.3                        # body height under the half board
HALF_PB_PLUG_DROP = 12.0                   # the mated plug and its cable's first bend, under the body: kept clear
CLIP_X, CLIP_Y = 16.6, -14.3               # behind CLIP_Y the board is only 2 x CLIP_X wide (the plates' inner seats)
# four M3 x 12 male-female hex standoffs screw through the board into M3 heat-set inserts in four case posts,
# clamping it; the cover drops onto them and takes four M3 x 6 screws (the same screws and inserts as the frames)
STANDOFF_HOLES = [(-17.75, 19.5), (17.75, 19.5), (-13.7, -22.5), (13.7, -22.5)]   # front pair, back pair
M_CLEAR = 3.2                              # M3 clearance
STANDOFF_AF = 5.5                          # M3 hex standoffs are 5 or 5.5 mm across flats: sized for 5.5
STANDOFF_THREAD = 6.0                      # male thread length
STANDOFF_L = 12.0                          # M3 male-female hex standoff body (board top -> cover boss)
COVER_BOSS_R = 2.5                         # bosses under the cover land on the hex tops (5 or 5.5 AF)
COVER_BOSS_H = 1.0                         # bosses under the cover sit on the standoffs (board top -> cover underside = 13)
STANDOFF_KEEP = 3.3                        # part- and copper-free radius around each hole, top (5.5 AF hex: 3.18)
POST_R = 3.6                               # case post under each standoff (M3 x 5 x 4 insert, 4.6 mm hole: 1.3 mm wall; the
                                           #   back pair can't grow, the plates' inner seats are right beside them)
BOSS_KEEP = POST_R + 0.4                   # no through-hole lead within this radius (the case post under the board)
STACK_ABOVE_BOARD = 8.5 + 2.54 + 1.0       # female socket + Pico male-header spacer + Pico board = Pico top
LEAD_BELOW = 2.0                           # leads + solder below the board (top-side parts)
LEAD_ABOVE = 1.5                           # leads + solder on top (underside parts)
BOTTOM_PARTS_H = 13.5                      # tallest underside part (MF-RHT050 standing) + its leads
TOP_PLUG_H = 12.5                          # mated header plugs above the board (< STANDOFF_L + COVER_BOSS_H)


def outline():
    """Board outline (shapely, board frame): back narrowed behind CLIP_Y, convex corners r = CORNER_R,
    inner corners r = 1."""
    from shapely.geometry import box
    o = box(-W2, Y_BACK, W2, Y_FRONT)
    o = o.difference(box(-W2 - 1, Y_BACK - 1, -CLIP_X, CLIP_Y)).difference(box(CLIP_X, Y_BACK - 1, W2 + 1, CLIP_Y))
    return o.buffer(-CORNER_R).buffer(CORNER_R, resolution=8).buffer(1.0, resolution=8).buffer(-1.0, resolution=8)

# optional RGB: the brightness the firmware caps the LEDs at (QMK's RGB_MATRIX_MAXIMUM_BRIGHTNESS, of 255). The
# controller's circuit simulation (compose/sim/controller_spice.py, E2) works out the highest value that keeps
# 84 LEDs at full white inside USB's budget, and fails when this one is above it.
RGB_MAX_BRIGHTNESS = 32
