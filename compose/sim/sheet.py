"""Copper as a resistor sheet, for copper that is an area (a pour) where a network of tracks
(compose.pcb.preroute.rail_resistance) has nothing to read.

Both faces' areas (pour, pads, via lands) are rastered on a square grid and solved as bilinear finite elements,
one per copper cell, with the nodes at the cells' corners. The two faces are joined at each via through its
barrel. Tracks are not rastered: a grid this size gets a 0.25 mm track's width wrong by a cell. Where a track
runs over rastered copper it adds nothing; each stretch of it outside is a resistor of its own length and
width between the copper it leaves and the copper it enters (or another track's end, where two meet outside).
Pads held at 0 V are the sinks; a load is a pad that feeds its current in evenly over its area, and its voltage
is the pad's mean. Copper values are those of rail_resistance (1 oz foil, +20 % for temperature and plating
tolerance).

What the grid costs: an area narrower than about four cells (a neck of pour, a thermal spoke) is a cell out
either way. A track that ends on the middle of another outside all rastered copper is not joined to it.

Needs no KiCad. `python3 -m compose.sim.sheet` runs the method against shapes whose answer is known.
"""
import math
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spl
from scipy.sparse.csgraph import connected_components
from shapely.geometry import Point, box
from compose.pcb.preroute import RHO_CU

GRID = 0.125                 # mm


def _rings(shape):
    for g in getattr(shape, "geoms", [shape]):
        if g.is_empty or g.geom_type != "Polygon":
            continue
        yield [np.asarray(g.exterior.coords[:-1], float)] + [np.asarray(r.coords[:-1], float) for r in g.interiors]


class Sheet:
    """areas: [(shapely polygon, face)], face "F" or "B": one conductor's pour, pads and via lands.
    vias: [xy] in mm, each joining the two faces through a barrel of that drill.
    tracks: [(a, b, width mm, face)], the same conductor's tracks."""

    def __init__(self, areas, vias=(), tracks=(), h=GRID, via_drill=0.3, copper_t=35e-6, derate=1.2, via_plating=18e-6,
                 board_t=1.6):
        self.h = h
        self.rs = derate * RHO_CU / copper_t                                       # ohm per square
        self.r_via = derate * RHO_CU * board_t * 1e-3 / (math.pi * via_drill * 1e-3 * via_plating)
        bx = np.array([s.bounds for s, _ in areas])
        self.x0, self.y0 = bx[:, 0].min() - h, bx[:, 1].min() - h
        self.nx = int((bx[:, 2].max() + h - self.x0) / h) + 1
        self.ny = int((bx[:, 3].max() + h - self.y0) / h) + 1
        self.g = {f: np.zeros((self.ny, self.nx), bool) for f in "FB"}
        for s, f in areas:
            self.raster(s, self.g[f])
        # each copper cell is one element: a sixth of the sheet conductance along each of its four edges, a
        # third across each diagonal
        self.idx, n = {}, 0
        gs = 1 / self.rs
        rows, cols, vals = [], [], []
        for f in "FB":
            c = self.g[f]
            used = np.zeros((self.ny + 1, self.nx + 1), bool)
            used[:-1, :-1] |= c; used[:-1, 1:] |= c; used[1:, :-1] |= c; used[1:, 1:] |= c
            a = np.full((self.ny + 1, self.nx + 1), -1, np.int64)
            a[used] = np.arange(n, n + int(used.sum()))
            n += int(used.sum())
            self.idx[f] = a
            n00, n10, n01, n11 = a[:-1, :-1][c], a[:-1, 1:][c], a[1:, :-1][c], a[1:, 1:][c]
            for u, v, k in ((n00, n10, 6), (n01, n11, 6), (n00, n01, 6), (n10, n11, 6), (n00, n11, 3), (n10, n01, 3)):
                rows.append(u); cols.append(v); vals.append(np.full(len(u), gs / k))
        self.vias = 0
        for v in vias:                                    # the barrel: every node pair inside the drill, in parallel
            pf, pb = self._pairs(v, via_drill / 2)
            if len(pf):
                rows.append(pf); cols.append(pb); vals.append(np.full(len(pf), 1 / (self.r_via * len(pf))))
                self.vias += 1
        # tracks: the stretches outside rastered copper, each a resistor between what it leaves and what it enters
        self.n_sheet, joint, self.pieces = n, {}, 0
        tie = 1e4 * gs
        for a, b, w, f in tracks:
            length = math.dist(a, b)
            if length == 0:
                continue
            k = max(2, int(math.ceil(length / (h / 4))) + 1)
            t = np.linspace(0.0, 1.0, k)
            px, py = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
            ins = self.g[f][np.clip(((py - self.y0) / h).astype(int), 0, self.ny - 1),
                            np.clip(((px - self.x0) / h).astype(int), 0, self.nx - 1)]
            i = 0
            while i < k:
                if ins[i]:
                    i += 1
                    continue
                j = i
                while j + 1 < k and not ins[j + 1]:
                    j += 1                                    # samples i..j are outside
                ends = []                                     # (where along the track, junction node, mouth nodes)
                for e, inner in ((i, i - 1), (j, j + 1)):
                    if 0 <= inner < k:                        # it meets rastered copper there
                        ends.append(((t[e] + t[inner]) / 2, None, self.near((px[inner], py[inner]), f, max(w / 2, h))))
                    else:                                     # the track's own end, outside: joins a track ending there
                        key = (f, round(float(px[e]), 3), round(float(py[e]), 3))
                        ends.append((t[e], joint.setdefault(key, n + len(joint)), None))
                (t0, j0, m0), (t1, j1, m1) = ends
                run = (t1 - t0) * length
                if run > 0:
                    node = []
                    for jn, mouth in ((j0, m0), (j1, m1)):
                        if jn is None:                        # a junction node tied to the copper's mouth
                            jn = n + len(joint)
                            joint[("mouth", self.pieces, len(node))] = jn
                            rows.append(np.full(len(mouth), jn)); cols.append(mouth); vals.append(np.full(len(mouth), tie))
                        node.append(jn)
                    rows.append(np.array([node[0]])); cols.append(np.array([node[1]]))
                    vals.append(np.array([1 / (self.rs * run / w)]))
                    self.pieces += 1
                i = j + 1
        n += len(joint)
        self.n = n
        r, c, v = np.concatenate(rows), np.concatenate(cols), np.concatenate(vals)
        self.A = sp.coo_matrix((np.concatenate([v, v]), (np.concatenate([r, c]), np.concatenate([c, r]))), shape=(n, n)).tocsr()
        self.groups, self.label = connected_components(self.A, directed=False)

    def _window(self, p, r):
        h = self.h
        j, i = int(round((p[1] - self.y0) / h)), int(round((p[0] - self.x0) / h))
        k = max(1, int(math.ceil(r / h)))
        jj, ii = np.mgrid[max(0, j - k):min(self.ny + 1, j + k + 1), max(0, i - k):min(self.nx + 1, i + k + 1)]
        return jj, ii, np.hypot(self.x0 + ii * h - p[0], self.y0 + jj * h - p[1])

    def near(self, p, face, r):
        """Copper nodes of a face within r of a point (the nearest one within a cell of r, if none is)."""
        jj, ii, d = self._window(p, r + self.h)
        a = self.idx[face][jj, ii]
        m = (a >= 0) & (d <= r)
        if not m.any() and (a >= 0).any():
            m = (a >= 0) & (d <= np.where(a >= 0, d, np.inf).min() + 1e-9)
        return a[m]

    def _pairs(self, p, r):
        """Node pairs (front, back) inside a drill at p: where both faces have copper."""
        jj, ii, d = self._window(p, r)
        u, w = self.idx["F"][jj, ii], self.idx["B"][jj, ii]
        m = (u >= 0) & (w >= 0)
        m &= d <= max(r, np.where(m, d, np.inf).min() + 1e-9) if m.any() else False
        return u[m], w[m]

    def raster(self, shape, grid):
        """Set the cells whose centre is inside shape (even-odd over its rings, so holes stay open)."""
        h, x0, y0 = self.h, self.x0, self.y0
        for rings in _rings(shape):
            p = np.concatenate(rings)
            q = np.concatenate([np.roll(r, -1, axis=0) for r in rings])
            j0 = max(0, int((p[:, 1].min() - y0) / h - 0.5))
            j1 = min(grid.shape[0] - 1, int((p[:, 1].max() - y0) / h + 0.5))
            for j in range(j0, j1 + 1):
                yc = y0 + (j + 0.5) * h
                m = (p[:, 1] <= yc) != (q[:, 1] <= yc)
                if not m.any():
                    continue
                xc = np.sort(p[m, 0] + (yc - p[m, 1]) * (q[m, 0] - p[m, 0]) / (q[m, 1] - p[m, 1]))
                for a, c in zip(xc[0::2], xc[1::2]):
                    i0, i1 = int(math.ceil((a - x0) / h - 0.5)), int(math.floor((c - x0) / h - 0.5))
                    if i1 >= i0:
                        grid[j, max(0, i0):i1 + 1] = True

    def pad(self, shape, face):
        """A pad on a face: (nodes of the copper cells under it, each node's share of the pad's area)."""
        m = np.zeros((self.ny, self.nx), bool)
        self.raster(shape, m)
        m &= self.g[face]
        w = np.zeros((self.ny + 1, self.nx + 1))
        w[:-1, :-1] += m; w[:-1, 1:] += m; w[1:, :-1] += m; w[1:, 1:] += m
        on = w > 0
        return self.idx[face][on], w[on] / max(1.0, w.sum())

    def solve(self, sinks, loads):
        """sinks, loads: [(polygon, face)]. Returns (ohm from the sinks, tied together, to each load drawing
        alone; volt at each load per ampere of total current with every reached load drawing the same). A load
        the sinks' copper doesn't reach reads infinite in both."""
        none = [math.inf] * len(loads)
        fixed = np.zeros(self.n, bool)
        for s, f in sinks:
            fixed[self.pad(s, f)[0]] = True
        if not fixed.any():
            return none, list(none)
        live = np.isin(self.label, np.unique(self.label[fixed]))
        free = live & ~fixed
        nf = int(free.sum())
        pos = np.full(self.n, -1, np.int64)
        pos[free] = np.arange(nf)
        lap = sp.diags(np.asarray(self.A.sum(axis=1)).ravel()) - self.A
        lu = spl.splu(lap[free][:, free].tocsc())
        at = []
        for s, f in loads:
            nodes, share = self.pad(s, f)
            at.append((nodes, share) if len(nodes) and live[nodes].all() else None)
        reached = sum(1 for c in at if c is not None)
        alone, total = [], np.zeros(nf)
        for c in at:
            if c is None:
                alone.append(math.inf)
                continue
            m = pos[c[0]] >= 0                                    # (a node shared with a sink stays at 0 V)
            rhs = np.zeros(nf)
            rhs[pos[c[0]][m]] = c[1][m]
            v = lu.solve(rhs)
            alone.append(float(v[pos[c[0]][m]] @ c[1][m]))
            total += v / reached
        same = [math.inf if c is None else float(total[pos[c[0]][pos[c[0]] >= 0]] @ c[1][pos[c[0]] >= 0]) for c in at]
        return alone, same


def selftest(h=GRID, say=print):
    """The method on shapes with a known answer. Returns the problems found."""
    bad = []
    rs = 1.2 * RHO_CU / 35e-6

    def case(what, got, want, tol):
        err = got / want - 1
        say(f"  {'ok  ' if abs(err) <= tol else 'FAIL'}  sheet method, {what}: {got * 1e3:.2f} mohm, {want * 1e3:.2f} by hand "
            f"({err * 100:+.1f} %, within {tol * 100:.0f} % asked)")
        if abs(err) > tol:
            bad.append(what)
    # a strip along the grid, a pad across each end: rs (gap + a third of the load pad) / width
    strip = [(box(0, 0, 40, 2), "F")]
    r = Sheet(strip, h=h).solve([(box(0, 0, 1, 2), "F")], [(box(39, 0, 40, 2), "F")])[0][0]
    case("a 40 x 2 mm strip", r, rs * (38 + 1 / 3) / 2, 0.02)
    # the same strip on each face, joined at the far end by one via, fed on the other face
    two = [(box(0, 0, 40, 2), "F"), (box(0, 0, 40, 2), "B")]
    sh = Sheet(two, [(39.5, 1.0)], h=h)
    r = sh.solve([(box(0, 0, 1, 2), "F")], [(box(0, 0, 1, 2), "B")])[0][0]
    case("two strips joined by a via (the barrel and the two runs; the spread round the via is on top)", r,
         2 * rs * 38.5 / 2 + sh.r_via, 0.05)
    # a pad in the middle of a round pour held at its rim: rs (ln(r2 / r1) / 2 pi + 1 / 8 pi)
    r1, r2 = 0.6, 15.0
    disc = Point(20, 20).buffer(r2 + 1, 64)
    r = Sheet([(disc, "F")], h=h).solve([(disc.difference(Point(20, 20).buffer(r2, 64)), "F")],
                                        [(Point(20, 20).buffer(r1, 64), "F")])[0][0]
    case(f"a {2 * r1} mm round pad in the middle of a {2 * r2:.0f} mm round pour", r,
         rs * (math.log(r2 / r1) / (2 * math.pi) + 1 / (8 * math.pi)), 0.05)
    # tracks, any way round: what 20 mm more of track between two pads adds, rs 20 / width
    for w, deg in ((0.25, 0), (0.25, 20), (0.25, 45), (0.5, 70)):
        got = []
        for length in (10.0, 30.0):
            a = (3.0, 3.0)
            b = (a[0] + length * math.cos(math.radians(deg)), a[1] + length * math.sin(math.radians(deg)))
            pa, pb = Point(a).buffer(1.0), Point(b).buffer(1.0)
            got.append(Sheet([(pa, "F"), (pb, "F")], tracks=[(a, b, w, "F")], h=h).solve([(pa, "F")], [(pb, "F")])[0][0])
        case(f"20 mm of {w} mm track at {deg} degrees", got[1] - got[0], rs * 20 / w, 0.02)
    # a stub from a pad to a via, the via into the other face's pour: the three in a row, and the spread on top
    pad_, land = box(0, 0, 1.5, 1), Point(4.0, 0.5).buffer(0.3)
    pour = box(-10, -10, 20, 11)
    sh = Sheet([(pad_, "B"), (land, "B"), (land, "F"), (pour, "F")], [(4.0, 0.5)], [((0.75, 0.5), (4.0, 0.5), 0.25, "B")], h=h)
    r = sh.solve([(pour.difference(box(-9, -9, 19, 10)), "F")], [(pad_, "B")])[0][0]
    want = rs * (4.0 - 0.3 - 1.5) / 0.25 + sh.r_via
    say(f"  {'ok  ' if want < r < want + 1.5e-3 else 'FAIL'}  sheet method, a pad, 2.2 mm of 0.25 mm stub, a via and the "
        f"other face's pour: {r * 1e3:.2f} mohm, of which {want * 1e3:.2f} are the stub and the barrel by hand")
    if not want < r < want + 1.5e-3:
        bad.append("stub")
    # copper the sinks don't reach
    r = Sheet(strip + [(box(0, 5, 2, 7), "F")], h=h).solve([(box(0, 0, 1, 2), "F")], [(box(0, 5, 2, 7), "F")])[0][0]
    say(f"  {'ok  ' if math.isinf(r) else 'FAIL'}  sheet method, a pad on copper apart from the sinks reads infinite")
    if not math.isinf(r):
        bad.append("apart")
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if selftest() else 0)
