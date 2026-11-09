"""
Rev 2 renders:  C58_REV=2 python3 -m compose gasket-render OUTDIR    (needs node + playwright, like `render`)

Exports the rev 2 assembly as STLs + a manifest for compose/render/web/view.html, then shoots the standard views
into OUTDIR/png/: case, plates, frames, cover, gasket pads, the controller with its parts, placeholder switches and
keycaps, and, for the assembly views, the half boards and the controller wearing their own Gerber renders
(board_preview.js; each texture's placement checked against the board's drill holes and pads), the parts of one
build (hotswap + RGB) and both flex jumpers in the shape flex-sim settles them into.
Needs the routed boards (half-rev2 in OUTDIR, controller in CTRL_OUT, default out).
"""
import os
import sys
import json
import math
import shutil
import subprocess
import numpy as np
import cadquery as cq
import trimesh
from compose import params as PR
from compose import geom as G
from compose.case import gasket as C
from compose.controller import rev2_std as CS
from compose.checks import gasket as K
from compose.geom import prism, union, poly_prism

OUT = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
HERE = os.path.dirname(os.path.abspath(__file__))
RD = os.path.join(OUT, "render2")
PNG = os.path.join(OUT, "png")
CT = C.CT
L = G.LAYOUT

CTRL_OUT = os.environ.get("CTRL_OUT", "out")
BUILD = "half_rev2_hotswap_rgb"            # the half board shown in the assembly views
METAL = ("standoff", "hhead", "hmetal", "cmetal", "cusb", "cpin")
COL = dict(jumper=(0xc98a2b, 0.45), hsock=(0x1a1a1a, 0.55), hdiode=(0xd2662e, 0.25), hband=(0x101010, 0.4),
           hled=(0xf4f4f0, 0.45), hcap=(0xb89b6c, 0.6), hffc=(0x2c2c2c, 0.55), hact=(0xcdb98d, 0.5),
           hhead=(0x9a9aa0, 0.3), hmetal=(0xcfcfc8, 0.3), cffc=(0x2c2c2c, 0.55), cslide=(0xd6ccb4, 0.5),
           cmetal=(0xcfcfc8, 0.3), cpico=(0x2e8b47, 0.6), cchip=(0x141414, 0.5), cusb=(0xc8c8cc, 0.25),
           chdr=(0x161616, 0.6), cpin=(0xd4af37, 0.25), cjst=(0xe8dfca, 0.55), cdip=(0x34343a, 0.3),
           cres=(0x7ea6cf, 0.45), ccer=(0xd99a2e, 0.45), celec=(0x22232a, 0.4), cfuse=(0xe3b52a, 0.5),
           case=(0x3a3f4b, 0.7), frame=(0x3a3f4b, 0.6), cover=(0x3a3f4b, 0.6), plate=(0x8c9bb0, 0.5),
           pads=(0xd8d2c4, 0.95), halfpcb=(0x2a2a22, 0.6), cpcb=(0x2a2a22, 0.55), pico=(0x2a8c4a, 0.6),
           sockets=(0x1b1b1b, 0.6), top=(0x2b2b2b, 0.6), bottom=(0x9a7b4f, 0.6), standoff=(0xc9a54a, 0.35),
           switch=(0x26262b, 0.6), keycap=(0xe8e4da, 0.75), keycap2=(0x7a8aa0, 0.75))


def stl(shape, name, tol=0.05):
    p = os.path.join(RD, f"r_{name}.stl")
    cq.exporters.export(cq.Workplane().add(shape), p, tolerance=tol, angularTolerance=0.2)
    return p


def keys_mesh():
    """Placeholder MX housings and keycaps on both halves (world)."""
    sw, caps, caps2 = [], [], []
    TH = PR.PLATE_T
    for k in L.keys:
        R = trimesh.transformations.rotation_matrix(math.radians(k.rot), [0, 0, 1])
        Tm = trimesh.transformations.translation_matrix([k.x, k.y, 0])
        hb = trimesh.creation.box([15.6, 15.6, 5.8])
        hb.apply_translation([0, 0, TH + 2.9])
        cap = trimesh.creation.cylinder(radius=1, height=1)       # placeholder, replaced below
        b0 = np.array([[-9.0, -9.0], [9.0, -9.0], [9.0, 9.0], [-9.0, 9.0]])
        t0 = np.array([[-6.3, -7.3], [6.3, -7.3], [6.3, 5.3], [-6.3, 5.3]])
        z0, z1 = TH + 6.6, TH + 14.0
        v = np.vstack([np.c_[b0, np.full(4, z0)], np.c_[t0, np.full(4, z1)]])
        f = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
             [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
        cap = trimesh.Trimesh(v, f)
        for m in (hb, cap):
            m.apply_transform(Tm @ R)
        sw.append(hb)
        (caps2 if getattr(k, "thumb", False) or k.y < -80 else caps).append(cap)
    out = {}
    for nm, ms in (("switch", sw), ("keycap", caps), ("keycap2", caps2)):
        if not ms:
            continue
        m = trimesh.util.concatenate(ms)
        m.apply_transform(G.M_LW)
        mr = m.copy()
        mr.apply_transform(np.diag([-1, 1, 1, 1]))
        mr.invert()
        out[nm] = trimesh.util.concatenate([m, mr])
    return out


# ---------------------------------------------------------------- board textures (decals)
def _svg_map(svg_path):
    """(viewBox, svg->board function) for a board_preview.js SVG. pcb-stackup draws Gerber coordinates in um;
    KiCad's Gerbers are its board coordinates with y flipped. Top view: svg = (x, -y_g - Ty); bottom view, mirrored
    as seen from below: svg = (Tx - x, -y_g - Ty)."""
    import re
    t = open(svg_path).read(4000)
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', t).group(1).split()]
    full = open(svg_path).read()
    ty = float(re.search(r'translate\(0,(-?[\d.]+)\) scale\(1,-1\)', full).group(1))
    m = re.search(r'translate\((-?[\d.]+),0\) scale\(-1,1\)', full)
    tx = float(m.group(1)) if m else None
    to_board = (lambda u, v: ((tx - u) / 1000.0 if tx is not None else u / 1000.0, (v - ty) / 1000.0))
    to_svg = (lambda X, Y: ((tx - X * 1000.0) if tx is not None else X * 1000.0, Y * 1000.0 + ty))
    return vb, to_board, to_svg


def board_decal(gerbers, board_path, face, name, to_world, z, ppm=12.0):
    """Rasterise one face of a routed board (face 'top' = F, 'bottom' = B) and place it: to_world maps (KiCad X, Y,
    z) to world. The placement is checked on the board itself: every drill hole of 1 mm or more must come out
    transparent and every SMD pad on that face opaque, else it raises (a mirrored or shifted texture can't pass)."""
    import pcbnew
    from PIL import Image
    pre = os.path.join(RD, f"tex_{name}")
    if not os.path.exists(pre + f"_{face}.svg"):
        subprocess.run(["node", os.path.join(HERE, "web", "board_preview.js"), gerbers, pre], check=True,
                       env=_node_env(), capture_output=True)
    svg = pre + f"_{face}.svg"
    png = os.path.join(RD, f"tex_{name}_{face}.png")
    subprocess.run(["node", os.path.join(HERE, "web", "svg2tex.js"), svg, png, str(ppm / 1000.0)], check=True,
                   env=_node_env(), capture_output=True)
    vb, to_board, to_svg = _svg_map(svg)
    im = Image.open(png).convert("RGBA")
    # opaque inside the board: pcb-stackup leaves parts of the copper and mask partly transparent, which would let
    # the board slab under the decal show through. Composite those over the laminate; holes and outside stay clear
    a_ = np.asarray(im).astype(float)
    al = a_[..., 3:4] / 255.0
    base = np.array([0x3a, 0x33, 0x24], float)
    rgb = a_[..., :3] * al + base * (1 - al)
    im = Image.fromarray(np.dstack([rgb, np.where(al[..., 0] >= 0.5, 255, 0)]).astype(np.uint8), "RGBA")
    im.save(png)
    W_, H_ = im.size
    px = lambda X, Y: ((to_svg(X, Y)[0] - vb[0]) / vb[2] * W_, (to_svg(X, Y)[1] - vb[1]) / vb[3] * H_)
    alpha = lambda X, Y: im.getpixel((min(W_ - 1, max(0, int(px(X, Y)[0]))), min(H_ - 1, max(0, int(px(X, Y)[1])))))[3]
    b = pcbnew.LoadBoard(board_path)
    mm = pcbnew.ToMM
    lay = pcbnew.F_Cu if face == "top" else pcbnew.B_Cu
    holes, pads = [], []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            X, Y = mm(p.GetPosition().x), mm(p.GetPosition().y)
            if p.GetDrillSize().x and mm(p.GetDrillSize().x) >= 1.0:
                holes.append((X, Y))
            elif p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and p.IsOnLayer(lay) and min(mm(p.GetSize().x), mm(p.GetSize().y)) >= 0.4:
                pads.append((X, Y))
    h_ok = sum(alpha(X, Y) < 128 for X, Y in holes)
    p_ok = sum(alpha(X, Y) >= 128 for X, Y in pads)
    print(f"  texture {name} {face}: {h_ok}/{len(holes)} holes clear, {p_ok}/{len(pads)} pads on copper", flush=True)
    if h_ok < 0.97 * len(holes) or p_ok < 0.97 * len(pads):
        raise RuntimeError(f"texture {name} {face} doesn't line up with the board")
    corners = [list(map(float, to_world(*to_board(u, v), z))) for u, v in
               ((vb[0], vb[1]), (vb[0] + vb[2], vb[1]), (vb[0], vb[1] + vb[3]))]
    return dict(decal=os.path.basename(png), corners=corners)


def _node_env():
    env = dict(os.environ)
    env.setdefault("NODE_PATH", os.path.join(HERE, "web", "node_modules"))
    return env


def build():
    os.makedirs(RD, exist_ok=True)
    man = []

    def add(name, path, smooth=False):
        c, r = COL[name]
        man.append(dict(file=os.path.basename(path), color=c, metal=0.8 if name in METAL else 0.0,
                        rough=r, smooth=smooth, name=name))
    pair = K.mirror_pair
    add("case", stl(C.case2_world(), "case"))
    add("plate", stl(pair(C.plate2_local()), "plate"))
    add("frame", stl(pair(C.frame2_local()), "frame"))
    add("cover", stl(G.P2W(C.cover2_P()), "cover"))
    lo, up = K.pads_local()
    add("pads", stl(pair(union(lo + up)), "pads"))
    hp = G.OUTLINE.buffer(-PR.PCB_INSET)
    add("halfpcb", stl(pair(prism(list(hp.exterior.coords)[:-1], -PR.PCB_T, 0.0)), "halfpcb"))
    cs = {k: G.P2W(v) for k, v in K.controller_solids().items()}
    add("cpcb", stl(cs["ctrl board"], "cpcb"))
    cb_ = os.path.join(CTRL_OUT, "pcb", "controller_rev2.kicad_pcb")
    from compose.render import parts3d as P3
    for nm, sols in P3.controller_parts_P(cb_).items():     # the Pico and every other part, from the footprints
        add(nm, stl(G.P2W(cq.Compound.makeCompound(sols)), nm, tol=0.02), smooth=nm in ("cres", "ccer", "celec"))
    add("standoff", stl(cs["standoffs"], "standoff"))
    for nm, m in keys_mesh().items():
        p = os.path.join(RD, f"r_{nm}.stl")
        m.export(p)
        add(nm, p)
    # ---- the assembly views' extras: parts of one build, board textures, the jumpers as they settle
    from compose.render import parts3d as P3
    hb_ = os.path.join(OUT, "pcb", BUILD + ".kicad_pcb")
    for nm, sols in P3.half_local(hb_).items():
        add(nm, stl(pair(cq.Compound.makeCompound(sols)), nm, tol=0.02), smooth=nm in ("hdiode", "hband"))
    for nm, sols in P3.controller_P(os.path.join(CTRL_OUT, "pcb", "controller_rev2.kicad_pcb")).items():
        add(nm, stl(G.P2W(cq.Compound.makeCompound(sols)), nm, tol=0.02))
    from compose.checks import flex_sim as F
    from compose.pcb import jumper as J
    st = F.Strip(J.solve())
    zj, ok, _ = st.solve(F.initial(st))
    assert ok, "flex-sim: the jumper doesn't settle"
    jl = G.P2W(st.solid(zj))
    add("jumper", stl(cq.Compound.makeCompound([jl, jl.mirror("YZ")]), "jumper", tol=0.02), smooth=True)
    from compose.pcb import kicad as PK
    S = np.diag([-1.0, 1, 1, 1])
    hb = os.path.join(OUT, "pcb", BUILD + ".kicad_pcb")
    hg = os.path.join(OUT, "pcb", BUILD + "_gerbers")
    loc = lambda X, Y, z: (X - PK.OX, PK.OY - Y, z)
    left = lambda X, Y, z: G.apply(G.M_LW, loc(X, Y, z))
    right = lambda X, Y, z: G.apply(S @ G.M_LW, loc(X, Y, z))    # the same board flipped: faces swap, x mirrors
    e = 0.02
    for nm, face, fn, z in (("halftex_l_bot", "bottom", left, -PR.PCB_T - e), ("halftex_l_top", "top", left, e),
                            ("halftex_r_bot", "top", right, -PR.PCB_T - e), ("halftex_r_top", "bottom", right, e)):
        d = board_decal(hg, hb, face, "half", fn, z)
        man.append(dict(d, name=nm, rough=0.5))
    from compose.controller import rev2 as CR
    cb = os.path.join(CTRL_OUT, "pcb", "controller_rev2.kicad_pcb")
    cg = os.path.join(CTRL_OUT, "pcb", "controller_rev2_gerbers")
    ctrl = lambda X, Y, z: G.apply(G.M_PW, (X - CR.CX, CT.y_pc - (Y - CR.CY), z))
    for nm, face, z in (("ctex_top", "top", CT.board_top + e), ("ctex_bot", "bottom", CT.board_bot - e)):
        d = board_decal(cg, cb, face, "ctrl", ctrl, z, ppm=20.0)
        man.append(dict(d, name=nm, rough=0.5))
    json.dump(man, open(os.path.join(RD, "manifest.json"), "w"))
    for f in ("view.html", "three.module.js", "STLLoader.js", "BufferGeometryUtils.js"):
        shutil.copy(os.path.join(HERE, "web", f), RD)


def q(cam, la, up=None, fov=None, hide=(), show=None, explode=None, clip=None):
    import urllib.parse
    d = {"cam": json.dumps(cam), "la": json.dumps(la), "man": "manifest.json"}
    if up: d["up"] = json.dumps(up)
    if fov: d["fov"] = str(fov)
    if hide: d["hide"] = ",".join(hide)
    if show: d["show"] = ",".join(show)
    if explode: d["explode"] = json.dumps(explode)
    if clip: d["clip"] = json.dumps(clip)
    return urllib.parse.urlencode(d)


def views():
    Cn = [0, -60, 25]
    n = G.plate_normal_world(-1)
    upv = G.up_P_world()
    ex = {"cover": [0, float(upv[1] * 60), float(upv[2] * 60)], "standoff": [0, 0, 0]}
    for nm, d in (("frame", 45), ("pads", 0), ("plate", 22), ("switch", 22), ("keycap", 70), ("keycap2", 70),
                  ("halfpcb", 22), ("halftex_l_bot", 22), ("halftex_l_top", 22), ("halftex_r_bot", 22),
                  ("halftex_r_top", 22), ("hsock", 22), ("hdiode", 22), ("hband", 22), ("hled", 22), ("hcap", 22),
                  ("hffc", 22), ("hact", 22), ("hmetal", 22), ("hhead", 22)):
        ex[nm] = [0, float(n[1] * d), float(n[2] * d)]
    ex["frame"] = [0, float(n[1] * 45), float(n[2] * 45)]
    ymid = (CT.y_pc - 0)
    P = lambda x, y, z: list(G.apply(G.M_PW, (x, y, z)))
    jc = np.array(G.apply(G.M_PW, (-CS.VFFC_SLOT_X - 4.0, CT.y_pc - CS.VFFC_Y0, CT.board_top + 5.0)))  # left jumper
    from compose.pcb import rev2_half as H2
    fc = H2.plan().ffc.c
    hc = np.array(G.apply(G.M_LW, (fc[0] + 2.5, fc[1], -PR.PCB_T - 1.0)))      # the left half's 200528
    cc = np.array(G.apply(G.M_PW, (-CS.VFFC_SLOT_X, CT.y_pc - CS.VFFC_Y0, CT.board_top + 3.0)))  # left 52610
    cb = np.array(G.apply(G.M_PW, (0.0, CT.y_pc, CT.board_bot - 4.0)))            # the controller's underside
    halfb = ["halfpcb", "halftex_l_bot", "halftex_l_top", "halftex_r_bot", "halftex_r_top", "hsock", "hdiode",
             "hband", "hled", "hcap", "hffc", "hact", "hmetal", "hhead"]
    caps = ["keycap", "keycap2", "switch"]
    return [
        ("r2_01_hero", q([-250, -360, 270], Cn)),
        ("r2_02_top", q([0, -62, 640], [0, -62, 0], up=[0, 1, 0])),
        ("r2_03_back", q([-160, 420, 170], [0, -60, 15])),
        ("r2_04_no_caps", q([-250, -360, 270], Cn, hide=caps)),
        ("r2_05_middle_cover_off", q([-60, -170, 150], [0, -30, 30], fov=22, hide=["cover"] + caps)),
        ("r2_06_gasket_exploded", q([-300, -330, 260], Cn, hide=caps[:2], explode=ex)),
        ("r2_07_section_mid", q([-10, -320, 60], P(0, -30, 30), fov=18, clip=[0, 1, 0, 48.5], hide=caps)),
        ("r2_08_section_front_seat", q([-10, -320, 60], P(0, -53, 30), fov=18, clip=[0, 1, 0, 53.5], hide=caps)),
        ("r2_09_case_only", q([-230, -330, 300], Cn, show=["case"])),
        ("r2_10_controller_underside", q([-90, -140, -120], [0, -30, 22], fov=24,
                                         show=["cpcb", "standoff", "ctex_top", "ctex_bot", "cffc", "cslide", "cmetal",
                                               "cpico", "cchip", "cusb", "chdr", "cpin", "cjst", "cdip", "cres", "ccer",
                                               "celec", "cfuse"])),
        # assembly views: real board faces, the parts of one build, the jumpers as they settle
        ("r2_11_assembly_underside", q([-170, -330, -230], [0, -60, 20], fov=30,
                                       hide=["case", "cover", "frame", "pads"])),
        ("r2_12_jumper_bay", q(list(jc + np.array([-45.0, -95.0, 80.0])), list(jc), fov=22,
                               hide=["cover"] + caps)),
        ("r2_13_jumper_section", q(list(jc + np.array([-8.0, -230.0, 25.0])), list(jc), fov=12,
                                   clip=[0, 1, 0, -float(jc[1])], hide=["cover"] + caps)),
        ("r2_14_boards_plates_off", q([-200, -330, 300], [0, -60, 15], fov=28,
                                      hide=["cover", "plate", "frame", "pads"] + caps)),
        ("r2_15_half_connector", q(list(hc + np.array([-25.0, -55.0, -55.0])), list(hc), fov=24,
                                   hide=["case", "cover", "frame", "pads"] + caps)),
        ("r2_16_controller_connector", q(list(cc + np.array([-62.0, -38.0, 40.0])), list(cc), fov=22,
                                         hide=["cover", "case", "frame", "plate", "pads"] + caps + halfb)),
        ("r2_17_controller_bottom", q(list(cb + np.array([-40.0, -75.0, -70.0])), list(cb), fov=26,
                                      show=["cpcb", "standoff", "ctex_top", "ctex_bot", "cffc", "cslide", "cmetal",
                                            "cpico", "cchip", "cusb", "chdr", "cpin", "cjst", "cdip", "cres", "ccer",
                                            "celec", "cfuse"])),
    ]


def shoot():
    import socket
    os.makedirs(PNG, exist_ok=True)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=RD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import time
        time.sleep(1.0)
        env = dict(os.environ)
        env.setdefault("NODE_PATH", os.path.join(HERE, "web", "node_modules"))
        subprocess.run(["node", os.path.join(HERE, "web", "shoot.js"), f"http://127.0.0.1:{port}",
                        os.path.abspath(PNG), json.dumps(views())], check=True, env=env)
    finally:
        srv.terminate()


if __name__ == "__main__":
    if "--shoot-only" not in sys.argv:
        build()
    shoot()
