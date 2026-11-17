"""Tracks of one conductor running beside tracks of others, and what couples across: the method and values of
compose.sim.controller_spice (coupled_runs, PCBZ), for boards that module doesn't read. Needs no KiCad."""
import math

MAX_GAP = 0.6                # mm, edge to edge: further apart doesn't count
PARALLEL = 0.97              # cosine: parallel within about 14 degrees
C_PER_MM = 0.05e-12          # F/mm, a 0.25 mm track on a two-layer board without a plane, at its lowest


def cm_per_mm(gap):
    """Mutual capacitance per mm of two edge-coupled tracks, F/mm: about 0.03 pF/mm at a 0.2 mm gap."""
    return 0.03e-12 * (0.2 / max(gap, 0.1)) ** 0.6


def beside(mine, others):
    """mine, others: [(a, b, width, face)] in mm. Returns (mm of `mine` that runs beside a track of `others` on
    the same face, the mutual capacitance of those runs in farads). A stretch beside two tracks counts twice."""
    run = cm = 0.0
    for a, b, w, f in mine:
        dx, dy = b[0] - a[0], b[1] - a[1]
        l1 = math.hypot(dx, dy)
        if l1 < 0.2:
            continue
        ux, uy = dx / l1, dy / l1
        x0, x1 = min(a[0], b[0]) - 1.5, max(a[0], b[0]) + 1.5
        y0, y1 = min(a[1], b[1]) - 1.5, max(a[1], b[1]) + 1.5
        for a2, b2, w2, f2 in others:
            if f2 != f or max(a2[0], b2[0]) < x0 or min(a2[0], b2[0]) > x1 or max(a2[1], b2[1]) < y0 or min(a2[1], b2[1]) > y1:
                continue
            ex, ey = b2[0] - a2[0], b2[1] - a2[1]
            l2 = math.hypot(ex, ey)
            if l2 < 0.2 or abs(ux * ex + uy * ey) / l2 < PARALLEL:
                continue
            p0 = (a2[0] - a[0]) * ux + (a2[1] - a[1]) * uy
            p1 = (b2[0] - a[0]) * ux + (b2[1] - a[1]) * uy
            lo, hi = max(0.0, min(p0, p1)), min(l1, max(p0, p1))
            if hi - lo <= 0.1:
                continue
            gap = abs(((a2[0] + b2[0]) / 2 - a[0]) * -uy + ((a2[1] + b2[1]) / 2 - a[1]) * ux) - (w + w2) / 2
            if gap > MAX_GAP:
                continue
            run += hi - lo
            cm += (hi - lo) * cm_per_mm(gap)
    return run, cm


def dip(swing, cm, c_victim):
    """Volts a high-impedance victim moves when its neighbours swing `swing` volts: the capacitive divider."""
    return swing * cm / (cm + c_victim) if cm > 0 else 0.0
