"""
Pre-routed copper: nets a layout lays out itself, by construction, before the autorouter runs.

Autorouting alone is the default, and a new layout needs nothing here. A layout opts in by adding
layouts/<name>/preroute.py with one function per board family (the rev 2 half boards call
`half_rev2(field, plan)`); with no such file, or with C58_PREROUTE=0, the boards are built, exported and routed
exactly as before.

  Field        a board's fixed geometry per copper face: pads with their nets, unplated holes, keep-out areas,
               the outline. It is what pre-routed copper has to keep clear of, by the board's own rules. The
               board builder makes it from the plan (pure shapely), so a layout's routing can be written and
               checked without KiCad.
  Field.track, via, route      lay copper: straight tracks, vias, and `route`, a track between two points that
               steps round whatever is in the way (the shortest octilinear path on a fine grid: the same
               input always gives the same copper).
  Field.problems               every rule the laid copper breaks: clearance to other nets' pads and copper, to
               holes, edges and keep-outs, loose ends, and each pre-routed net in one piece on all its pads.
  place, check_board, dsn_fix  the KiCad side: the copper onto the board, the same check against the board's
               real pads, and the Specctra export. A pre-routed net leaves the router's job the way GND does
               on the rev 2 RGB boards (rev2_half._export_dsn_power): its pads lose their net, its tracks
               become keep-outs and its vias fixed vias of a net with no pins, which route() skips on import.
"""
import os
import re
import sys
import math
import heapq
import importlib
import numpy as np
import shapely
from shapely.geometry import Point, LineString, Polygon, box as sbox
from shapely.ops import unary_union
from compose import REPO_ROOT
from compose import params as PR

NET = "PREROUTED"            # the router's name for every pre-routed via (a net with no pins)
SLACK = 0.05                 # laid out this far beyond each rule (mm)
VIA_PAD_EXTRA = 0.15         # vias keep this much more from pads: the router measures via-to-pad clearance more
                             #   conservatively than KiCad (as rev2_half.gnd_fanout)
TURN = 0.15                  # route(): what a 45-degree bend costs, as extra length (mm)
RHO_CU = 1.72e-8             # ohm m


def hook(name):
    """The current layout's pre-routing function `name` (layouts/<layout>/preroute.py), or None: no such file,
    no such function, or C58_PREROUTE=0."""
    if os.environ.get("C58_PREROUTE", "1") == "0":
        return None
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    mod = f"layouts.{PR.LAYOUT}.preroute"
    try:
        return getattr(importlib.import_module(mod), name, None)
    except ModuleNotFoundError as e:
        if e.name != mod:
            raise
        return None


class Field:
    def __init__(self, outline, clearance=None, edge=0.4, hole=0.4, via=None):
        """outline: the board (cutouts as holes). clearance: copper to copper of another net. edge: copper to the
        board edge. hole: copper to an unplated hole (KiCad applies the edge clearance to those)."""
        self.outline = outline
        self.clearance = PR.CLEARANCE if clearance is None else clearance
        self.edge_clr, self.hole_clr = edge, hole
        self.via_d, self.via_drill = via or (PR.VIA_D, PR.VIA_DRILL)
        self.pads = []                       # (shape, faces "F" / "B" / "FB", net or None, label)
        self.holes, self.keepouts = [], []
        self.tracks, self.vias = [], []      # (net, face, a, b, width), (net, xy)
        self.worst = {}
        self._static = {}

    # ------------------------------------------------------------ the board
    def pad(self, faces, shape, net=None, label=""):
        self.pads.append((shape, faces, net or None, label))
        self._static.clear()

    def hole(self, shape):
        self.holes.append(shape)
        self._static.clear()

    def keepout(self, shape):
        self.keepouts.append(shape)
        self._static.clear()

    def nets(self):
        return sorted({t[0] for t in self.tracks} | {v[0] for v in self.vias})

    # ------------------------------------------------------------ laying copper
    def track(self, net, face, pts, w):
        """Straight segments through pts on one face."""
        pts = [(float(x), float(y)) for x, y in pts]
        for a, b in zip(pts[:-1], pts[1:]):
            if math.dist(a, b) > 1e-9:
                self.tracks.append((net, face, a, b, float(w)))
        return pts[-1]

    def via(self, net, xy):
        self.vias.append((net, (float(xy[0]), float(xy[1]))))
        return self.vias[-1][1]

    def _free(self, face, net, grow, window=None, via=False):
        """Where the centre line of `net` copper may run on `face` (a via: on both), the copper reaching `grow`
        from it: clear of other nets' pads and copper, holes, keep-outs and the edge by the rules."""
        key = (face, net, round(grow, 4), via)
        if key not in self._static:
            c = self.clearance + (VIA_PAD_EXTRA if via else 0.0)
            blk = [s.buffer(c + grow) for s, f, n, _ in self.pads if n != net and (via or face in f)]
            blk += [h.buffer(self.hole_clr + grow) for h in self.holes]
            blk += [k.buffer(grow) for k in self.keepouts]
            self._static[key] = self.outline.buffer(-(self.edge_clr + grow)).difference(unary_union(blk))
        free = self._static[key]
        if window is not None:
            free = free.intersection(window)
        dyn = [LineString([a, b]).buffer(w / 2 + self.clearance + grow)
               for n, f, a, b, w in self.tracks if n != net and (via or f == face)]
        dyn += [Point(p).buffer(self.via_d / 2 + self.clearance + grow) for n, p in self.vias if n != net]
        if window is not None:
            dyn = [d for d in dyn if d.intersects(window)]
        return free.difference(unary_union(dyn)) if dyn else free

    def can_via(self, net, xy, slack=SLACK):
        return self._free("F", net, self.via_d / 2 + slack, via=True).contains(Point(xy))

    def can_track(self, net, face, pts, w, slack=SLACK):
        return self._free(face, net, w / 2 + slack).covers(LineString(pts))

    def route(self, net, face, a, b, w, slack=SLACK, reach=3.0, step=0.1):
        """A track from a to b on one face: straight if that is clear, else the shortest way round on a grid
        of `step` through a (octilinear, bends cost TURN), searched up to 4 x `reach` beyond the two points."""
        a, b = (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))
        grow = w / 2 + slack
        for r in (reach, 2 * reach, 4 * reach):
            win = sbox(min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r)
            free = self._free(face, net, grow, win)
            if free.covers(LineString([a, b])):
                pts = [a, b]
            else:
                pts = _astar(free, a, b, step, win.bounds)
            if pts:
                return self.track(net, face, pts, w)
        raise RuntimeError(f"pre-route: no way for {net} on {face}.Cu from ({a[0]:.2f}, {a[1]:.2f}) to "
                           f"({b[0]:.2f}, {b[1]:.2f}) at {w} mm")

    def through(self, net, face, pts, w, **kw):
        """route() through a list of points, in order."""
        for a, b in zip(pts[:-1], pts[1:]):
            self.route(net, face, a, b, w, **kw)
        return pts[-1]

    # ------------------------------------------------------------ the result
    def segments(self):
        """The tracks, split wherever another track of the same net and face ends on them, so every junction
        is a shared end point (KiCad and the checks then read a T as joined)."""
        segs = list(self.tracks)
        again = True
        while again:
            again = False
            ends = {}
            for n, f, a, b, w in segs:
                ends.setdefault((n, f), set()).update((a, b))
            out = []
            for n, f, a, b, w in segs:
                cut = [p for p in ends[(n, f)] if p != a and p != b and _on(a, b, p)]
                if cut:
                    again = True
                    cut.sort(key=lambda p: math.dist(a, p))
                    for p, q in zip([a] + cut, cut + [b]):
                        out.append((n, f, p, q, w))
                else:
                    out.append((n, f, a, b, w))
            segs = out
        return segs

    def problems(self):
        """Every rule the laid copper breaks, as text (empty: none). Also fills self.worst: the smallest gap
        found to other nets' pads, to holes, to the edge and between pre-routed nets."""
        out = []
        worst = {"pad": 9.0, "hole": 9.0, "edge": 9.0, "copper": 9.0}
        at = lambda p: f"({p[0]:.2f}, {p[1]:.2f})"
        segs = self.segments()
        items = [(n, f, LineString([a, b]).buffer(w / 2), f"{n} track on {f}.Cu {at(a)}-{at(b)}") for n, f, a, b, w in segs]
        items += [(n, "FB", Point(p).buffer(self.via_d / 2), f"{n} via at {at(p)}") for n, p in self.vias]
        tol = 1e-6
        border = self.outline.boundary
        for i, (n, f, shp, what) in enumerate(items):
            for s, pf, pn, label in self.pads:
                if pn != n and any(x in pf for x in f):
                    d = shp.distance(s)
                    worst["pad"] = min(worst["pad"], d)
                    if d < self.clearance - tol:
                        out.append(f"{what}: {d:.3f} mm from pad {label or '?'} ({pn or 'no net'}), under {self.clearance}")
            for h in self.holes:
                d = shp.distance(h)
                worst["hole"] = min(worst["hole"], d)
                if d < self.hole_clr - tol:
                    out.append(f"{what}: {d:.3f} mm from an unplated hole at {at(h.centroid.coords[0])}, under {self.hole_clr}")
            d = shp.distance(border) if self.outline.contains(shp) else -1.0
            worst["edge"] = min(worst["edge"], d)
            if d < self.edge_clr - tol:
                out.append(f"{what}: {d:.3f} mm from the board edge, under {self.edge_clr}" if d >= 0 else f"{what}: off the board")
            if any(shp.intersects(k) for k in self.keepouts):
                out.append(f"{what}: in a keep-out area")
            for n2, f2, shp2, what2 in items[i + 1:]:
                if n2 != n and any(x in f2 for x in f):
                    d = shp.distance(shp2)
                    worst["copper"] = min(worst["copper"], d)
                    if d < self.clearance - tol:
                        out.append(f"{what}: {d:.3f} mm from {what2}, under {self.clearance}")
        self.worst = worst
        # each net: one piece, on every pad of the net, no loose ends
        for net in self.nets():
            mine = [(f, shp, what) for n, f, shp, what in items if n == net]
            pads = [(pf, s, f"pad {label}") for s, pf, pn, label in self.pads if pn == net]
            allp = mine + pads
            parent = list(range(len(allp)))

            def find(i):
                while parent[i] != i:
                    parent[i] = parent[parent[i]]
                    i = parent[i]
                return i
            for i in range(len(allp)):
                for j in range(i + 1, len(allp)):
                    if any(x in allp[j][0] for x in allp[i][0]) and allp[i][1].intersects(allp[j][1]):
                        parent[find(i)] = find(j)
            groups = {}
            for i in range(len(allp)):
                groups.setdefault(find(i), []).append(i)
            if len(groups) > 1:
                small = sorted(groups.values(), key=len)[:-1]
                eg = "; ".join(allp[g[0]][2] for g in small[:4])
                out.append(f"{net}: in {len(groups)} pieces, not one ({sum(len(g) for g in small)} items apart from the "
                           f"rest, e.g. {eg})")
            for n, f, a, b, w in segs:
                if n != net:
                    continue
                for e in (a, b):
                    pe = Point(e)
                    if any(x == f and (p == e or q == e) and (p, q) != (a, b) for m, x, p, q, _ in segs if m == net):
                        continue
                    if any(m == net and math.dist(p, e) < self.via_d / 2 for m, p in self.vias):
                        continue
                    if any(pn == net and f in pf and s.covers(pe) for s, pf, pn, _ in self.pads):
                        continue
                    out.append(f"{net} track on {f}.Cu ends on nothing at {at(e)}")
        return out

    # ------------------------------------------------------------ resistance
    def resistance(self, net, feeds, loads, copper_t=35e-6, derate=1.2, via_plating=18e-6, board_t=None, width=None):
        """Worst resistance (ohm) from the feed points, tied together, to any load point, through this net's
        laid copper: 1 oz copper with +20 % for temperature and plating tolerance, as board_facts() in
        compose/sim/controller_spice.py; a via is its barrel. Points are (xy, face)."""
        segs = [(a, b, w, f) for n, f, a, b, w in self.segments() if n == net]
        vias = [p for n, p in self.vias if n == net]
        pads = [(s, pf) for s, pf, pn, _ in self.pads if pn == net]
        return rail_resistance(segs, vias, pads, feeds, loads, self.via_d, self.via_drill, copper_t, derate, via_plating,
                               PR.PCB_T if board_t is None else board_t, width)[0]


def _on(a, b, p, tol=1e-6):
    """p on the segment a-b (ends included)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.dist(a, p) <= tol
    u = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    return -1e-9 <= u <= 1 + 1e-9 and math.hypot(a[0] + u * dx - p[0], a[1] + u * dy - p[1]) <= tol


_DIRS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))


def _astar(free, a, b, step, bounds):
    """Shortest octilinear path from a to b inside `free` (a shapely area), on a grid of `step` through a.
    Returns the corner points, or None."""
    x0, y0, x1, y1 = bounds
    i0, i1 = int(math.floor((x0 - a[0]) / step)), int(math.ceil((x1 - a[0]) / step))
    j0, j1 = int(math.floor((y0 - a[1]) / step)), int(math.ceil((y1 - a[1]) / step))
    ni, nj = i1 - i0 + 1, j1 - j0 + 1
    xs, ys = a[0] + step * np.arange(i0, i1 + 1), a[1] + step * np.arange(j0, j1 + 1)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    ok = shapely.contains_xy(free, X.ravel(), Y.ravel()).reshape(ni, nj)
    xy = lambda i, j: (a[0] + step * (i + i0), a[1] + step * (j + j0))
    start = (-i0, -j0)
    if not ok[start]:
        return None
    # the goal: the free grid point nearest b that sees b
    gi, gj = int(round((b[0] - a[0]) / step)) - i0, int(round((b[1] - a[1]) / step)) - j0
    goal = None
    for r in range(0, 5):
        cand = [(gi + di, gj + dj) for di in range(-r, r + 1) for dj in range(-r, r + 1) if max(abs(di), abs(dj)) == r]
        cand = [c for c in cand if 0 <= c[0] < ni and 0 <= c[1] < nj and ok[c] and free.covers(LineString([xy(*c), b]))]
        if cand:
            goal = min(cand, key=lambda c: math.dist(xy(*c), b))
            break
    if goal is None:
        return None
    h = lambda i, j: step * (max(abs(i - goal[0]), abs(j - goal[1])) + (math.sqrt(2) - 1) * min(abs(i - goal[0]), abs(j - goal[1])))
    best = {(start[0], start[1], -1): 0.0}
    came = {}
    heap = [(h(*start), 0.0, start[0], start[1], -1)]
    end = None
    while heap:
        _, g, i, j, d = heapq.heappop(heap)
        if g > best.get((i, j, d), 1e18) + 1e-12:
            continue
        if (i, j) == goal:
            end = (i, j, d)
            break
        for nd, (di, dj) in enumerate(_DIRS):
            ii, jj = i + di, j + dj
            if not (0 <= ii < ni and 0 <= jj < nj) or not ok[ii, jj]:
                continue
            if di and dj and not (ok[ii, j] and ok[i, jj]):      # no cutting a corner
                continue
            turn = 0 if d < 0 else min((nd - d) % 8, (d - nd) % 8)
            if turn > 2:                                          # nothing sharper than a right angle
                continue
            g2 = g + step * (math.sqrt(2) if di and dj else 1.0) + TURN * turn
            k = (ii, jj, nd)
            if g2 < best.get(k, 1e18) - 1e-12:
                best[k] = g2
                came[k] = (i, j, d)
                heapq.heappush(heap, (g2 + h(ii, jj), g2, ii, jj, nd))
    if end is None:
        return None
    nodes = []
    k = end
    while k in came:
        nodes.append(k)
        k = came[k]
    nodes.append(k)
    nodes.reverse()
    # corners only: a point stays where the direction after it changes
    corners = [xy(nodes[0][0], nodes[0][1])]
    for m, n in zip(nodes[1:], nodes[2:] + [None]):
        if n is None or n[2] != m[2]:
            corners.append(xy(m[0], m[1]))
    while len(corners) >= 2 and free.covers(LineString([corners[-2], b])):     # the last leg straight onto b
        corners.pop()
    if math.dist(corners[-1], b) > 1e-9:
        corners.append(b)
    return corners


# ---------------------------------------------------------------- resistance of a rail's copper
def rail_resistance(segs, vias, pads, feeds, loads, via_d, via_drill, copper_t=35e-6, derate=1.2, via_plating=18e-6,
                    board_t=1.6, width=None):
    """A net's copper as a resistor network. segs: (a, b, width mm, face); vias: xy; pads: (shape, faces), each
    one node. feeds, loads: (xy, face) points on that copper; the feeds are tied together. Returns
    (worst feed-to-load resistance, the load it is at, resistance to each load, the far load's drop per ampere
    of total current with every load drawing the same). A load the copper doesn't reach reads infinite.
    width: read every track at this width instead (negative control)."""
    node = {}

    def nid(key):
        return node.setdefault(key, len(node))
    parent = []

    def find(i):
        while len(parent) <= i:
            parent.append(len(parent))
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def tie(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    rnd = lambda p: (round(p[0], 4), round(p[1], 4))
    edges = []                                    # (node, node, ohm)
    pts_on = [[] for _ in segs]                   # split points along each segment: (u, node)
    for k, (a, b, w, f) in enumerate(segs):
        pts_on[k] += [(0.0, nid(("p", f, rnd(a)))), (1.0, nid(("p", f, rnd(b))))]
    for k, (a, b, w, f) in enumerate(segs):       # another track's end on this one: a junction
        L = math.dist(a, b)
        if L == 0:
            continue
        for k2, (a2, b2, w2, f2) in enumerate(segs):
            if k2 == k or f2 != f:
                continue
            for e in (a2, b2):
                u = ((e[0] - a[0]) * (b[0] - a[0]) + (e[1] - a[1]) * (b[1] - a[1])) / (L * L)
                if 0 < u < 1 and math.hypot(a[0] + u * (b[0] - a[0]) - e[0], a[1] + u * (b[1] - a[1]) - e[1]) <= w / 2:
                    pts_on[k].append((u, nid(("p", f, rnd(e)))))
    for iv, v in enumerate(vias):                 # a via: one node per face, its barrel between them
        nf, nb = nid(("v", iv, "F")), nid(("v", iv, "B"))
        edges.append((nf, nb, derate * RHO_CU * board_t * 1e-3 / (math.pi * via_drill * 1e-3 * via_plating)))
        for k, (a, b, w, f) in enumerate(segs):
            L = math.dist(a, b)
            u = 0.0 if L == 0 else max(0.0, min(1.0, ((v[0] - a[0]) * (b[0] - a[0]) + (v[1] - a[1]) * (b[1] - a[1])) / (L * L)))
            if math.hypot(a[0] + u * (b[0] - a[0]) - v[0], a[1] + u * (b[1] - a[1]) - v[1]) <= via_d / 2:
                pts_on[k].append((u, nid(("v", iv, f))))
    for ip, (shape, faces) in enumerate(pads):    # a pad: one node; a track is tied to it where it enters and leaves
        pn = nid(("pad", ip))
        for iv, v in enumerate(vias):
            if shape.covers(Point(v)):
                for f in faces:
                    tie(pn, nid(("v", iv, f)))
        for k, (a, b, w, f) in enumerate(segs):
            if f not in faces:
                continue
            L = math.dist(a, b)
            cut = LineString([a, b]).intersection(shape) if L else (Point(a) if shape.covers(Point(a)) else Point())
            for g in getattr(cut, "geoms", [cut]):
                if g.is_empty:
                    continue
                for q in g.coords:
                    u = 0.0 if L == 0 else max(0.0, min(1.0, math.dist(a, q) / L))
                    m = nid(("pp", ip, k, round(u, 6)))
                    pts_on[k].append((u, m))
                    tie(pn, m)
    for k, (a, b, w, f) in enumerate(segs):
        L = math.dist(a, b)
        ww = w if width is None else width
        pp = sorted(pts_on[k])
        for (u1, n1), (u2, n2) in zip(pp[:-1], pp[1:]):
            if u2 - u1 < 1e-9:
                tie(n1, n2)
            else:
                edges.append((n1, n2, derate * RHO_CU * (u2 - u1) * L * 1e-3 / (ww * 1e-3 * copper_t)))

    def at(point):
        xy, f = point
        p = Point(xy)
        for ip, (shape, faces) in enumerate(pads):
            if f in faces and shape.covers(p):
                return find(nid(("pad", ip)))
        return None
    src = [at(p) for p in feeds]
    dst = [at(p) for p in loads]
    if any(s is None for s in src):
        raise ValueError("a feed point is on no pad of the net")
    for s in src[1:]:
        tie(src[0], s)
    root = find(src[0])
    roots = sorted({find(i) for i in range(len(node))})
    idx = {r: i for i, r in enumerate(roots)}
    n = len(roots)
    Gm = np.zeros((n, n))
    for i, j, r in edges:
        i, j = idx[find(i)], idx[find(j)]
        if i != j:
            g = 1.0 / r
            Gm[i, i] += g
            Gm[j, j] += g
            Gm[i, j] -= g
            Gm[j, i] -= g
    # nodes the feed reaches
    seen, todo = {idx[root]}, [idx[root]]
    while todo:
        i = todo.pop()
        for j in np.nonzero(Gm[i])[0]:
            if int(j) not in seen:
                seen.add(int(j))
                todo.append(int(j))
    keep = sorted(seen - {idx[root]})
    pos = {i: k for k, i in enumerate(keep)}
    Rm = np.linalg.inv(Gm[np.ix_(keep, keep)]) if keep else np.zeros((0, 0))
    each, cols = [], []
    for d in dst:
        i = None if d is None else idx[find(d)]
        if i is not None and i == idx[root]:
            each.append(0.0)
        elif i is None or i not in pos:
            each.append(float("inf"))
        else:
            each.append(float(Rm[pos[i], pos[i]]))
            cols.append(pos[i])
    worst = max(each) if each else 0.0
    far = each.index(worst) if each else None
    shared = float((Rm[:, cols].sum(axis=1) / len(dst)).max()) if cols else 0.0
    if any(math.isinf(e) for e in each):
        shared = float("inf")
    return worst, far, each, shared


# ---------------------------------------------------------------- KiCad side
def place(board, field, K):
    """The field's copper onto the board (K: its coordinates -> KiCad mm), and the nets it holds noted on the
    board (kb2_prerouted) for the export, the import and the clean-up after routing."""
    import pcbnew
    from compose.pcb import kicad as PK
    nets = board.GetNetsByName()
    lay = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu}
    names = field.nets()
    for n in names:
        try:
            nets[n]
        except (KeyError, IndexError):
            raise RuntimeError(f"pre-route: the board has no net {n}")
    for n, f, a, b, w in field.segments():
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(PK.V(*K(a)))
        t.SetEnd(PK.V(*K(b)))
        t.SetWidth(PK.MM(w))
        t.SetLayer(lay[f])
        t.SetNet(nets[n])
        board.Add(t)
    for n, p in field.vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(PK.V(*K(p)))
        v.SetWidth(PK.MM(field.via_d))
        v.SetDrill(PK.MM(field.via_drill))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(nets[n])
        board.Add(v)
    board.kb2_prerouted = tuple(names)
    return len(field.segments()), len(field.vias)


def board_field(board):
    """A Field read back from the KiCad board itself (KiCad mm, y down): its real pad shapes and nets, unplated
    holes, exposed-copper art, keep-out areas, and every track and via on it."""
    import pcbnew
    from compose.pcb import kicad as PK
    ToMM = pcbnew.ToMM
    ol, ox, oy = board.kb2_outline
    kol = Polygon([PK.K(p, ox, oy) for p in ol.exterior.coords], [[PK.K(p, ox, oy) for p in r.coords] for r in ol.interiors])
    ec = ToMM(board.GetDesignSettings().m_CopperEdgeClearance)
    f = Field(kol, edge=ec, hole=ec)
    lays = (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu))

    def poly(p, lay):
        ps = pcbnew.SHAPE_POLY_SET()
        p.TransformShapeToPolygon(ps, lay, 0, PK.MM(0.005))
        o = ps.Outline(0)
        return Polygon([(ToMM(o.CPoint(i).x), ToMM(o.CPoint(i).y)) for i in range(o.PointCount())])
    for fp in board.GetFootprints():
        for p in fp.Pads():
            q = p.GetPosition()
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:      # a slot as the circle round it
                f.hole(Point(ToMM(q.x), ToMM(q.y)).buffer(max(ToMM(p.GetDrillSize().x), ToMM(p.GetDrillSize().y)) / 2))
                continue
            on = [(c, lay) for c, lay in lays if p.IsOnLayer(lay)]
            if on:
                f.pad("".join(c for c, _ in on), poly(p, on[0][1]), p.GetNetname(), f"{fp.GetReference()}.{p.GetNumber()}")
    for d in board.GetDrawings():                               # exposed-copper art
        for c, lay in lays:
            if d.GetLayer() == lay:
                bb = d.GetBoundingBox()
                f.pad(c, sbox(ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())), None, "art")
    for z in list(board.Zones()) + [z for fp in board.GetFootprints() for z in fp.Zones()]:
        if z.GetIsRuleArea() and (z.GetDoNotAllowVias() or z.GetDoNotAllowTracks()):
            o = z.Outline()
            for i in range(o.OutlineCount()):
                ln = o.Outline(i)
                f.keepout(Polygon([(ToMM(ln.CPoint(j).x), ToMM(ln.CPoint(j).y)) for j in range(ln.PointCount())]).buffer(0))
    name = {pcbnew.F_Cu: "F", pcbnew.B_Cu: "B"}
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            q = t.GetPosition()
            f.via(t.GetNetname(), (ToMM(q.x), ToMM(q.y)))
        else:
            a, c = t.GetStart(), t.GetEnd()
            f.track(t.GetNetname(), name[t.GetLayer()], [(ToMM(a.x), ToMM(a.y)), (ToMM(c.x), ToMM(c.y))], ToMM(t.GetWidth()))
    return f


def check_board(board):
    """The pre-routed copper against the KiCad board's own pads, holes, art, keep-outs and edge, before the
    router gets it: a rule broken here would otherwise only show as a DRC error after every routing attempt."""
    f = board_field(board)
    probs = f.problems()
    if probs:
        raise RuntimeError("pre-routed copper breaks the board's rules:\n  " + "\n  ".join(probs[:40]))
    return f.worst


def board_copper(board):
    """The pre-routed tracks and vias on the board, in the router's units: (layer name, width, (x, y), (x, y))
    and (x, y), micrometres, y up."""
    import pcbnew
    um = lambda q: (pcbnew.ToMM(q.x) * 1000.0, -pcbnew.ToMM(q.y) * 1000.0)
    pre = set(getattr(board, "kb2_prerouted", ()))
    tracks, vias = [], []
    for t in board.GetTracks():
        if t.GetNetname() not in pre:
            continue
        if t.GetClass() == "PCB_VIA":
            vias.append(um(t.GetPosition()))
        else:
            lay = "F.Cu" if t.GetLayer() == pcbnew.F_Cu else "B.Cu"
            tracks.append((lay, pcbnew.ToMM(t.GetWidth()) * 1000.0, um(t.GetStart()), um(t.GetEnd())))
    return tracks, vias


def dsn_fix(t, nets, tracks, vias):
    """Take pre-routed nets out of a Specctra DSN (text in, text out): their pads lose their net, their wires
    go, their tracks come back as keep-outs on their layer and their vias as fixed vias of NET, a net with no
    pins. tracks, vias: board_copper(). The router then keeps clear of that copper and never routes it."""
    if not nets:
        return t
    i, j = t.index("(network"), t.find("(wiring")
    j = len(t) if j < 0 else j
    head, netw, wiring = t[:i], t[i:j], t[j:]
    first = True
    for n in nets:
        q = r'"?' + re.escape(n) + r'"?'
        netw, k = re.subn(r"\(net " + q + r"\s*\(pins[^)]*\)\s*\)", f"(net {NET})" if first else "", netw, count=1)
        if not k:
            raise RuntimeError(f"pre-route: net {n} isn't in the router's net list")
        first = False
        netw = re.sub(r"(?<=[\s(])" + q + r"(?=[\s)])", "", netw)
        # its wires out (KiCad joins end-to-end tracks into one multi-point path, wrapped over lines)
        out, pos = [], 0
        for m in re.finditer(r"\s*\(wire ", wiring):
            if m.start() < pos:
                continue
            depth, e = 0, m.end() - len("(wire ")
            for e in range(e, len(wiring)):
                depth += (wiring[e] == "(") - (wiring[e] == ")")
                if depth == 0:
                    break
            if re.search(r"\(net " + q + r"\)", wiring[m.start():e + 1]):
                out.append(wiring[pos:m.start()])
                pos = e + 1
        wiring = "".join(out) + wiring[pos:]
        wiring = re.sub(r'(\(via "[^"]*"\s+-?[\d.]+\s+-?[\d.]+\s*)\(net ' + q + r"\)\(type \w+\)",
                        rf"\1(net {NET})(type fix)", wiring)
    got = len(re.findall(r"\(net " + NET + r"\)\(type fix\)", wiring))
    if got != len(vias):
        raise RuntimeError(f"pre-route: {len(vias)} vias on the board, {got} in the router's file")
    # tracks -> keep-outs, stopped short of every fixed via's clearance ring: the router reads a keep-out that
    # touches a via as a violation (as the GND fanout stubs)
    cut = (PR.VIA_D / 2 * 1.1 + PR.CLEARANCE + 0.05) * 1000
    rings = unary_union([Point(v).buffer(cut) for v in vias]) if vias else None
    keep = []
    for lay, w, a, b in tracks:
        band = LineString([a, b]).buffer(w / 2 + 20, quad_segs=4)            # + 0.02 mm
        if rings is not None:
            band = band.difference(rings)
        for g in getattr(band, "geoms", [band]):
            if g.is_empty or g.geom_type != "Polygon" or g.area < 1.0:
                continue
            keep.append(f'    (keepout "" (polygon {lay} 0 ' + " ".join(f"{x:.1f} {y:.1f}" for x, y in g.exterior.coords) + "))\n")
    st = head.index("(structure")                             # after the layers and the boundary
    k = min(x for x in (head.find("\n    (keepout", st), head.find("\n    (via ", st)) if x > 0) + 1
    return head[:k] + "".join(keep) + head[k:] + netw + wiring
