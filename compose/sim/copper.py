"""
A board's copper as geometry, and what touches what: Copper(path) loads a .kicad_pcb and joins pads,
tracks, vias and filled zones that overlap on a layer into nets of its own, without KiCad's netlist. The
simulations ask it which pads the copper really connects.
"""
import pcbnew
from shapely.geometry import Point, LineString, Polygon
from shapely.strtree import STRtree

ToMM = pcbnew.ToMM


# ---------------------------------------------------------------- copper connectivity (geometry only)
class Copper:
    def __init__(self, path):
        self.b = pcbnew.LoadBoard(path)
        self.items = []                                   # (shape, layers, label)
        for fp in self.b.GetFootprints():
            for p in fp.Pads():
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    continue
                for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                    if not p.IsOnLayer(lay):
                        continue
                    ps = p.GetEffectivePolygon()
                    ol = ps.Outline(0)
                    pts = [(ToMM(ol.CPoint(i).x), ToMM(ol.CPoint(i).y)) for i in range(ol.PointCount())]
                    self.items.append((Polygon(pts).buffer(0), lay, f"{fp.GetReference()}.{p.GetNumber()}"))
        for t in self.b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                q = t.GetPosition()
                shp = Point(ToMM(q.x), ToMM(q.y)).buffer(ToMM(t.GetWidth()) / 2)
                for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                    self.items.append((shp, lay, "via"))
            else:
                a, c = t.GetStart(), t.GetEnd()
                shp = LineString([(ToMM(a.x), ToMM(a.y)), (ToMM(c.x), ToMM(c.y))]).buffer(ToMM(t.GetWidth()) / 2)
                self.items.append((shp, t.GetLayer(), "track"))
        for z in self.b.Zones():                          # copper pours (filled), e.g. the rev 2 RGB boards' GND
            if z.GetIsRuleArea():
                continue
            for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
                if not z.IsOnLayer(lay):
                    continue
                fp_ = z.GetFilledPolysList(lay)
                for k in range(fp_.OutlineCount()):
                    o = fp_.Outline(k)
                    pts = [(ToMM(o.CPoint(i).x), ToMM(o.CPoint(i).y)) for i in range(o.PointCount())]
                    holes = []
                    for h in range(fp_.HoleCount(k)):
                        hh = fp_.Hole(k, h)
                        holes.append([(ToMM(hh.CPoint(i).x), ToMM(hh.CPoint(i).y)) for i in range(hh.PointCount())])
                    if len(pts) >= 3:
                        self.items.append((Polygon(pts, holes).buffer(0), lay, "zone"))
        # a PTH pad / via is one conductor on both layers: join its two layer entries
        self.parent = list(range(len(self.items)))
        key = {}
        for i, (s, lay, lab) in enumerate(self.items):
            if lab not in ("track", "zone"):
                k = (lab, round(s.centroid.x, 3), round(s.centroid.y, 3))
                if k in key:
                    self.union(i, key[k])
                key[k] = i
        for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
            idx = [i for i, it in enumerate(self.items) if it[1] == lay]
            tree = STRtree([self.items[i][0] for i in idx])
            for n, i in enumerate(idx):
                for m in tree.query(self.items[i][0], predicate="intersects"):
                    self.union(i, idx[int(m)])

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def node_at(self, xy, layer):
        """Conductor group of the copper covering point xy on a layer (None if bare)."""
        p = Point(xy)
        hits = [i for i, (s, lay, lab) in enumerate(self.items) if lay == layer and lab not in ("track", "zone") and s.contains(p)]
        return self.find(hits[0]) if hits else None
