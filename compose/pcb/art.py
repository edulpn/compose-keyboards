"""
Board graphics, generated from the layout (pure Python + shapely):
  - exposed-copper title (∘ ring logo + BOARD_NAME) on both faces, in a box the
    router keeps clear of tracks
  - silkscreen tagline / credit, per-face build labels (lhs / rhs)
  - a hex lattice in silkscreen over every free bit of board
Text is rendered to outlines from real fonts (lettering.py: KiCad 7's API has no font engine).
Geometry is in plate-local coords, y up.
B-face items are mirrored about their own box so they read correctly from behind.
"""
import math
from shapely.geometry import Point, LineString, box as sbox
from shapely.affinity import scale as sscale, translate as strans, rotate as srot
from shapely.ops import unary_union
from compose import params as PR
from compose import geom as G
from compose.pcb import switch as SW
from compose.pcb.lettering import text_shape, fit, mirror_about, ring_logo

L = G.LAYOUT


# ---------------------------------------------------------------- free board area
def free_area(plan):
    keep = [SW.switch_cutout(k, grow=0.8) for k in L.keys]
    keep += [SW.bottom_keepout(k).buffer(0.5) for k in L.keys]
    keep += [LineString([ks.cathode, ks.anode]).buffer(2.4) for ks in plan.keys]        # incl. the 'K' marks
    keep += [Point(p).buffer(3.0) for p in plan.holes_m2]
    keep.append(plan.conn_body.buffer(1.2))
    keep += [Point(p).buffer(1.2) for p in plan.conn_pins]
    for p in (plan.conn_pins[0], plan.conn_pins[-1]):                              # "lhs/rhs: pin 1" labels
        keep.append(sbox(p[0] - 8.5, p[1] - 1.2, p[0] - 0.5, p[1] + 1.2))
    keep += list(getattr(plan, "extra_keep", []))                                  # rev 2: LEDs, capacitors
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


def turned(g, rot):
    """g turned by rot degrees about the origin: art laid along an edge (rot 90) is placed and lettered in a frame
    turned by -rot, then turned back."""
    return srot(g, rot, origin=(0, 0)) if rot else g


def art_box(free, tries, w_max, w_min):
    """The box for one piece of art. `tries` lists (height, anchor, rot) in order of preference; the first that fits
    near its anchor wins. Returns (box, height, rot) with the box in the frame turned by -rot, or (None, None, 0)."""
    for h, anc, rot in tries:
        f = turned(free, -rot)
        a = turned(Point(anc), -rot).coords[0] if rot else anc
        b = widest_box(f, h, a, w_max=w_max, w_min=w_min)
        if b is not None:
            return b, h, rot
    return None, None, 0


def art_spots(name):
    """Where the layout puts one piece of art: [(anchor, rot)], from its Layout.art (layouts/<name>/layout.py)."""
    spots = (L.art or {}).get(name)
    if spots is None:
        raise RuntimeError(f"board art: layouts/{PR.LAYOUT}/layout.py gives no place for the {name} (Layout.art, "
                           f"see layouts/compose58/layout.py)")
    spots = [spots] if isinstance(spots[0], (int, float)) else list(spots)
    return [((s[0], s[1]), s[2] if len(s) > 2 else 0) for s in spots]


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
            for a, b in zip(pts[:-1], pts[1:], strict=True):
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

    # Each piece goes where the layout puts it (Layout.art: an anchor, or several in order of preference, each
    # optionally turned 90 degrees to run along an edge). It is lettered in a frame turned with it, then turned back;
    # the B face's copy is mirrored about its own box so it reads correctly from behind.
    def place(g_frame, rot, box):
        return turned(g_frame, rot), (box.bounds[0] + box.bounds[2]) / 2

    # 1. title: ring + name, exposed copper
    tb, _, rot = art_box(free, [(th, anc, r_) for anc, r_ in art_spots("title") for th in (6.0, 5.0, 4.5)],
                         w_max=40.0, w_min=28.0)       # the tallest that fits: the board edge is well inside the plate's
    if tb is None:
        raise RuntimeError(f"board art: no free box for the title at layouts/{PR.LAYOUT}/layout.py's place for it")
    x0, y0, x1, y1 = tb.bounds
    h = y1 - y0
    r = h * 0.42
    ring = ring_logo(x0 + r + 0.3, (y0 + y1) / 2, r)
    name, _ = fit(text_shape(PR.BOARD_NAME, PR.ART_TITLE_FONT), x0 + 2 * r + 1.6, y0 + 0.4, x1 - x0 - 2 * r - 1.9, h - 0.8, "left")
    tb = turned(tb, rot)
    title, cx = place(unary_union([ring, name]), rot, tb)
    a.copper["F"].append(title)
    a.copper["B"].append(mirror_about(title, cx))
    a.keepout = tb.buffer(PR.ART_COPPER_KEEPOUT, join_style="mitre")
    a.boxes.append(tb)

    # 2. tagline + credit, silkscreen
    bb, bh, rot = art_box(free.difference(tb.buffer(1.0)),
                          [(h_, anc, r_) for anc, r_ in art_spots("tagline") for h_ in (5.4, 4.8, 4.2)], w_max=58.0, w_min=30.0)
    if bb is None:
        raise RuntimeError(f"board art: no free box for the tagline at layouts/{PR.LAYOUT}/layout.py's place for it")
    x0, y0, x1, y1 = bb.bounds
    s_ = bh / 5.4                                    # the two lines shrink with a lower box: 2.0 and 3.0 mm in 5.4
    credit_txt = f"{PR.HANDLE} · {PR.REVISION} · {PR.YEAR} · {PR.CREDIT}"
    credit, k2 = fit(text_shape(credit_txt, PR.ART_TEXT_FONT), x0, y0, x1 - x0, 2.0 * s_)
    # one shared size for both faces' code lines: the longer one sets it
    raw = {f: text_shape(PR.TAGLINE[f], PR.ART_CODE_FONT) for f in ("F", "B")}
    k1 = min(fit(raw[f], x0, y0, x1 - x0, 3.0 * s_)[1] for f in ("F", "B"))
    bb = turned(bb, rot)
    for f in ("F", "B"):
        g = sscale(raw[f], k1, k1, origin=(0, 0))
        gx0, gy0, gx1, gy1 = g.bounds
        g = strans(g, x0 - gx0 + (x1 - x0 - (gx1 - gx0)) / 2, y0 + 2.4 * s_ - gy0 + (3.0 * s_ - (gy1 - gy0)) / 2)
        g, cx = place(g, rot, bb)
        c, _ = place(credit, rot, bb)
        a.silk[f].append(g if f == "F" else mirror_about(g, cx))
        a.silk[f].append(c if f == "F" else mirror_about(c, cx))
    a.boxes.append(bb)

    # 3. build labels, per face (the same board is lhs from one face, rhs from the other). The first spot takes the
    #    tallest that fits there, the others 4 mm: the denser boards may not take the tallest
    spots = art_spots("labels")
    tries = [(lh, spots[0][0], spots[0][1]) for lh in (5.0, 4.4, 4.0)] + [(4.0, anc, r_) for anc, r_ in spots[1:]]
    lb, _, rot = art_box(free.difference(unary_union([b.buffer(1.0) for b in a.boxes])), tries, w_max=34.0, w_min=20.0)
    if lb is None:
        raise RuntimeError(f"board art: no free box for the lhs / rhs build labels at layouts/{PR.LAYOUT}/layout.py's places "
                           f"for them")
    x0, y0, x1, y1 = lb.bounds
    lb_board = turned(lb, rot)
    for face, sw, parts in (("F", lhs, rhs), ("B", rhs, lhs)):
        t1 = text_shape(f"{sw} → switches on this side", PR.ART_TEXT_FONT)
        t2 = text_shape(f"{parts} → sockets & diodes on this side", PR.ART_TEXT_FONT)
        k = min(fit(t, x0, y0, x1 - x0, 2.2 * (y1 - y0) / 5.0)[1] for t in (t1, t2))   # same size for both lines
        l1 = strans(sscale(t1, k, k, origin=(0, 0)), x0, y0 + 2.9 * (y1 - y0) / 5.0)
        l2 = strans(sscale(t2, k, k, origin=(0, 0)), x0, y0 + 0.5)
        g, cx = place(unary_union([l1, l2]), rot, lb_board)
        a.silk[face].append(g if face == "F" else mirror_about(g, cx))
    a.boxes.append(lb_board)

    # 4. board id, small (both faces), where the layout puts one
    if (L.art or {}).get("board_id") is not None:
        ib, _, rot = art_box(free.difference(unary_union([b.buffer(1.0) for b in a.boxes] + [a.keepout.buffer(0.8)])),
                             [(2.0, anc, r_) for anc, r_ in art_spots("board_id")], w_max=40.0, w_min=16.0)
        if ib is not None:
            x0, y0, x1, y1 = ib.bounds
            t, _ = fit(text_shape(f"{PR.BOARD_NAME} · half · {variant} · {PR.REVISION}", PR.ART_TEXT_FONT), x0, y0, x1 - x0, y1 - y0)
            ib = turned(ib, rot)
            t, cx = place(t, rot, ib)
            a.silk["F"].append(t)
            a.silk["B"].append(mirror_about(t, cx))
            a.boxes.append(ib)

    # 5. hex lattice everywhere else
    region = free.difference(unary_union([b.buffer(1.0) for b in a.boxes] + [a.keepout.buffer(0.6)]))
    a.lines = hex_lattice(region, PR.ART_HEX_CELL)
    return a

