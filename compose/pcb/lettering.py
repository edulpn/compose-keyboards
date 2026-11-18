"""
Text and the ∘ logo as shapes (pure Python + shapely): text is rendered to outlines from real fonts (KiCad 7's
API has no font engine), fitted into a box, and mirrored for the back of a board. No layout and no KiCad
needed: the half boards' graphics (art.py) and the controller rev 2's labels are both made from these.
"""
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.affinity import scale as sscale, translate as strans
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties


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
