"""
The pointer module's cable as the checks see it: a tube (POINTER_CABLE_D) along straight segments, world frame.

Route: off the device's pads, down to the plate, through the carrier's cable channel into the switch hole, through
the half board's MX centre hole, down below the board's parts (the slot); or straight down from the pads through the
carrier's base into the thumb bay's pocket and through the diamond hole in the half's wall, under the case ledge (a
bay). Then under the board to its inner edge, down into the bay below everything under the controller board, along
to beside the connector, up to just under the cover, across and down into the plug (J4, soldered on the board's
underside: straight along below the board, up into the plug). Where it leaves the half
(bridge-frame y) is solved: the candidate nearest the connector that keeps the tube clear of everything (route()).
"""
import math
from functools import lru_cache
import numpy as np
import cadquery as cq
from compose import params as PR
from compose import geom as G
from compose.case import gasket as C
from compose.controller import rev2_std as CS

CLEAR = {"jumpers": 0.5, "standoffs": 0.5, "pico": 0.5, "ctrl board": 0.5, "bottom parts": 0.5, "top parts": 0.5,
         "lead tails": 0.5, "cover": 0.5, "case": 0.3, "pointer plug": 0.5}               # minimum distance (mm)
NO_OVERLAP = ("plate", "frame", "half pcb", "half parts", "pointer", "pointer carrier")   # may touch, not overlap
ROUTE = {}                # PointerConfig -> {"pts", "problems", "y"}: the last route() result, for pointer-checks


@lru_cache(maxsize=2)
def port_P(port):
    """(x, y, z of the plug's free end) of the cable's connector on controller rev 2, bridge frame P (its courtyard
    centre): the plug top, or for a header on the board's underside (J4) the plug bottom."""
    import pcbnew
    from compose.controller import rev2 as CV
    b = CV.build()
    fp = b.FindFootprintByReference(port)
    fp.BuildCourtyardCaches()
    r = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    x = (pcbnew.ToMM(r.GetLeft()) + pcbnew.ToMM(r.GetRight())) / 2 - CV.CX
    y = (pcbnew.ToMM(r.GetTop()) + pcbnew.ToMM(r.GetBottom())) / 2 - CV.CY
    px, py = C.CT.to_P(x, y)
    from compose.checks.gasket import PLUG_TOP, UNDER_PORTS   # function-local: that module reads sys.argv and makes its
    if port in UNDER_PORTS:                                  # output folder when imported
        return px, py, C.CT.board_bot - PLUG_TOP[port]       # header on the underside: the plug's free end, below
    return px, py, C.CT.board_top + PLUG_TOP[port]           # mated plug above the controller board


def local_to_P(p, side):
    q = G.apply(G.M_LP, p)
    return (float(q[0]) if side == "L" else -float(q[0]), float(q[1]), float(q[2]))


def module_points(pl):
    """Local-frame centreline from the pads to under the half board (at the key, or just inside the wall from the
    bay); and the depth it runs on at (local z)."""
    r = PR.POINTER_CABLE_D / 2
    from compose.checks.gasket import HALF_PART_H
    z_under = -PR.PCB_T - HALF_PART_H["ffc"] - r - 0.5         # below the half board's tallest part
    if pl.kind == "bay":
        from compose.pointer import place as PL, solids as PS
        px, py = PL.pads_centre(pl)
        (wx, wy), n, _ = PS.wall_hole_frame(pl.frame)
        zh = PS.wall_hole_z()
        out = PR.BAY_POCKET_GAP + PR.WALL_T + 0.5 * PR.BAY_POCKET_GAP     # pocket side of the wall
        inn = PR.LEDGE_W + PR.FLOAT_GAP + 2.0                              # past the ledge's chamfer
        pts = [(px, py, pl.pad_pt[2] - 1.0 - r), (px, py, zh), (wx + n[0] * out, wy + n[1] * out, zh),
               (wx - n[0] * inn, wy - n[1] * inn, zh)]
        return pts, z_under
    from compose.pointer import place as PL
    kx, ky = pl.frame[0], pl.frame[1]                   # the slot's key centre: its switch hole
    px, py = PL.pads_centre(pl)
    n = math.hypot(px - kx, py - ky)
    ux, uy = (px - kx) / n, (py - ky) / n
    d_in = PR.SWITCH_HOLE / 2 - r - 0.1                 # just inside the switch hole's edge, toward the pads
    z_run = PR.PLATE_T + r + 0.05                        # along the plate top, in the carrier's cable channel
    pts = [(px, py, pl.pad_pt[2] - 1.0 - r), (px, py, z_run), (kx + ux * d_in, ky + uy * d_in, z_run),
           (kx, ky, r + 0.3), (kx, ky, z_under)]
    return pts, z_under


def crossing_points(cfg, yc, z_under, port=None):
    """Bridge-frame centreline from under the half board's inner edge (leaving it at P y = yc) to the connector's
    plug: down into the bay below everything under the controller board, along to beside the connector, up there to
    just under the cover, across and down into the plug. Where the plates' inner edges come too close beside the
    connector to rise straight up, it rises in two steps: under the plates' edge, in over the board, then up."""
    s = -1.0 if cfg.side == "L" else 1.0
    r = PR.POINTER_CABLE_D / 2
    x_l = G.ANCHOR[0] - PR.PCB_INSET - 3.0
    a = local_to_P((x_l, C._local_y_at_P(x_l, yc, z_under), z_under), cfg.side)
    px, py, ptop = port or port_P(cfg.port)
    t = 1.0 if px > 0 else -1.0                          # rise on the connector's side of the controller
    y_up = max(py, -PR.BRIDGE_LEN + PR.BRIDGE_WALL_T + r + 0.5)
    z_low = C.CT.board_bot - CS.BOTTOM_PARTS_H - r - 0.5     # below everything under the controller board
    if ptop < C.CT.board_bot:                            # the plug hangs under the board: along below, up into it
        assert z_low + r < ptop, "the run along below must pass under the plug (BOTTOM_PARTS_H > the plug's height)"
        X = CS.W2 + 2.5
        return [a, (s * X, yc, z_low), (t * X, y_up, z_low), (px, py, z_low), (px, py, ptop - r)]
    z_top = C.CT.cover_under - r - 0.6                   # just under the cover
    x_room = abs(G.interface_x(y_up, z_top)) - PR.FLOAT_GAP - r - 0.5    # inside the plates' inner edges
    x_out = min(CS.W2 + 2.5, x_room)
    direct = x_out >= CS.W2 + r + 0.5                     # room beside the board all the way up
    X = x_out if direct else CS.W2 + 2.5
    pts = [a, (s * X, yc, z_low), (t * X, y_up, z_low)]
    if direct:
        pts += [(t * X, y_up, z_top)]
    else:
        z_mid = G.Z0 - r - 0.6                           # under the plates' inner edge
        x_in = CS.W2 - 2.0                               # in over the board's edge
        pts += [(t * (CS.W2 + 2.5), y_up, z_mid), (t * x_in, y_up, z_mid), (t * x_in, y_up, z_top)]
    return pts + [(px, py, z_top), (px, py, ptop + r)]


def tube(pts, r):
    """Cylinders along the segments and a sphere at every inner joint (a compound: for checks only)."""
    sol = []
    for a, b in zip(pts[:-1], pts[1:]):
        a, b = cq.Vector(*a), cq.Vector(*b)
        d = b - a
        if d.Length > 1e-6:
            sol.append(cq.Solid.makeCylinder(r, d.Length, a, d.normalized()))
    sol += [cq.Solid.makeSphere(r, cq.Vector(*p), angleDegrees1=-90, angleDegrees2=90) for p in pts[1:-1]]
    return cq.Compound.makeCompound(sol)


def length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts[:-1], pts[1:]))


def stock_length(pts):
    """Shortest stock cable that covers the route plus POINTER_CABLE_SLACK, or None."""
    need = length(pts) + PR.POINTER_CABLE_SLACK
    return next((s for s in PR.POINTER_CABLE_STOCK if s >= need), None)


def problems(pts, parts):
    """Clearance failures of the tube along `pts` (world) against the parts dict of checks/gasket.py parts_world().
    The last segment is the lead into the plug: it's held only to the no-overlap rules."""
    r = PR.POINTER_CABLE_D / 2
    body, full = tube(pts[:-1], r), tube(pts, r)
    out = []
    for name, lim in CLEAR.items():
        if name in parts:
            d = body.distance(parts[name])
            if d < lim:
                out.append(f"{name} {d:.2f} mm (>= {lim})")
    for name in NO_OVERLAP:
        if name in parts:
            v = full.intersect(parts[name]).Volume()
            if v > 1e-3:
                out.append(f"overlaps {name} by {v:.3f} mm3")
    return out


def route(pl, cfg, parts, port=None):
    """{"pts": world points, "problems": [...], "y": crossing (P y)}: the crossing nearest the connector with no
    problems, else the candidate with the fewest (its problems say why). Also kept in ROUTE[cfg]."""
    mod, z_under = module_points(pl)
    head = [local_to_P(p, cfg.side) for p in mod]
    py = (port or port_P(cfg.port))[1]
    ys = sorted((float(y) for y in np.arange(-1.0, -PR.BRIDGE_LEN + 0.5, -1.0)), key=lambda y: abs(y - py))
    best = None
    for yc in ys:
        pts = [tuple(float(v) for v in G.apply(G.M_PW, p)) for p in head + crossing_points(cfg, yc, z_under, port)]
        probs = problems(pts, parts)
        if best is None or len(probs) < len(best["problems"]):
            best = {"pts": pts, "problems": probs, "y": yc}
        if not probs:
            break
    ROUTE[cfg] = best
    return best
