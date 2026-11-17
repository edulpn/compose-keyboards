"""
The MX switch on a board, as geometry: where a footprint's points fall on the plate (fp2local), their
mirror images on a reversible board, the plate's hole, the hotswap socket's body, everything that sticks out
of the underside, every hole the footprint drills, and the places a key's diode can take. Shapely shapes in
plate-local coordinates; no KiCad needed.
"""
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import unary_union
from compose import params as PR
from compose import geom as G
from compose import layout as layouts


def fp2local(k, fx, fy):
    """Footprint coords (KiCad, y down) of key k -> plate-local (y up)."""
    return layouts.key_point(k, fx, -fy)


def mirror_fp(p):
    return (-p[0], p[1])


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


def diode_candidates():
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
