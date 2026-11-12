"""
Rev 2 fit checks (C58_REV=2): exact solids (OpenCascade), the controller's part envelopes from its KiCad
placement (both faces), the foam pads at their installed thickness.

    C58_REV=2 python3 -m compose gasket-checks [outdir]     -> prints PASS/FAIL lines, writes outdir/checks2.json

What is checked
  A  interference: every pair of parts that must not touch (case, plates, frames, cover, controller board,
     its parts on both faces, Pico + sockets + male headers, standoffs, half-board proxies)
  B  clearances: plate float to the case and frame, cover to frames, board / parts to the case
  C  gasket stack: at every pad, seat -> flange -> frame distances measured on the solids along the
     plate normal (installed pad thickness and squeeze of the weatherstrip tape)
  D  assembly paths: plate and frame drop in along the plate normal, the cover goes down 1.5 mm forward of
     home and slides back onto its hooks, the controller goes in tongues-first, tilted
  E  hardware: screw / standoff / insert engagement, Pico gap, cable plugs under the cover
  F  printability: each exported part in its print orientation is watertight and has no overhang steeper
     than 45 degrees off the bed (short bridges over holes allowed)
"""
import os
import sys
import json
import math
import numpy as np
import cadquery as cq
from shapely.geometry import Point
from compose import params as PR
from compose import geom as G
from compose.case import gasket as C
from compose.controller import rev2_std as CS
from compose.geom import prism, cyl, union, big_box, poly_prism

OUT = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
os.makedirs(OUT, exist_ok=True)
CT = C.CT
RES = []


def rec(name, ok, val="", warn=False):
    tag = "PASS" if ok else ("WARN" if warn else "FAIL")
    RES.append(dict(check=name, result=tag, value=val))
    print(f"{tag:4s}  {name}  {val}", flush=True)


def vol(a, b):
    try:
        return a.intersect(b).Volume()
    except Exception:
        return float("nan")


def dist(a, b):
    return a.distance(b)


# ---------------------------------------------------------------- the controller as placed (board frame -> P)
H_TOP = {"U1": 8.5, "JL": CS.VFFC_H, "JR": CS.VFFC_H, "J4": 8.5, "J6": 8.5, "J5": 4.3}
PLUG_TOP = {"J4": CS.TOP_PLUG_H, "J6": CS.TOP_PLUG_H, "J5": 10.0}
H_BOT = {"U2": 5.0, "C1": 6.0, "C2": 12.5, "F1": CS.BOTTOM_PARTS_H, "R": 3.0}


_CS = {}


def controller_solids():
    if not _CS:
        _CS.update(_controller_solids())
    return dict(_CS)


def _controller_solids():
    """P-frame solids: board, top envelopes (+ mated plugs), bottom envelopes, lead tails, Pico stack,
    standoffs. Returns dict name -> solid (P frame)."""
    from compose.controller import rev2 as CV
    import pcbnew
    from compose.pcb import kicad as PK
    os.makedirs(PK.PCB_OUT, exist_ok=True)
    b = CV.build()
    to_P = CT.to_P
    bt, bb = CT.board_top, CT.board_bot
    out = {}
    hol = union([cyl(*to_P(x, y), CS.M_CLEAR / 2, bb - 1, bt + 1) for x, y in CS.STANDOFF_HOLES])
    out["ctrl board"] = prism(list(CT.outline_P.exterior.coords)[:-1], bb, bt).cut(hol)
    top, bot, tails = [], [], []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        flipped = fp.IsFlipped()
        fp.BuildCourtyardCaches()
        r_ = fp.GetCourtyard(pcbnew.B_CrtYd if flipped else pcbnew.F_CrtYd).BBox()
        x0, x1 = pcbnew.ToMM(r_.GetLeft()) - CV.CX, pcbnew.ToMM(r_.GetRight()) - CV.CX
        y0, y1 = pcbnew.ToMM(r_.GetTop()) - CV.CY, pcbnew.ToMM(r_.GetBottom()) - CV.CY
        sh = 0.25
        (px0, py0), (px1, py1) = to_P(x0 + sh, y1 - sh), to_P(x1 - sh, y0 + sh)
        if flipped:
            h = next(v for k, v in H_BOT.items() if ref.startswith(k))
            bot.append(big_box(px0, px1, py0, py1, bb - h, bb))
        else:
            k = next((k for k in H_TOP if ref.startswith(k)), None)
            if k:
                top.append(big_box(px0, px1, py0, py1, bt, bt + H_TOP[k]))
                if k in PLUG_TOP:
                    top.append(big_box(px0, px1, py0, py1, bt + H_TOP[k] - 3.0, bt + PLUG_TOP[k]))
        for p in fp.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                x, y = to_P(pcbnew.ToMM(p.GetPosition().x) - CV.CX, pcbnew.ToMM(p.GetPosition().y) - CV.CY)
                if flipped:
                    tails.append(big_box(x - 0.4, x + 0.4, y - 0.4, y + 0.4, bt, bt + CS.LEAD_ABOVE))
                else:
                    tails.append(big_box(x - 0.4, x + 0.4, y - 0.4, y + 0.4, bb - CS.LEAD_BELOW, bb))
    out["top parts"] = union(top)
    out["bottom parts"] = union(bot)
    out["lead tails"] = union(tails)
    yc = CT.y_pc
    pico = big_box(-PR.PICO_W / 2, PR.PICO_W / 2, yc - PR.PICO_L / 2, yc + PR.PICO_L / 2, CT.pico_bot, CT.pico_top)
    mh = union([big_box(sx * CS.PICO_X - 1.25, sx * CS.PICO_X + 1.25, yc - 25.4, yc + 25.4, bt + 8.5, CT.pico_bot)
                for sx in (-1, 1)])
    out["pico"] = pico.fuse(mh)
    out["standoffs"] = union([cyl(*to_P(x, y), CS.STANDOFF_AF / 2 / math.cos(math.radians(30)), bt, bt + CS.STANDOFF_L)
                              for x, y in CS.STANDOFF_HOLES])
    return out


# ---------------------------------------------------------------- rev 2 half board: underside parts; flex jumpers
HALF_PART_H = {"sockets": PR.HS_HEIGHT, "diodes": PR.DIODE_BODY[1], "caps": 1.3,
               "ffc": 2.1,       # Molex 200528: 1.9 +/- 0.2 mm (drawing)
               "leds": 1.0,      # SK6812 MINI-E: 1.78 body - 0.84 above the leads = 0.94 below the pads, + solder
               "heads": PR.M2_HEAD_H,
               "pins": 2.0}


def half_parts_local(no_switch=None):
    """Everything under a half board (left local frame), every variant at once: hotswap sockets, diode bodies,
    capacitors, LEDs, the cable connector, M2 screw heads, solder-in switch pins. `no_switch`: index of a key that
    has no switch (a slot device stands there), so no socket and no switch pins either."""
    from compose.pcb import rev2_half as H2
    from compose.pcb import layout as PL
    from shapely.geometry import LineString as LS
    from shapely.ops import unary_union as uu
    s = H2.plan("hotswap", True)
    z0 = -PR.PCB_T
    shapes = {
        "sockets": s.socks,
        "diodes": uu([LS([ks.cathode, ks.anode]).buffer(PR.DIODE_BODY[1] / 2) for ks in s.keys]),
        "caps": uu([H2.cap_box(G.LAYOUT.keys[i], f).buffer(-0.5) for i in s.caps for f in ("B", "F")]),
        "ffc": s.ffc.body,
        "leds": uu(s.ledcut),            # reverse-mount MINI-E: the body (3.2 x 2.8) within its cutout
        "heads": uu([Point(p).buffer(PR.M2_HEAD_D / 2) for p in s.posts]),
        "pins": uu([Point(PL.fp2local(k, *pp)).buffer(0.8) for i, k in enumerate(G.LAYOUT.keys) if i != no_switch
                    for p_ in (PR.MX_PIN1, PR.MX_PIN2) for pp in (p_, PL.mirror_fp(p_))]),
    }
    if no_switch is not None:
        shapes["sockets"] = shapes["sockets"].difference(H2.socket_shapes(G.LAYOUT.keys[no_switch]).buffer(0.01))
    sol = [poly_prism(g, z0 - HALF_PART_H[n], z0) for n, g in shapes.items() if not g.is_empty]
    return union(sol)


def jumpers_P():
    """Both flex jumpers (bridge frame P): the solved left one and its mirror. A compound: they're only used for
    interference checks."""
    from compose.pcb import jumper as J
    left = J.solid_P(J.solve())
    return cq.Compound.makeCompound([left, left.mirror("YZ")])


def jumper_insert_P():
    """What the controller end of a jumper sweeps while it's pushed 4.1 mm straight down into its slot (cover
    off): the stiffened end's column from the slot opening up to 4.1 mm above where it ends up."""
    from compose.pcb import jumper as J
    g = J.solve()
    top = g.ctrl.top
    W, T = PR.JUMPER_W, J.T_SOLID
    lo = top + J.Z * 0.05
    sol = (cq.Workplane("XY").box(T, W, J.STIFF_OUT + CS.VFFC_INSERT, centered=(True, True, False))
           .translate(cq.Vector(*lo)).val())
    return cq.Compound.makeCompound([sol, sol.mirror("YZ")])


# ---------------------------------------------------------------- gasket pads (installed thickness)
def pads_local():
    """Lower and upper pads (left local frame) at their installed thickness."""
    lo, up = [], []
    for c, t, n in C.GL.tabs:
        poly = C.pad_poly(c, t, n)
        lo.append(poly_prism(poly, PR.LEDGE_TOP, PR.FLANGE_Z0))
        up.append(poly_prism(poly, PR.FLANGE_Z0 + PR.FLANGE_T, PR.FRAME_LIP_Z))
    for c in C.GL.inner:
        poly = C.inner_pad_poly(c)
        lo.append(poly_prism(poly, PR.LEDGE_TOP, PR.FLANGE_Z0))
        up.append(poly_prism(poly, PR.FLANGE_Z0 + PR.FLANGE_T, PR.FRAME_LIP_Z))
    return lo, up


LINE_W = 0.45                     # one extrusion line (0.4 mm nozzle)


def overhangs(m, layer=0.2, bridge_max=12.0, lip_max=LINE_W, seats=()):
    """Slice the part in print orientation and compare each layer with the one under it: material more than
    one layer height (45 deg) beyond the layer below is unsupported. A patch is fine if it is no wider than one
    extrusion line (lip_max: the perimeter still lands mostly on the layer below), or a bridge (narrower than
    bridge_max and resting on support around most of its edge, like a hole's ceiling). Anything else, a
    stepped overhang included, fails: overhangs are meant to be smooth chamfers. The exception is `seats`
    (print-frame polygons): the flat shoulders screw heads clamp on, inside their counterbores, which the tent
    tilts so that each layer exposes a thin crescent of them. Returns (worst patch or None, n bridges, n lips,
    n seat patches)."""
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.ops import unary_union as uu
    z0, z1 = m.bounds[0][2], m.bounds[1][2]
    zs = np.arange(z0 + layer / 2, z1, layer)
    secs = m.section_multiplane(plane_origin=[0, 0, 0], plane_normal=[0, 0, 1], heights=zs)
    prev, worst, n_br, n_thin, n_seat = None, None, 0, 0, 0
    seat_u = uu(list(seats)) if seats else Polygon()
    for z, s in zip(zs, secs):
        cur = uu([p for p in s.polygons_full]) if s is not None else Polygon()
        cur = cur.buffer(0)
        if prev is not None and not cur.is_empty:
            sup = prev.buffer(layer)
            un = cur.difference(sup)
            for u in getattr(un, "geoms", [un]):
                if u.is_empty or u.area < 0.3:
                    continue
                if u.buffer(-lip_max / 2).is_empty:
                    n_thin += 1
                    continue
                touch = u.exterior.intersection(sup.buffer(0.05)).length / max(u.exterior.length, 1e-9)
                if u.buffer(-bridge_max / 2).is_empty and touch > 0.5:
                    n_br += 1
                    continue
                c = u.centroid
                if not seat_u.is_empty and seat_u.contains(c):
                    n_seat += 1
                    continue
                worst = f"{u.area:.1f} mm2 at z {z:.1f} ({c.x:.0f}, {c.y:.0f})"
        prev = cur if not cur.is_empty else prev
    return worst, n_br, n_thin, n_seat


def mirror_pair(local):
    w = G.L2W(local)
    return w.fuse(w.mirror("YZ"))


def parts_world(jumpers=True):
    """Every part of the assembled keyboard (world frame) as the checks use them: {name: solid}, plus the gasket
    pads (lower, upper)."""
    from compose import pointer as PTR
    cfg = PTR.active()
    case = C.case2_world()
    cover = G.P2W(C.cover2_P())
    hp = G.OUTLINE.buffer(-PR.PCB_INSET)
    if cfg is None:
        plateL = C.plate2_local()
        frameL = C.frame2_local()
        plate = mirror_pair(plateL)
        frame = mirror_pair(frameL)
        half_pcb = mirror_pair(prism(list(hp.exterior.coords)[:-1], -PR.PCB_T, 0.0))
        half_parts = mirror_pair(half_parts_local())
    else:                                  # one side carries a pointer device: each side on its own
        from compose.pointer import place as PPL
        pl = PPL.place(cfg)
        side_w = {"L": G.L2W, "R": G.R2W}
        plain = [s for s in "LR" if s != cfg.side][0]
        plate = G.L2W(C.plate2_local("L")).fuse(G.R2W(C.plate2_local("R")))
        frame = G.L2W(C.frame2_local("L")).fuse(G.R2W(C.frame2_local("R")))
        hp_m = hp if pl.kind == "bay" else hp.difference(Point(pl.frame[:2]).buffer(PR.MX_CENTER_D / 2))
        half_pcb = side_w[plain](prism(list(hp.exterior.coords)[:-1], -PR.PCB_T, 0.0)).fuse(    # the cable's way
            side_w[cfg.side](poly_prism(hp_m, -PR.PCB_T, 0.0)))                                    # down at the key
        half_parts = side_w[plain](half_parts_local()).fuse(side_w[cfg.side](half_parts_local(pl.key_index)))
    ctrl = {k: G.P2W(v) for k, v in controller_solids().items()}
    lo, up = pads_local()
    pads_lo, pads_up = mirror_pair(union(lo)), mirror_pair(union(up))
    parts = dict(case=case, plate=plate, frame=frame, cover=cover, **{"half pcb": half_pcb, "half parts": half_parts},
                 **ctrl)
    if jumpers:
        parts["jumpers"] = G.P2W(jumpers_P())
    if cfg is not None:
        from compose.pointer import solids as PS, cable as PC
        to_w = side_w[cfg.side]
        parts["pointer"] = to_w(PS.module_solid(pl).fuse(PS.screws_solid(pl)))
        parts["pointer carrier"] = to_w(PS.carrier_solid(pl))
        r = PC.route(pl, cfg, parts)
        parts["pointer cable"] = PC.tube(r["pts"], PR.POINTER_CABLE_D / 2)
    return parts, case, pads_lo, pads_up


def main():
    print("building parts ...", flush=True)
    from compose.pcb import jumper as J
    jg = J.solve()                                       # the jumper path (raises if there's none)
    parts, case, pads_lo, pads_up = parts_world()
    from compose import pointer as PTR
    sides = None if PTR.active() is None else {"plate": (C.plate2_local("L"), C.plate2_local("R")),     # a device:
                                               "frame": (C.frame2_local("L"), C.frame2_local("R"))}    # as built
    plate, frame, cover = parts["plate"], parts["frame"], parts["cover"]
    ctrl = {k: parts[k] for k in controller_solids()}

    # ---- A: interference (volume of overlap, mm3)
    allowed = {("ctrl board", "standoffs"), ("ctrl board", "lead tails"), ("ctrl board", "pico"),
               ("lead tails", "pico"), ("lead tails", "top parts"), ("lead tails", "bottom parts"),
               ("pico", "top parts"), ("plate", "half pcb"),
               ("ctrl board", "top parts"), ("ctrl board", "bottom parts"),
               ("pointer cable", "top parts")}      # the cable's end is in its plug (pointer-checks P4 holds the rest)
    names = list(parts)
    for i, a in enumerate(names):
        for b_ in names[i + 1:]:
            if (a, b_) in allowed or (b_, a) in allowed:
                continue
            v = vol(parts[a], parts[b_])
            rec(f"A no overlap: {a} / {b_}", v < 1e-3, f"{v:.3f} mm3")
    for nm, pd in (("lower pads", pads_lo), ("upper pads", pads_up)):
        for a in ("case", "plate", "frame", "half pcb", "half parts", "cover"):
            v = vol(pd, parts[a])
            rec(f"A no overlap: {nm} / {a}", v < 0.05, f"{v:.3f} mm3")

    # ---- B: clearances (mm)
    no_posts = case.cut(G.P2W(union([cyl(x, y, CS.POST_R + 0.5, CT.board_bot - 0.6, CT.board_bot + 5)
                                      for x, y in CT.mounts])))      # the board sits on the post tops
    parts_b = dict(parts, **{"case (posts excl.)": no_posts})
    for a, b_, lim in (("plate", "case", PR.FLOAT_GAP - 0.05), ("plate", "frame", 0.5), ("plate", "cover", 0.5),
                       ("cover", "frame", PR.FIT_GAP - 0.05), ("ctrl board", "case (posts excl.)", 0.2),
                       ("top parts", "case", 0.3), ("bottom parts", "case", 0.3), ("pico", "cover", 0.5),
                       ("pico", "case", 0.3), ("half pcb", "case", 0.3), ("standoffs", "case", 0.3),
                       ("ctrl board", "plate", 0.5), ("top parts", "plate", 0.5), ("ctrl board", "half pcb", 0.5),
                       ("half parts", "case", 0.3), ("jumpers", "case", 0.5), ("jumpers", "plate", 1.0),
                       ("jumpers", "frame", 0.5), ("jumpers", "cover", 0.5), ("jumpers", "half pcb", 0.5),
                       ("jumpers", "standoffs", 0.5), ("jumpers", "pico", 0.5), ("jumpers", "ctrl board", 0.5)):
        if a not in parts_b or b_ not in parts_b:
            continue
        d = dist(parts_b[a], parts_b[b_])
        rec(f"B clearance {a} / {b_} >= {lim:.2f}", d >= lim, f"{d:.2f} mm")

    # ---- C: gasket stack along the plate normal at every pad centre
    import trimesh
    meshes = {}
    for nm in ("case", "plate", "frame"):
        p = os.path.join(OUT, f"_c2_{nm}.stl")
        cq.exporters.export(cq.Workplane().add(parts[nm]), p, tolerance=0.02, angularTolerance=0.1)
        meshes[nm] = trimesh.load(p)
    nrm = G.plate_normal_world(-1)
    centres = [c for c, _, _ in C.GL.tabs] + list(C.GL.inner)
    worst = []
    for c in centres:
        o = np.array(G.apply(G.M_LW, (c[0], c[1], PR.LEDGE_TOP - 1.0)))
        hits = {}
        for nm, m in meshes.items():
            locs, _, _ = m.ray.intersects_location([o], [nrm])
            hits[nm] = sorted(float(np.dot(l - o, nrm)) for l in locs)
        seat = 1.0                                               # the case surface the ray starts under
        case_top = min((h for h in hits["case"] if h > 0.5), default=None)
        fl = [h for h in hits["plate"] if h > 0]
        fr = [h for h in hits["frame"] if h > 0]
        if case_top is None or len(fl) < 2 or not fr:
            worst.append((c, "missing", hits))
            continue
        lower = fl[0] - case_top
        upper = fr[0] - fl[1]
        worst.append((c, round(lower, 3), round(upper, 3)))
    ok = all(isinstance(w[1], float) and abs(w[1] - PR.GK_C) < 0.05 and abs(w[2] - PR.GK_C) < 0.05 for w in worst)
    rec("C pad gaps = installed thickness at every pad (lower, upper)", ok,
        f"{len(worst)} pads, target {PR.GK_C:.2f}; " + "; ".join(str(w[1:]) for w in worst if not
                                                              (isinstance(w[1], float) and abs(w[1] - PR.GK_C) < 0.05 and abs(w[2] - PR.GK_C) < 0.05))[:300])
    rec("C squeeze of 3.0-3.2 mm tape", True,
        f"{(1 - PR.GK_C / 3.0) * 100:.0f}-{(1 - PR.GK_C / 3.2) * 100:.0f} % (closed-cell EPDM/neoprene sponge: 25-50 %)")
    pad_area = PR.GK_PAD_L * PR.GK_PAD_W
    rec("C pad count / area per half", True, f"{len(centres)} pairs, {pad_area:.0f} mm2 each")

    # ---- D: assembly paths
    unsided = {}

    def sweep_local(local, d0, d1, step):
        return [G.L2W(local.translate(cq.Vector(0, 0, z))) for z in np.arange(d0, d1 + 1e-9, step)]

    def both_sides(name, d0, d1, step):
        """Both halves' plate or frame swept along its normal: the left shape and its mirror, or with a pointer
        device each side's own shape."""
        if sides is None:
            if name not in unsided:                          # built here, once: only this path uses them
                unsided[name] = {"plate": C.plate2_local, "frame": C.frame2_local}[name]()
            local = unsided[name]
            return [s.fuse(s.mirror("YZ")) for s in sweep_local(local, d0, d1, step)]
        l_, r_ = sides[name]
        return [a.fuse(b.mirror("YZ")) for a, b in zip(sweep_local(l_, d0, d1, step), sweep_local(r_, d0, d1, step))]
    # plate in along its normal: never hits the case on the way (pads off)
    bad = max(vol(case, s) for s in both_sides("plate", 2.0, 30.0, 4.0))
    rec("D plate drops in along its normal (case)", bad < 1e-3, f"{bad:.3f} mm3")
    bad = max(vol(case, s) for s in both_sides("frame", 1.0, 30.0, 3.0))
    rec("D frame drops in along its normal (case)", bad < 1e-3, f"{bad:.3f} mm3")
    bad = max(vol(plate, s) for s in both_sides("frame", 1.0, 30.0, 3.0))
    rec("D frame drops in along its normal (plates)", bad < 1e-3, f"{bad:.3f} mm3")
    # cover: drops straight down onto the standoffs
    cvP = C.cover2_P()
    others = case.fuse(frame).fuse(ctrl["pico"]).fuse(ctrl["standoffs"]).fuse(ctrl["top parts"])
    worst_c = max(vol(others, G.P2W(cvP.translate(cq.Vector(0, 0, dz)))) for dz in (0.0, 1.0, 3.0, 6.0, 10.0, 20.0))
    rec("D cover drops straight onto its standoffs", worst_c < 1e-3, f"{worst_c:.3f} mm3")
    seat = vol(ctrl["standoffs"], G.P2W(cvP.translate(cq.Vector(0, 0, -0.2))))
    rec("D cover seats on all four standoffs (bosses land on them)", seat > 0.5, f"{seat:.2f} mm3 if pushed 0.2 mm lower")

    # controller: drops straight in from above onto its four posts
    brd = controller_solids()
    board_all = union([brd["ctrl board"], brd["top parts"], brd["bottom parts"], brd["lead tails"]])
    worst_b = max(vol(case, G.P2W(board_all.translate(cq.Vector(0, 0, dz)))) for dz in (0.0, 1.0, 4.0, 8.0, 12.0, 16.0))
    rec("D controller drops straight in onto its posts", worst_b < 1e-3, f"{worst_b:.3f} mm3")

    # ---- E: hardware
    cover_t = CT.cover_top - CT.cover_under
    grip = cover_t - (PR.M3_HEAD_H + 0.2) + CS.COVER_BOSS_H
    rec("E cover screws M3x6 button: thread into the standoffs", 2.5 <= 6 - grip <= 5.0, f"{6 - grip:.2f} mm engaged")
    eng = CS.STANDOFF_THREAD - CS.PCB_T
    rec("E standoff male thread through the board into the post insert", 3.0 <= eng <= PR.M3_INSERT_L,
        f"{eng:.1f} mm, hole {PR.M3_INSERT_L} mm")
    rec("E Pico top -> cover underside", CT.pico_gap >= PR.STANDOFF_MIN_GAP, f"{CT.pico_gap:.2f} mm")
    rec("E mated header plugs under the cover", CS.TOP_PLUG_H <= CS.STANDOFF_L + CS.COVER_BOSS_H - 0.4,
        f"{CS.TOP_PLUG_H} mm of {CS.STANDOFF_L + CS.COVER_BOSS_H} mm")
    fl = CT.board_bot - PR.FLOOR_T
    sk = max(abs(v) for v in jg.skews)
    rec(f"E jumper path: one straight strip for both sides, climb {jg.rise_deg:.0f} deg, every bend r {jg.r} mm with its "
        f"bend line <= {math.degrees(sk):.1f} deg off square", jg.r >= 1.4 and min(jg.Ls) >= 0 and sk <= J.SKEW_MAX + 1e-9,
        f"straights {' / '.join(f'{v:.2f}' for v in jg.Ls)} mm, {jg.length:.1f} mm long")
    ins = G.P2W(jumper_insert_P())
    hits = {nm: GK_vol for nm in ("plate", "frame", "pico", "standoffs", "top parts", "case")
            if nm in parts and (GK_vol := vol(ins, parts[nm])) >= 1e-3}
    rec("E jumper's controller end slides 4.1 mm straight down into its slot (cover off)", not hits,
        ", ".join(f"{k} {v:.2f} mm3" for k, v in hits.items()) or "clear")
    rec("E room under the controller for the bottom parts", fl - CS.BOTTOM_PARTS_H >= 3.0, f"{fl:.1f} mm to the floor")

    # ---- F: printability of the exported parts in their print orientation
    import trimesh
    C.export_print(OUT)
    pdir = os.path.join(OUT, "print")
    for f in sorted(os.listdir(pdir)):
        if not f.endswith(".stl"):
            continue
        m = trimesh.load(os.path.join(pdir, f))
        u, cnt = np.unique(m.edges_sorted, axis=0, return_counts=True)
        rec(f"F {f}: watertight, no non-manifold edges", m.is_watertight and not (cnt > 2).any(),
            f"{int((cnt > 2).sum())} non-manifold edges")
        seats = []
        if f == "rev2_case.stl":                     # the frame screws' counterbore shoulders, in the STL's frame
            bb = parts["case"].BoundingBox()
            for x, y in C.GL.screws:
                pw = G.apply(G.M_LW, (x, y, PR.SEAM_Z - PR.SHELF_T))
                for sx in (1, -1):
                    seats.append(Point(sx * pw[0] - bb.center.x, pw[1] - bb.center.y).buffer(PR.M3_CBORE_D / 2 + 0.5))
        worst, n_br, n_thin, n_seat = overhangs(m, seats=seats)
        rec(f"F {f}: every layer supported (45 deg rule; bridges <= 12 mm, no step wider than a {LINE_W} mm line)",
            worst is None,
            f"{n_br} bridges, {n_thin} thin lips" + (f", {n_seat} patches on the {len(seats)} screw seats" if seats else "")
            + ("" if worst is None else f"; unsupported {worst}"))

    json.dump(RES, open(os.path.join(OUT, "checks2.json"), "w"), indent=1)
    n_f = sum(r["result"] == "FAIL" for r in RES)
    print(f"\n{len(RES)} checks, {n_f} FAIL, {sum(r['result'] == 'WARN' for r in RES)} WARN")
    return n_f


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
