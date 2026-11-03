"""
Board graphics, generated from the layout (pure Python + shapely):
  - exposed-copper title (∘ ring logo + BOARD_NAME) on both faces, in a box the
    router keeps clear of tracks
  - silkscreen tagline / credit, per-face build labels (lhs / rhs)
  - a hex lattice in silkscreen over every free bit of board
Text is rendered to outlines from real fonts (KiCad 7's API has no font engine).
Geometry is in plate-local coords (half board) or P coords (controller), y up.
B-face items are mirrored about their own box so they read correctly from behind.
"""
import math
import numpy as np
from shapely.geometry import Point, Polygon, LineString, MultiPolygon, box as sbox
from shapely.affinity import scale as sscale, translate as strans
from shapely.ops import unary_union
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties
from compose import params as PR
from compose.pcb import layout as PL

L = PL.L


# ---------------------------------------------------------------- text -> outlines
def text_shape(s, font, em=1.0):
    fam, weight = font
    tp = TextPath((0, 0), s, size=em, prop=FontProperties(family=fam, weight=weight))
    out = None
    for ring in tp.to_polygons(closed_only=True):
        if len(ring) < 3:
            continue
        p = Polygon(ring).buffer(0)
        out = p if out is None else out.symmetric_difference(p)      # even-odd: counters become holes
    return out if out is not None else MultiPolygon()


def fit(shape, x0, y0, w, h, align="center"):
    """Scale shape uniformly to fit in the box, then place it (left/center aligned, vertically centred)."""
    bx0, by0, bx1, by1 = shape.bounds
    k = min(w / (bx1 - bx0), h / (by1 - by0))
    s = sscale(shape, k, k, origin=(0, 0))
    bx0, by0, bx1, by1 = s.bounds
    dx = x0 - bx0 + (0 if align == "left" else (w - (bx1 - bx0)) / 2)
    return strans(s, dx, y0 - by0 + (h - (by1 - by0)) / 2), k


def mirror_about(geom, cx):
    return sscale(geom, -1, 1, origin=(cx, 0))


def ring_logo(cx, cy, r):
    """The composition operator ∘ as a bold ring."""
    return Point(cx, cy).buffer(r).difference(Point(cx, cy).buffer(r * 0.55))


# ---------------------------------------------------------------- free board area
def free_area(plan):
    keep = [PL.switch_cutout(k, grow=0.8) for k in L.keys]
    keep += [PL.bottom_keepout(k).buffer(0.5) for k in L.keys]
    keep += [LineString([ks.cathode, ks.anode]).buffer(2.4) for ks in plan.keys]        # incl. the 'K' marks
    keep += [Point(p).buffer(3.0) for p in plan.holes_m3 + plan.holes_m2]
    keep.append(plan.conn_body.buffer(1.2))
    keep += [Point(p).buffer(1.2) for p in plan.conn_pins]
    for p in (plan.conn_pins[0], plan.conn_pins[-1]):                              # "lhs/rhs: pin 1" labels
        keep.append(sbox(p[0] - 8.5, p[1] - 1.2, p[0] - 0.5, p[1] + 1.2))
    return plan.outline.buffer(-1.2).difference(unary_union(keep))


def find_box(free, w, h, anchor, step=0.5, search=40.0):
    """Box of w x h inside `free`, as close to `anchor` (its centre) as possible."""
    ax, ay = anchor
    best = None
    n = int(search / step)
    for i in range(-n, n + 1):
        for j in range(-n // 2, n // 2 + 1):
            cx, cy = ax + i * step, ay + j * step
            d = math.hypot(cx - ax, cy - ay)
            if best and d >= best[0]:
                continue
            b = sbox(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if free.contains(b):
                best = (d, b)
    return best[1] if best else None


def widest_box(free, h, anchor, w_max=80.0, w_min=10.0):
    w = w_max
    while w >= w_min:
        b = find_box(free, w, h, anchor, step=0.5, search=12.0)
        if b is not None:
            return b
        w -= 1.0
    return None


# ---------------------------------------------------------------- hex lattice
def hex_lattice(region, cell, origin=(0.0, 0.0)):
    """Hex cell outlines (flat-to-flat = cell) clipped to region, as LineStrings."""
    R = cell / math.sqrt(3)
    x0, y0, x1, y1 = region.bounds
    lines = []
    i0, i1 = int((x0 - origin[0]) / (1.5 * R)) - 2, int((x1 - origin[0]) / (1.5 * R)) + 2
    j0, j1 = int((y0 - origin[1]) / cell) - 2, int((y1 - origin[1]) / cell) + 2
    seen = set()
    for i in range(i0, i1):
        for j in range(j0, j1):
            cx = origin[0] + i * 1.5 * R
            cy = origin[1] + j * cell + (cell / 2 if i % 2 else 0)
            pts = [(cx + R * math.cos(math.radians(60 * k)), cy + R * math.sin(math.radians(60 * k))) for k in range(7)]
            for a, b in zip(pts[:-1], pts[1:]):
                key = tuple(sorted(((round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3)))))
                if key in seen:
                    continue
                seen.add(key)
                seg = LineString([a, b]).intersection(region)
                if seg.is_empty:
                    continue
                for g in getattr(seg, "geoms", [seg]):
                    if g.geom_type == "LineString" and g.length > 0.4:
                        lines.append(g)
    return lines


# ---------------------------------------------------------------- half board art
def plan_half_art(plan, variant="hotswap"):
    """Returns a namespace: copper (per face), silk_polys (per face), silk_lines,
    keepout box. Faces: 'F' and 'B'."""
    from types import SimpleNamespace
    free = free_area(plan)
    a = SimpleNamespace(copper={"F": [], "B": []}, silk={"F": [], "B": []}, lines=[], boxes=[])
    lhs, rhs = PR.HALF_NAMES

    # 1. title: ring + name, exposed copper, top-left margin
    tb = widest_box(free, 6.0, (8.0, 11.0), w_max=40.0, w_min=28.0)
    x0, y0, x1, y1 = tb.bounds
    h = y1 - y0
    r = h * 0.42
    ring = ring_logo(x0 + r + 0.3, (y0 + y1) / 2, r)
    name, _ = fit(text_shape(PR.BOARD_NAME, PR.ART_TITLE_FONT), x0 + 2 * r + 1.6, y0 + 0.4, x1 - x0 - 2 * r - 1.9, h - 0.8, "left")
    title = unary_union([ring, name])
    cx = (x0 + x1) / 2
    a.copper["F"].append(title)
    a.copper["B"].append(mirror_about(title, cx))
    a.keepout = tb.buffer(PR.ART_COPPER_KEEPOUT, join_style="mitre")
    a.boxes.append(tb)

    # 2. tagline + credit, silkscreen, the band between the last key row and the thumbs
    bb = widest_box(free, 5.4, (58.0, -65.5), w_max=58.0, w_min=30.0)
    x0, y0, x1, y1 = bb.bounds
    credit_txt = f"{PR.HANDLE} · {PR.REVISION} · {PR.YEAR} · {PR.CREDIT}"
    credit, k2 = fit(text_shape(credit_txt, PR.ART_TEXT_FONT), x0, y0, x1 - x0, 2.0)
    # one shared size for both faces' code lines: the longer one sets it
    raw = {f: text_shape(PR.TAGLINE[f], PR.ART_CODE_FONT) for f in ("F", "B")}
    k1 = min(fit(raw[f], x0, y0, x1 - x0, 3.0)[1] for f in ("F", "B"))
    for f in ("F", "B"):
        g = sscale(raw[f], k1, k1, origin=(0, 0))
        gx0, gy0, gx1, gy1 = g.bounds
        g = strans(g, x0 - gx0 + (x1 - x0 - (gx1 - gx0)) / 2, y0 + 2.4 - gy0 + (3.0 - (gy1 - gy0)) / 2)
        a.silk[f].append(g if f == "F" else mirror_about(g, (x0 + x1) / 2))
        a.silk[f].append(credit if f == "F" else mirror_about(credit, (x0 + x1) / 2))
    a.text_em = (k1, k2)
    a.boxes.append(bb)

    # 3. build labels, per face (the same board is lhs from one face, rhs from the other)
    lb = widest_box(free.difference(unary_union([b.buffer(1.0) for b in a.boxes])), 5.0, (38.0, -87.0), w_max=34.0, w_min=20.0)
    x0, y0, x1, y1 = lb.bounds
    for face, sw, parts in (("F", lhs, rhs), ("B", rhs, lhs)):
        t1 = text_shape(f"{sw} → switches on this side", PR.ART_TEXT_FONT)
        t2 = text_shape(f"{parts} → sockets & diodes on this side", PR.ART_TEXT_FONT)
        k = min(fit(t, x0, y0, x1 - x0, 2.2)[1] for t in (t1, t2))           # same size for both lines
        l1 = strans(sscale(t1, k, k, origin=(0, 0)), x0, y0 + 2.9)
        l2 = strans(sscale(t2, k, k, origin=(0, 0)), x0, y0 + 0.5)
        g = unary_union([l1, l2])
        a.silk[face].append(g if face == "F" else mirror_about(g, (x0 + x1) / 2))
    a.boxes.append(lb)

    # 4. board id, small, in the top margin (both faces)
    ib = widest_box(free.difference(unary_union([b.buffer(1.0) for b in a.boxes] + [a.keepout.buffer(0.8)])),
                    2.0, (65.0, 18.5), w_max=40.0, w_min=16.0)
    if ib is not None:
        x0, y0, x1, y1 = ib.bounds
        t, _ = fit(text_shape(f"{PR.BOARD_NAME} · half · {variant} · {PR.REVISION}", PR.ART_TEXT_FONT), x0, y0, x1 - x0, y1 - y0)
        a.silk["F"].append(t)
        a.silk["B"].append(mirror_about(t, (x0 + x1) / 2))
        a.boxes.append(ib)

    # 5. hex lattice everywhere else
    region = free.difference(unary_union([b.buffer(1.0) for b in a.boxes] + [a.keepout.buffer(0.6)]))
    a.lines = hex_lattice(region, PR.ART_HEX_CELL)
    return a


def plan_ctrl_art(cplan, stack):
    """Controller: name + ring on the back face, in the open area between the
    header rows and clear of the carrier screw holes; lhs/rhs labels on both
    faces next to their connectors."""
    from types import SimpleNamespace
    a = SimpleNamespace(silk={"F": [], "B": []})
    hys = sorted({y for _, y in stack.carrier_holes})
    y_lo, y_hi = hys[0] + PR.CARRIER_POST_R + 1.2, hys[-1] - PR.CARRIER_POST_R - 1.2
    w = 2 * PR.PICO_PIN_ROW_X - 2 * (PR.FEMALE_HEADER_W / 2 + 1.0)
    mid = (y_lo + y_hi) / 2
    ring = ring_logo(0.0, mid + 6.5, 2.8)
    name, _ = fit(text_shape(PR.BOARD_NAME, PR.ART_TITLE_FONT), -w / 2, mid - 0.2, w, 3.0)
    sub, _ = fit(text_shape(f"controller · {PR.HANDLE}", PR.ART_TEXT_FONT), -w / 2, mid - 3.6, w, 1.7)
    a.silk["B"].append(mirror_about(unary_union([ring, name, sub]), 0.0))
    # connector labels: between each header row and its connector (front), beside the pins (back)
    n, p = PR.HALF_CONN_PINS, PR.HALF_CONN_PITCH
    for side, sx, nm in (("L", -1, PR.HALF_NAMES[0]), ("R", 1, PR.HALF_NAMES[1])):
        cy = sum(y for _, y in cplan.conn[side]) / len(cplan.conn[side])
        t = text_shape(nm, PR.ART_TEXT_FONT)
        from shapely.affinity import rotate as srot
        t = srot(t, 90 * sx, origin=(0, 0))
        x_front = sx * (PR.PICO_PIN_ROW_X + PR.FEMALE_HEADER_W / 2 + 0.25 + (PR.CTRL_CONN_X - 1.55 - PR.PICO_PIN_ROW_X - PR.FEMALE_HEADER_W / 2 - 0.5) / 2)
        g, _ = fit(t, x_front - 0.7, cy - 3.0, 1.4, 6.0)
        a.silk["F"].append(g)
        x_back = sx * (PR.CTRL_CONN_X + 2.3)
        gb, _ = fit(t, x_back - 0.8, cy - 3.5, 1.6, 7.0)
        a.silk["B"].append(mirror_about(gb, x_back))
    return a
