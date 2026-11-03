"""
Printed parts. Every function returns a CadQuery solid.

  plate_local()  - left switch plate in its local frame (right = mirror)
  bezel_local()  - left bevel frame in its local frame (right = mirror)
  case_world()   - one-piece bottom case in the world frame
  cover_P()      - centre cover in the bridge (P) frame

Derived heights (P frame) for the controller stack are in pico_stack().
"""
import math
import numpy as np
import cadquery as cq
from shapely.geometry import box as sbox
from shapely.ops import unary_union
from compose import params as PR
from compose import geom as G
if PR.MATRIX == "pcb":
    from compose.pcb import layout as pcb_layout  # noqa: F401  (moves the plate posts clear of the board's parts)
from compose.geom import prism, poly_prism, cyl, union, ring, loft, big_box

L = G.LAYOUT
P = PR.KEY_PITCH
TH = PR.PLATE_T
OUT = ring(G.OUTLINE)


# ================================================================ plate
def _switch_cutter():
    h, t = PR.SWITCH_HOLE, TH
    hole = cq.Workplane("XY").rect(h, h).extrude(t + 1).translate((0, 0, -0.5))
    notch = (cq.Workplane("XY").pushPoints([(0, h / 2 + PR.CLIP_NOTCH_D / 2), (0, -h / 2 - PR.CLIP_NOTCH_D / 2)])
             .rect(PR.CLIP_NOTCH_W, PR.CLIP_NOTCH_D + 0.2).extrude(t - PR.SWITCH_CLIP_LIP))
    c = PR.PLATE_HOLE_CHAMFER
    cham = (cq.Workplane("XY").workplane(offset=t - c).rect(h, h)
            .workplane(offset=c + 0.01).rect(h + 2 * c + 0.02, h + 2 * c + 0.02).loft())
    return hole.union(notch).union(cham).val()


def trim_ring_local(width, z0, z1, end_gap=0.0):
    """Ring along the outline (width inward), stopped at the bridge's back and
    front faces (along the bridge the edge is hidden and open). The stop faces
    run along the plate's install direction; end_gap shortens the ring at each
    end (the lip uses it to clear the ends of the reveal)."""
    r = G.OUTLINE.difference(G.OUTLINE.buffer(-width, join_style="round"))
    solid = poly_prism(r, z0, z1)
    return solid.cut(G.bridge_zone_local(grow=end_gap))


def plate_local():
    plate = cq.Workplane("XY").polyline(OUT).close().extrude(TH)
    try:
        plate = plate.faces(">Z").edges().chamfer(PR.PLATE_EDGE_CHAMFER)
    except Exception:
        pass
    cut = _switch_cutter()
    cutters = [cut.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), k.rot).translate(cq.Vector(k.x, k.y, 0))
               for k in L.keys]
    plate = plate.val().cut(cq.Compound.makeCompound(cutters))
    plate = plate.cut(union([cyl(x, y, PR.M3_CLEAR / 2, -1, TH + 1) for x, y in L.screws]))
    plate = plate.cut(union([cyl(x, y, PR.M2_INSERT_D / 2, -0.01, PR.M2_PLATE_INSERT_L) for x, y in L.posts]))
    if PR.MATRIX == "pcb":
        # pockets over the board's top-side solder joints (diode leads, connector pins)
        from compose.pcb import layout as pcb_layout
        plate = plate.cut(poly_prism(pcb_layout.plan_half().pockets, -1.0, PR.JOINT_POCKET_D))
    lip = trim_ring_local(PR.TRIM_LIP_T, -PR.TRIM_LIP_H, 0.01, end_gap=PR.REVEAL_SIDE_GAP)
    return plate.fuse(lip).clean()


# ================================================================ bezel
def bridge_profile_P(z0, h, bevel, gap_side=0.0):
    """Centre-section block (P frame) from z0 up h, bevelled at the back and
    front faces like the frames; sides cut on the interface planes."""
    yb, yf = 0.0, -PR.BRIDGE_LEN
    w = 200.0
    bot = [(-w, yb), (w, yb), (w, yf), (-w, yf)]
    top = [(-w, yb - bevel), (w, yb - bevel), (w, yf + bevel), (-w, yf + bevel)]
    blk = loft(bot, z0, top, z0 + h)
    return blk.cut(G.half_space_P(-1, gap_side)).cut(G.half_space_P(1, gap_side))


def key_opening():
    cells = unary_union([G.key_poly(k) for k in L.keys]).buffer(PR.KEY_OPENING_GAP, join_style="mitre")
    r = PR.KEY_OPENING_CLOSE_R
    cells = cells.buffer(r, join_style="round").buffer(-r, join_style="round")
    c = PR.KEY_OPENING_CORNER_R
    cells = cells.buffer(-c, join_style="round").buffer(c, join_style="round").simplify(0.02)
    from shapely.geometry import Polygon
    return Polygon(cells.exterior)          # one opening, no islands left between key groups


def bezel_local():
    """Bevelled frame: ruled loft from the outline to a BEZEL_BEVEL inset copy;
    along the bridge the inner face stays on the interface plane and its ends
    follow the cover's bevelled back/front faces, so frame and cover read as
    one surface."""
    base = OUT
    top = G.miter_offset(base, PR.BEZEL_BEVEL)
    body = loft(base, TH, top, TH + PR.BEZEL_H)
    # straight inner face along the bridge: the cover's profile, extended into the half
    reach = PR.BEZEL_BEVEL + 3.0
    straight_P = bridge_profile_P(G.Z_DECK, PR.BEZEL_H, PR.COVER_BEVEL, gap_side=0.0)
    wide_P = bridge_profile_P(G.Z_DECK, PR.BEZEL_H, PR.COVER_BEVEL, gap_side=-reach)
    band_L = G.P2L(wide_P.cut(straight_P))          # the half-side strip next to the bridge
    body = body.fuse(prism(base, TH, TH + PR.BEZEL_H).intersect(band_L)).clean()
    body = body.cut(poly_prism(key_opening(), TH - 1, TH + PR.BEZEL_H + 1))
    body = body.cut(union([cyl(x, y, PR.M3_INSERT_D / 2, TH - 0.5, TH + PR.M3_INSERT_L) for x, y in L.screws]))
    return body.clean()


# ================================================================ controller stack (P frame)
def _stack():
    """Heights and positions of the Pico, its socket headers and the perfboard
    carrier, all derived from params (P frame)."""
    from types import SimpleNamespace
    s = SimpleNamespace()
    s.pico_top = G.Z_DECK - PR.CLAMP_GAP
    s.pico_bot = s.pico_top - PR.PICO_T
    s.female_top = s.pico_bot - PR.MALE_HEADER_SPACER
    s.carrier_top = s.female_top - PR.FEMALE_HEADER_H
    s.carrier_bot = s.carrier_top - PR.PERF_T
    s.tail_bot = s.carrier_bot - PR.HEADER_TAIL
    s.pico_back = PR.PICO_BACK_Y
    s.pico_front = PR.PICO_BACK_Y - PR.PICO_L
    s.pico_cy = PR.PICO_BACK_Y - PR.PICO_L / 2
    s.pin1_y = PR.PICO_BACK_Y - PR.PICO_PIN1_FROM_END
    s.pin_ys = [s.pin1_y - i * PR.PICO_PIN_PITCH for i in range(PR.PICO_PINS_PER_SIDE)]
    s.carrier_back = s.pin1_y + PR.PERF_PITCH / 2
    s.carrier_front = s.pin1_y - (PR.PERF_ROWS - 0.5) * PR.PERF_PITCH
    s.carrier_cy = (s.carrier_back + s.carrier_front) / 2
    s.carrier_hw = PR.PERF_COLS * PR.PERF_PITCH / 2
    gx, gy = PR.CARRIER_SCREW_GRID
    s.carrier_holes = [(sx * gx * PR.PERF_PITCH, s.carrier_cy + sy * gy * PR.PERF_PITCH)
                       for sx in (-1, 1) for sy in (-1, 1)]
    s.window_hw = PR.PICO_W / 2 - PR.WINDOW_EDGE_OVER_PCB
    s.window_front = s.pico_front - PR.WINDOW_FRONT_MARGIN
    s.clamp_hw = PR.PICO_PIN_ROW_X - 1.7          # between the header rows, clear of the pin tops
    if PR.CONTROLLER == "rev2":
        _stack_rev2(s)
    return s


def _stack_rev2(s):
    """Controller rev 2: the board sits on four case bosses, clamped by M3 male-female standoffs that carry the
    cover. Pico height from the stock standoff length; board placed back against the bridge's back wall."""
    from compose.controller import rev2_std as CS
    need = CS.STACK_ABOVE_BOARD + PR.STANDOFF_MIN_GAP
    s.standoff_len = min(L_ for L_ in PR.STANDOFF_LENGTHS if L_ >= need)
    s.board_top = G.Z_DECK - s.standoff_len
    s.board_bot = s.board_top - CS.PCB_T
    s.pico_top = s.board_top + CS.STACK_ABOVE_BOARD
    s.pico_bot = s.pico_top - PR.PICO_T
    s.female_top = s.pico_bot - PR.MALE_HEADER_SPACER
    s.y_pc = -PR.BRIDGE_WALL_T - PR.CTRL_BACK_CLEAR + CS.Y_BACK      # Pico centre, P frame
    s.pico_back = s.y_pc + CS.PICO_HALF_L
    s.pico_front = s.y_pc - CS.PICO_HALF_L
    s.pico_cy = s.y_pc
    s.pin1_y = s.y_pc + CS.PICO_Y
    s.pin_ys = [s.pin1_y - i * PR.PICO_PIN_PITCH for i in range(PR.PICO_PINS_PER_SIDE)]
    s.to_P = lambda x, y: (x, s.y_pc - y)                         # board frame -> P frame
    s.standoffs = [s.to_P(x, y) for x, y in CS.COVER_HOLES]
    s.outline_P = _ctrl_outline_P(s)
    s.board_front = s.y_pc - CS.Y_FRONT
    s.window_hw = PR.PICO_W / 2 - PR.WINDOW_EDGE_OVER_PCB
    s.window_front = s.pico_front - PR.WINDOW_FRONT_MARGIN
    s.carrier_holes = []
    # legacy names some callers read
    s.carrier_top, s.carrier_bot = s.board_top, s.board_bot
    s.carrier_back, s.carrier_front = s.y_pc - CS.Y_BACK, s.board_front
    s.carrier_cy, s.carrier_hw = s.y_pc, CS.W2


def _ctrl_outline_P(s):
    from compose.controller import rev2_std as CS
    from shapely.affinity import scale as _sc, translate as _tr
    return _tr(_sc(CS.outline(), 1.0, -1.0, origin=(0, 0)), 0.0, s.y_pc)


Stack = _stack()


def pillar_positions():
    """Cover screw pillars: as far out as possible while staying FIT_GAP clear
    of the plate (the interface plane is narrowest at plate-underside level).
    Controller rev 2: the cover screws into the standoffs instead."""
    if PR.CONTROLLER == "rev2":
        return list(Stack.standoffs)
    out = []
    for y in PR.COVER_SCREW_Y:
        x = abs(G.interface_x(y, G.Z0)) - PR.PILLAR_R - PR.FIT_GAP - 0.2
        out += [(-x, y), (x, y)]
    return out


# ================================================================ case
DEEP = -200.0


def _bridge_block_P(y_back, y_front, z0, z1, reach):
    """P-frame block between y_front..y_back, sides on the interface planes
    moved `reach` into each half (reach < 0: stops short of the planes)."""
    w = 300.0
    blk = prism([(-w, y_back), (w, y_back), (w, y_front), (-w, y_front)], z0, z1)
    return blk.cut(G.half_space_P(-1, -reach)).cut(G.half_space_P(1, -reach))


def floor_details_world(cav_world):
    """Hex rib lattice on the floor of each half + 45-degree flares at the base
    of every post. Kept WIRE_KEEPOUT below the plates."""
    d = PR.FLOOR_RIB_CELL
    R = d / math.sqrt(3)
    t = PR.FLOOR_RIB_T
    f = PR.FLOOR_T
    hexes = []
    for i in range(-15, 16):
        for j in range(-11, 3):
            cx, cy = i * 1.5 * R, j * d + (d / 2 if i % 2 else 0) - 50.0
            rr = R - t / math.sqrt(3)
            pts = [(cx + rr * math.cos(math.radians(60 * k)), cy + rr * math.sin(math.radians(60 * k))) for k in range(6)]
            hexes.append(prism(pts, f - 1, f + PR.FLOOR_RIB_H + 1))
    slab = big_box(-200, 200, -200, 60, f - 0.01, f + PR.FLOOR_RIB_H)
    ribs = slab.cut(cq.Compound.makeCompound(hexes)).intersect(cav_world)

    def floor_pt(M, x, y):
        a, b = G.apply(M, (x, y, 0.0)), G.apply(M, (x, y, 1.0))
        k = (f - a[2]) / (b[2] - a[2])
        return a[0] + k * (b[0] - a[0]), a[1] + k * (b[1] - a[1])

    def flare(x, y, r):
        return cq.Solid.makeCone(r + PR.POST_FLARE, max(r - 0.3, 0.5), PR.POST_FLARE + 0.01,
                                 cq.Vector(x, y, f - 0.01), cq.Vector(0, 0, 1))
    fl = []
    for pts, r in ((L.screws, PR.BOSS_R), (L.posts, PR.POST_R)):
        for x, y in pts:
            fx, fy = floor_pt(G.M_LW, x, y)
            fl += [flare(fx, fy, r), flare(-fx, fy, r)]
    ctrl = (((Stack.standoffs, PR.CTRL_BOSS_R),) if PR.CONTROLLER == "rev2" else
            ((Stack.carrier_holes, PR.CARRIER_POST_R), (pillar_positions(), PR.PILLAR_R)))
    for pts, r in ctrl:
        for x, y in pts:
            fx, fy = floor_pt(G.M_PW, x, y)
            fl.append(flare(fx, fy, r))
    det = ribs.fuse(union(fl))
    keep = G.L2W(prism(ring(G.OUTLINE.buffer(5.0)), -PR.WIRE_KEEPOUT, 80.0))
    return det.cut(keep).cut(keep.mirror("YZ")).clean()


def case_world():
    W = PR.WALL_T
    reveal_w = PR.TRIM_LIP_T + PR.REVEAL_SIDE_GAP
    reveal_h = PR.TRIM_LIP_H + PR.REVEAL_SHADOW
    inn = ring(G.OUTLINE.buffer(-W, join_style="round").simplify(0.02))

    # ---- halves (local), then both into the world
    tub = prism(OUT, DEEP, 0.0).cut(trim_ring_local(reveal_w, -reveal_h, 1.0))
    cav = prism(inn, DEEP, 1.0)
    tubL, cavL = G.L2W(tub), G.L2W(cav)
    tubR, cavR = tubL.mirror("YZ"), cavL.mirror("YZ")

    # ---- centre section (P): outer block, interior, plate clearance at the top
    yb, yf = 0.0, -PR.BRIDGE_LEN
    BW = PR.BRIDGE_WALL_T
    zl = G.Z0
    lower = _bridge_block_P(yb, yf, DEEP, zl, 0.0)
    upper = _bridge_block_P(yb, yf, zl, G.Z_DECK, -PR.FIT_GAP)    # clear of the plate edge
    bridge = G.P2W(lower.fuse(upper))
    interior = G.P2W(_bridge_block_P(yb - BW, yf + BW, DEEP, G.Z_DECK + 1, W + 1.0))


    body = union([tubL, tubR, bridge]).intersect(big_box(-500, 500, -500, 500, 0, 500))
    hollow = union([cavL, cavR, interior]).intersect(big_box(-500, 500, -500, 500, PR.FLOOR_T, 500))
    body = body.cut(hollow)


    # ---- posts, bosses, pillars, carrier posts, floor details
    st = Stack
    U = PR.UNDER_PLATE                     # the half board sits between the plate and the bosses/posts
    bosses = [cyl(x, y, PR.BOSS_R, DEEP, -U) for x, y in L.screws]
    bosses += [cyl(x, y, PR.POST_R, DEEP, -U) for x, y in L.posts]
    bosses = union(bosses)
    bossL = G.L2W(bosses)
    if PR.CONTROLLER == "rev2":     # bosses under the board's standoffs; the board sits on their tops
        cposts = G.P2W(union([cyl(x, y, PR.CTRL_BOSS_R, DEEP, st.board_bot) for x, y in st.standoffs]))
        pillars = None
    else:
        cposts = G.P2W(union([cyl(x, y, PR.CARRIER_POST_R, DEEP, st.carrier_bot) for x, y in st.carrier_holes]))
        pillars = G.P2W(union([cyl(x, y, PR.PILLAR_R, DEEP, G.Z_DECK) for x, y in pillar_positions()]))
    details = floor_details_world(union([cavL, cavR])).intersect(hollow)
    add = union([s_ for s_ in (bossL, bossL.mirror("YZ"), cposts, pillars, details) if s_ is not None]
                ).intersect(big_box(-500, 500, -500, 500, 0, 500))
    body = body.fuse(add).clean()
    if PR.CONTROLLER == "rev2":     # the controller's envelope (board + leads below, everything above) is kept clear,
        from compose.controller import rev2_std as CS  # except its own bosses
        keep = prism(list(Stack.outline_P.buffer(0.45, join_style="mitre").exterior.coords)[:-1],
                     Stack.board_bot - CS.LEAD_BELOW - 0.6, G.Z_DECK + 1)
        keep = keep.cut(union([cyl(x, y, PR.CTRL_BOSS_R, DEEP, st.board_bot) for x, y in st.standoffs]))
        body = body.cut(G.P2W(keep)).clean()

    # ---- holes
    cb = [cyl(x, y, PR.M3_CBORE_D / 2, DEEP - 10, -U - PR.SHELF_T) for x, y in L.screws]
    cb += [cyl(x, y, PR.M3_CLEAR / 2, -U - PR.SHELF_T - 1, 1.0) for x, y in L.screws]
    cb += [cyl(x, y, PR.M2_CBORE_D / 2, DEEP - 10, -U - PR.POST_SHELF_T) for x, y in L.posts]
    cb += [cyl(x, y, PR.M2_CLEAR / 2, -U - PR.POST_SHELF_T - 1, 1.0) for x, y in L.posts]
    cbL = G.L2W(union(cb))
    body = body.cut(cbL).cut(cbL.mirror("YZ"))
    if PR.CONTROLLER == "rev2":
        # deep enough for the insert plus the standoff's 6 mm male thread
        holes_P = [cyl(x, y, PR.M3_INSERT_D / 2, st.board_bot - PR.M3_INSERT_L - 2.0, st.board_bot + 1) for x, y in st.standoffs]
    else:
        holes_P = [cyl(x, y, PR.M2_INSERT_D / 2, st.carrier_bot - PR.M2_INSERT_L, st.carrier_bot + 1) for x, y in st.carrier_holes]
        holes_P += [cyl(x, y, PR.M3_INSERT_D / 2, G.Z_DECK - PR.M3_INSERT_L, G.Z_DECK + 1) for x, y in pillar_positions()]
    usb_z = st.pico_bot - PR.USB_NOTCH_BELOW_PCB
    holes_P.append(big_box(-PR.USB_NOTCH_W / 2, PR.USB_NOTCH_W / 2, -BW - 3.0, 3.0, usb_z, G.Z_DECK + 10))
    body = body.cut(G.P2W(union(holes_P)))

    # ---- rubber feet recesses
    feet = []
    for x, y in L.feet:
        p = G.apply(G.M_LW, (x, y, 0))
        feet += [cyl(p[0], p[1], PR.FOOT_D / 2, -1, PR.FOOT_DEPTH), cyl(-p[0], p[1], PR.FOOT_D / 2, -1, PR.FOOT_DEPTH)]
    for sx in (-1, 1):
        y = yf + 8.0
        p = G.apply(G.M_PW, (sx * (abs(G.interface_x(y, G.Z0)) - 8.0), y, 0))
        feet.append(cyl(p[0], p[1], PR.FOOT_D / 2, -1, PR.FOOT_DEPTH))
    body = body.cut(union(feet)).clean()
    sol = body.Solids()
    if len(sol) > 1:      # drop slivers some angle combinations leave (floor ribs, wall offcuts): keep the case itself
        big = max(sol, key=lambda s_: s_.Volume())
        assert all(s_.Volume() < 2.0 for s_ in sol if s_ is not big), "case splits into real pieces"
        body = big
    return body


# ================================================================ cover
def cover_P():
    st = Stack
    body = bridge_profile_P(G.Z_DECK, PR.COVER_H, PR.COVER_BEVEL, gap_side=PR.FIT_GAP)
    z0, z1 = G.Z_DECK - 1, G.Z_DECK + PR.COVER_H + 1
    win = big_box(-st.window_hw, st.window_hw, st.window_front, 20.0, z0, z1)
    if PR.CONTROLLER == "rev2":     # the Pico sits in its sockets on a clamped board: no clamp tab
        body = body.cut(win)
    else:
        tab = big_box(-st.clamp_hw, st.clamp_hw, st.window_front - 1.0, st.pico_front + PR.CLAMP_TAB_OVERLAP, z0 - 1, z1 + 1)
        body = body.cut(win.cut(tab))
    body = body.cut(union([cyl(x, y, PR.M3_CLEAR / 2, z0, z1) for x, y in pillar_positions()]))
    return body.clean()
