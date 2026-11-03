"""
Rev 2 renders:  C58_REV=2 python3 -m compose gasket-render OUTDIR    (needs node + playwright, like `render`)

Exports the rev 2 assembly (case, plates, frames, cover, gasket pads, controller with its part envelopes,
half-board proxies, placeholder switches and keycaps) as STLs + a manifest for compose/render/web/view.html, then
shoots the standard views into OUTDIR/png/.
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
from compose.geom import prism, union

OUT = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
HERE = os.path.dirname(os.path.abspath(__file__))
RD = os.path.join(OUT, "render2")
PNG = os.path.join(OUT, "png")
CT = C.CT
L = G.LAYOUT

COL = dict(case=(0x3a3f4b, 0.7), frame=(0x3a3f4b, 0.6), cover=(0x3a3f4b, 0.6), plate=(0x8c9bb0, 0.5),
           pads=(0xd8d2c4, 0.95), halfpcb=(0x1f6b45, 0.6), cpcb=(0x1f7a4d, 0.55), pico=(0x2a8c4a, 0.6),
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


def build():
    os.makedirs(RD, exist_ok=True)
    man = []

    def add(name, path, smooth=False):
        c, r = COL[name]
        man.append(dict(file=os.path.basename(path), color=c, metal=0.0 if name != "standoff" else 0.8,
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
    add("pico", stl(cs["pico"], "pico"))
    add("top", stl(cs["top parts"], "top"))
    add("bottom", stl(cs["bottom parts"], "bottom"))
    add("standoff", stl(cs["standoffs"], "standoff"))
    for nm, m in keys_mesh().items():
        p = os.path.join(RD, f"r_{nm}.stl")
        m.export(p)
        add(nm, p)
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
                  ("halfpcb", 22)):
        ex[nm] = [0, float(n[1] * d), float(n[2] * d)]
    ex["frame"] = [0, float(n[1] * 45), float(n[2] * 45)]
    ymid = (CT.y_pc - 0)
    P = lambda x, y, z: list(G.apply(G.M_PW, (x, y, z)))
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
                                         show=["cpcb", "pico", "top", "bottom", "standoff"])),
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
