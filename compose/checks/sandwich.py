"""
Automated checks:  python3 -m compose checks [outdir]     (run `build` and `model` first)

  1. every printed part is a closed, single-body mesh
  2. printed parts don't overlap in the assembled position
  3. nothing electronic or metal sits inside a printed part; wire clearance
  4. assembly sweeps: each part is moved along its install direction, in
     assembly order, and must not hit anything already installed
  5. tool access to every screw
  6. overhangs in print orientation (only short bridges allowed)
  7. bed fit
Exit code 1 if anything fails.
"""
import os
import sys
import numpy as np
import trimesh
from compose import params as PR
from compose import geom as G
from compose.case import sandwich as PT

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
FAIL = []
L = lambda *p: trimesh.load(os.path.join(OUT, *p))
RENDER = os.path.join(OUT, "render")


def ok(cond, msg):
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        FAIL.append(msg)


def vol_inter(a, b):
    """Overlap between two closed meshes (mm3). Raises if either isn't a volume,
    so a broken mesh can never pass a check silently."""
    if not (a.is_watertight and b.is_watertight):
        raise ValueError("vol_inter needs closed meshes")
    r = trimesh.boolean.intersection([a, b], engine="manifold")
    return r.volume if r is not None and len(r.faces) else 0.0


# Point-in-mesh and signed-distance queries on up to 120 000 sample points. trimesh casts one ray per point
# and sizes its arrays by points x candidate triangles: in one call that peaked at ~40 GB. The points go in
# chunks of CHUNK instead, spread over worker processes (forked, so they share the mesh and its ray index);
# every point's answer is computed exactly as before and the chunks are joined in order.
CHUNK = 1000
_NPROC = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else 1
_MESH = None


def _chunks(p):
    return [p[i:i + CHUNK] for i in range(0, len(p), CHUNK)] or [p]


def _contains(c):
    return _MESH.contains(c)


def _IN(m, p):
    """m.contains(p), in chunks, in parallel where the platform can fork."""
    global _MESH
    cs = _chunks(p)
    if _NPROC < 2 or len(cs) < 2 or not sys.platform.startswith("linux"):
        return np.concatenate([m.contains(c) for c in cs])
    import multiprocessing
    m.contains(p[:1])                       # build the ray index once, before the workers fork
    _MESH = m
    with multiprocessing.get_context("fork").Pool(min(_NPROC, len(cs))) as pool:
        out = pool.map(_contains, cs)
    _MESH = None
    return np.concatenate(out)


def _SD(m, p):
    """trimesh.proximity.signed_distance(m, p), in chunks."""
    return np.concatenate([trimesh.proximity.signed_distance(m, c) for c in _chunks(p)])


def collide(a, b, n=20000):
    """Collision measure for any pair: overlap volume when both are closed,
    otherwise penetration depth (mm) of the open mesh's surface samples into
    the closed one. Returns (value, unit)."""
    if a.is_watertight and b.is_watertight:
        return vol_inter(a, b), "mm3"
    op, cl = (a, b) if not a.is_watertight else (b, a)
    if not cl.is_watertight:
        raise ValueError("collide: at least one mesh must be closed")
    pts, _ = trimesh.sample.sample_surface(op, n, seed=5)
    ins = _IN(cl, pts)
    if not ins.any():
        return 0.0, "mm"
    return float(_SD(cl, pts[ins]).max()), "mm"


def group(*names):
    ms = [trimesh.load(os.path.join(RENDER, f"a_{n}.stl")) for n in names if os.path.exists(os.path.join(RENDER, f"a_{n}.stl"))]
    ms = [m for m in ms if isinstance(m, trimesh.Trimesh) and len(m.faces)]
    return trimesh.util.concatenate(ms) if ms else None


def penetration(mesh, solids, n=25000):
    pts, _ = trimesh.sample.sample_surface(mesh, n, seed=3)
    worst = 0.0
    for s in solids:
        ins = _IN(s, pts)
        if ins.any():
            worst = max(worst, float(_SD(s, pts[ins]).max()))
    return worst


printed = {n: L("world", n + ".stl") for n in ("case", "plate_left", "plate_right", "frame_left", "frame_right", "cover")}

print("1. meshes")
for f in sorted(os.listdir(os.path.join(OUT, "print"))):
    m = L("print", f)
    ok(m.is_watertight and len(m.split(only_watertight=False)) == 1, f"{f}: closed single body ({m.extents.round(1).tolist()} mm)")

print("2. printed parts in assembly position")
names = list(printed)
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        v = vol_inter(printed[names[i]], printed[names[j]])
        if v > 0.0 or (names[i], names[j]) == ("case", "plate_left"):
            ok(v < 0.5, f"{names[i]} x {names[j]}: {v:.3f} mm3 overlap" + (" (resting contact)" if 0 < v < 0.5 else ""))

print("3. electronics and hardware vs printed parts")
solids = list(printed.values())
for n in ("switch", "pins", "leg", "diode", "copper", "kapton", "solder", "lead_row", "lead_col", "stub_row",
          "stub_col", "swlegs", "pcb", "silver", "perf", "header", "headerm", "ctail", "pinsm", "csolder", "screw", "cscrew",
          "coverscrew", "keycap", "keycap2", "foam", "hpcb", "hsocket", "band", "hconn", "cpcb", "cconn", "plug",
          "chip", "passive", "cstandoff"):
    m = group(n)
    if m is None:
        continue
    p = penetration(m, solids)
    tol = 0.1 if n in ("kapton", "foam", "screw", "coverscrew", "cscrew", "solder") else 0.02
    ok(p <= tol, f"{n}: max depth inside printed parts {p:.2f} mm")
def _caps_pressed_check():
    """Keycaps at rest and pressed to the end of travel (along each half's plate normal):
    no contact with the frames, cover or case, and the gap that's left."""
    nL_, nR_ = G.plate_normal_world(-1), G.plate_normal_world(1)
    caps = group("keycap", "keycap2")
    hard = [printed[n] for n in ("frame_left", "frame_right", "cover", "case")]
    worst_p, worst_g = 0.0, 1e9
    for side, n in ((-1, nL_), (1, nR_)):
        parts_ = [p for p in caps.split(only_watertight=False) if np.sign(p.centroid[0]) == side]
        m = trimesh.util.concatenate(parts_)
        for d in (0.0, PR.MX_TRAVEL):
            mv = m.copy(); mv.apply_translation(-n * d)
            worst_p = max(worst_p, penetration(mv, hard, n=40000))
            if d > 0:
                worst_g = min(worst_g, min(min_gap(mv, h, n=30000) for h in hard))
    ok(worst_p <= 0.02, f"keycaps at rest and fully pressed: max depth into frame/cover/case {worst_p:.2f} mm")
    ok(worst_g >= 0.3, f"keycaps fully pressed: closest approach to frame/cover/case {worst_g:.2f} mm")


def min_gap(mesh, solid, n=40000):
    pts, _ = trimesh.sample.sample_surface(mesh, n, seed=2)
    return min(trimesh.proximity.closest_point(solid, ch)[1].min() for ch in np.array_split(pts, 20))


def edge_gap(poly, M, z, solid, mirror=False):
    """Distance from a board's outline (sampled at mid-thickness) to a solid.
    The boards rest on bosses/posts by design, so only the edge is measured."""
    ln = poly.exterior.length
    pts = [poly.exterior.interpolate(t) for t in np.arange(0, ln, 0.5)]
    w = np.array([G.apply(M, (p.x, p.y, z)) for p in pts])
    if mirror:
        w = w * np.array([-1, 1, 1])
    return float(trimesh.proximity.closest_point(solid, w)[1].min())


if PR.MATRIX == "pcb":
    from compose.pcb import layout as PLY
    hp = PLY.plan_half()
    g = min(edge_gap(hp.outline, G.M_LW, -PR.PCB_T / 2, printed["case"], m) for m in (False, True))
    ok(g >= PR.PCB_EDGE_GAP - 0.1, f"half board edges to the case: {g:.2f} mm (designed {PR.PCB_EDGE_GAP})")
    if PR.CONTROLLER == "rev2":
        st_ = PT.Stack
        g = edge_gap(st_.outline_P, G.M_PW, (st_.board_bot + st_.board_top) / 2, printed["case"])
        ok(g >= 0.44, f"controller rev 2 board edge to the case: {g:.2f} mm (envelope kept 0.45 clear)")
        cparts = group("cconn", "chip", "passive", "plug", "header")
        for nm_, solid_, lim in (("case", printed["case"], 0.44), ("cover", printed["cover"], 0.5),
                                 ("left plate", printed["plate_left"], 0.5), ("right plate", printed["plate_right"], 0.5)):
            g = min(min_gap(cparts, solid_), min_gap(group("cstandoff"), solid_) if nm_ != "cover" else 9.0)
            ok(g >= lim, f"controller rev 2 parts, plugs and standoffs to the {nm_}: {g:.2f} mm")
        # the cover sits on the standoff tops (that's the joint): contact, no overlap
        g = min_gap(group("cstandoff"), printed["cover"])
        p_ = penetration(group("cstandoff"), [printed["cover"]])
        ok(g < 0.05 and p_ <= 0.02, f"cover seats on the standoff tops: gap {g:.2f} mm, overlap {p_:.2f} mm")
        g = min_gap(group("ctail"), printed["case"])
        ok(g >= 0.5, f"controller rev 2 leads under the board to the case floor: {g:.2f} mm")
        g = min_gap(group("pcb"), printed["cover"])
        ok(g >= PR.STANDOFF_MIN_GAP - 0.05, f"Pico top to the cover: {g:.2f} mm ({st_.standoff_len} mm standoffs)")
    else:
        cp = PLY.plan_ctrl(PT.Stack, PT.pillar_positions())
        g = edge_gap(cp.outline, G.M_PW, (PT.Stack.carrier_bot + PT.Stack.carrier_top) / 2, printed["case"])
        ok(g >= 0.5, f"controller board edge to the case/pillars: {g:.2f} mm")
    g = min_gap(group("hsocket", "diode", "hconn", "leg"), printed["case"])
    ok(g >= 0.25, f"half-board parts to the case: {g:.2f} mm")
    g = min_gap(group("cconn"), printed["case"])
    ok(g >= 0.5, f"controller connectors to the case: {g:.2f} mm")
    hb = group("hpcb", "hsocket", "diode", "hconn")
    for nm in ("cpcb", "cconn") + (("passive", "plug", "cstandoff") if PR.CONTROLLER == "rev2" else ()):
        v, u = collide(group(nm), group("hpcb")) if group(nm).is_watertight else collide(group("hpcb"), group(nm))
        ok(v < 0.02, f"{nm} vs half boards: {v:.3f} {u}")
    # every switch pin, plastic leg and centre post must pass through a hole in the board
    sw_under = trimesh.util.concatenate([group("pins"), group("swlegs")])
    pts, _ = trimesh.sample.sample_surface(sw_under, 120000, seed=4)
    hpcb = group("hpcb")
    ins = _IN(hpcb, pts)
    depth = float(_SD(hpcb, pts[ins]).max()) if ins.any() else 0.0
    ok(depth < 0.02, f"switch pins, legs and centre posts through the board holes: max {depth:.2f} mm into the board")
    # diodes vs hotswap sockets, on the face they share (both orientations): bare leads must not reach a tab
    from shapely.geometry import Point as SP, LineString as SL, Polygon as SPo
    from shapely.ops import unary_union as SU
    def _rect(k, c_, sz, mir):
        cc = PLY.mirror_fp(c_) if mir else c_
        return SPo([PLY.fp2local(k, cc[0] + dx * sz[0] / 2, cc[1] + dy * sz[1] / 2) for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    lead_gap = body_gap = 9.0
    for mir in (False, True):
        pads = SU([_rect(k, c_, sz, mir) for k in G.LAYOUT.keys for c_, sz in (PR.HS_PAD2, PR.HS_PAD1)])
        for ks in hp.keys:
            ca, an = np.array(ks.cathode), np.array(ks.anode)
            u_ = (an - ca) / np.linalg.norm(an - ca)
            m_, dhl = (an + ca) / 2, PR.DIODE_BODY[0] / 2
            body = SL([m_ - u_ * dhl, m_ + u_ * dhl]).buffer(PR.DIODE_BODY[1] / 2)
            leads = SU([SL([ca, m_ - u_ * dhl]).buffer(0.25), SL([an, m_ + u_ * dhl]).buffer(0.25)])
            lead_gap, body_gap = min(lead_gap, leads.distance(pads)), min(body_gap, body.distance(pads))
    ok(lead_gap >= 0.5 and body_gap > 0.0,
       f"diodes vs hotswap socket pads (both halves): bare leads {lead_gap:.2f} mm, glass body {body_gap:.2f} mm")
    hs = group("hsocket")
    pts, _ = trimesh.sample.sample_surface(group("swlegs"), 60000, seed=6)
    v, u = 0.0, "mm"
    for lobe in hs.split(only_watertight=False):
        if lobe.is_watertight:
            ins = _IN(lobe, pts)
            if ins.any():
                v = max(v, float(_SD(lobe, pts[ins]).max()))
    ok(v < 0.02, f"switch legs/posts vs hotswap socket bodies: {v:.2f} {u}")
    g = min_gap(group("cconn", "cpcb"), hb)
    ok(g >= 1.0, f"controller to half boards and their parts: {g:.2f} mm (room for the cable plugs)")
else:
    g = min_gap(group("lead_row", "lead_col", "copper"), printed["case"])
    ok(g >= 0.8, f"closest wire to the case: {g:.2f} mm")

_caps_pressed_check()

print("4. assembly sweeps (part moved along its install direction)")
up_P = G.up_P_world()
nL, nR = G.plate_normal_world(-1), G.plate_normal_world(1)
steps = (0.3, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0)
socket = group("perf", "cpcb", "cconn", "header", "headerm", "pcb", "silver", "pinsm", "ctail",
               *(("chip", "passive", "plug", "cstandoff", "cscrew") if PR.CONTROLLER == "rev2" else ()))
sw_all = group("switch", "swlegs", "pins", "leg", "diode", "copper", "kapton", "solder", "hpcb", "hsocket", "band", "hconn")


def sweep(label, moving, direction, fixed):
    """moving / fixed: lists of meshes. Every moving mesh is translated along
    `direction` by each step and tested against every fixed mesh."""
    worst = {"mm3": 0.0, "mm": 0.0}
    for d in steps:
        for m in moving:
            mv = m.copy()
            mv.apply_translation(direction * d)
            for f in fixed:
                v, u = collide(mv, f)
                worst[u] = max(worst[u], v)
    good = worst["mm3"] < 0.01 and worst["mm"] < 0.02
    ok(good, f"{label}: worst {worst['mm3']:.3f} mm3 overlap / {worst['mm']:.2f} mm penetration on the way in")


def split_side(mesh, side):
    parts_ = [p for p in mesh.split(only_watertight=False) if np.sign(p.centroid[0]) == side]
    return trimesh.util.concatenate(parts_) if parts_ else None


case = printed["case"]
sweep("1 Pico on its carrier, into the case", [socket], up_P, [case])
for side, nm, n in ((-1, "left", nL), (1, "right", nR)):
    sweep(f"2 {nm} plate with switches + wiring, into the case",
          [printed[f"plate_{nm}"], split_side(sw_all, side)], n, [case, socket])
for side, nm, n in ((-1, "left", nL), (1, "right", nR)):
    sweep(f"3 {nm} frame onto the plate", [printed[f"frame_{nm}"]], n,
          [case, printed["plate_left"], printed["plate_right"], split_side(group("switch"), side)])
sweep("4 cover onto the centre section", [printed["cover"]], up_P,
      [case, printed["plate_left"], printed["plate_right"], printed["frame_left"], printed["frame_right"], socket])

print("4b. negative controls (wrong direction must collide, or the sweep test is blind)")
for lab, m, d, f in (("plate pushed 6 mm against its normal", printed["plate_left"], -nL * 6, case),
                     ("wiring pushed 8 mm against the plate normal", split_side(sw_all, -1), -nL * 8, case),
                     ("cover pushed 2 mm down", printed["cover"], -up_P * 2, case),
                     ("carrier pushed 2 mm down", socket, -up_P * 2, case)):
    mv = m.copy()
    mv.apply_translation(d)
    v, u = collide(mv, f)
    ok(v > 0.05, f"{lab}: {v:.2f} {u} detected")

print("5. tool access (2.5 mm hex key, 40 mm straight path)")


def key_path(p0, direction, length=40.0, r=1.3):
    c = trimesh.creation.cylinder(radius=r, segment=[p0, p0 + direction * length], sections=16)
    return c


bad = 0
for x, y in G.LAYOUT.screws + G.LAYOUT.posts:
    for side in (-1, 1):
        shelf = PR.SHELF_T if (x, y) in G.LAYOUT.screws else PR.POST_SHELF_T
        zk = -PR.UNDER_PLATE - shelf - 2.0
        p = G.apply(G.M_LW, (x, y, zk))
        if side == 1:
            p = p * np.array([-1, 1, 1])
        n = nL if side == -1 else nR
        if vol_inter(key_path(p, -n), case) > 0.01:
            bad += 1
ok(bad == 0, f"sandwich and plate-post screws reachable from below ({bad} blocked)")
bad = 0
for x, y in PT.Stack.carrier_holes:
    p = G.apply(G.M_PW, (x, y, PT.Stack.carrier_top + 1.5))
    if vol_inter(key_path(p, up_P), case) > 0.01:
        bad += 1
ok(bad == 0, f"Pico carrier screws reachable from above with the cover off ({bad} blocked)")
if PR.CONTROLLER == "rev2":     # standoffs are tightened with a slim 5.5 mm nut driver before the halves go in
    bad = 0
    for x, y in PT.Stack.standoffs:
        p = G.apply(G.M_PW, (x, y, PT.Stack.board_top + 0.5))
        if vol_inter(key_path(p, up_P, length=60.0, r=4.0), case) > 0.01:
            bad += 1
    ok(bad == 0, f"controller standoffs reachable with a slim 5.5 mm nut driver, 8 mm OD ({bad} blocked)")

print("6. overhangs in print orientation (> 45 deg, off the bed)")
for f in sorted(os.listdir(os.path.join(OUT, "print"))):
    m = L("print", f)
    n_, c_ = m.face_normals, m.triangles_center
    sel = (n_[:, 2] < -np.cos(np.radians(45)) - 1e-6) & (c_[:, 2] > 0.3)
    worst = 0.0
    if sel.any():
        for p in m.submesh([np.where(sel)[0]], append=True).split(only_watertight=False):
            if p.area > 2:
                worst = max(worst, sorted(p.extents[:2])[0])
    ok(worst <= 11.0, f"{f}: widest unsupported span {worst:.1f} mm")

print("7. bed fit")
for f in sorted(os.listdir(os.path.join(OUT, "print"))):
    e = L("print", f).extents
    fits = (e[0] <= PR.BED_X - 2 * PR.BED_MARGIN and e[1] <= PR.BED_Y - 2 * PR.BED_MARGIN)
    ok(fits, f"{f}: {e[0]:.0f} x {e[1]:.0f} mm on a {PR.BED_X:.0f} x {PR.BED_Y:.0f} bed")

print("\n" + ("ALL CHECKS PASSED" if not FAIL else f"{len(FAIL)} CHECK(S) FAILED"))
sys.exit(1 if FAIL else 0)
