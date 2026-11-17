"""
The holes the keys need in a printed part: the cutter for one switch hole in a plate (clip notches and
chamfer included) and the single opening round all the keycaps in a frame.
"""
import cadquery as cq
from shapely.ops import unary_union
from compose import params as PR
from compose import geom as G

L = G.LAYOUT
TH = PR.PLATE_T


def switch_cutter():
    h, t = PR.SWITCH_HOLE, TH
    hole = cq.Workplane("XY").rect(h, h).extrude(t + 1).translate((0, 0, -0.5))
    notch = (cq.Workplane("XY").pushPoints([(0, h / 2 + PR.CLIP_NOTCH_D / 2), (0, -h / 2 - PR.CLIP_NOTCH_D / 2)])
             .rect(PR.CLIP_NOTCH_W, PR.CLIP_NOTCH_D + 0.2).extrude(t - PR.SWITCH_CLIP_LIP))
    c = PR.PLATE_HOLE_CHAMFER
    cham = (cq.Workplane("XY").workplane(offset=t - c).rect(h, h)
            .workplane(offset=c + 0.01).rect(h + 2 * c + 0.02, h + 2 * c + 0.02).loft())
    return hole.union(notch).union(cham).val()


def key_opening():
    cells = unary_union([G.key_poly(k) for k in L.keys]).buffer(PR.KEY_OPENING_GAP, join_style="mitre")
    r = PR.KEY_OPENING_CLOSE_R
    cells = cells.buffer(r, join_style="round").buffer(-r, join_style="round")
    c = PR.KEY_OPENING_CORNER_R
    cells = cells.buffer(-c, join_style="round").buffer(c, join_style="round").simplify(0.02)
    from shapely.geometry import Polygon
    return Polygon(cells.exterior)          # one opening, no islands left between key groups
