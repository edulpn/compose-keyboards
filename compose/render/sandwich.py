"""
Standard renders:  python3 -m compose render [outdir]     (after `build` and `model`)

Needs node + playwright (NODE_PATH pointing at a node_modules with playwright,
or playwright installed in compose/render/web/). Images go to outdir/png/.
Explode offsets follow the real install directions (plate normal, bridge up).
"""
import os
import sys
import json
import shutil
import socket
import subprocess
import urllib.parse
import numpy as np
from compose import geom as G
from compose import params as PR

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
HERE = os.path.dirname(os.path.abspath(__file__))
RD = os.path.join(OUT, "render")
PNG = os.path.join(OUT, "png")

ELECTRONICS = ["pcb", "gold", "hole", "chip", "silver", "button", "buttoncap", "led", "inductor", "passive", "silk",
               "perf", "perfpad", "perfhole", "header", "headerm", "ctail", "pinsm", "csolder", "cscrew", "cscrewhex"]
WIRING = ["copper", "lead_col", "lead_row", "stub_row", "stub_col", "kapton", "diode", "band", "solder", "leg", "pins"]
SWITCHES = ["switch", "stem"]
CAPS = ["keycap", "keycap2"]
COVER = ["cover", "coverscrew", "coverhex", "foam"]


def q(cam, la, up=None, fov=None, hide=(), show=None, explode=None, clip=None, bg=None):
    d = {"cam": json.dumps(cam), "la": json.dumps(la), "man": "manifest.json"}
    if up: d["up"] = json.dumps(up)
    if fov: d["fov"] = str(fov)
    if hide: d["hide"] = ",".join(hide)
    if show: d["show"] = ",".join(show)
    if explode: d["explode"] = json.dumps(explode)
    if clip: d["clip"] = json.dumps(clip)
    if bg: d["bg"] = str(bg)
    return urllib.parse.urlencode(d)


def install_explode(d_plate=40.0, d_frame=80.0, d_cover=110.0, d_caps=120.0):
    """Offsets along the install directions. The render mesh holds both halves
    in one part, so x (which flips sign between halves) is dropped: the halves
    differ only in that, and only by a few degrees."""
    n = G.plate_normal_world(-1)
    up = G.up_P_world()
    v = lambda vec, d: [0.0, float(vec[1] * d), float(vec[2] * d)]
    ex = {}
    for p in ["plate"] + SWITCHES + WIRING:
        ex[p] = v(n, d_plate)
    ex["bezel"] = v(n, d_frame)
    for p in CAPS:
        ex[p] = v(n, d_caps)
    for p in COVER:
        ex[p] = v(up, d_cover)
    return ex


C = [0, -62, 12]                                   # middle of the board
VIEWS = [
    ("01_hero", q([-250, -360, 270], C)),
    ("02_top", q([0, -62, 640], [0, -62, 0], up=[0, 1, 0])),
    ("03_back", q([-160, 420, 170], [0, -60, 15])),
    ("04_side", q([-480, -80, 60], [0, -62, 18])),
    ("05_no_caps", q([-250, -360, 270], C, hide=CAPS)),
    ("06_wiring_case_hidden", q([-120, -260, -330], [0, -62, 25], hide=["case"] + COVER + CAPS)),
    ("07_pico_cover_off", q([-70, 90, 150], [0, -28, 28], fov=22, hide=COVER)),
    ("08_pico_section", q([-230, -60, 60], [0, -50, 25], fov=20, clip=[1, 0, 0, 0], hide=CAPS)),
    ("09_case_only", q([-230, -330, 300], C, show=["case"])),
    ("10_floor_lattice", q([0, -70, 470], [0, -62, 0], up=[0, 1, 0], show=["case"])),
    ("11_frames_and_cover", q([-230, -330, 300], C, show=["bezel", "cover", "case", "plate"])),
    ("12_lip_front_junction", q([-110, -230, 70], [-25, -64, 26], fov=16, show=["case", "plate", "bezel", "cover"])),
    ("13_lip_back_junction", q([-110, 170, 75], [-22, 12, 32], fov=16, show=["case", "plate", "bezel", "cover"])),
    ("15_exploded_install", q([-330, -420, 330], [0, -40, 60], explode=install_explode())),
    ("17_pcbs_case_hidden", q([-150, -330, 260], [0, -55, 15], show=["hpcb", "hsocket", "diode", "band", "leg", "hconn", "solder",
                              "cpcb", "cconn", "plug", "cable", "header", "headerm", "pcb", "chip", "silver", "gold", "button",
                              "buttoncap", "passive", "inductor", "led", "pinsm", "ctail"])),
    ("18_cables_from_below", q([-60, -160, -120], [0, -30, 20], fov=24, show=["hpcb", "hsocket", "diode", "hconn", "cpcb", "cconn",
                               "plug", "cable", "header", "headerm", "pcb", "ctail", "pinsm"])),
    ("19_board_holes_top", q([-95, -95, 150], [-75, -40, 22], fov=22, show=["hpcb", "hsocket", "diode", "band", "leg"])),
    ("20_board_switches_below", q([-60, -120, -60], [-80, -45, 20], fov=22, show=["hpcb", "hsocket", "diode", "band", "leg", "swlegs", "pins"])),
    ("21_caps_closeup", q([-200, -235, 120], [-85, -55, 24], fov=30)),
    ("22_thumbs_low", q([-40, -260, 60], [-40, -85, 24], fov=26)),
    ("23_row_profile", q([-270, -45, 30], [-110, -42, 24], fov=20)),
    ("16_insert_plate", q([-250, -360, 270], [0, -50, 30], hide=["bezel"] + COVER + CAPS,
                          explode=install_explode(d_plate=25, d_frame=60, d_cover=90, d_caps=90))),
]


SECTIONS = [
    # name, plane origin, plane normal, (u-range), (z-range), title
    ("30_section_outer_wall", (0, -60, 0), (0, 1, 0), (-172, -128), (0, 46), "Left half, outer wall (world y = -60): lip in reveal"),
    ("31_section_bridge_interface", (0, -30, 0), (0, 1, 0), (-60, 60), (0, 46), "Across the bridge (world y = -30): plates, frames, cover"),
    ("32_section_bridge_detail", (0, -30, 0), (0, 1, 0), (-40, -10), (20, 46), "Left interface plane detail (world y = -30)"),
]
COLORS = {"hpcb": "#1f7a3f", "case": "#3a3f8f", "plate_left": "#a9acd0", "plate_right": "#a9acd0", "frame_left": "#5a60b8",
          "frame_right": "#5a60b8", "cover": "#7a2f8f", "screw": "#444444"}


def sections():
    """True cross-sections of the printed parts (2D, to scale)."""
    import trimesh
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPoly
    meshes = {n: trimesh.load(os.path.join(OUT, "world", n + ".stl")) for n in COLORS if n in ("case", "plate_left", "plate_right", "frame_left", "frame_right", "cover")}
    for hn in ("hpcb", "screw"):
        if os.path.exists(os.path.join(RD, f"a_{hn}.stl")):
            meshes[hn] = trimesh.load(os.path.join(RD, f"a_{hn}.stl"))
    # an extra section straight through the front-outer M3 sandwich screw of the left half
    sx, sy = G.LAYOUT.screws[3]
    w = G.apply(G.M_LW, (sx, sy, 0.0))
    extra = [("33_section_m3_sandwich", (0, w[1], 0), (0, 1, 0), (w[0] - 12, w[0] + 12), (0, 30),
              "Through an M3 sandwich screw: case boss / PCB / plate / frame insert")]
    for name, o, n, ur, zr, title in SECTIONS + extra:
        fig, ax = plt.subplots(figsize=(12, 12 * (zr[1] - zr[0]) / (ur[1] - ur[0]) + 0.8), dpi=130)
        for pn, m in meshes.items():
            sec = m.section(plane_origin=o, plane_normal=n)
            if sec is None:
                continue
            for ent in sec.discrete:
                pts = np.asarray(ent)
                ax.add_patch(MPoly(np.c_[pts[:, 0], pts[:, 2]], closed=True, fc=COLORS[pn], ec="k", lw=0.4, alpha=0.9))
        ax.set_xlim(*ur); ax.set_ylim(*zr); ax.set_aspect("equal")
        ax.set_xlabel("world x (mm)"); ax.set_ylabel("world z (mm)"); ax.set_title(title)
        ax.grid(alpha=0.25)
        lg = [("#3a3f8f", "case"), ("#a9acd0", "plate"), ("#5a60b8", "frame"), ("#7a2f8f", "cover"), ("#1f7a3f", "PCB")]
        handles = [plt.Rectangle((0, 0), 1, 1, fc=c) for c, _ in lg]
        ax.legend(handles, [t for _, t in lg], loc="upper right")
        if name[:2] in ("33", "34"):
            # screw: from under the case boss, through the board and plate, into the frame insert
            import matplotlib.patches as mp
            top = G.apply(G.M_LW, (sx, sy, PR.PLATE_T + 2.0))
            n_ = G.plate_normal_world(-1)
            from compose.case import build as _B
            L_ = float(_B.pick_length(*(lambda b: (b + PR.UNDER_PLATE + PR.PLATE_T + 2.5, b + PR.UNDER_PLATE + PR.PLATE_T + PR.M3_INSERT_L - 0.5))(
                PR.SHELF_T)))
            base = G.apply(G.M_LW, (sx, sy, -PR.UNDER_PLATE - PR.SHELF_T))
            tip = base + n_ * L_
            ax.plot([base[0], tip[0]], [base[2], tip[2]], color="#888888", lw=9 if name.startswith("33") else 26,
                    solid_capstyle="butt", alpha=0.55, zorder=5)
            if name.startswith("33"):
                ax.annotate(f"M3 x {int(L_)}", (tip[0], tip[2]), xytext=(tip[0] + 3, tip[2] + 4), arrowprops=dict(arrowstyle="->"))
        fig.tight_layout(); fig.savefig(os.path.join(PNG, name + ".png")); plt.close(fig)
        print("section", name)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def board_previews():
    """Realistic board images from the fab Gerbers (black mask, white silk, HASL copper):
    pcb-stackup renders SVG, Chromium rasterises it. Needs node with pcb-stackup + playwright."""
    pcb = os.path.join(OUT, "pcb")
    for name in ("half_hotswap", "half_solder", "controller"):
        g = os.path.join(pcb, name + "_gerbers")
        if not os.path.isdir(g):
            continue
        pref = os.path.join(PNG, "board_" + name)
        r = subprocess.run(["node", os.path.join(HERE, "web", "board_preview.js"), g, pref], capture_output=True, text=True)
        if r.returncode:
            print("board preview skipped:", r.stderr.strip()[-200:])
            return
        for side in ("top", "bottom"):
            subprocess.run(["node", os.path.join(HERE, "web", "svg2png.js"), f"{pref}_{side}.svg", f"{pref}_{side}.png", "1400"], check=True)
            os.remove(f"{pref}_{side}.svg")
        print("board preview", name)


def main(only=None):
    os.makedirs(PNG, exist_ok=True)
    sections()
    board_previews()
    for f in ("view.html", "three.module.js", "STLLoader.js", "BufferGeometryUtils.js"):
        shutil.copy(os.path.join(HERE, "web", f), RD)
    port = free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=RD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import time
        time.sleep(1.0)
        views = [v for v in VIEWS if not only or any(o in v[0] for o in only)]
        subprocess.run(["node", os.path.join(HERE, "web", "shoot.js"), f"http://127.0.0.1:{port}",
                        os.path.abspath(PNG), json.dumps(views)], check=True)
    finally:
        srv.terminate()


if __name__ == "__main__":
    main(sys.argv[2:] or None)
