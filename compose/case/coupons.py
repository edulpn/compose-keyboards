"""
Test coupons: matching chunks of the real case, plate, frame and a 1.6 mm dummy PCB, cut from the
left half so they bolt together like the board does.

    python3 -m compose coupons [out]

The chunk covers the outer wall (trim lip + reveal), one perimeter M3 sandwich point, one middle M2
post and six whole switch cutouts (Tab Q W / Ctrl A S). Its edges follow the key grid, so they fall
in the gaps between switch cutouts.
"""
import os
import sys
import cadquery as cq
import numpy as np
import trimesh
from shapely.geometry import box as sbox
from shapely.ops import unary_union
from compose import params as PR
from compose import geom as G
from compose.case import sandwich as PT

TOL = dict(tolerance=0.01, angularTolerance=0.1)
KEYS = ("Tab", "Q", "W", "Ctrl", "A", "S")


def region_local():
    L = G.LAYOUT
    ks = [k for k in L.keys if k.label_l in KEYS]
    assert len(ks) == len(KEYS), [k.label_l for k in ks]
    P = PR.KEY_PITCH
    cells = [sbox(k.x - P / 2, k.y - P / 2, k.x + P / 2, k.y + P / 2) for k in ks]
    col0 = [k for k in ks if k.col == 0]
    y0, y1 = min(k.y for k in col0) - P / 2, max(k.y for k in col0) + P / 2
    x_left = min(k.x for k in col0) - P / 2
    edge = sbox(G.OUTLINE.bounds[0] - 5, y0, x_left, y1)             # out to (and past) the outer edge
    reg = unary_union(cells + [edge]).intersection(G.OUTLINE.buffer(0.01))
    # the chunk must hold one sandwich screw and one middle post
    from shapely.geometry import Point
    scr = [s for s in L.screws if reg.contains(Point(s).buffer(PR.BOSS_R))]
    pst = [p for p in L.posts if reg.contains(Point(p).buffer(PR.POST_R))]
    return reg, scr, pst


def main(out="out"):
    d = os.path.join(out, "coupons")
    os.makedirs(d, exist_ok=True)
    reg, scr, pst = region_local()
    print(f"coupon region {reg.bounds}, screws {scr}, posts {pst}")
    assert scr and pst, "coupon region must contain a sandwich screw and a middle post"
    cut_l = PT.poly_prism(reg, -80.0, 80.0)
    mount = "rigid"

    # case: world orientation (floor down), moved next to the origin
    case_c = PT.case_world().intersect(G.L2W(cut_l))
    bb = case_c.BoundingBox()
    case_c = case_c.translate(cq.Vector(-bb.xmin, -bb.ymin, 0))
    outs = {f"coupon_case_{mount}.stl": case_c}

    if not os.path.exists(os.path.join(d, "coupon_plate.stl")):
        plate_c = PT.plate_local().intersect(cut_l)
        plate_c = plate_c.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 180).translate(cq.Vector(0, 0, PR.PLATE_T))
        frame_c = PT.bezel_local().intersect(cut_l).translate(cq.Vector(0, 0, -PR.PLATE_T))
        for nm, s in (("coupon_plate.stl", plate_c), ("coupon_frame.stl", frame_c)):
            b = s.BoundingBox()
            outs[nm] = s.translate(cq.Vector(-b.xmin, -b.ymin, 0))

    for nm, s in outs.items():
        n = len(s.Solids()) if hasattr(s, "Solids") else 1
        cq.exporters.export(s, os.path.join(d, nm), **TOL)
        b = s.BoundingBox()
        print(f"{nm}: {b.xlen:.1f} x {b.ylen:.1f} x {b.zlen:.1f} mm, {n} solid(s)")

    # dummy PCB (1.6 mm): the routed board outline and every hole, from the render model, flat
    hp = os.path.join(out, "render", "a_hpcb.stl")
    if os.path.exists(hp):
        m = trimesh.load(hp)
        left = trimesh.util.concatenate([p for p in m.split(only_watertight=False) if p.centroid[0] < 0])
        left.apply_transform(np.linalg.inv(G.M_LW))                    # back to half-local coordinates
        pts = np.array(reg.exterior.coords)
        cutter = trimesh.creation.extrude_polygon(reg, 10.0)
        cutter.apply_translation([0, 0, -5.0])
        pcb_c = trimesh.boolean.intersection([left, cutter], engine="manifold")
        pcb_c.apply_translation(-pcb_c.bounds[0])
        pcb_c.export(os.path.join(d, "coupon_pcb_dummy.stl"))
        print(f"coupon_pcb_dummy.stl: {pcb_c.extents.round(1).tolist()} mm, watertight {pcb_c.is_watertight}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
