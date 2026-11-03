"""
Render/check model: switches, keycaps, diodes, copper wiring, controller
leads, the Pico on its socket, hardware - as trimesh meshes in world
position, grouped by material. Used by the checks (clearances) and the renders.

    python3 -m compose model [outdir]   -> outdir/render/*.stl + manifest.json
"""
import sys, json, math, os
import numpy as np, trimesh
from compose import params as PR
from compose import REPO_ROOT
from compose import geom as G
from compose.case import sandwich as PT
from types import SimpleNamespace

ST = PT.Stack
P = PR.KEY_PITCH
Z0 = G.Z0
x0, y0, _, _ = G.OUTLINE.bounds
x1, y1 = G.ANCHOR
TILTM = G.M_PW
M_L, M_R = G.M_LW, G.M_RW
S = np.diag([-1, 1, 1, 1.0])
INV_LP = np.linalg.inv(G.M_LP)
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "out"
WORLD = os.path.join(OUT_DIR, "world")


def side_x(py):
    return abs(G.interface_x(py, G.Z0))


# old-name shims used by the wiring code below
C = SimpleNamespace(Z0=G.Z0, Z_DECK=G.Z_DECK, side_x=side_x, PICO_C=(0.0, ST.pico_cy),
                    PICO_BOARD_BOTTOM=ST.pico_bot, CARRIER_BOTTOM=ST.carrier_bot, CARRIER_TOP=ST.carrier_top,
                    CARRIER_X=ST.carrier_hw, CARRIER_Y=(ST.carrier_back, ST.carrier_front),
                    PITCH_IN=PR.PERF_PITCH, CARRIER_COLS=PR.PERF_COLS, CARRIER_ROWS=PR.PERF_ROWS,
                    FEMALE_H=PR.FEMALE_HEADER_H, MALE_SPACER=PR.MALE_HEADER_SPACER, CARRIER_HOLES=ST.carrier_holes,
                    PICO_TOP_Y=PR.PICO_BACK_Y, PICO_L=PR.PICO_L, CLAMP_HW=ST.clamp_hw, CLAMP_OVERLAP=PR.CLAMP_TAB_OVERLAP,
                    COVER_SCREWS=PT.pillar_positions(), BEZ_H=PR.COVER_H, POST_SHELF=PR.POST_SHELF_T,
                    SHELF=PR.SHELF_T, WALL=PR.WALL_T)


def T(x=0, y=0, z=0):
    m = np.eye(4); m[:3, 3] = [x, y, z]; return m
def Rz(d):
    a = math.radians(d); c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1.0]])
def W(M, p):
    v = M @ np.array([p[0], p[1], p[2], 1.0]); return v[:3]
def P2L(p):
    return W(INV_LP, p)


class _Keys:
    """Adapter: layout keys as the dicts the wiring code expects."""
    @staticmethod
    def keys(side):
        lab = "label_l" if side == "L" else "label_r"
        return [dict(x=k.x, y=k.y, rot=k.rot, w=k.w, h=k.h, row=k.row, col=k.col, label=getattr(k, lab))
                for k in G.LAYOUT.keys]


class _Plate:
    THICKNESS = PR.PLATE_T
    PITCH = PR.KEY_PITCH

    @staticmethod
    def support_positions():
        return G.LAYOUT.posts
    @staticmethod
    def screw_positions():
        return G.LAYOUT.screws


LL = _Keys
SP = _Plate

os.makedirs(os.path.join(OUT_DIR, 'render'), exist_ok=True)
for _f in os.listdir(os.path.join(OUT_DIR, 'render')):          # no stale parts from another build mode
    if _f.startswith("a_") and _f.endswith(".stl"):
        os.remove(os.path.join(OUT_DIR, 'render', _f))
parts = {}
def add(name, mesh, M=None):
    m = mesh.copy()
    if M is not None: m.apply_transform(M)
    parts.setdefault(name, []).append(m)

def box(cx, cy, z0, z1, sx, sy):
    b = trimesh.creation.box(extents=[sx, sy, z1 - z0]); b.apply_translation([cx, cy, (z0+z1)/2]); return b
def cylz(x, y, r, z0, z1, sec=20):
    c = trimesh.creation.cylinder(radius=r, height=abs(z1-z0), sections=sec); c.apply_translation([x, y, (z0+z1)/2]); return c
def seg(a, b, r, sec=14):
    return trimesh.creation.cylinder(radius=r, segment=[a, b], sections=sec)
def tube(pts, r, sec=14):
    pts = [np.asarray(p, float) for p in pts]
    ms = [seg(pts[i], pts[i+1], r, sec) for i in range(len(pts)-1) if np.linalg.norm(pts[i+1]-pts[i]) > 1e-6]
    ms += [trimesh.creation.icosphere(subdivisions=1, radius=r).apply_translation(p) for p in pts[1:-1]]
    return trimesh.util.concatenate(ms)
def rrect(w, h, r, n=6):
    pts = []
    for cx, cy, a0 in ((w/2-r, h/2-r, 0), (-w/2+r, h/2-r, 90), (-w/2+r, -h/2+r, 180), (w/2-r, -h/2+r, 270)):
        for i in range(n+1):
            a = math.radians(a0 + 90*i/n); pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
    return pts
def hull_loft(w0, h0, r0, w1, h1, r1, z0, z1, dy1=0.0):
    pts = [(x, y, z0) for x, y in rrect(w0, h0, r0)] + [(x, y + dy1, z1) for x, y in rrect(w1, h1, r1)]
    return trimesh.convex.convex_hull(np.array(pts))

TH = SP.THICKNESS
PIN1, PIN2 = (-3.81, 2.54), (2.54, 5.08)
ROW_BUS_DY, ROW_BUS_Z, COL_Z = 12.5, -2.6, -0.5
COL_DX = PIN1[0] - 1.0
WIRE_R = 0.5
INNER_X = x1 - C.WALL - 2.5      # lead lane just inside the inner wall

add("plate", trimesh.load(os.path.join(WORLD, "plate_left.stl"))); add("plate", trimesh.load(os.path.join(WORLD, "plate_right.stl")))
add("case", trimesh.load(os.path.join(WORLD, "case.stl")))
add("bezel", trimesh.load(os.path.join(WORLD, "frame_left.stl"))); add("bezel", trimesh.load(os.path.join(WORLD, "frame_right.stl")))
add("cover", trimesh.load(os.path.join(WORLD, "cover.stl")))


def kpt(K, p):
    return tuple(W(K, (p[0], p[1], p[2] if len(p) > 2 else 0.0)))


def crossings(col_paths, row_paths):
    """2D crossings between column copper and row buses -> kapton sleeves."""
    out = []
    for cp in col_paths:
        for a, b in zip(cp[:-1], cp[1:]):
            for rp in row_paths:
                for c, d in zip(rp[:-1], rp[1:]):
                    A, B, Cc, D = (np.array(v[:2]) for v in (a, b, c, d))
                    r, s = B - A, D - Cc
                    den = r[0] * s[1] - r[1] * s[0]
                    if abs(den) < 1e-9:
                        continue
                    t = ((Cc - A)[0] * s[1] - (Cc - A)[1] * s[0]) / den
                    u = ((Cc - A)[0] * r[1] - (Cc - A)[1] * r[0]) / den
                    if 0.02 < t < 0.98 and 0 <= u <= 1:
                        p = A + t * r
                        dirn = r / np.linalg.norm(r)
                        out.append((p - 2.6 * dirn, p + 2.6 * dirn))
    return out


PCB = PR.MATRIX == "pcb"
if PCB:
    from compose.pcb import layout as PLY
    from shapely.geometry import Point as _Pt
    from shapely.ops import unary_union as _uu
    PLAN = PLY.plan_half()
    BT = PR.PCB_T


def slab(poly, z0, z1):
    m = trimesh.creation.extrude_polygon(poly, z1 - z0)
    m.apply_translation([0, 0, z0])
    return m


def pcb_half(side, M):
    """Half board + its underside parts, built for the left half in plate-local
    coords; the right half is the exact mirror image (the board is flipped)."""
    holes = [_Pt(x, y).buffer(PR.M3_CLEAR / 2) for x, y in PLAN.holes_m3]
    holes += [_Pt(x, y).buffer(PR.M2_CLEAR / 2) for x, y in PLAN.holes_m2]
    for k in G.LAYOUT.keys:
        holes += PLY.key_holes(k, PR.RENDER_PCB_VARIANT)
    ms = {"hpcb": [slab(PLAN.outline.difference(_uu(holes)), -BT, 0.0)], "hsocket": [], "diode": [], "band": [],
          "leg": [], "hconn": [], "solder": []}
    x0_, x1_, y0_, y1_ = PR.HS_BODY
    for ks in PLAN.keys:
        k = ks.k
        # Kailh socket in the left-half orientation (B face): the pin-1/pin-2 lobes
        # two lobes, inside the HS_BODY envelope the post solver keeps clear
        for (cx, cy), (w, h) in (((x0_ + 2.35, -2.9), (4.7, 3.8)), ((0.4, y0_ + 2.2), (9.8, 4.4))):
            pc = PLY.fp2local(k, cx, cy)
            b = box(0, 0, -BT - PR.HS_HEIGHT, -BT, w, h)
            b.apply_transform(Rz(k.rot))
            b.apply_translation([pc[0], pc[1], 0])
            ms["hsocket"].append(b)
        c, an = np.array(ks.cathode), np.array(ks.anode)
        u = (an - c) / np.linalg.norm(an - c)
        zc = -BT - 1.05
        ms["diode"].append(seg((*(c + u * 1.85), zc), (*(an - u * 1.85), zc), 0.95, 18))
        ms["band"].append(seg((*(c + u * 1.95), zc), (*(c + u * 2.45), zc), 0.97, 18))
        for p, q in ((c, c + u * 1.85), (an, an - u * 1.85)):
            ms["leg"].append(tube([(*p, 0.5), (*p, zc), (*q, zc)], 0.25, 8))
            ms["solder"].append(trimesh.creation.icosphere(subdivisions=2, radius=0.75).apply_translation([*p, 0.15]))
    if PR.CONTROLLER != "rev2":     # rev 2 halves get their FFC connector with the rev 2 half board
        b = PLAN.conn_body.bounds
        ms["hconn"].append(box((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, -BT - PR.CONN_BODY_UNDER, -BT, b[2] - b[0], b[3] - b[1]))
        for p in PLAN.conn_pins:
            ms["solder"].append(trimesh.creation.icosphere(subdivisions=2, radius=0.6).apply_translation([*p, 0.1]))
    for name, lst in ms.items():
        m = trimesh.util.concatenate(lst)
        if side == "L":
            add(name, m, M)
        else:
            add(name, m.copy().apply_transform(S), M)


pads = {}
MODS = {"Esc", "Tab", "Ctrl", "Shift", "Alt", "Gui", "Lower", "Raise", "Space", "Enter", "Bksp", "`", "-", "'", "[", "]"}


def half(side, M):
    sgn = 1 if side == "L" else -1
    ks = LL.keys(side)
    KM = {}
    for k in ks:
        K = T(sgn * k["x"], k["y"], 0) @ Rz(sgn * k["rot"])
        KM[(k["row"], k["col"])] = (K, k)
        A = M @ K
        add("switch", box(0, 0, 0.0, TH, 13.9, 13.9), A)
        add("switch", hull_loft(15.6, 15.6, 0.8, 11.6, 11.0, 1.0, TH, TH + 5.6, 0.6), A)
        add("stem", box(0, 0, TH+5.6, TH+9.4, 1.3, 4.1), A); add("stem", box(0, 0, TH+5.6, TH+9.4, 4.1, 1.3), A)
        add("swlegs", cylz(0, 0, 2.0, -3.0, 0.01), A)                     # centre post
        for sx_ in (-1, 1):                                              # plastic PCB-mount legs
            add("swlegs", cylz(sx_ * PR.MX_PEG_X, 0, PR.MX_PEG_D / 2 - 0.1, -3.0, 0.01, 14), A)
        for px, py in (PIN1, PIN2):
            add("pins", cylz(px, py, 0.5, -3.3, 0.01, 10), A)
        hcap = k["h"] * P - 1.05                                        # XDA-like stand-in cap
        cap = hull_loft(18.0, hcap, 1.2, 12.8, hcap - 5.2, 2.2, 0, 7.6)
        cap.apply_translation([0, 0, TH + 5.3])
        add("keycap2" if k["label"] in MODS else "keycap", cap, A)
        if PCB:
            continue
        ax, ay = PIN2
        ring_ = [(ax + 0.95*math.cos(t), ay + 0.95*math.sin(t), -1.6 + 0.1*t/6.28) for t in np.linspace(0, 2*math.pi*1.6, 22)]
        add("leg", tube(ring_, 0.25, 8), A)
        add("leg", tube([(ax, ay + 0.95, -1.5), (ax, ay + 1.6, -1.6)], 0.25, 8), A)
        add("diode", seg((ax, ay + 1.6, -1.6), (ax, ay + 5.4, -1.6), 0.9, 20), A)
        add("band", seg((ax, ay + 4.6, -1.6), (ax, ay + 5.0, -1.6), 0.92, 20), A)
        by = ROW_BUS_DY
        add("leg", tube([(ax, ay + 5.4, -1.6), (ax, by - 0.4, -1.6), (ax, by, ROW_BUS_Z + 0.55)], 0.25, 8), A)
        wrap = [(ax + 0.2*math.sin(t*3), by + 0.75*math.sin(t), ROW_BUS_Z + 0.75*math.cos(t)) for t in np.linspace(0, 2*math.pi*1.2, 18)]
        add("leg", tube(wrap, 0.25, 8), A)
        add("solder", trimesh.creation.icosphere(subdivisions=2, radius=0.85).apply_translation([ax, by, ROW_BUS_Z]), A)
        add("solder", trimesh.creation.icosphere(subdivisions=2, radius=0.75).apply_translation([ax, ay, -1.0]), A)
        add("solder", trimesh.creation.icosphere(subdivisions=2, radius=0.95).apply_translation([PIN1[0] - 0.5, PIN1[1], COL_Z]), A)

    if PCB:
        pcb_half(side, M)
        return KM
    # ---- row buses (staggered: jog between columns where it is clearest)
    col_bus_x = [sgn * c * P + COL_DX for c in range(6)]
    post_x = [sgn * x for x, _ in SP.support_positions()]
    def jog_x(xa, xb, xh):
        """Jog between diode legs xa -> xb, inside the higher column's
        footprint (centre xh) so the higher bus never overhangs the lower
        column's margin, away from column buses and posts."""
        lo, hi = sorted((xa, xb)); best, bx = -1, (xa + xb) / 2
        lo, hi = max(lo + 1.6, xh - P / 2 + 0.8), min(hi - 1.6, xh + P / 2 - 0.8)
        for x in np.linspace(lo, hi, 200):
            d = min([abs(x - c) for c in col_bus_x] + [abs(x - p) - 3.25 for p in post_x])
            if d > best: best, bx = d, x
        return bx
    row_paths = []
    for r in range(4):
        pts = [kpt(KM[(r, c)][0], (PIN2[0], ROW_BUS_DY, ROW_BUS_Z)) for c in range(6)]
        path = [(pts[0][0] - 3.0 * sgn, pts[0][1], ROW_BUS_Z)]
        for c, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
            path.append(a)
            if abs(a[1] - b[1]) > 1e-6:
                xh = sgn * (c if a[1] > b[1] else c + 1) * P
                jx = jog_x(a[0], b[0], xh); path += [(jx, a[1], ROW_BUS_Z), (jx, b[1], ROW_BUS_Z)]
        path += [pts[-1], (pts[-1][0] + 3.0 * sgn, pts[-1][1], ROW_BUS_Z)]
        add("copper", tube(path, WIRE_R), M); row_paths.append(path)
        pads[(side, "row", r)] = (M, path[-1])
    # row 4: thumbs (outer -> inner) then the inner key
    r4 = sorted([v for (rr, c), v in KM.items() if rr == 4], key=lambda v: v[1]["x"])
    r4 = [v for v in r4 if v[1]["label"] not in ("[", "]")] + [v for v in r4 if v[1]["label"] in ("[", "]")]
    pts = [kpt(K, (PIN2[0], ROW_BUS_DY, ROW_BUS_Z)) for K, k in r4]
    path = [kpt(r4[0][0], (PIN2[0] - 3.0, ROW_BUS_DY, ROW_BUS_Z))] + pts + [(pts[-1][0] + 3.0 * sgn, pts[-1][1], ROW_BUS_Z)]
    add("copper", tube(path, WIRE_R), M); row_paths.append(path)
    pads[(side, "row", 4)] = (M, path[-1])

    # ---- columns (bare copper lapped on pin 1) + extensions to row-4 keys
    col_paths = []
    for c in range(6):
        Kt, Kb = KM[(0, c)][0], KM[(3, c)][0]
        top = kpt(Kt, (COL_DX, PIN1[1] + 1.5, COL_Z)); bot = kpt(Kb, (COL_DX, PIN1[1] - 2.0, COL_Z))
        path = [top, bot]
        k4 = KM.get((4, c))
        jumper = None
        if k4 is not None:
            K4, kk = k4
            lt = kpt(K4, (COL_DX, PIN1[1] + 1.5, COL_Z)); lb = kpt(K4, (COL_DX, PIN1[1] - 2.0, COL_Z))
            if kk["label"] in ("[", "]"):
                # inner key: insulated jumper routed deep, under everything
                jy = bot[1] - 5.0
                jumper = [bot, (bot[0], bot[1] - 1.5, -4.2), (bot[0], jy, -4.2), (lb[0] - 1.5 * sgn, jy, -4.2),
                          (lt[0], lt[1] - 1.5, -4.2), (lt[0], lt[1] - 1.5, COL_Z), lb]
            else:
                path += [(lt[0], lt[1] + 2.5, COL_Z), lt, lb]
        add("copper", tube(path, WIRE_R), M); col_paths.append(path)
        if jumper:
            add("lead_col", tube(jumper, 0.42, 10), M)
        pads[(side, "col", c)] = (M, top)
    for a, b in crossings(col_paths, row_paths):
        add("kapton", seg((a[0], a[1], COL_Z), (b[0], b[1], COL_Z), 0.56, 18), M)
    return KM


KML = half("L", M_L)
KMR = half("R", M_R)

# ---------------- Pico ----------------
PW, PL = 21.0, 51.0
pm = TILTM @ T(C.PICO_C[0], C.PICO_C[1], C.PICO_BOARD_BOTTOM)
add("pcb", trimesh.creation.box(extents=[PW, PL, 1.0]).apply_translation([0, 0, 0.5]), pm)
pad_y = [PL/2 - 1.61 - i*2.54 for i in range(20)]
for sx in (-1, 1):
    for i, yy in enumerate(pad_y):
        add("gold", box(sx*(PW/2 - 0.8), yy, 0.98, 1.06, 1.6, 1.5), pm)
        add("gold", box(sx*(PW/2 - 0.8), yy, -0.06, 0.02, 1.6, 1.5), pm)
        add("hole", cylz(sx*PW/2, yy, 0.5, -0.07, 1.07, 12), pm)
for hx, hy in ((-5.7, 23.5), (5.7, 23.5), (-5.7, -23.5), (5.7, -23.5)):
    add("gold", cylz(hx, hy, 1.6, 0.98, 1.06, 20), pm); add("hole", cylz(hx, hy, 1.05, -0.07, 1.07, 16), pm)
add("chip", box(0, -1.0, 1.0, 1.9, 7.0, 7.0), pm)                      # RP2040
for i in range(14):                                                     # QFN pins hint
    t = -3.0 + i*6.0/13
    for (px, py, sx_, sy_) in ((t, -4.55, 0.25, 0.35), (t, 2.55, 0.25, 0.35), (-3.55, t-1, 0.35, 0.25), (3.55, t-1, 0.35, 0.25)):
        add("silver", box(px, py, 1.0, 1.15, sx_, sy_), pm)
add("chip", box(-5.0, 7.5, 1.0, 2.5, 4.0, 5.0), pm)                     # flash
for i in range(4):
    for sx in (-1, 1):
        add("silver", box(-5.0 + sx*2.35, 7.5 - 1.9 + i*1.27, 1.0, 1.6, 0.9, 0.4), pm)
add("silver", box(4.5, -9.0, 1.0, 1.8, 3.2, 2.5), pm)                   # crystal
add("button", box(-4.0, 15.5, 1.0, 2.0, 3.6, 4.6), pm)                  # BOOTSEL
add("buttoncap", cylz(-4.0, 15.5, 1.1, 2.0, 2.6, 18), pm)
add("led", box(-6.8, 20.8, 1.0, 1.5, 1.0, 1.7), pm)
add("chip", box(5.8, 13.5, 1.0, 1.9, 3.0, 3.0), pm)                     # regulator
add("inductor", box(5.8, 18.0, 1.0, 2.6, 2.6, 2.6), pm)
for (cx_, cy_) in ((2.5, 6.0), (3.6, 6.0), (-1.5, 5.0), (-2.6, 5.0), (5.0, 4.0), (5.0, 2.8), (-6.5, -5.0), (-6.5, -6.2), (2.0, -8.5), (-2.0, -8.5), (6.5, 9.5), (-7.5, 12.0), (1.0, 12.0), (2.2, 12.0)):
    add("passive", box(cx_, cy_, 1.0, 1.45, 1.0, 0.55), pm)
usb_y = PL/2 - 2.5 + 1.3
add("silver", box(0, usb_y, 1.0, 3.6, 7.6, 5.0), pm)                    # micro-USB shell
add("hole", box(0, usb_y + 2.45, 1.6, 3.0, 6.4, 0.2), pm)
for dx in (-2.54, 0, 2.54):                                             # SWD debug pads
    add("gold", cylz(dx, -PL/2 + 1.6, 0.75, 0.98, 1.06, 16), pm)
for (lx, ly, lr) in ((4.2, -17.5, 1.0), (5.6, -18.6, 1.0), (2.8, -18.6, 1.0), (4.2, -19.8, 1.0), (5.6, -21.0, 0.9), (2.8, -21.0, 0.9), (4.2, -22.0, 0.85), (3.6, -16.3, 0.6), (4.8, -16.3, 0.6)):
    add("silk", cylz(lx, ly, lr, 1.0, 1.04, 18), pm)                    # raspberry logo hint
add("silk", box(-8.2, -8.0, 1.0, 1.04, 0.5, 26.0), pm)                  # silkscreen text line


LEFT_IDX = {"row": [0, 1, 3, 4, 5], "col": [6, 8, 9, 10, 11, 13]}     # GP0-4 | GP5-10
RIGHT_IDX = {"row": [6, 8, 9, 11, ("L", 14)], "col": [13, 14, 15, 16, 18, 19]}   # GP28,27,26,22,(GP11) | GP21-16
pz_board = C.PICO_BOARD_BOTTOM
for (side, kind, i), (M, p0) in ({} if PCB else pads).items():
    sgn = 1 if side == "L" else -1
    sgnP = -1 if side == "L" else 1
    idx = (LEFT_IDX if side == "L" else RIGHT_IDX)[kind][i]
    pad_side = side
    if isinstance(idx, tuple):
        pad_side, idx = idx
    py = -12.0 if kind == "row" else -38.0
    lane = i * 1.0 - 2.5
    zc = Z0 - 6.0 + lane * 0.5
    ent_P = (sgnP * (C.side_x(py) + 6.0), py + lane * 0.7, zc)
    ent_L = P2L((-abs(ent_P[0]), ent_P[1], ent_P[2]))
    if side == "R":
        ent_L = ent_L * np.array([-1, 1, 1])
    if kind == "row":
        zl = -5.0 - 0.12 * i
        xr = sgn * min(sgn * p0[0] + 1.5 + 0.9 * i, INNER_X)
        lp = [p0, (xr, p0[1], zl), (xr, ent_L[1], zl), tuple(ent_L)]
    else:
        zl = -5.7 - 0.12 * i
        ly = 6.0 + 0.9 * i
        xi = sgn * (INNER_X - 3.3 + 0.5 * i)
        lp = [p0, (p0[0], p0[1], zl), (p0[0], ly, zl), (xi, ly, zl), (xi, ent_L[1], zl), tuple(ent_L)]
    wpts = [W(M, q) for q in lp]
    pad_y_P = C.PICO_C[1] + pad_y[idx]
    psgn = -1 if pad_side == "L" else 1
    sx9 = psgn * 8.89
    tail_z = C.CARRIER_BOTTOM - 2.2
    cz = tail_z - 1.2 - 0.35 * (i % 3)
    zlow = tail_z - 2.6 - 0.45 * (i % 4)
    xr9 = sgnP * (9.6 - 0.3 * (i % 3))
    tail_pts = [W(TILTM, (sgnP * 13.0, py + lane * 0.7, zc)), W(TILTM, (xr9, py + lane * 0.7, zlow)),
                W(TILTM, (xr9, pad_y_P, zlow))]
    if psgn != sgnP:
        tail_pts += [W(TILTM, (psgn * 9.6, pad_y_P, zlow - 0.8))]
    tail_pts += [W(TILTM, (sx9 + psgn * 0.6, pad_y_P, tail_z - 0.6)), W(TILTM, (sx9, pad_y_P, tail_z))]
    nm = "lead_row" if kind == "row" else "lead_col"
    add(nm, tube(wpts + tail_pts, 0.42, 10))
    add("stub" + nm[4:], tube([W(TILTM, ent_P)] + tail_pts, 0.42, 10))
    add("csolder", trimesh.creation.icosphere(subdivisions=2, radius=0.7).apply_translation(tail_pts[-1]))

def ctrl_rev2_model():
    """Controller rev 2 as built: board (from the routed KiCad board when present), part envelopes with their
    real heights (mated cable plugs included), Pico male headers, the four standoffs and their threads,
    through-hole leads under the board. Board frame -> P: (x, y_pc - y)."""
    from compose.controller import rev2_std as CS
    import glob
    cm_ = TILTM
    bt, bb = ST.board_top, ST.board_bot
    P_ = lambda x, y: (x, ST.y_pc - y)
    hol = _uu([_Pt(x, y).buffer(CS.M3_CLEAR / 2) for x, y in ST.standoffs])
    add("cpcb", slab(ST.outline_P.difference(hol), bb, bt), cm_)
    path = next((p for p in (os.path.join(OUT_DIR, "pcb", "controller_rev2.kicad_pcb"),
                             os.path.join(REPO_ROOT, "out", "pcb", "controller_rev2.kicad_pcb"))
                 if os.path.exists(p)), None)
    assert path, "controller_rev2.kicad_pcb not found: run `python3 -m compose controller` first"
    import pcbnew
    brd = pcbnew.LoadBoard(path)
    # heights above the board (mm) and what plugs into them
    H = {"U1": ("header", 8.5, None), "JL": ("cconn", 2.0, None), "JR": ("cconn", 2.0, None),
         "J4": ("cconn", 8.5, 13.5), "J6": ("cconn", 8.5, 13.5), "J5": ("cconn", 4.3, 10.0),
         "U2": ("chip", 5.0, None), "C1": ("passive", 6.0, None), "C2": ("passive", 7.0, None),
         "F1": ("passive", CS.TALL_PART_MAX_H, None), "R": ("passive", 3.0, None)}
    for fp in brd.GetFootprints():
        ref = fp.GetReference()
        key = next((k for k in H if ref.startswith(k)), None)
        for p in fp.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                q = p.GetPosition()
                x_, y_ = P_(pcbnew.ToMM(q.x) - 100.0, pcbnew.ToMM(q.y) - 100.0)
                add("ctail", box(x_, y_, bb - CS.LEAD_BELOW, bb, 0.8, 0.8), cm_)
        if key is None:
            continue
        fp.BuildCourtyardCaches()
        r_ = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        x0_, x1_ = pcbnew.ToMM(r_.GetLeft()) - 100.0, pcbnew.ToMM(r_.GetRight()) - 100.0
        y0_, y1_ = pcbnew.ToMM(r_.GetTop()) - 100.0, pcbnew.ToMM(r_.GetBottom()) - 100.0
        grp, h, plug = H[key]
        sh = 0.25                                       # courtyards carry margin: the body is a little smaller
        cx_, cy_ = P_((x0_ + x1_) / 2, (y0_ + y1_) / 2)
        add(grp, box(cx_, cy_, bt, bt + h, x1_ - x0_ - 2 * sh, y1_ - y0_ - 2 * sh), cm_)
        if plug:
            add("plug", box(cx_, cy_, bt + h - 3.0, bt + plug, x1_ - x0_ - 2 * sh, y1_ - y0_ - 2 * sh), cm_)
    # Pico male headers (plastic spacer + pins)
    for sx in (-1, 1):
        hx = sx * 8.89
        add("headerm", box(hx, ST.pico_cy, ST.female_top, ST.pico_bot, 2.5, 50.8), cm_)
        for yy in ST.pin_ys:
            add("pinsm", box(hx, yy, ST.pico_bot + 1.0, ST.pico_bot + 1.7, 0.64, 0.64), cm_)
    # standoffs (hex across corners) and their male threads through the board into the boss inserts
    for x_, y_ in ST.standoffs:
        add("cstandoff", cylz(x_, y_, CS.STANDOFF_AF / 2 / math.cos(math.radians(30)), bt, G.Z_DECK, 6), cm_)
        add("cscrew", cylz(x_, y_, 1.45, bb - 6.0, bt, 16), cm_)


if PR.CONTROLLER == "rev2":
    ctrl_rev2_model()
else:
    # ---- socket: perfboard carrier, female headers, male header spacer, pins, carrier screws
    cm = TILTM
    x0c, x1c = -C.CARRIER_X, C.CARRIER_X
    yb, yf = C.CARRIER_Y
    if PCB:
        CPLAN = PLY.plan_ctrl(ST, PT.pillar_positions())
        hol = _uu([_Pt(x, y).buffer(PR.M2_CLEAR / 2) for x, y in C.CARRIER_HOLES])
        add("cpcb", slab(CPLAN.outline.difference(hol), C.CARRIER_BOTTOM, C.CARRIER_TOP), cm)
        n_ = PR.HALF_CONN_PINS
        for sd, pins in CPLAN.conn.items():
            sx = -1 if sd == "L" else 1
            xm = sx * (PR.CTRL_CONN_X + (4.95 - 1.55) / 2)
            ym = (pins[0][1] + pins[-1][1]) / 2
            add("cconn", box(xm, ym, C.CARRIER_TOP, C.CARRIER_TOP + 3.6, 6.5, (n_ - 1) * PR.HALF_CONN_PITCH + 3.2), cm)
            for px_, py_ in pins:
                add("ctail", box(px_, py_, C.CARRIER_BOTTOM - 1.5, C.CARRIER_BOTTOM, 0.5, 0.5), cm)
            # mated cable plugs + a loose bundle down to the half board's plug (shown, not checked: it's flexible)
            L_ = (n_ - 1) * PR.HALF_CONN_PITCH + 3.0
            wx = sx * (CPLAN.wing_hw + 3.0)
            add("plug", box(wx, ym, C.CARRIER_TOP + 0.4, C.CARRIER_TOP + 3.4, 6.0, L_), cm)
            cb = PLAN.conn_body.bounds
            hz = -BT - PR.CONN_BODY_UNDER
            hp = box((cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2, hz - 5.5, hz + 0.01, 3.2, L_)
            hpm = hp.copy().apply_transform(M_L) if sd == "L" else hp.copy().apply_transform(S).apply_transform(M_R)
            add("plug", hpm)
            a = W(cm, (sx * (CPLAN.wing_hw + 6.0), ym, C.CARRIER_TOP + 1.9))
            bl = np.array([(cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2, hz - 5.5])
            b_ = W(M_L, bl) * (np.array([-1, 1, 1]) if sd == "R" else 1)
            mid1 = W(cm, (sx * (CPLAN.wing_hw + 9.0), ym, C.CARRIER_TOP - 3.0))
            mid2 = b_ + np.array([0, 0, -4.0])
            for off in np.linspace(-L_ / 2 + 1.5, L_ / 2 - 1.5, 4):
                o = W(cm, (0, off, 0)) - W(cm, (0, 0, 0))
                add("cable", tube([a + o, mid1 + o, mid2 + o, b_ + o], 0.55, 10))
    else:
        add("perf", box(0, (yb + yf) / 2, C.CARRIER_BOTTOM, C.CARRIER_TOP, x1c - x0c, yb - yf), cm)
    for ci in range(0 if PCB else C.CARRIER_COLS):
        gx = x0c + (ci + 0.5) * C.PITCH_IN
        for ri in range(C.CARRIER_ROWS):
            gy = yb - (ri + 0.5) * C.PITCH_IN
            add("perfpad", cylz(gx, gy, 0.9, C.CARRIER_TOP - 0.01, C.CARRIER_TOP + 0.04, 10), cm)
            add("perfhole", cylz(gx, gy, 0.5, C.CARRIER_TOP - 0.02, C.CARRIER_TOP + 0.06, 8), cm)
    pin_rows_y = [C.PICO_C[1] + yy for yy in pad_y]
    for sx in (-1, 1):
        hx = sx * 8.89
        add("header", box(hx, (pin_rows_y[0] + pin_rows_y[-1]) / 2, C.CARRIER_TOP, C.CARRIER_TOP + C.FEMALE_H, 2.5, 50.8), cm)
        add("headerm", box(hx, (pin_rows_y[0] + pin_rows_y[-1]) / 2, C.PICO_BOARD_BOTTOM - C.MALE_SPACER, C.PICO_BOARD_BOTTOM, 2.5, 50.8), cm)
        for yy in pin_rows_y:
            add("perfhole", box(hx, yy, C.CARRIER_TOP + C.FEMALE_H - 0.05, C.CARRIER_TOP + C.FEMALE_H + 0.02, 1.0, 1.0), cm)
            add("ctail", box(hx, yy, C.CARRIER_BOTTOM - 2.8, C.CARRIER_BOTTOM, 0.64, 0.64), cm)           # female header tails
            add("pinsm", box(hx, yy, C.PICO_BOARD_BOTTOM + 1.0, C.PICO_BOARD_BOTTOM + 1.7, 0.64, 0.64), cm)  # male pin tops
            add("pinsm", box(hx, yy, C.PICO_BOARD_BOTTOM - C.MALE_SPACER - 6.0, C.PICO_BOARD_BOTTOM - C.MALE_SPACER, 0.64, 0.64), cm)  # male pins (in the socket)
    for hx, hy in C.CARRIER_HOLES:
        add("cscrew", cylz(hx, hy, 1.75, C.CARRIER_TOP, C.CARRIER_TOP + 1.3, 24), cm)
        add("cscrewhex", cylz(hx, hy, 0.75, C.CARRIER_TOP + 1.25, C.CARRIER_TOP + 1.35, 6), cm)

    # foam pad on the cover's clamp tab (compressed against the Pico's front edge)
    fy0 = C.PICO_TOP_Y - C.PICO_L - 1.3
    fy1 = C.PICO_TOP_Y - C.PICO_L + C.CLAMP_OVERLAP - 0.1
    add("foam", box(0, (fy0 + fy1) / 2, C.PICO_BOARD_BOTTOM + 1.0, C.Z_DECK, 2 * (C.CLAMP_HW - 0.8), fy1 - fy0), TILTM)


# cover screws (M3 button heads, visible on top)
for cx_, cy_ in C.COVER_SCREWS:
    hd = cylz(cx_, cy_, 2.85, C.Z_DECK + C.BEZ_H, C.Z_DECK + C.BEZ_H + 1.65, 28); hd.apply_transform(TILTM); add("coverscrew", hd)
    hx = cylz(cx_, cy_, 1.0, C.Z_DECK + C.BEZ_H + 1.6, C.Z_DECK + C.BEZ_H + 1.7, 6); hx.apply_transform(TILTM); add("coverhex", hx)

for sx_, sy_ in SP.support_positions():
    head = cylz(sx_, sy_, 1.75, -C.POST_SHELF - PR.UNDER_PLATE - 1.3, -C.POST_SHELF - PR.UNDER_PLATE, 24)
    add("screw", head, M_L)
    add("screw", head.copy().apply_transform(S), M_R)
for sx_, sy_ in SP.screw_positions():
    head = cylz(sx_, sy_, 2.85, -C.SHELF - PR.UNDER_PLATE - 1.65, -C.SHELF - PR.UNDER_PLATE, 24)
    add("screw", head, M_L); add("screw", head.copy().apply_transform(S), M_R)
COLORS = {
    "hpcb": (0x1a5c34, 0.0, 0.55), "cpcb": (0x1a5c34, 0.0, 0.55), "hsocket": (0xe9e4d8, 0.0, 0.6),
    "hconn": (0xf0ece0, 0.0, 0.6), "cconn": (0xf0ece0, 0.0, 0.6), "plug": (0xf6f3ea, 0.0, 0.6),
    "cable": (0x3b3b3b, 0.0, 0.7), "swlegs": (0x26262b, 0.0, 0.6),
    "plate": (0x8c90b8, 0.0, 0.7), "switch": (0x26262b, 0.0, 0.6), "stem": (0xb3262b, 0.0, 0.5),
    "pins": (0xd6b25e, 0.7, 0.35), "keycap": (0xf1eee7, 0.0, 0.85), "keycap2": (0xd9d2c3, 0.0, 0.85),
    "leg": (0xc9c9c9, 0.8, 0.3), "diode": (0x161616, 0.0, 0.3), "band": (0xd8d8d8, 0.0, 0.5),
    "solder": (0xe2e2e2, 0.85, 0.25), "copper": (0xc8743c, 0.75, 0.3), "kapton": (0xd8901f, 0.0, 0.35),
    "stab": (0x1d1d1d, 0.0, 0.6), "stabwire": (0xcfcfcf, 0.85, 0.25),
    "pcb": (0x0f7a3a, 0.0, 0.55), "gold": (0xd8b24a, 0.8, 0.3), "hole": (0x0a0a0a, 0.0, 0.9),
    "chip": (0x1a1a1a, 0.0, 0.45), "silver": (0xc4c4c4, 0.9, 0.25), "button": (0xe8e2d0, 0.0, 0.6),
    "buttoncap": (0xf4f0e2, 0.0, 0.5), "led": (0x6fe36f, 0.0, 0.3), "inductor": (0x5a5a5a, 0.3, 0.5),
    "passive": (0x9b7d55, 0.0, 0.6), "silk": (0xf2f2f2, 0.0, 0.7),
    "lead_row": (0xc0392b, 0.0, 0.55), "lead_col": (0x2e6fd1, 0.0, 0.55),
    "cstandoff": (0xc9a24a, 0.8, 0.3), "case": (0x3a3f6e, 0.0, 0.7), "insert": (0xc9a24a, 0.8, 0.3), "dowel": (0xd0d3d6, 0.9, 0.2), "bezel": (0x3a3f6e, 0.0, 0.7), "cover": (0x3a3f6e, 0.0, 0.7), "screw": (0x1b1b1d, 0.6, 0.35), "coverscrew": (0x1b1b1d, 0.6, 0.35), "perf": (0x1f6b3a, 0.0, 0.6), "csolder": (0xe2e2e2, 0.85, 0.25), "foam": (0x2a2a2a, 0.0, 0.95), "perfpad": (0xd8b24a, 0.8, 0.3), "perfhole": (0x0a0a0a, 0.0, 0.9), "headerm": (0x151515, 0.0, 0.55), "pinsm": (0xd6b25e, 0.7, 0.35), "ctail": (0xd6b25e, 0.7, 0.35), "cscrew": (0x1b1b1d, 0.6, 0.35), "cscrewhex": (0x050505, 0.0, 0.9), "header": (0x151515, 0.0, 0.55), "stub_row": (0xc0392b, 0.0, 0.55), "stub_col": (0x2e6fd1, 0.0, 0.55), "coverhex": (0x050505, 0.0, 0.9), "screwhex": (0x050505, 0.0, 0.9),
}
manifest = []
for k, v in parts.items():
    m = trimesh.util.concatenate(v); fn = f"a_{k}.stl"; m.export(os.path.join(OUT_DIR, "render", fn))
    c, met, rough = COLORS[k]
    manifest.append({"file": fn, "color": c, "metal": met, "rough": rough, "smooth": k in ("cable", "copper","leg","lead_row","lead_col","stub_row","stub_col","kapton","stabwire","solder","diode","band","buttoncap"), "name": k})
json.dump(manifest, open(os.path.join(OUT_DIR, "render", "manifest.json"), "w"))
allm = trimesh.util.concatenate([trimesh.util.concatenate(v) for v in parts.values()])
print("parts", len(parts), "bounds", allm.bounds.round(1).tolist())
