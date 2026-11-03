"""
PCB geometry shared by the KiCad generator (compose/pcb/kicad.py), the case/plate
(plate pockets, stack heights) and the 3D/render model. Pure Python + shapely.

Half board: drawn for the LEFT half in plate-local coordinates (x right, y up,
z = 0 at the plate underside). The board is reversible: the right half is the
same board flipped over, which mirrors it exactly onto the right plate.
  left  half: switches on F, sockets/diodes/connector on B
  right half: board flipped, switches on B, sockets/diodes/connector on F

Controller board: P frame (bridge), replaces the perfboard carrier.
"""
import math
from types import SimpleNamespace
from shapely.geometry import Point, Polygon, LineString, box as sbox
from shapely.affinity import rotate as srot, translate as strans
from shapely.ops import unary_union
from compose import params as PR
from compose import geom as G
from compose import layout as layouts

L = G.LAYOUT


# ---------------------------------------------------------------- frames
def fp2local(k, fx, fy):
    """Footprint coords (KiCad, y down) of key k -> plate-local (y up)."""
    return layouts.key_point(k, fx, -fy)


def mirror_fp(p):
    return (-p[0], p[1])


# ---------------------------------------------------------------- outline
def half_outline():
    """Inside the case cavity; along the bridge stretch the cavity is open, so
    the board runs out to the interface plane (minus the edge gap)."""
    inn = G.OUTLINE.buffer(-(PR.WALL_T + PR.PCB_EDGE_GAP), join_style="round")
    ax = G.ANCHOR[0]
    yb, yf = G.bridge_stretch_local()
    s = PR.BRIDGE_WALL_T + PR.PCB_EDGE_GAP + 1.0
    strip = sbox(ax - PR.WALL_T - 2.0, yf + s, ax - PR.PCB_EDGE_GAP, yb - s)
    o = unary_union([inn, strip.intersection(G.OUTLINE.buffer(-PR.PCB_EDGE_GAP))])
    o = o.buffer(1.0, join_style="round").buffer(-1.0, join_style="round")   # tidy the joins
    return o.simplify(0.02)


# ---------------------------------------------------------------- per-key features
def switch_cutout(k, grow=0.6):
    """Plate switch hole (+ grow) in plate-local coords: pockets must stay clear."""
    return G.key_poly(k, PR.SWITCH_HOLE, grow=grow)


def socket_body(k):
    """Socket body region for both orientations (one is on each face)."""
    x0, x1, y0, y1 = PR.HS_BODY
    pts = [fp2local(k, x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    return Polygon(pts)


def bottom_keepout(k):
    """Everything that sticks out of a half board's underside at key k, for
    BOTH faces (the board is reversible): socket bodies and tabs, switch pins
    and solder joints, the centre post and pegs."""
    x0, x1, y0, y1 = PR.HS_BODY
    loc = lambda p: fp2local(k, *p)
    shapes = [Polygon([loc((x, y)) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])]
    for (c, sz) in (PR.HS_PAD2, PR.HS_PAD1):
        for cc in (c, mirror_fp(c)):
            w, h = sz
            shapes.append(Polygon([loc((cc[0] + dx * w / 2, cc[1] + dy * h / 2)) for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]))
    for p in (PR.MX_PIN1, PR.MX_PIN2):
        for pp in (p, mirror_fp(p)):
            shapes.append(Point(loc(pp)).buffer(PR.HS_HOLE_D / 2))
    shapes.append(Point(loc((0, 0))).buffer(PR.MX_CENTER_D / 2 + 0.3))
    for sx in (-1, 1):
        shapes.append(Point(loc((sx * PR.MX_PEG_X, 0))).buffer(PR.MX_PEG_D / 2 + 0.3))
    return unary_union(shapes)


def key_holes(k, variant="hotswap"):
    """Every hole a switch footprint drills, as shapely shapes in plate-local
    coords: centre post, both plastic legs, and the pin holes for BOTH
    orientations (hotswap: merged into two slots; solder: four plated holes)."""
    loc = lambda p: Point(fp2local(k, *p))
    out = [loc((0, 0)).buffer(PR.MX_CENTER_D / 2)]
    out += [loc((sx * PR.MX_PEG_X, 0)).buffer(PR.MX_PEG_D / 2) for sx in (-1, 1)]
    p1, p2 = PR.MX_PIN1, PR.MX_PIN2
    if variant == "hotswap":
        for a, c in ((p1, mirror_fp(p2)), (p2, mirror_fp(p1))):
            out.append(LineString([fp2local(k, *a), fp2local(k, *c)]).buffer(PR.HS_HOLE_D / 2))
    else:
        out += [loc(p).buffer(PR.MX_PTH_DRILL / 2) for p in (p1, p2, mirror_fp(p1), mirror_fp(p2))]
    return out


def connector_zone():
    ax = G.ANCHOR[0]
    yb, yf = G.bridge_stretch_local()
    cx, cy = ax - PR.HALF_CONN_INSET, (yb + yf) / 2
    n, p = PR.HALF_CONN_PINS, PR.HALF_CONN_PITCH
    pins = [(cx, cy + (n - 1) * p / 2 - i * p) for i in range(n)]
    body = sbox(cx - 2.55, pins[-1][1] - 2.0, cx + 1.65, pins[0][1] + 2.0)
    return pins, body


def solve_posts(posts, search=16.0, step=0.5):
    """Move each plate-support post to the nearest spot where the case post's
    contact disc clears all underside parts and the plate insert sits in solid
    plate. Returns the new list (same order)."""
    keep = unary_union([bottom_keepout(k) for k in L.keys] + [connector_zone()[1]]).buffer(0.3)
    cuts = unary_union([switch_cutout(k, grow=0.0) for k in L.keys])
    board = half_outline().buffer(-(PR.POST_R + 0.5))
    plate_r = PR.M2_INSERT_D / 2 + 0.8
    out = []
    for (x0, y0) in posts:
        best = None
        n = int(search / step)
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                x, y = x0 + i * step, y0 + j * step
                d = math.hypot(x - x0, y - y0)
                if d > search or (best and d >= best[0]):
                    continue
                pt = Point(x, y)
                if not board.contains(pt) or pt.distance(keep) < PR.POST_R or pt.distance(cuts) < plate_r:
                    continue
                if any(math.hypot(x - a, y - b) < 2 * PR.POST_R + 2 for a, b in out):
                    continue
                best = (d, (x, y))
        if best is None:
            raise RuntimeError(f"no place for the plate post near ({x0:.1f}, {y0:.1f})")
        out.append(best[1])
    return out


def check_bosses():
    keep = unary_union([bottom_keepout(k) for k in L.keys] + [connector_zone()[1]])
    return [(x, y, round(Point(x, y).distance(keep) - PR.BOSS_R, 2)) for x, y in L.screws
            if Point(x, y).distance(keep) < PR.BOSS_R + 0.3]


def _diode_candidates():
    """Diode placements in footprint coords: (pad cathode, pad anode)."""
    h = PR.DIODE_PITCH / 2
    out = []
    for c in (0.0, 1.0, -1.0, 2.0, -2.0, 3.0, -3.0):
        for ux in (9.525, -9.525):
            out.append(((ux, c + h), (ux, c - h)))           # vertical in the column gap
    for c in (0.0, 1.5, -1.5, 3.0, -3.0):
        for vy in (9.525, -9.525):
            out.append(((c - h, vy), (c + h, vy)))           # horizontal in the row gap
    return out


def plan_half():
    """Place everything on the half board; returns a namespace with all
    features in plate-local coords and per-key footprint data."""
    s = SimpleNamespace()
    s.outline = half_outline()
    cut_all = unary_union([switch_cutout(k) for k in L.keys])
    # plate side: insert/clearance holes; board underside: the case bosses and posts
    holes = unary_union([Point(x, y).buffer(PR.M3_CLEAR / 2 + 1.0) for x, y in L.screws] +
                        [Point(x, y).buffer(PR.M2_INSERT_D / 2 + 1.0) for x, y in L.posts])
    supports = unary_union([Point(x, y).buffer(PR.BOSS_R + 0.3) for x, y in L.screws] +
                           [Point(x, y).buffer(PR.POST_R + 0.3) for x, y in L.posts])
    bodies = unary_union([socket_body(k) for k in L.keys])
    inside = s.outline.buffer(-1.0)

    # connector: vertical, pin row along the inner edge inside the bridge stretch
    s.conn_pins, s.conn_body = connector_zone()                                 # pad 1 at the back end
    s.conn_slot = LineString([s.conn_pins[0], s.conn_pins[-1]]).buffer(PR.JOINT_POCKET_R)
    taken = unary_union([s.conn_slot, s.conn_body.buffer(0.5)])

    s.keys = []
    pockets = []
    for i, k in enumerate(L.keys):
        best = None
        for cat, an in _diode_candidates():
            pc, pa = fp2local(k, *cat), fp2local(k, *an)
            pk = unary_union([Point(pc).buffer(PR.JOINT_POCKET_R), Point(pa).buffer(PR.JOINT_POCKET_R)])
            body = LineString([pc, pa]).buffer(PR.DIODE_BODY[1] / 2 + 0.9)
            if pk.intersects(cut_all) or pk.intersects(holes) or not inside.contains(body):
                continue
            if body.intersects(bodies) or body.intersects(taken) or body.intersects(supports):
                continue
            best = (pc, pa, pk, body)
            break
        if best is None:
            raise RuntimeError(f"no room for the diode of key {k.label_l} (row {k.row}, col {k.col})")
        pc, pa, pk, body = best
        taken = unary_union([taken, pk.buffer(0.3), body])
        pockets.append(pk)
        s.keys.append(SimpleNamespace(i=i, k=k, cathode=pc, anode=pa,
                                      row=k.row, col=k.col, ref=f"SW{i + 1}", dref=f"D{i + 1}"))
    s.pockets = unary_union(pockets + [s.conn_slot])
    s.holes_m3 = list(L.screws)
    s.holes_m2 = list(L.posts)
    return s


def half_nets():
    """Connector pad -> net (half board).

    STABLE INTERFACE: the controller board, the half-to-controller wiring and the QMK pin map
    (LEFT_GPIO / RIGHT_GPIO, firmware.py) all depend on this. Positions 1-5 = ROW0-4,
    6-11 = COL0-5, 12 = NC (GND on the controller). Future layouts should keep it (up to 5x6 keys
    per half) so they reuse the same controller and firmware config; see README "Controller interface"."""
    nets = {i + 1: f"ROW{i}" for i in range(5)}
    nets.update({6 + i: f"COL{i}" for i in range(6)})
    nets[12] = None
    return nets


# ---------------------------------------------------------------- controller board (P frame)
PICO_PIN_GPIO = {1: 0, 2: 1, 4: 2, 5: 3, 6: 4, 7: 5, 9: 6, 10: 7, 11: 8, 12: 9, 14: 10, 15: 11, 16: 12, 17: 13,
                 19: 14, 20: 15, 21: 16, 22: 17, 24: 18, 25: 19, 26: 20, 27: 21, 29: 22, 31: 26, 32: 27, 34: 28}
PICO_GND_PINS = (3, 8, 13, 18, 23, 28, 33, 38)
LEFT_GPIO = {"ROW": [0, 1, 2, 3, 4], "COL": [5, 6, 7, 8, 9, 10]}            # in Pico pin order along the connector
RIGHT_GPIO = {"ROW": [15, 16, 17, 18, 19], "COL": [20, 21, 22, 26, 27, 28]}   # in Pico pin order along the reversed connector: no crossings


def pico_pin_xy(pin, stack):
    """Pico pin -> P-frame (x, y). USB end at +y; pins 1-20 down the left, 21-40 up the right."""
    if pin <= 20:
        return (-PR.PICO_PIN_ROW_X, stack.pin_ys[pin - 1])
    return (PR.PICO_PIN_ROW_X, stack.pin_ys[40 - pin])


def ctrl_conn_nets(side):
    """Controller connector pad -> net. Cable is straight through (pin k to pin k).
    The right half board is flipped, so its connector's physical pin k sits on
    footprint pad 13-k: the right connector here is wired in reverse."""
    hn = half_nets()
    gp = LEFT_GPIO if side == "L" else RIGHT_GPIO
    out = {}
    for k in range(1, PR.HALF_CONN_PINS + 1):
        pad = k if side == "L" else PR.HALF_CONN_PINS + 1 - k
        net = hn[pad]
        if net is None:
            out[k] = "GND"
        else:
            kind, idx = net[:3], int(net[3:])
            out[k] = f"GP{gp[kind][idx]}"
    return out


def plan_ctrl(stack, pillars):
    s = SimpleNamespace()
    n, p = PR.HALF_CONN_PINS, PR.HALF_CONN_PITCH
    py = [y for _, y in pillars]
    y_hi, y_lo = max(py) - PR.PILLAR_R - PR.CTRL_MARGIN, min(py) + PR.PILLAR_R + PR.CTRL_MARGIN
    cy = (y_hi + y_lo) / 2
    s.conn = {}
    for side, sx in (("L", -1), ("R", 1)):
        pins = [(sx * PR.CTRL_CONN_X, cy + (n - 1) * p / 2 - i * p) for i in range(n)]
        s.conn[side] = pins
    # outline: carrier rectangle + wings for the connectors, minus the pillars
    hw0 = PR.PICO_PIN_ROW_X + PR.FEMALE_HEADER_W / 2 + 0.6
    body = sbox(-hw0, stack.carrier_front, hw0, stack.carrier_back)
    wing_hw = PR.CTRL_CONN_X + 4.95 + 0.05
    wings = sbox(-wing_hw, cy - (n - 1) * p / 2 - 2.6, wing_hw, cy + (n - 1) * p / 2 + 2.6)
    o = unary_union([body, wings])
    for x, y in pillars:
        o = o.difference(Point(x, y).buffer(PR.PILLAR_R + PR.CTRL_MARGIN))
    s.outline = o.buffer(0.5, join_style="round").buffer(-0.5, join_style="round").simplify(0.02)
    s.wing_hw = wing_hw
    s.span = (y_lo, y_hi)
    return s


ORIGINAL_POSTS = list(L.posts)
if PR.MATRIX == "pcb":
    L.posts[:] = solve_posts(ORIGINAL_POSTS)          # shared with the case, plate, BOM and checks


if __name__ == "__main__":
    from compose.case import sandwich as PT
    for a, b in zip(ORIGINAL_POSTS, L.posts):
        print("post", [round(v, 1) for v in a], "->", [round(v, 1) for v in b])
    print("bosses touching board parts:", check_bosses())
    h = plan_half()
    print("half board", [round(v, 1) for v in h.outline.bounds], "area", round(h.outline.area))
    print("diodes placed:", len(h.keys), "connector at", [round(v, 2) for v in h.conn_pins[0]], [round(v, 2) for v in h.conn_pins[-1]])
    c = plan_ctrl(PT.Stack, PT.pillar_positions())
    print("controller", [round(v, 1) for v in c.outline.bounds], "conn span", [round(v, 1) for v in c.span])
    print("L", ctrl_conn_nets("L"))
    print("R", ctrl_conn_nets("R"))
