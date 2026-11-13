"""
Build the KiCad boards:  python3 -m compose pcb [outdir]

  half_hotswap  reversible half board, Kailh MX hotswap sockets  (order 5: 2 per keyboard)
  half_solder   reversible half board, switches soldered in
  controller    Pico socket + two cable connectors, replaces the perfboard carrier

For each: place from compose.pcb.layout -> autoroute (Freerouting) -> DRC (KiCad) ->
Gerbers + drill zipped for JLCPCB, SVG previews. Needs KiCad 7 (pcbnew) and
java + tools/freerouting.jar.
"""
import os
import re
import sys
import json
import math
import time
import shutil
import zipfile
import subprocess
import pcbnew
from types import SimpleNamespace
from compose import REPO_ROOT
from compose import params as PR
from compose import geom as G
from compose.case import sandwich as PT
from compose.pcb import layout as PL

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "out")
PCB_OUT = os.path.join(OUT, "pcb")
FREEROUTING = os.environ.get("FREEROUTING", os.path.join(REPO_ROOT, "..", "tools", "freerouting.jar"))
FPLIB = os.environ.get("KICAD_FOOTPRINTS", "/usr/share/kicad/footprints")
MM = pcbnew.FromMM
V = lambda x, y: pcbnew.VECTOR2I(MM(x), MM(y))
DEG = lambda d: pcbnew.EDA_ANGLE(d, pcbnew.DEGREES_T)
OX, OY = 40.0, 60.0            # half board: plate-local (x, y) -> KiCad (x + OX, OY - y)
JOB_TIMEOUT_MIN = 8            # Freerouting job limit per attempt (minutes)
STALL_PASSES = 40              # stop the router when its best unrouted count hasn't improved for this many passes
ROUTER_JOBS = int(os.environ.get("ROUTER_JOBS", max(1, (os.cpu_count() or 2) // 2)))   # parallel router runs


def K(p, ox=OX, oy=OY):
    return (p[0] + ox, oy - p[1])


# ---------------------------------------------------------------- board helpers
def new_board():
    b = pcbnew.BOARD()
    ds = b.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    nc = ds.m_NetSettings.m_DefaultNetClass
    nc.SetClearance(MM(PR.CLEARANCE))
    nc.SetTrackWidth(MM(PR.TRACE_W))
    nc.SetViaDiameter(MM(PR.VIA_D))
    nc.SetViaDrill(MM(PR.VIA_DRILL))
    ds.m_TrackMinWidth = MM(0.2)
    ds.m_ViasMinSize = MM(0.5)
    ds.m_MinThroughDrill = MM(0.3)
    ds.m_HoleClearance = MM(0.25)
    ds.m_CopperEdgeClearance = MM(0.4)
    return b


class Nets:
    def __init__(self, board):
        self.b, self.n = board, {}

    def __call__(self, name):
        if name is None:
            return None
        if name not in self.n:
            ni = pcbnew.NETINFO_ITEM(self.b, name)
            self.b.Add(ni)
            self.n[name] = ni
        return self.n[name]


def outline(board, poly, ox, oy):
    """Edge.Cuts from a shapely polygon (its holes become board cutouts); returns the segments."""
    segs = []
    rings = [list(poly.exterior.coords)] + [list(r.coords) for r in poly.interiors]
    for a, c in ((a, c) for pts in rings for a, c in zip(pts[:-1], pts[1:])):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*K(a, ox, oy)))
        s.SetEnd(V(*K(c, ox, oy)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        board.Add(s)
        segs.append(s)
    return segs


def set_outline(board, poly, ox, oy):
    for d in list(board.GetDrawings()):
        if d.GetLayer() == pcbnew.Edge_Cuts:
            board.Remove(d)
    outline(board, poly, ox, oy)


def text(board, msg, p, layer, size=1.2, mirror=False, angle=0.0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(msg)
    t.SetPosition(V(*p))
    t.SetLayer(layer)
    t.SetTextSize(V(size, size))
    t.SetTextThickness(MM(size * 0.15))
    t.SetMirrored(mirror)
    t.SetTextAngle(DEG(angle))
    board.Add(t)


def _layers(*ids):
    ls = pcbnew.LSET()
    for i in ids:
        ls.AddLayer(i)
    return ls


def add_pad(fp, num, kind, shape, pos, size, drill=None, layers=None, angle=0.0, net=None):
    p = pcbnew.PAD(fp)
    p.SetNumber(num)
    p.SetAttribute({"pth": pcbnew.PAD_ATTRIB_PTH, "npth": pcbnew.PAD_ATTRIB_NPTH, "smd": pcbnew.PAD_ATTRIB_SMD}[kind])
    p.SetShape({"circle": pcbnew.PAD_SHAPE_CIRCLE, "rect": pcbnew.PAD_SHAPE_RECT, "oval": pcbnew.PAD_SHAPE_OVAL,
                "roundrect": pcbnew.PAD_SHAPE_ROUNDRECT}[shape])
    p.SetSize(V(*size))
    if drill is not None:
        p.SetDrillSize(V(*drill))
        if drill[0] != drill[1]:
            p.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
    if layers is None:
        layers = {"pth": p.PTHMask(), "npth": p.UnplatedHoleMask(), "smd": p.SMDMask()}[kind]
    p.SetLayerSet(layers)
    p.SetPos0(V(*pos))                 # footprint-relative (the footprint sits at the origin while built)
    p.SetPosition(V(*pos))
    p.SetOrientation(DEG(angle))
    if net is not None:
        p.SetNet(net)
    fp.Add(p)
    return p


def silk_poly(fp, pts, layer, w=0.12):
    """Closed polyline of footprint graphics (footprint at origin, orientation 0)."""
    for a, c in zip(pts, pts[1:] + pts[:1]):
        s = pcbnew.FP_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart0(V(*a))
        s.SetEnd0(V(*c))
        s.SetLayer(layer)
        s.SetWidth(MM(w))
        s.SetDrawCoord()
        fp.Add(s)


def courtyard(fp, x0, y0, x1, y1, layer):
    silk_poly(fp, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, 0.05)


# ---------------------------------------------------------------- footprints
def switch_fp(board, variant, ref, net_col, net_anode):
    """Reversible MX footprint: every pin also at its mirror image (same net),
    so the switch fits from either face. Built at the origin, orientation 0."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("kb2", f"MX_Reversible_{'Hotswap' if variant == 'hotswap' else 'PCB'}"))
    fp.SetReference(ref)
    fp.SetValue("MX")
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    p1, p2 = PR.MX_PIN1, PR.MX_PIN2
    m1, m2 = PL.mirror_fp(p1), PL.mirror_fp(p2)
    add_pad(fp, "", "npth", "circle", (0, 0), (PR.MX_CENTER_D,) * 2, (PR.MX_CENTER_D,) * 2)
    for sx in (-1, 1):
        add_pad(fp, "", "npth", "circle", (sx * PR.MX_PEG_X, 0), (PR.MX_PEG_D,) * 2, (PR.MX_PEG_D,) * 2)
    if variant == "solder":
        for pos in (p1, m1):
            add_pad(fp, "1", "pth", "circle", pos, (PR.MX_PTH_PAD,) * 2, (PR.MX_PTH_DRILL,) * 2, net=net_anode)
        for pos in (p2, m2):
            add_pad(fp, "2", "pth", "circle", pos, (PR.MX_PTH_PAD,) * 2, (PR.MX_PTH_DRILL,) * 2, net=net_col)
    else:
        d = PR.HS_HOLE_D
        for a, c in ((p1, m2), (p2, m1)):                    # each pin merges with a mirrored one into a slot
            mid = ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2)
            ln = math.dist(a, c)
            ang = -math.degrees(math.atan2(c[1] - a[1], c[0] - a[0]))
            add_pad(fp, "", "npth", "oval", mid, (ln + d, d), (ln + d, d), angle=ang)
        bl = _layers(pcbnew.B_Cu, pcbnew.B_Mask, pcbnew.B_Paste)
        fl = _layers(pcbnew.F_Cu, pcbnew.F_Mask, pcbnew.F_Paste)
        (c2, s2), (c1, s1) = PR.HS_PAD2, PR.HS_PAD1
        # left-half orientation: socket on B; right-half (flipped) orientation: socket on F, mirrored
        add_pad(fp, "2", "smd", "rect", c2, s2, layers=bl, net=net_col)
        add_pad(fp, "1", "smd", "rect", c1, s1, layers=bl, net=net_anode)
        add_pad(fp, "2", "smd", "rect", PL.mirror_fp(c2), s2, layers=fl, net=net_col)
        add_pad(fp, "1", "smd", "rect", PL.mirror_fp(c1), s1, layers=fl, net=net_anode)
    if variant == "solder":
        for lay in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            silk_poly(fp, [(-7, -7), (7, -7), (7, 7), (-7, 7)], lay, 0.1)
    courtyard(fp, -7.5, -7.5, 7.5, 7.5, pcbnew.F_CrtYd)
    return fp


def lib_fp(board, lib, name):
    fp = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    fp.SetParent(board)
    return fp


def pad_pos(fp, num):
    for p in fp.Pads():
        if p.GetNumber() == num:
            q = p.GetPosition()
            return (pcbnew.ToMM(q.x), pcbnew.ToMM(q.y))
    raise KeyError(num)


def place_by_pads(fp, na, pa, nb, pb):
    """Rotate/translate fp so pad na lands on pa and pad nb on the pb side
    (KiCad coords)."""
    fp.SetPosition(V(0, 0))
    qa, qb = pad_pos(fp, na), pad_pos(fp, nb)
    now = math.atan2(qb[1] - qa[1], qb[0] - qa[0])
    want = math.atan2(pb[1] - pa[1], pb[0] - pa[0])
    fp.Rotate(V(0, 0), DEG(-math.degrees(want - now)))      # KiCad: +angle = CCW on screen (y down)
    qa = pad_pos(fp, na)
    fp.Move(V(pa[0] - qa[0], pa[1] - qa[1]))
    qa, qb = pad_pos(fp, na), pad_pos(fp, nb)
    assert math.dist(qa, pa) < 1e-3 and abs(math.atan2(qb[1] - qa[1], qb[0] - qa[0]) - want) < 1e-4, "placement"


def hole_fp(board, ref, pos, d):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("kb2", f"Hole_{d:.1f}"))
    fp.SetReference(ref)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    add_pad(fp, "", "npth", "circle", (0, 0), (d, d), (d, d))
    courtyard(fp, -d / 2 - 0.5, -d / 2 - 0.5, d / 2 + 0.5, d / 2 + 0.5, pcbnew.F_CrtYd)
    fp.SetPosition(V(*pos))
    board.Add(fp)


# ---------------------------------------------------------------- art helpers
def add_poly(board, geom, layer, ox, oy):
    """Filled polygon(s) from shapely (holes allowed) on a layer."""
    for p in getattr(geom, "geoms", [geom]):
        if p.is_empty or p.geom_type != "Polygon":
            continue
        sps = pcbnew.SHAPE_POLY_SET()
        sps.NewOutline()
        for x, y in list(p.exterior.coords)[:-1]:
            X, Y = K((x, y), ox, oy)
            sps.Append(MM(X), MM(Y))
        for ring in p.interiors:
            h = sps.NewHole()
            for x, y in list(ring.coords)[:-1]:
                X, Y = K((x, y), ox, oy)
                sps.Append(MM(X), MM(Y), 0, h)
        sps.Fracture(pcbnew.SHAPE_POLY_SET.PM_FAST)
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_POLY)
        s.SetPolyShape(sps)
        s.SetFilled(True)
        s.SetWidth(0)
        s.SetLayer(layer)
        board.Add(s)


def add_keepout(board, poly, ox, oy):
    """Rule area on both copper layers: no tracks, no vias (the router honours it)."""
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowCopperPour(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetLayerSet(_layers(pcbnew.F_Cu, pcbnew.B_Cu))
    ol = z.Outline()
    ol.NewOutline()
    for x, y in list(poly.exterior.coords)[:-1]:
        X, Y = K((x, y), ox, oy)
        ol.Append(MM(X), MM(Y))
    board.Add(z)


def add_art_half(b, art, ox, oy):
    face = {"F": (pcbnew.F_Cu, pcbnew.F_Mask, pcbnew.F_SilkS), "B": (pcbnew.B_Cu, pcbnew.B_Mask, pcbnew.B_SilkS)}
    add_keepout(b, art.keepout, ox, oy)
    for f, (cu, mask, silk) in face.items():
        for g in art.copper[f]:
            add_poly(b, g, cu, ox, oy)                         # bare copper...
            add_poly(b, g.buffer(0.05), mask, ox, oy)          # ...with the mask opened over it (HASL finish)
        for g in art.silk[f]:
            add_poly(b, g, silk, ox, oy)
        for ln in art.lines:
            pts = list(ln.coords)
            for a_, c_ in zip(pts[:-1], pts[1:]):
                s = pcbnew.PCB_SHAPE(b)
                s.SetShape(pcbnew.SHAPE_T_SEGMENT)
                s.SetStart(V(*K(a_, ox, oy)))
                s.SetEnd(V(*K(c_, ox, oy)))
                s.SetLayer(silk)
                s.SetWidth(MM(PR.ART_LINE_W))
                b.Add(s)


# ---------------------------------------------------------------- half board
def build_half(variant):
    plan = PL.plan_half()
    b = new_board()
    b.kb2_outline = (plan.outline, OX, OY)
    net = Nets(b)
    outline(b, plan.outline, OX, OY)
    for ks in plan.keys:
        k = ks.k
        dnet = net(f"D{ks.i + 1}")
        fp = switch_fp(b, variant, ks.ref, net(f"COL{ks.col}"), dnet)
        fp.SetOrientation(DEG(k.rot))
        fp.SetPosition(V(*K((k.x, k.y))))
        b.Add(fp)
        exp = K(PL.fp2local(k, *(PR.MX_PIN2 if variant == "solder" else PR.HS_PAD2[0])))
        assert any(math.dist(exp, g) < 1e-3 for g in [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in fp.Pads() if p.GetNumber() == "2"]), "switch frame"
        d = lib_fp(b, "Diode_THT", "D_DO-35_SOD27_P7.62mm_Horizontal")
        d.SetReference(ks.dref)
        d.Reference().SetVisible(False)
        d.Value().SetVisible(False)
        d.Flip(d.GetPosition(), False)                         # body on the B face (left half)
        place_by_pads(d, "1", K(ks.cathode), "2", K(ks.anode))
        for p in d.Pads():
            p.SetNet(net(f"ROW{ks.row}") if p.GetNumber() == "1" else dnet)
        b.Add(d)
        # F-side silkscreen for the right half: diode outline with the cathode band
        c, a = K(ks.cathode), K(ks.anode)
        ux, uy = (a[0] - c[0]) / PR.DIODE_PITCH, (a[1] - c[1]) / PR.DIODE_PITCH
        nx, ny = -uy, ux
        h0, h1, r = 1.8, PR.DIODE_PITCH - 1.8, 0.95
        corner = lambda t, s: (c[0] + ux * t + nx * s, c[1] + uy * t + ny * s)
        sh = pcbnew.PCB_SHAPE(b)
        for t0, s0, t1, s1 in ((h0, -r, h1, -r), (h1, -r, h1, r), (h1, r, h0, r), (h0, r, h0, -r), (h0 + 0.6, -r, h0 + 0.6, r)):
            sh = pcbnew.PCB_SHAPE(b)
            sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
            sh.SetStart(V(*corner(t0, s0)))
            sh.SetEnd(V(*corner(t1, s1)))
            sh.SetLayer(pcbnew.F_SilkS)
            sh.SetWidth(MM(0.12))
            b.Add(sh)
    # cable connector (vertical PicoBlade) on the B face, pad 1 at the back end
    j = lib_fp(b, "Connector_Molex", "Molex_PicoBlade_53047-1210_1x12_P1.25mm_Vertical")
    j.SetReference("J1")
    j.Flip(j.GetPosition(), False)
    place_by_pads(j, "1", K(plan.conn_pins[0]), "12", K(plan.conn_pins[-1]))
    for p in j.Pads():
        p.SetNet(net(PL.half_nets()[int(p.GetNumber())]))
    b.Add(j)
    for i, (x, y) in enumerate(plan.holes_m3):
        hole_fp(b, f"H{i + 1}", K((x, y)), PR.M3_CLEAR)
    for i, (x, y) in enumerate(plan.holes_m2):
        hole_fp(b, f"H{i + 20}", K((x, y)), PR.M2_CLEAR)
    # labels + art (pcb_art): exposed-copper title, taglines, build labels, hex lattice
    from compose.pcb import art as pcb_art
    art = pcb_art.plan_half_art(plan, variant)
    add_art_half(b, art, OX, OY)
    c1, c12 = K(plan.conn_pins[0]), K(plan.conn_pins[-1])
    lhs, rhs = PR.HALF_NAMES
    text(b, f"{lhs}: pin 1", (c1[0] - 4.4, c1[1]), pcbnew.B_SilkS, 0.9, mirror=True)
    text(b, f"{rhs}: pin 1", (c12[0] - 4.4, c12[1]), pcbnew.F_SilkS, 0.9)
    return b


# ---------------------------------------------------------------- controller board
COX, COY = 60.0, 30.0           # P-frame (x, y) -> KiCad (x + COX, COY - y)


def build_ctrl():
    st = PT.Stack
    plan = PL.plan_ctrl(st, PT.pillar_positions())
    b = new_board()
    b.kb2_outline = (plan.outline, COX, COY)
    net = Nets(b)
    KC = lambda p: K(p, COX, COY)
    outline(b, plan.outline, COX, COY)
    pin_net = {pin: f"GP{g}" for pin, g in PL.PICO_PIN_GPIO.items()}
    pin_net.update({pin: "GND" for pin in PL.PICO_GND_PINS})
    for side, first, last in (("L", 1, 20), ("R", 40, 21)):
        h = lib_fp(b, "Connector_PinSocket_2.54mm", "PinSocket_1x20_P2.54mm_Vertical")
        h.SetReference(f"U1{side}")
        place_by_pads(h, "1", KC(PL.pico_pin_xy(first, st)), "20", KC(PL.pico_pin_xy(last, st)))
        for p in h.Pads():
            n_ = int(p.GetNumber())
            pin = first + (n_ - 1) * (1 if side == "L" else -1)
            p.SetNet(net(pin_net.get(pin)))
        b.Add(h)
    for side in ("L", "R"):
        j = lib_fp(b, "Connector_Molex", "Molex_PicoBlade_53048-1210_1x12_P1.25mm_Horizontal")
        j.SetReference(f"J{side}")
        j.Reference().SetVisible(False)                 # the lhs/rhs art labels name them
        pins = plan.conn[side]
        place_by_pads(j, "1", KC(pins[0]), "12", KC(pins[-1]))
        # body must open outward (toward its half); if not, mirror the pad order
        bb = j.GetCourtyard(pcbnew.F_CrtYd).BBox() if hasattr(j, "GetCourtyard") else j.GetBoundingBox(False, False)
        cxm = pcbnew.ToMM((bb.GetLeft() + bb.GetRight()) // 2) - COX
        if (cxm > PR.CTRL_CONN_X) != (side == "R"):
            place_by_pads(j, "12", KC(pins[0]), "1", KC(pins[-1]))
        cn = PL.ctrl_conn_nets(side)
        for p in j.Pads():
            p.SetNet(net(cn[int(p.GetNumber())]))
        b.Add(j)
    for i, (x, y) in enumerate(st.carrier_holes):
        hole_fp(b, f"H{i + 1}", KC((x, y)), PR.M2_CLEAR)
    lhs, rhs = PR.HALF_NAMES
    from compose.pcb import art as pcb_art
    art = pcb_art.plan_ctrl_art(plan, st)
    for f, lay in (("F", pcbnew.F_SilkS), ("B", pcbnew.B_SilkS)):
        for g in art.silk[f]:
            add_poly(b, g, lay, COX, COY)
    return b


# ---------------------------------------------------------------- routing
def _sexp(s):
    toks = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', s)
    stack = [[]]
    for t in toks:
        if t == "(":
            stack.append([])
        elif t == ")":
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t.strip('"'))
    return stack[0][0]


def _find(node, key):
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            yield x


def _router_stats(log):
    """The statistics Freerouting prints for the board it finished with (last JSON block of its log)."""
    try:
        t = open(log).read()
        i = t.rfind("\n{\n")
        return json.loads(t[i + 1:t.index("\n}\n", i) + 2]) if i >= 0 else None
    except (OSError, ValueError):
        return None


_JAVA_OK = False


def check_java():
    """Freerouting 2.1.0 is built for Java 21 (class files version 65): an older `java` exits at once without
    writing a .ses, which would look like a board that never routes. Fail early with the reason instead."""
    global _JAVA_OK
    if _JAVA_OK:
        return
    try:
        r = subprocess.run(["java", "-version"], capture_output=True, text=True)
    except OSError:
        raise RuntimeError("Freerouting needs Java 21+, and `java` isn't on PATH")
    m = re.search(r'version "(\d+)(?:\.(\d+))?', r.stderr + r.stdout)
    major = int(m.group(1)) if m else 0
    major = int(m.group(2)) if major == 1 and m.group(2) else major          # "1.8" -> 8
    if major < 21:
        first = (r.stderr + r.stdout).strip().splitlines()[0] if (r.stderr + r.stdout).strip() else "?"
        raise RuntimeError(f"Freerouting 2.1.0 needs Java 21+, but `java` on PATH is: {first}")
    if not os.path.exists(FREEROUTING):
        raise RuntimeError(f"Freerouting jar not found at {FREEROUTING}: set FREEROUTING")
    _JAVA_OK = True


def route(board, name, passes=40):
    check_java()
    dsn = os.path.join(PCB_OUT, name + ".dsn")
    ses = os.path.join(PCB_OUT, name + ".ses")
    poly, ox, oy = board.kb2_outline
    edge = getattr(board, "kb2_route_edge", PR.CLEARANCE + 0.25)   # route inside the real edge by the edge clearance
    set_outline(board, poly.buffer(-edge, join_style="mitre"), ox, oy)
    # KiCad applies the edge clearance to unplated holes too; the router only knows
    # the copper clearance, so grow those holes by the difference while exporting
    g = 2 * (board.GetDesignSettings().m_CopperEdgeClearance / 1e6 - PR.CLEARANCE + 0.05)
    saved = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                sz = pcbnew.VECTOR2I(p.GetSize().x, p.GetSize().y)      # copy: GetSize() is a live reference
                saved.append((p, sz))
                p.SetSize(pcbnew.VECTOR2I(sz.x + MM(g), sz.y + MM(g)))
    assert pcbnew.ExportSpecctraDSN(board, dsn), "DSN export failed"
    for p, sz in saved:
        p.SetSize(sz)
    set_outline(board, poly, ox, oy)
    if os.path.exists(ses):
        os.remove(ses)
    fixed = len(re.findall(r"\(via [^\n]*\(type fix\)", open(dsn).read()))     # pre-placed, not in the .ses
    base = os.path.splitext(ses)[0]
    jobs = []
    for i in range(ROUTER_JOBS):        # independent router runs side by side; the first good one wins
        out = ses if ROUTER_JOBS == 1 else f"{base}_job{i + 1}.ses"
        logf = (base if ROUTER_JOBS == 1 else f"{base}_job{i + 1}") + "_freerouting.log"
        for f in (out, logf):
            if os.path.exists(f):
                os.remove(f)
        cmd = ["java", "-Djava.awt.headless=true", "-jar", FREEROUTING, "-de", dsn, "-do", out, "-mp", str(passes),
               "--gui.enabled=false", "--router.optimizer.max_passes=5",
               "--router.automatic_neckdown=false",       # no tracks below the 0.2 mm minimum
               f"--router.job_timeout={JOB_TIMEOUT_MIN // 60:02d}:{JOB_TIMEOUT_MIN % 60:02d}:00",
               "--usage_and_diagnostic_data.disable_analytics=true"]
        log = open(logf, "w")
        jobs.append(SimpleNamespace(ses=out, logf=logf, log=log, best=None, best_pass=0, done=False,
                                    proc=subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)))

    def verdict(j):
        """(ok, unrouted) for a finished job: ok = its .ses is the board the router finished with."""
        if not os.path.exists(j.ses):
            return False, None
        stats = _router_stats(j.logf)
        nv = open(j.ses).read().count("(via ")
        if stats is None:                                # no statistics block (other Freerouting versions)
            return True, None
        if stats["items"]["via_count"] - fixed != nv:
            # Freerouting 2.1 can "restore an earlier board" mid-run, keep routing, then write the
            # restored board to the .ses instead of the one it finished with: reject that output
            return False, stats["connections"]["incomplete_count"]
        return True, stats["connections"]["incomplete_count"]
    t0, winner, rejected, silent = time.time(), None, 0, 0
    while any(not j.done for j in jobs) and winner is None:
        time.sleep(2)
        for j in jobs:
            if j.done:
                continue
            if j.proc.poll() is not None:
                j.done = True
                ok, inc = verdict(j)
                if ok and inc == 0:
                    winner = j
                    break
                silent += not os.path.exists(j.ses)
                rejected += not ok and os.path.exists(j.ses)
                continue
            if time.time() - t0 > JOB_TIMEOUT_MIN * 60 + 240:
                j.proc.kill()
                continue
            seen = [(int(p_), int(u)) for p_, u in
                    re.findall(r"Auto-rout(?:er|ing) pass #(\d+) .*?\((\d+) unrouted", open(j.logf).read())]
            if seen:
                p_, u = min(seen, key=lambda pu: (pu[1], pu[0]))
                if j.best is None or u < j.best:
                    j.best, j.best_pass = u, p_
                if seen[-1][0] - j.best_pass >= STALL_PASSES:          # congested: more passes won't help
                    j.proc.kill()
    for j in jobs:
        if j.proc.poll() is None:
            j.proc.kill()
        j.proc.wait()
        j.log.close()
    if winner is None:                  # none fully routed: take a sound one with the fewest open connections
        sound = [(v[1] if v[1] is not None else 10 ** 6, k) for k, j in enumerate(jobs) for v in [verdict(j)] if v[0]]
        if not sound:
            print(f"  {name}: no usable router output ({rejected} of {len(jobs)} wrote an earlier board, "
                  f"{silent} wrote nothing: see {jobs[0].logf})")
            return None
        winner = jobs[min(sound)[1]]
    if winner.ses != ses:
        shutil.copy(winner.ses, ses)
        shutil.copy(winner.logf, base + "_freerouting.log")
    txt = open(ses).read()
    tree = _sexp(txt)
    routes = next(_find(tree, "routes"))
    res = next(_find(routes, "resolution"))
    unit = {"um": 1e-3, "mm": 1.0, "mil": 0.0254, "inch": 25.4}[res[1]] / float(res[2])
    layer = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    nets = board.GetNetsByName()
    netout = next(_find(routes, "network_out"))
    n_tracks = n_vias = 0
    for nn in _find(netout, "net"):
        if nn[1] == "GNDFIX":                       # fixed GND fanout (rev 2 RGB boards): already on the board
            continue
        ni = nets[nn[1]]
        for w in _find(nn, "wire"):
            for pth in _find(w, "path"):
                lay, width = layer[pth[1]], float(pth[2]) * unit
                xy = [float(v) * unit for v in pth[3:]]
                pts = [(xy[i], -xy[i + 1]) for i in range(0, len(xy), 2)]
                for a, c in zip(pts[:-1], pts[1:]):
                    t = pcbnew.PCB_TRACK(board)
                    t.SetStart(V(*a))
                    t.SetEnd(V(*c))
                    t.SetWidth(MM(width))
                    t.SetLayer(lay)
                    t.SetNet(ni)
                    board.Add(t)
                    n_tracks += 1
        for v in _find(nn, "via"):
            x, y = float(v[2]) * unit, -float(v[3]) * unit
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(V(x, y))
            # the size the router placed and spaced it at: KiCad names a via padstack "Via[0-1]_800:400_um", and a
            # net class with its own via (controller rev 2's Power class) gets its own padstack
            m = re.search(r"_(\d+):(\d+)_um", v[1])
            dia, drill = (int(m.group(1)) / 1000, int(m.group(2)) / 1000) if m else (PR.VIA_D, PR.VIA_DRILL)
            via.SetWidth(MM(dia))
            via.SetDrill(MM(drill))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNet(ni)
            board.Add(via)
            n_vias += 1
    return n_tracks, n_vias - remove_dangling(board)


def _on_centreline(seg, p, tol=MM(0.005)):
    """True if point p = (x, y) lies on segment seg = (ax, ay, cx, cy) within tol.
    Not HitTest: that counts the track's whole width, so in a chain of short
    collinear stubs each free end sits inside its neighbour's copper and the
    chain never gets removed. Plain tuples: calling GetStart()/GetEnd() inside
    the inner loop makes KiCad 7's SWIG start returning bare pointers."""
    ax, ay, cx, cy = seg
    dx, dy = cx - ax, cy - ay
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(ax + u * dx - p[0], ay + u * dy - p[1]) <= tol


def remove_dangling(board):
    """Delete router leftovers: a track end that touches no pad, via or other
    track of its net (an end on another segment's centreline, T-junctions
    included, counts as touching), repeated until stable; then vias joined to
    fewer than two tracks. Returns the number of vias removed."""
    removed_v = 0
    # boards poured with GND after routing (rev 2 RGB): their GND copper is pre-placed fanout, joined by the pour
    poured = board.GetNetsByName()["GND"].GetNetCode() if getattr(board, "kb2_gnd_pour", False) else None
    while True:
        tracks = [t for t in board.GetTracks() if t.GetClass() != "PCB_VIA" and t.GetNetCode() != poured]
        vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() != poured]
        pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
        by_net, seg = {}, {}
        for i, t in enumerate(tracks):
            by_net.setdefault((t.GetNetCode(), t.GetLayer()), []).append(i)
            a, c = t.GetStart(), t.GetEnd()
            seg[i] = (a.x, a.y, c.x, c.y)
        dead = []
        for i, t in enumerate(tracks):
            same = by_net[(t.GetNetCode(), t.GetLayer())]
            ax, ay, cx, cy = seg[i]
            for e, xy in ((t.GetStart(), (ax, ay)), (t.GetEnd(), (cx, cy))):
                if any(j != i and _on_centreline(seg[j], xy) for j in same):
                    continue
                if any(v.GetNetCode() == t.GetNetCode() and v.HitTest(e, 1) for v in vias):
                    continue
                if any(p.GetNetCode() == t.GetNetCode() and p.IsOnLayer(t.GetLayer()) and p.HitTest(e) for p in pads):
                    continue
                dead.append(t)
                break
        for v in vias:
            n = sum(1 for t in tracks if t.GetNetCode() == v.GetNetCode() and t not in dead
                    and any(v.HitTest(e, 1) for e in (t.GetStart(), t.GetEnd())))
            if n < 2:
                dead.append(v)
                removed_v += 1
        if not dead:
            return removed_v
        for t in set(dead):              # Delete, not Remove: a removed item is freed by Python's GC,
            board.Delete(t)              #   which leaves KiCad 7's SWIG handing back bare pointers


# ---------------------------------------------------------------- DRC + exports
def drc_counts(rep):
    """(errors, warnings, unconnected) in a DRC report that drc() wrote."""
    txt = open(rep).read()
    errors = len(re.findall(r"Severity: error", txt))
    # library-path notes only exist because the boards are generated outside a KiCad project
    warnings = len(re.findall(r"Severity: warning", txt)) - len(re.findall(r"\[lib_footprint_issues\]", txt))
    unc = int(re.search(r"\*\* Found (\d+) unconnected pads", txt).group(1))
    return errors, warnings, unc


def drc(board, name):
    rep = os.path.join(PCB_OUT, name + "_drc.txt")
    pcbnew.WriteDRCReport(board, rep, pcbnew.EDA_UNITS_MILLIMETRES, True)
    return (*drc_counts(rep), rep)


def export(board_path, name, layers=None, drill=True, rename=None):
    """Gerbers (+ drill files) zipped for JLCPCB, and front/back SVG previews. A single-sided flex passes its own
    `layers` and drill=False; `rename` maps a Gerber's file-name suffix to a clearer one in the zip."""
    gdir = os.path.join(PCB_OUT, name + "_gerbers")
    shutil.rmtree(gdir, ignore_errors=True)
    os.makedirs(gdir)
    layers = layers or "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
    subprocess.run(["kicad-cli", "pcb", "export", "gerbers", "--layers", layers, "--subtract-soldermask",
                    "--no-x2", "-o", gdir + "/", board_path], check=True, capture_output=True)
    if drill:
        subprocess.run(["kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
                        "--generate-map", "--map-format", "gerberx2", "-o", gdir + "/", board_path], check=True, capture_output=True)
    for old, new in (rename or {}).items():
        for f in os.listdir(gdir):
            if f.endswith(old):
                os.rename(os.path.join(gdir, f), os.path.join(gdir, f[:-len(old)] + new))
            elif f.endswith(".gbrjob"):                  # it lists the old file names
                os.remove(os.path.join(gdir, f))
    z = os.path.join(PCB_OUT, f"{name}_JLCPCB.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir(gdir)):
            zf.write(os.path.join(gdir, f), f)
    for side, lay in (("front", "F.Cu,F.SilkS,F.Mask,Edge.Cuts"), ("back", "B.Cu,B.SilkS,B.Mask,Edge.Cuts")):
        subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers", lay, "--exclude-drawing-sheet",
                        "--page-size-mode", "2", "-o", os.path.join(PCB_OUT, f"{name}_{side}.svg"), board_path]
                       + (["--mirror"] if side == "back" else []), check=True, capture_output=True)
        try:                                            # PNG preview if cairosvg is around
            import cairosvg
            cairosvg.svg2png(url=os.path.join(PCB_OUT, f"{name}_{side}.svg"), write_to=os.path.join(PCB_OUT, f"{name}_{side}.png"),
                             output_width=1600, background_color="white")
        except ImportError:
            pass
    return z


def make(name, builder, passes=60, attempts=10):
    """Route from a fresh board until DRC is clean (Freerouting is randomized)."""
    for attempt in range(1, attempts + 1):
        err, unc = _make_once(name, builder(), passes)
        if err == 0 and unc == 0:
            return err, unc
        print(f"  {name}: attempt {attempt} not clean, rerouting")
    raise RuntimeError(f"{name}: no clean route after {attempts} attempts")


def _make_once(name, board, passes):
    r = route(board, name, passes)
    if r is None:
        print(f"  {name}: router gave no result")
        return 1, 1
    t, v = r
    path = os.path.join(PCB_OUT, name + ".kicad_pcb")
    if hasattr(board, "kb2_after_route"):           # e.g. copper pours + stitching vias (rev 2 RGB half boards)
        # on a reloaded board: one made with pcbnew.BOARD() has no project, and KiCad 7's ZONE_FILLER
        # segfaults on it; the kb2_* attributes are Python-side, so carry them across
        extra = {k: x for k, x in vars(board).items() if k.startswith("kb2_")}
        pcbnew.SaveBoard(path, board)
        board = pcbnew.LoadBoard(path)
        for k, x in extra.items():
            setattr(board, k, x)
        board.kb2_after_route(board)
    pcbnew.SaveBoard(path, board)
    board = pcbnew.LoadBoard(path)
    err, warn, unc, rep = drc(board, name)
    for _ in range(3):                          # strip stubs KiCad itself reports as dangling
        txt = open(rep).read()
        stubs = [(float(x), float(y), lay, float(ln)) for x, y, lay, ln in re.findall(
            r"\[track_dangling\][^\n]*\n[^\n]*\n\s+@\(([\d.]+) mm, ([\d.]+) mm\): Track \[[^\]]*\] on ([FB])\.Cu, length ([\d.]+) mm", txt)]
        if not stubs:
            break
        for trk in list(board.GetTracks()):
            if trk.GetClass() == "PCB_VIA":
                continue
            lay = "F" if trk.GetLayer() == pcbnew.F_Cu else "B"
            ln = pcbnew.ToMM(trk.GetLength())
            ends = [(pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)) for e in (trk.GetStart(), trk.GetEnd())]
            if any(lay == sl and abs(ln - sln) < 2e-3 and any(math.dist(e, (sx, sy)) < 2e-3 for e in ends)
                   for sx, sy, sl, sln in stubs):
                board.Delete(trk)
        pcbnew.SaveBoard(path, board)
        board = pcbnew.LoadBoard(path)
        err, warn, unc, rep = drc(board, name)
    z = export(path, name)
    print(f"{name}: {t} track segments, {v} vias | DRC {err} errors, {warn} warnings, {unc} unconnected | {os.path.basename(z)}")
    return err, unc


def main(which=None):
    os.makedirs(PCB_OUT, exist_ok=True)
    jobs = {"half_hotswap": lambda: build_half("hotswap"), "half_solder": lambda: build_half("solder"),
            "controller": build_ctrl}
    res = {}
    for n, f in jobs.items():
        if which and n not in which:
            continue
        res[n] = make(n, f)
    return res


if __name__ == "__main__":
    main(sys.argv[2:] or None)
