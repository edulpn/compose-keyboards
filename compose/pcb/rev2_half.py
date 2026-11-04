"""
Rev 2 half boards (controller rev 2 standard):  C58_REV=2 python3 -m compose half-rev2 OUT [board ...]

  half_rev2_hotswap / half_rev2_solder           no LEDs: RGB data passes straight through (slot 3 -> slot 18)
  half_rev2_hotswap_rgb / half_rev2_solder_rgb   an SK6812 MINI-E under every switch, chained, 100 nF per 3 LEDs

One reversible board serves both halves, as on rev 1: the left half has its switches on F and everything else
on B; the right half is the same board flipped (switches on B, the rest on F). So every one-sided part has a
copy on each face (hotswap sockets, LEDs, capacitors, the cable connector) and only the bottom face's copies
are fitted. Through-hole parts (diodes, solder-in switches) serve both.

  - Outline: the plate outline less PCB_INSET (inside the gasket pads). No case screws go through it: the
    board hangs from the plate on four M2 screws into heat-set inserts in the plate (posts solved here).
  - Matrix: the layout's (row, col), COL2ROW, a through-hole diode per key in the same spot at every key.
  - Cable: Molex 200528-0200 FFC connector (20 pos, 1.0 mm, bottom contact) on the bottom face along the
    inner edge, centred on the controller connector's row (bridge-frame y). The ribbon hangs in a slack U
    between the two boards. Contacts get their nets by physical position: the back-most contact is slot 1,
    as on the controller (type B cable, same physical order at both ends).
  - Slots: 1 GND, 2 5V, 3 RGB in, 4 GND, 5-11 COL0-6, 12-17 ROW0-5, 18 RGB out, 19 5V, 20 GND.

Coordinates: plate-local (left half, x right, y up, z = 0 plate underside), like compose/pcb/layout.py.
"""
import os
import sys
import math
import numpy as np
from types import SimpleNamespace
from shapely.geometry import Point, Polygon, LineString, box as sbox
from shapely.affinity import rotate as srot, translate as strans
from shapely.ops import unary_union
from compose import params as PR
from compose import geom as G
from compose import layout as layouts
from compose.pcb import layout as PL
from compose.controller import rev2_std as CS

L = G.LAYOUT
BOARDS = {"half_rev2_hotswap": ("hotswap", False), "half_rev2_solder": ("solder", False),
          "half_rev2_hotswap_rgb": ("hotswap", True), "half_rev2_solder_rgb": ("solder", True)}

# ---------------------------------------------------------------- parts
LED_AT = (0.0, 5.05)                 # MINI-E centre, footprint coords (KiCad, y down): under the switch's LED window
LED_CUT = (3.6, 3.2, 0.5)            # board cutout w x h, corner radius (body 3.2 x 2.8, router corners r 0.5)
LED_PAD_X, LED_PAD_Y = 2.85, 0.75    # pad centres (pads 1.2 x 0.82: 0.45 mm of copper-edge clearance to the cutout)
LED_PAD = (1.2, 0.82)
LED_PINS = {"1": (1, -1), "2": (1, 1), "3": (-1, 1), "4": (-1, -1)}   # VDD, DOUT, GND, DIN (pad-side view, F)
CAP_EVERY = 3                        # 100 nF (1206) per this many LEDs (hot-plug inrush, see the controller sim)
CAP_AT = (5.6, 5.05)                 # footprint coords, upright (pads along y) beside the LED, inside the switch
                                     #   cell, so the row gaps stay free for the diodes
FFC_LIB, FFC_NAME = "Connector_FFC-FPC", "Molex_200528-0200_1x20-1MP_P1.00mm_Horizontal"
FFC_BODY = (-12.65, 12.65, -0.5, 5.15)   # along the row (u) / toward the cable side (n), from the contact row
                                         #   (n from -0.5: the contacts' back ends)
FFC_H = 2.0                          # body height under the board
FFC_EDGE = 0.3                       # cable side of the body to the board's inner edge (flush, as on the controller)
SLOT_NET = {1: "GND", 2: "+5V", 3: "RGB_IN", 4: "GND", 18: "RGB_OUT", 19: "+5V", 20: "GND"}
SLOT_NET.update({5 + c: f"COL{c}" for c in range(7)})
SLOT_NET.update({12 + r: f"ROW{r}" for r in range(6)})
POST_SEARCH = 18.0


def fp2local(k, fx, fy):
    return PL.fp2local(k, fx, fy)


def outline():
    return G.OUTLINE.buffer(-PR.PCB_INSET, join_style="round").simplify(0.02)


# ---------------------------------------------------------------- per-key shapes (plate-local)
def led_cut(k):
    w, h, r = LED_CUT
    c = fp2local(k, *LED_AT)
    rect = sbox(-w / 2 + r, -h / 2 + r, w / 2 - r, h / 2 - r).buffer(r, resolution=8)
    return strans(srot(rect, k.rot, origin=(0, 0)), *c)


def led_pads(k, face):
    """{pin: pad polygon} for the LED copy on `face` ('B' = left half, 'F' = right half)."""
    out = {}
    for pin, (sx, sy) in LED_PINS.items():
        x = sx * LED_PAD_X * (-1 if face == "B" else 1)       # B: the footprint flipped (mirrored in x)
        y = sy * LED_PAD_Y
        w, h = LED_PAD
        q = [fp2local(k, LED_AT[0] + x + dx * w / 2, LED_AT[1] + y + dy * h / 2) for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        out[pin] = Polygon(q)
    return out


def cap_box(k, face):
    x0, y0 = CAP_AT
    if face == "F":
        x0 = -x0
    q = [fp2local(k, x0 + dx * 1.15, y0 + dy * 2.3) for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return Polygon(q)


def cap_pads(k, face):
    x0, y0 = CAP_AT
    if face == "F":
        x0 = -x0
    return [fp2local(k, x0, y0 - 1.475), fp2local(k, x0, y0 + 1.475)]


def socket_shapes(k):
    """Both faces' hotswap sockets (bodies and SMD tabs)."""
    x0, x1, y0, y1 = PR.HS_BODY
    loc = lambda p: fp2local(k, *p)
    sh = [Polygon([loc((x, y)) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])]
    for (c, sz) in (PR.HS_PAD2, PR.HS_PAD1):
        for cc in (c, PL.mirror_fp(c)):
            w, h = sz
            sh.append(Polygon([loc((cc[0] + dx * w / 2, cc[1] + dy * h / 2)) for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]))
    return unary_union(sh)


# ---------------------------------------------------------------- cable connector
def ffc_frame():
    """Contact-row direction u (toward the back) and the cable-side normal n (toward the bridge), unit vectors
    in the board plane (plate-local xy). The row runs along the board's inner edge: turned to the bridge
    frame's y axis instead (the splay, 10 deg) its 25 mm body would sweep into the inner column's sockets.
    The ribbon hangs in a slack U between the boards, and its two vertical runs take the splay up with a
    slight twist."""
    return np.array([0.0, 1.0]), np.array([1.0, 0.0])


def ffc_row_y_P():
    """The controller's contact row (bridge-frame y)."""
    from compose.case import gasket as C
    return C.CT.y_pc - CS.FFC_Y0


def ffc_place(keep, ol):
    """Contact-row centre (local) on the bridge-frame line of the controller's row, as close to the board's
    inner edge as the parts allow."""
    u, n = ffc_frame()
    yP = ffc_row_y_P()
    ax = G.ANCHOR[0] - PR.PCB_INSET                          # board inner edge (local x) along the bridge
    M = G.M_LP

    def body(c):
        q = [c + u * a + n * b for a, b in ((FFC_BODY[0], FFC_BODY[2]), (FFC_BODY[1], FFC_BODY[2]),
                                             (FFC_BODY[1], FFC_BODY[3]), (FFC_BODY[0], FFC_BODY[3]))]
        return Polygon(q)
    best = None
    for shift in np.arange(0.0, 8.01, 0.25):                 # along the row, either way, if the spot is taken
        for s in (shift, -shift):
            for back in np.arange(0.0, 15.01, 0.25):         # in from the edge
                # row centre: P-frame y = yP, cable-side corner FFC_EDGE + back from the edge
                lo, hi = -80.0, 40.0
                for _ in range(60):                          # local y on the edge line giving P y = yP
                    mid = (lo + hi) / 2
                    if G.apply(M, (ax, mid, -PR.PCB_T))[1] > yP:
                        hi = mid
                    else:
                        lo = mid
                c0 = np.array([ax, (lo + hi) / 2])
                c = c0 - n * FFC_BODY[3] + u * s
                bx = body(c)
                d = max(x for x, _ in bx.exterior.coords) - ax
                c = c - n * (d + FFC_EDGE + back)
                bx = body(c)
                if ol.buffer(-0.29).contains(bx) and not bx.buffer(PR.CLEARANCE + 0.01).intersects(keep):
                    best = (c, bx, s, back)
                    break
            if best:
                break
        if best:
            break
    if best is None:
        raise RuntimeError("no room for the FFC connector near the inner edge")
    c, bx, s, back = best
    f2 = lambda v: tuple(float(t) for t in v)
    pads = [f2(c + u * (9.5 - i)) for i in range(20)]         # back-most first (index 0 = slot 1)
    return SimpleNamespace(c=f2(c), u=f2(u), n=f2(n), body=bx, pads=pads, shift=float(s), back=float(back))


# ---------------------------------------------------------------- plan
def _diode_candidates():
    return PL._diode_candidates()


_PLACEMENT = {}


def plan(variant="hotswap", rgb=False):
    """Board plan for one variant. Placement (connector, diodes, capacitors, posts) is shared by all four
    boards: it is solved once against everything any variant puts on the board, so one plate (M2 inserts,
    solder-joint pockets) fits them all."""
    if "s" not in _PLACEMENT:
        _PLACEMENT["s"] = _place()
    base = _PLACEMENT["s"]
    s = SimpleNamespace(**vars(base))
    s.variant, s.rgb = variant, rgb
    s.holes = unary_union([h for k in L.keys for h in PL.key_holes(k, variant)])
    s.socks = base.socks if variant == "hotswap" else Polygon()
    if not rgb:
        s.ledcut, s.leds, s.led_order, s.caps = [], {"B": {}, "F": {}}, [], []
        s.extra_keep = [s.ffc.body.buffer(1.0)] + base.extra_keep[4:]
    return s


def _place():
    s = SimpleNamespace()
    s.outline = outline()
    ol = s.outline
    keys = L.keys
    rgb = True
    cuts = unary_union([PL.switch_cutout(k) for k in keys])            # plate switch holes (+0.6)
    holes = unary_union([h for k in keys for v in ("hotswap", "solder") for h in PL.key_holes(k, v)])
    socks = unary_union([socket_shapes(k) for k in keys])
    variant = "hotswap"
    leds = {"B": {}, "F": {}}
    ledcut = []
    for i, k in enumerate(keys):
        ledcut.append(led_cut(k))
        for f in ("B", "F"):
            leds[f][i] = led_pads(k, f)
    ledcut_u = unary_union(ledcut)
    ledpads_u = unary_union([p for f in leds for d in leds[f].values() for p in d.values()])

    # LED chain: up the outer column, down the next and so on, so it leaves the inner column at the front, then
    # the inner key and the thumb arc from the inside out
    grid = sorted([i for i in range(len(keys)) if keys[i].row != 4],
                  key=lambda i: (keys[i].col, -keys[i].row if keys[i].col % 2 == 0 else keys[i].row))
    rest = sorted([i for i in range(len(keys)) if keys[i].row == 4], key=lambda i: -keys[i].x)
    s.led_order = grid + rest
    s.caps = []
    capshape = []
    if rgb:
        for j in range(1, len(s.led_order), CAP_EVERY):
            i = s.led_order[j]
            s.caps.append(i)
            capshape += [cap_box(keys[i], "B"), cap_box(keys[i], "F")]
    caps_u = unary_union(capshape) if capshape else Polygon()

    # cable connector (both faces, same spot): clear of every hole, socket, LED and capacitor
    keep = unary_union([holes, socks, ledcut_u.buffer(0.3), ledpads_u, caps_u])
    # diodes go after the connector, the connector only needs the column-edge strip
    s.ffc = ffc_place(keep, ol)

    # diodes: one candidate spot for every key if one fits all of them, else per key. As on rev 1 the body
    # keeps a 0.9 mm margin to socket bodies and other diodes; to SMD pads, LEDs and the connector it keeps
    # 0.25 mm from its real (2 mm) diameter
    inside = ol.buffer(-1.0)
    sbodies = unary_union([PL.socket_body(k) for k in keys]) if variant == "hotswap" else Polygon()
    smd = unary_union([socks.difference(sbodies), s.ffc.body, ledcut_u, ledpads_u, caps_u])
    taken0 = Polygon()

    def fits(k, cand, taken):
        cat, an = cand
        pc, pa = fp2local(k, *cat), fp2local(k, *an)
        pk = unary_union([Point(pc).buffer(PR.JOINT_POCKET_R), Point(pa).buffer(PR.JOINT_POCKET_R)])
        seg = LineString([pc, pa])
        body = seg.buffer(PR.DIODE_BODY[1] / 2 + 0.9)
        real = seg.buffer(PR.DIODE_BODY[1] / 2 + 0.25)
        if pk.intersects(cuts) or not inside.contains(body):
            return None
        if body.intersects(sbodies) or body.intersects(taken) or real.intersects(smd):
            return None
        if pk.intersects(holes.buffer(0.3)):
            return None
        return pc, pa, pk, body
    cands = _diode_candidates()
    common = None
    for cand in cands:
        taken, okall = taken0, True
        for k in keys:
            r = fits(k, cand, taken)
            if r is None:
                okall = False
                break
            taken = unary_union([taken, r[2].buffer(0.3), r[3]])
        if okall:
            common = cand
            break
    s.diode_common = common is not None
    taken = taken0
    s.keys = []
    for i, k in enumerate(keys):
        got = None
        for cand in ([common] if common else []) + cands:
            got = fits(k, cand, taken)
            if got:
                break
        if got is None:
            raise RuntimeError(f"no room for the diode of key {k.label_l}")
        pc, pa, pk, body = got
        taken = unary_union([taken, pk.buffer(0.3), body])
        s.keys.append(SimpleNamespace(i=i, k=k, cathode=pc, anode=pa, row=k.row, col=k.col,
                                      ref=f"SW{i + 1}", dref=f"D{i + 1}", pocket=pk, dbody=body))
    s.pockets = unary_union([ks.pocket for ks in s.keys])

    # M2 posts (board -> plate inserts): near rev 1's, clear of everything on either face, the insert in
    # solid plate (core, away from switch holes and the flange)
    # underside (screw head): real part outlines; plate side (insert): switch holes and solder-joint pockets
    allparts = unary_union([holes, socks, ledcut_u, ledpads_u, caps_u, s.ffc.body,
                            unary_union([LineString([ks.cathode, ks.anode]).buffer(PR.DIODE_BODY[1] / 2) for ks in s.keys]),
                            unary_union([Point(p).buffer(0.8) for ks in s.keys for p in (ks.cathode, ks.anode)])])
    core = G.OUTLINE.buffer(-PR.FLANGE_W - (PR.M2_INSERT_D / 2 + 0.8), join_style="round")
    board = ol.buffer(-(PR.M2_HEAD_D / 2 + 0.6))
    plate_r = PR.M2_INSERT_D / 2 + 0.8
    head_r = PR.M2_HEAD_D / 2 + 0.4
    cuts0 = unary_union([PL.switch_cutout(k, grow=0.0) for k in keys])     # the plate's real switch holes
    s.posts = []
    for (x0, y0) in PL.ORIGINAL_POSTS:
        best = None
        n = int(POST_SEARCH / 0.5)
        for a in range(-n, n + 1):
            for b in range(-n, n + 1):
                x, y = x0 + a * 0.5, y0 + b * 0.5
                d = math.hypot(x - x0, y - y0)
                if d > POST_SEARCH or (best and d >= best[0]):
                    continue
                pt = Point(x, y)
                if not board.contains(pt) or not core.contains(pt):
                    continue
                if pt.distance(allparts) < head_r or pt.distance(cuts0) < plate_r or pt.distance(s.pockets) < plate_r - 0.4:
                    continue
                if any(math.hypot(x - p, y - q) < 12 for p, q in s.posts):
                    continue
                best = (d, (x, y))
        if best is None:
            if os.environ.get("R2DBG"):
                import collections
                why = collections.Counter()
                for a in range(-n, n + 1):
                    for b in range(-n, n + 1):
                        x, y = x0 + a * 0.5, y0 + b * 0.5
                        if math.hypot(x - x0, y - y0) > POST_SEARCH:
                            continue
                        pt = Point(x, y)
                        why[(board.contains(pt), core.contains(pt), round(pt.distance(allparts) >= head_r),
                             pt.distance(cuts0) >= plate_r, all(math.hypot(x - p, y - q) >= 12 for p, q in s.posts))] += 1
                print(why)
            raise RuntimeError(f"no place for the M2 post near ({x0:.1f}, {y0:.1f})")
        s.posts.append(best[1])

    s.ledcut = ledcut
    s.leds = leds
    s.cuts, s.holes, s.socks = cuts, holes, socks
    pl = np.array(s.ffc.pads[-1]) - np.array(s.ffc.u) * 5.0 + np.array(s.ffc.n) * 2.4
    s.extra_keep = [s.ffc.body.buffer(1.0), ledcut_u.buffer(0.6), ledpads_u.buffer(0.4), caps_u.buffer(0.4),
                    Point(*pl).buffer(2.6)]
    s.extra_keep += [Point(ks.cathode).buffer(3.2) for ks in s.keys]           # the diodes' 'K' marks
    # art.free_area compatibility (rev 1 plan fields)
    s.conn_body = s.ffc.body
    s.conn_pins = [s.ffc.pads[0], s.ffc.pads[-1]]
    s.holes_m3, s.holes_m2 = [], list(s.posts)
    return s


def slot_of_pad_xy(s):
    """Physical order -> slot: the contact row's pads sorted by bridge-frame y, back first."""
    M = G.M_LP
    ys = [(G.apply(M, (x, y, -PR.PCB_T))[1], i) for i, (x, y) in enumerate(s.ffc.pads)]
    order = [i for _, i in sorted(ys, reverse=True)]
    return {s.ffc.pads[i]: k + 1 for k, i in enumerate(order)}


# ---------------------------------------------------------------- KiCad
POWER_NETS = ("+5V", "GND")
POWER_W = PR.TRACE_W         # power at the signal width: brightness is capped at 32/255, so a half draws ~0.13 A,
                             #   and 0.4 mm power tracks to 116 pads per rail left the router stuck


def _pc():
    import pcbnew
    from compose.pcb import kicad as PK
    return pcbnew, PK


def led_fp(b, ref, face):
    """SK6812 MINI-E, reverse mount: pads on `face`, the body down through the board cutout, light to the
    other face (the switch side). Built on F and flipped for B (mirrors the pad layout, as the part itself
    is seen from the other side)."""
    pcbnew, PK = _pc()
    fp = pcbnew.FOOTPRINT(b)
    fp.SetFPID(pcbnew.LIB_ID("compose", "LED_SK6812MINI-E_ReverseMount"))
    fp.SetReference(ref)
    fp.SetValue("SK6812MINI-E")
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    for pin, (sx, sy) in LED_PINS.items():
        PK.add_pad(fp, pin, "smd", "roundrect", (sx * LED_PAD_X, sy * LED_PAD_Y), LED_PAD)
    PK.courtyard(fp, -3.65, -1.85, 3.65, 1.85, pcbnew.F_CrtYd)
    # pin 1 mark: a short bar outside pad 1
    PK.silk_poly(fp, [(LED_PAD_X + 0.9, -LED_PAD_Y - 0.5), (LED_PAD_X + 0.9, -LED_PAD_Y + 0.5)], pcbnew.F_SilkS, 0.15)
    if face == "B":
        fp.Flip(pcbnew.VECTOR2I(0, 0), True)                   # left-right: x mirrored, as in the plan
    return fp


def _fp_pad_xy(fp, num):
    import pcbnew
    return [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in fp.Pads() if p.GetNumber() == num]


def build(name):
    pcbnew, PK = _pc()
    variant, rgb = BOARDS[name]
    s = plan(variant, rgb)
    K, V, MM, DEG = PK.K, PK.V, PK.MM, PK.DEG
    b = PK.new_board()
    net = PK.Nets(b)
    ol = s.outline
    if rgb:
        ol = ol.difference(unary_union(s.ledcut))
    b.kb2_outline = (ol, PK.OX, PK.OY)
    PK.outline(b, ol, PK.OX, PK.OY)
    if rgb:
        b.kb2_gnd_pour = True
        b.kb2_after_route = gnd_pour
    if rgb and POWER_W > PR.TRACE_W:
        pw = pcbnew.NETCLASS("Power")
        pw.SetTrackWidth(MM(POWER_W))
        pw.SetClearance(MM(PR.CLEARANCE))
        pw.SetViaDiameter(MM(PR.VIA_D + 0.2))
        pw.SetViaDrill(MM(PR.VIA_DRILL + 0.1))
        b.GetDesignSettings().m_NetSettings.m_NetClasses["Power"] = pw
        for n in POWER_NETS:
            net(n).SetNetClass(pw)
    near = lambda a, c: math.dist(a, c) < 2e-3
    # ---- switches + diodes (as rev 1)
    for ks in s.keys:
        k = ks.k
        dnet = net(f"D{ks.i + 1}")
        fp = PK.switch_fp(b, variant, ks.ref, net(f"COL{ks.col}"), dnet)
        for g in list(fp.GraphicalItems()):                     # no courtyard: on a reversible board the LED,
            if g.GetLayer() == pcbnew.F_CrtYd:                  #   capacitor and other face's copies sit inside
                fp.Remove(g)                                    #   it by design (clearances checked in plan())
        fp.SetOrientation(DEG(k.rot))
        fp.SetPosition(V(*K((k.x, k.y))))
        b.Add(fp)
        d = PK.lib_fp(b, "Diode_THT", "D_DO-35_SOD27_P7.62mm_Horizontal")
        d.SetReference(ks.dref)
        d.Reference().SetVisible(False)
        d.Value().SetVisible(False)
        d.Flip(d.GetPosition(), False)
        PK.place_by_pads(d, "1", K(ks.cathode), "2", K(ks.anode))
        for p in d.Pads():
            p.SetNet(net(f"ROW{ks.row}") if p.GetNumber() == "1" else dnet)
        b.Add(d)
        c, a = K(ks.cathode), K(ks.anode)                         # F-side outline + cathode band (right half)
        ux, uy = (a[0] - c[0]) / PR.DIODE_PITCH, (a[1] - c[1]) / PR.DIODE_PITCH
        nx, ny = -uy, ux
        h0, h1, r = 1.8, PR.DIODE_PITCH - 1.8, 0.95
        corner = lambda t, s_: (c[0] + ux * t + nx * s_, c[1] + uy * t + ny * s_)
        for t0, s0, t1, s1 in ((h0, -r, h1, -r), (h1, -r, h1, r), (h1, r, h0, r), (h0, r, h0, -r), (h0 + 0.6, -r, h0 + 0.6, r)):
            sh = pcbnew.PCB_SHAPE(b)
            sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
            sh.SetStart(V(*corner(t0, s0)))
            sh.SetEnd(V(*corner(t1, s1)))
            sh.SetLayer(pcbnew.F_SilkS)
            sh.SetWidth(MM(0.12))
            b.Add(sh)
    # ---- LEDs + capacitors (RGB boards): B = the left half's chain, F = the right half's
    if rgb:
        n_led = len(s.led_order)
        for face, tag in (("B", "LB"), ("F", "LF")):
            for j, i in enumerate(s.led_order):
                k = L.keys[i]
                fp = led_fp(b, f"{tag}{j + 1}", face)              # built (and flipped) at the origin:
                fp.Rotate(V(0, 0), DEG(k.rot))                      #   turn relative to that, then move
                fp.Move(V(*K(fp2local(k, *LED_AT))))
                want = led_pads(k, face)
                for pin, poly in want.items():
                    got = _fp_pad_xy(fp, pin)
                    assert got and near(got[0], K(poly.centroid.coords[0])), f"LED {face} pad {pin} misplaced"
                din = "RGB_IN" if j == 0 else f"{tag}_{j}"
                dout = "RGB_OUT" if j == n_led - 1 else f"{tag}_{j + 1}"
                nets = {"1": "+5V", "2": dout, "3": "GND", "4": din}
                for p in fp.Pads():
                    p.SetNet(net(nets[p.GetNumber()]))
                b.Add(fp)
            for m, i in enumerate(s.caps):
                k = L.keys[i]
                c_ = PK.lib_fp(b, "Capacitor_SMD", "C_1206_3216Metric")
                c_.SetReference(f"C{m + 1}{face}")
                c_.Reference().SetVisible(False)
                c_.Value().SetVisible(False)
                if face == "B":
                    c_.Flip(c_.GetPosition(), False)
                pa, pb = cap_pads(k, face)
                PK.place_by_pads(c_, "1", K(pa), "2", K(pb))
                for p in c_.Pads():
                    p.SetNet(net("+5V" if p.GetNumber() == "1" else "GND"))
                b.Add(c_)
    # ---- cable connectors: one per face, same spot; nets by physical position (back-most contact = slot 1)
    slot = slot_of_pad_xy(s)
    for face in ("B", "F"):
        j = PK.lib_fp(b, FFC_LIB, FFC_NAME)
        j.SetReference(f"J1{face}")
        j.Reference().SetVisible(False)
        if face == "B":
            j.Flip(j.GetPosition(), False)
        for first, last in (("1", "20"), ("20", "1")):
            PK.place_by_pads(j, first, K(s.ffc.pads[0]), last, K(s.ffc.pads[-1]))
            mp = [pcbnew.ToMM(p.GetPosition().x) for p in j.Pads() if p.GetNumber() == "MP"]
            if sum(mp) / len(mp) - PK.OX > s.ffc.c[0]:               # body (and cable side) toward the bridge
                break
        else:
            raise RuntimeError("FFC: cable side won't face the bridge")
        for p in j.Pads():
            if p.GetNumber() == "MP":
                continue
            xy = (pcbnew.ToMM(p.GetPosition().x) - PK.OX, PK.OY - pcbnew.ToMM(p.GetPosition().y))
            k_ = [q for q in slot if math.dist(q, xy) < 1e-3]
            assert k_, f"FFC pad {p.GetNumber()} off the planned row"
            sl = slot[k_[0]]
            nm = SLOT_NET[sl]
            if nm in ("COL6", "ROW5"):
                nm = None                                             # the matrix's spare line: unused here
            elif not rgb and nm in ("RGB_IN", "RGB_OUT"):
                nm = "RGB_PASS"                                       # no LEDs: data straight back
            elif not rgb and nm in ("+5V", "GND"):
                nm = None
            if nm:
                p.SetNet(net(nm))
        b.Add(j)
    # ---- M2 holes (board -> plate inserts)
    for i, (x, y) in enumerate(s.posts):                      # no courtyard: they sit in the column gaps,
        h = pcbnew.FOOTPRINT(b)                                  #   inside the switches' 15 mm courtyards
        h.SetFPID(pcbnew.LIB_ID("compose", "Hole_M2"))
        h.SetReference(f"H{i + 1}")
        h.Reference().SetVisible(False)
        h.Value().SetVisible(False)
        PK.add_pad(h, "", "npth", "circle", (0, 0), (PR.M2_CLEAR,) * 2, (PR.M2_CLEAR,) * 2)
        h.SetPosition(V(*K((x, y))))
        b.Add(h)
    # ---- art + connector labels
    from compose.pcb import art as pcb_art
    PR.REVISION = "rev 2"
    art = pcb_art.plan_half_art(s, variant + (" · rgb" if rgb else ""))
    PK.add_art_half(b, art, PK.OX, PK.OY)
    p1 = np.array(s.ffc.pads[0])
    u, n = np.array(s.ffc.u), np.array(s.ffc.n)
    lhs, rhs = PR.HALF_NAMES
    for face, nm, lay, mir in (("B", lhs, pcbnew.B_SilkS, True), ("F", rhs, pcbnew.F_SilkS, False)):
        PK.text(b, "1", K(tuple(float(t) for t in p1 + u * 1.3 - n * 1.6)), lay, 1.0, mirror=mir)
        pl = np.array(s.ffc.pads[-1])                            # past the body's front end, mid-depth
        PK.text(b, nm, K(tuple(float(t) for t in pl - u * 5.0 + n * 2.4)), lay, 1.0, mirror=mir, angle=90)
    return b


GND_POUR_CLEAR = 0.3
STITCH_PITCH = 3.0


def gnd_pour(b):
    """After routing (RGB boards): GND fills both copper layers, tied together by stitching vias wherever one
    fits. The router never sees GND (see _export_dsn_power): 136 pads on one net was what kept it from
    finishing. KiCad's DRC then reports any GND pad the pour can't reach."""
    pcbnew, PK = _pc()
    from shapely.geometry import Point as P_, LineString as LS_, Polygon as Pg_
    from shapely.ops import unary_union as uu
    from shapely.strtree import STRtree
    ToMM = pcbnew.ToMM
    gnd = b.GetNetsByName()["GND"]
    ol, ox, oy = b.kb2_outline
    kol = Pg_([PK.K(p, ox, oy) for p in ol.exterior.coords], [[PK.K(p, ox, oy) for p in r.coords] for r in ol.interiors])
    # obstacles per layer for a via (both layers) in KiCad coordinates
    obst = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            q = p.GetPosition()
            r = math.hypot(ToMM(p.GetSize().x), ToMM(p.GetSize().y)) / 2   # half the diagonal: covers square pads' corners
            obst.append(P_(ToMM(q.x), ToMM(q.y)).buffer(r))
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            q = t.GetPosition()
            obst.append(P_(ToMM(q.x), ToMM(q.y)).buffer(ToMM(t.GetWidth()) / 2))
        else:
            a, c = t.GetStart(), t.GetEnd()
            obst.append(LS_([(ToMM(a.x), ToMM(a.y)), (ToMM(c.x), ToMM(c.y))]).buffer(ToMM(t.GetWidth()) / 2))
    for d in b.GetDrawings():                                    # exposed-copper art
        if d.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
            bb = d.GetBoundingBox()
            obst.append(Pg_([(ToMM(bb.GetLeft()), ToMM(bb.GetTop())), (ToMM(bb.GetRight()), ToMM(bb.GetTop())),
                             (ToMM(bb.GetRight()), ToMM(bb.GetBottom())), (ToMM(bb.GetLeft()), ToMM(bb.GetBottom()))]))
    for z in b.Zones():
        if z.GetIsRuleArea():
            o = z.Outline()
            pts = [(ToMM(o.CVertex(i).x), ToMM(o.CVertex(i).y)) for i in range(o.TotalVertices())]
            obst.append(Pg_(pts).buffer(0))
    tree = STRtree(obst)
    vr = PR.VIA_D / 2
    keep = kol.buffer(-(vr + 0.5))
    minx, miny, maxx, maxy = keep.bounds
    n = 0
    y = miny
    while y <= maxy:
        x = minx
        while x <= maxx:
            c = P_(x, y)
            if keep.contains(c):
                probe = c.buffer(vr + PR.CLEARANCE + 0.05)
                if not any(obst[int(i)].intersects(probe) for i in tree.query(probe)):
                    v = pcbnew.PCB_VIA(b)
                    v.SetPosition(PK.V(x, y))
                    v.SetWidth(PK.MM(PR.VIA_D))
                    v.SetDrill(PK.MM(PR.VIA_DRILL))
                    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    v.SetNet(gnd)
                    b.Add(v)
                    n += 1
            x += STITCH_PITCH
        y += STITCH_PITCH
    for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(b)
        z.SetLayer(lay)
        z.SetNet(gnd)
        z.SetLocalClearance(PK.MM(GND_POUR_CLEAR))
        z.SetMinThickness(PK.MM(0.25))
        z.SetThermalReliefGap(PK.MM(0.3))
        z.SetThermalReliefSpokeWidth(PK.MM(0.35))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetAssignedPriority(0)
        o = z.Outline()
        o.NewOutline()
        for p in list(kol.exterior.coords)[:-1]:
            o.Append(PK.MM(p[0]), PK.MM(p[1]))
        b.Add(z)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    # stitching vias the pour didn't reach on both faces would dangle: drop them
    dead = []
    zs = [z for z in b.Zones() if not z.GetIsRuleArea()]
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gnd.GetNetCode() and not t.GetNetname() == "":
            q = t.GetPosition()
            hit = sum(1 for z in zs if z.GetFilledPolysList(z.GetLayer()).Contains(q))
            if hit < 2 and not any(tr.GetNetCode() == gnd.GetNetCode() and tr.GetClass() != "PCB_VIA" and
                                   (tr.GetStart() == q or tr.GetEnd() == q) for tr in b.GetTracks()):
                dead.append(t)
    for t in dead:
        b.Delete(t)                     # see kicad.remove_dangling
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    print(f"  GND pour on F and B, {n - len(dead)} stitching vias")


_export_dsn = None


def _export_dsn_power(board, path):
    """Power nets into the router's Power class (KiCad 7 keeps net-class membership in the project file,
    which generated boards don't have)."""
    import re
    okx = _export_dsn(board, path)
    t = open(path).read()
    if getattr(board, "kb2_gnd_pour", False):            # GND is poured after routing: not the router's job
        t = re.sub(r"\(net GND\s*\(pins[^)]*\)\s*\)", "", t, count=1)
        i = t.index("(network")
        t = t[:i] + re.sub(r'(?<=[\s(])"?GND"?(?=[\s)])', "", t[i:])
        open(path, "w").write(t)
    m = re.search(r"\(class kicad_default ([^(]*)", t)
    if m and "(class Power" in t:
        names = m.group(1).split()
        keep = [n for n in names if n.strip('"') not in POWER_NETS]
        moved = [n for n in names if n.strip('"') in POWER_NETS]
        t = t[:m.start(1)] + " ".join(keep) + "\n      " + t[m.end(1):]
        t = t.replace("(class Power\n", "(class Power " + " ".join(moved) + "\n", 1)
        open(path, "w").write(t)
    return okx


def main(which=None):
    global _export_dsn
    pcbnew, PK = _pc()
    os.makedirs(PK.PCB_OUT, exist_ok=True)
    _export_dsn = pcbnew.ExportSpecctraDSN
    pcbnew.ExportSpecctraDSN = _export_dsn_power
    res = {}
    for nm in BOARDS:
        if which and nm not in which:
            continue
        rgb = BOARDS[nm][1]
        PK.JOB_TIMEOUT_MIN = 45 if rgb else 8                     # ceiling; stalls are stopped much sooner
        res[nm] = PK.make(nm, lambda nm=nm: build(nm), passes=100 if rgb else 60, attempts=12 if rgb else 10)
    return res


# ---------------------------------------------------------------- debug drawing
def draw(s, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(16, 11))

    def P(g, **kw):
        for p in getattr(g, "geoms", [g]):
            if p.is_empty or p.geom_type != "Polygon":
                continue
            x, y = p.exterior.xy
            ax.fill(x, y, **kw)
    P(s.outline, fc="#1f6b45", alpha=0.25, ec="k")
    P(s.cuts, fc="none", ec="#999", lw=0.4)
    P(s.holes, fc="k")
    P(s.socks, fc="#c33", alpha=0.35)
    for c in s.ledcut:
        P(c, fc="white", ec="b")
    for f, col in (("B", "#36c"), ("F", "#c6c")):
        for d in s.leds[f].values():
            for p in d.values():
                P(p, fc=col, alpha=0.5)
    for i in s.caps:
        P(cap_box(L.keys[i], "B"), fc="orange", alpha=0.5)
        P(cap_box(L.keys[i], "F"), fc="gold", alpha=0.5)
    for ks in s.keys:
        P(ks.dbody, fc="#555", alpha=0.6)
        ax.plot(*ks.cathode, "o", ms=2, c="w")
    P(s.ffc.body, fc="#a70", alpha=0.6)
    for p in s.ffc.pads[:1]:
        ax.plot(*p, "r*", ms=8)
    for x, y in s.posts:
        ax.add_patch(plt.Circle((x, y), PR.M2_CLEAR / 2, fc="none", ec="m"))
    if s.led_order:
        xy = [G.LAYOUT.keys[i] for i in s.led_order]
        ax.plot([fp2local(k, *LED_AT)[0] for k in xy], [fp2local(k, *LED_AT)[1] for k in xy], "-", c="#36c", lw=0.6)
    ax.set_aspect("equal")
    fig.savefig(path, dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    args = [a for a in sys.argv[2:] if not a.startswith("-")]
    if "--plan" in sys.argv:
        out = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
        os.makedirs(os.path.join(out, "pcb"), exist_ok=True)
        s = plan("hotswap", True)
        print("diodes in one common spot:", s.diode_common, "| ffc shift/back", s.ffc.shift, s.ffc.back,
              "| posts", [tuple(round(v, 1) for v in p) for p in s.posts], "| caps", len(s.caps))
        draw(s, os.path.join(out, "pcb", "half_rev2_plan.png"))
    else:
        main(args or None)
