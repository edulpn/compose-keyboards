"""Rev 2 assembly section views (matplotlib): C58_REV=2 python3 -m compose gasket-sections OUTDIR."""
import os, sys
import numpy as np
import cadquery as cq
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from compose import params as PR
from compose import geom as G
from compose.case import gasket as C
from compose.controller import rev2_std as CS
from compose.geom import prism, cyl, union, big_box

OUT = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
os.makedirs(OUT, exist_ok=True)
CT = C.CT


def mesh(shape):
    p = os.path.join(OUT, "_tmp.stl")
    cq.exporters.export(cq.Workplane().add(shape), p, tolerance=0.03, angularTolerance=0.15)
    return trimesh.load(p)


def assembly():
    parts = {}
    parts["case"] = (C.case2_world(), "#b9b2a6")
    from compose import pointer as PTR
    if not C.sided():
        pl = G.L2W(C.plate2_local()); pl = pl.fuse(pl.mirror("YZ"))
        fr = G.L2W(C.frame2_local()); fr = fr.fuse(fr.mirror("YZ"))
    else:                                                  # a device or a one-sided bay: each side as built
        pl = G.L2W(C.plate2_local("L")).fuse(G.R2W(C.plate2_local("R")))
        fr = G.L2W(C.frame2_local("L")).fuse(G.R2W(C.frame2_local("R")))
    parts["plate"] = (pl, "#7a8fa6")
    parts["frame"] = (fr, "#55606e")
    parts["cover"] = (G.P2W(C.cover2_P()), "#3d4652")
    hp = G.OUTLINE.buffer(-PR.PCB_INSET)
    h = G.L2W(prism(list(hp.exterior.coords)[:-1], -PR.PCB_T, 0.0))
    parts["half pcb"] = (h.fuse(h.mirror("YZ")), "#2f7d4f")
    b = prism(list(CT.outline_P.exterior.coords)[:-1], CT.board_bot, CT.board_top)
    parts["ctrl pcb"] = (G.P2W(b), "#1f9e5a")
    pico = big_box(-PR.PICO_W / 2, PR.PICO_W / 2, CT.y_pc - PR.PICO_L / 2, CT.y_pc + PR.PICO_L / 2, CT.pico_bot, CT.pico_top)
    sock = union([big_box(sx * CS.PICO_X - 1.25, sx * CS.PICO_X + 1.25, CT.y_pc - 25.4, CT.y_pc + 25.4,
                          CT.board_top, CT.pico_bot) for sx in (-1, 1)])
    parts["pico"] = (G.P2W(pico.fuse(sock)), "#c9a227")
    so = union([cyl(x, y, CS.STANDOFF_AF / 2 / np.cos(np.pi / 6), CT.board_top, CT.board_top + CS.STANDOFF_L) for x, y in CT.mounts])
    parts["standoff"] = (G.P2W(so), "#d0d0d0")
    return parts


def section(parts, origin, normal, axes, title, fn, lim):
    fig, ax = plt.subplots(figsize=(12, 6), dpi=130)
    for name, (m, col) in parts.items():
        s = m.section(plane_origin=origin, plane_normal=normal)
        if s is None:
            continue
        for e in s.discrete:
            pts = np.asarray(e)
            ax.fill(pts[:, axes[0]], pts[:, axes[1]], color=col, alpha=0.85, lw=0.4, ec="k")
        ax.plot([], [], color=col, lw=6, label=name)
    ax.set_aspect("equal"); ax.set_title(title); ax.grid(alpha=0.3)
    ax.set_xlim(*lim[0]); ax.set_ylim(*lim[1])
    ax.legend(loc="upper left", fontsize=7, ncol=3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, fn)); plt.close(fig)


if __name__ == "__main__":
    parts = {k: (mesh(v), c) for k, (v, c) in assembly().items()}
    for k, (m, c) in parts.items():
        m.export(os.path.join(OUT, f"asm_{k.replace(' ', '_')}.stl"))
    def P(x, y, z=0):
        return G.apply(G.M_PW, (x, y, z))
    o = np.array(P(0, 0)); ex = np.array(P(1, 0)) - o; ey = np.array(P(0, 1)) - o
    # x-z cuts across the middle (normal = P y axis)
    for y in (-8.0, -20.0, -29.0, -48.5, -53.5):
        org = P(0, y, 0)
        section(parts, org, ey, (0, 2), f"cut across the middle at P y = {y}", f"sec_y{abs(y):.0f}.png",
                ((-60, 60), (-2, 55)))
    # y-z cuts along the middle (normal = P x axis)
    for x in (0.0, 13.0, 17.75, 20.0):
        org = P(x, 0, 0)
        section(parts, org, ex, (1, 2), f"cut along the middle at P x = {x}", f"sec_x{x:.0f}.png",
                ((-70, 8), (-2, 55)))
    print("ok")
