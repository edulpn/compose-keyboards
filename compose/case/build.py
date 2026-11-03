"""
Build everything:  python3 -m compose build [outdir]

Writes, into outdir (default ./out):
  print/   STLs in print orientation (plate: switch side down; frames and
           cover: underside down; case: floor down)
  step/    STEPs of each part in assembly position + assembly.step
  world/   world-position STLs (used by the checks and the renders)
  bom.txt  hardware list with screw lengths computed from params
"""
import os
import sys
import cadquery as cq
from compose import params as PR
from compose import geom as G
from compose.case import sandwich as PT

TOL = dict(tolerance=0.02, angularTolerance=0.15)


def pick_length(lo, hi):
    ok = [l for l in PR.STANDARD_SCREW_LENGTHS if lo <= l <= hi]
    return max(ok) if ok else None


def bom():
    L = G.LAYOUT
    n_keys = len(L.keys) * 2
    U = PR.UNDER_PLATE
    below = PR.SHELF_T                     # head -> board underside
    m3_sand = pick_length(below + U + PR.PLATE_T + 2.5, below + U + PR.PLATE_T + PR.M3_INSERT_L - 0.5)
    m3_cover = pick_length(PR.COVER_H + 2.5, PR.COVER_H + PR.M3_INSERT_L - 0.5)
    m2_post = pick_length(PR.POST_SHELF_T + U + 2.0, PR.POST_SHELF_T + U + PR.M2_PLATE_INSERT_L - 0.3)
    m2_carrier = pick_length(PR.PERF_T + 2.0, PR.PERF_T + PR.M2_INSERT_L - 0.5)
    ns, npost = len(L.screws) * 2, len(L.posts) * 2
    lines = [
        f"{PR.BOARD_NAME} ({PR.REVISION}) - {L.name} layout, {n_keys} keys",
        "",
        f"M3 x {m3_sand} button head   x {ns:>2}   plate sandwich (from below into the frames)",
        f"M3 x {m3_cover} button head   x  4   centre cover (from the top)",
        f"M3 heat-set insert          x {ns + 4:>2}   frames ({ns}) + cover pillars (4)",
        f"M2 x {m2_post} button head    x {npost:>2}   plate support posts (from below)",
        f"M2 x {m2_carrier} button head    x  4   {'controller board' if PR.MATRIX == 'pcb' else 'Pico carrier'}",
        f"M2 heat-set insert          x {npost + 4:>2}   plate undersides ({npost}) + carrier posts (4)",
        "",
        f"MX switches                 x {n_keys}",
        f"1N4148 diodes (through-hole) x {n_keys}",
        f"Keycaps                     x {n_keys}  (1.5u: {sum(1 for k in L.keys if k.h > 1.01) * 2})",
        "Raspberry Pi Pico (W) + 2x 20-pin male headers",
        f"Rubber bumpons {PR.FOOT_D - 0.5:.0f} mm  x {len(L.feet) * 2 + 2}",
        "Foam pad ~1 mm for the cover's clamp tab (optional)",
    ]
    if PR.MATRIX == "pcb":
        lines += [
            "",
            "PCBs (out/pcb/*_JLCPCB.zip, 1.6 mm FR4, 2 layers):",
            "  half_hotswap OR half_solder   x 2 (one reversible design; the right half is the same board flipped)",
            "  controller                    x 1",
            f"Kailh MX hotswap sockets      x {n_keys}  (hotswap boards only)",
            f"2x 20-pin female headers ({PR.FEMALE_HEADER_H} mm) for the Pico, on the controller board",
            "Molex PicoBlade 12-pin: 2x 53047-1210 (vertical, half boards), 2x 53048-1210 (right angle, controller)",
            "2x 12-pin 1.25 mm double-ended cable wired 1:1 (pin 1 to pin 1; flat with straight wires = latches on opposite sides), about 150 mm, e.g. Molex 15134-1202",
        ]
    else:
        lines += [f"2x 20-pin female headers ({PR.FEMALE_HEADER_H} mm), perfboard {PR.PERF_COLS}x{PR.PERF_ROWS} holes",
                  "1 mm bare copper wire, Kapton tape, hookup wire for the controller leads"]
    return "\n".join(lines)


def main(out="out"):
    for d in ("print", "step", "world"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    issues = G.validate_layout()
    if issues:
        print("LAYOUT ISSUES:\n  " + "\n  ".join(issues))
    plate = PT.plate_local()
    bezel = PT.bezel_local()
    case = PT.case_world()
    cover = PT.cover_P()

    pr = lambda n: os.path.join(out, "print", n)
    st = lambda n: os.path.join(out, "step", n)
    wo = lambda n: os.path.join(out, "world", n)

    plate_print = plate.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 180).translate(cq.Vector(0, 0, PR.PLATE_T))
    cq.exporters.export(plate_print, pr("plate_left.stl"), **TOL)
    cq.exporters.export(plate_print.mirror("YZ"), pr("plate_right.stl"), **TOL)
    bz_print = bezel.translate(cq.Vector(0, 0, -PR.PLATE_T))
    cq.exporters.export(bz_print, pr("frame_left.stl"), **TOL)
    cq.exporters.export(bz_print.mirror("YZ"), pr("frame_right.stl"), **TOL)
    cq.exporters.export(case, pr("case.stl"), **TOL)
    cq.exporters.export(cover.translate(cq.Vector(0, 0, -G.Z_DECK)), pr("cover.stl"), **TOL)

    world = {
        "plate_left": G.L2W(plate), "plate_right": G.R2W(plate),
        "frame_left": G.L2W(bezel), "frame_right": G.R2W(bezel),
        "case": case, "cover": G.P2W(cover),
    }
    for n, s in world.items():
        cq.exporters.export(s, st(n + ".step"))
        cq.exporters.export(s, wo(n + ".stl"), tolerance=0.03, angularTolerance=0.2)

    from compose.case import assembly as assembly
    assembly.build(world).save(st("assembly.step"))
    with open(os.path.join(out, "bom.txt"), "w") as f:
        f.write(bom() + "\n")
    print(bom())
    print(f"\nZ0 = {G.Z0}, deck = {G.Z_DECK}; outputs in {out}/")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
