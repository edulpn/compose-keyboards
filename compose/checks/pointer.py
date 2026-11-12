"""
Pointer module checks (rev 2): docs/pointer-modules.md.

    C58_REV=2 C58_POINTER=pim447:R python3 -m compose pointer-checks [outdir] [--fast]       (the slot)
    C58_REV=2 C58_POINTER=pim447:R:bay30 python3 -m compose pointer-checks [outdir] [--fast] (a bay)
    C58_REV=2 C58_THUMB_BAY=bay30:R python3 -m compose pointer-checks [outdir]               (an empty bay: L, R or LR)
    C58_REV=2 python3 -m compose pointer-checks --list           (the devices in pointers/ and their footprints)
    C58_REV=2 python3 -m compose pointer-checks --suggest-bay [--one-sided]   (a position for each bay size, for
                                                                  Layout.bays; one-sided: a bay on one half only)

Three groups (the footprints are in compose/pointer/std.py, the devices in pointers/<name>/):
  S1-S5, B1-B7  this layout gives the footprint: the slot at its 1.5u thumb key, or the bay it declares
  M1-M8         the device on its carrier fits the footprint
  P1-P7         assembled and wired: overlaps, frame clearance, carrier printing, cable, bus, firmware
--fast runs S, B and M (seconds); without it P too (minutes). Writes outdir/pointer_checks.json; exits 1 on any FAIL.
"""
import os
import sys
import json
import math
from compose import params as PR
from compose import pointer as PT
from compose.pointer import std as S
from compose.pointer import device as D
from compose.pointer import place as PL
from compose.case import bay as B

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
FAST = "--fast" in sys.argv
OUT = ARGS[0] if ARGS else "out_r2t"
RES = []
OTHER_I2C = {0x3C: "OLED (SSD1306)"}       # other I2C modules the controller docs name


def rec(name, ok, val="", warn=False):
    tag = "PASS" if ok else ("WARN" if warn else "FAIL")
    RES.append(dict(check=name, result=tag, value=val))
    print(f"{tag:4s}  {name}  {val}", flush=True)


def _by(probs, cid):
    return "; ".join(m for c, m in probs if c == cid)


# ---------------------------------------------------------------- the layout gives the footprint
def check_slot(ctx, fp="slot"):
    f = S.get(fp)
    try:
        i, k = B.thumb_key()
    except ValueError as e:
        rec("S1 a 1.5u thumb key for the slot", False, str(e))
        return False
    rec("S1 a 1.5u thumb key for the slot", True, f"key {i} ({k.label_l} / {k.label_r})")
    p = PL.slot_problems(fp)
    i_, fr = PL.frame(fp)
    g = PL.window(fp, fr).distance(PL.keycaps(i_))
    rec(f"S2 {fp} window {f.w:g} x {f.l:g} clear of every other keycap by >= {PR.POINTER_ENV_CLR}",
        not _by(p, "S2"), f"{g:.2f} mm")
    rec("S3 slot window inside the plate core", not _by(p, "S3"), _by(p, "S3") or "inside")
    rec(f"S4 slot inserts: walls >= {PR.POINTER_INSERT_WALL} to switch holes and the core's edge", not _by(p, "S4"),
        _by(p, "S4") or f"{len(f.points)} inserts clear")
    rec(f"S5 slot inserts: >= {PR.POINTER_INSERT_UNDER} mm from cuts in the plate's underside", not _by(p, "S5"),
        _by(p, "S5") or "clear")
    return not p


def check_bay(ctx, fp=None):
    from shapely.geometry import Point
    try:
        fp = fp or B.active()
        b = B.solve(fp)
    except ValueError as e:
        rec("B1 the layout declares the thumb bay", False, str(e))
        return False
    rec("B1 the layout declares the thumb bay", True, f"{fp} at ({b.x:g}, {b.y:g}), {b.rot:g} deg")
    _, k = B.arc_anchor()
    on = B.sides()
    wg = B.gap(b, on)
    what = "the halves' outer walls" if len(on) == 2 else "the lobe and the other half's plain wall"
    rec(f"B2 >= {PR.BAY_WALL_GAP} mm between {what}", wg >= PR.BAY_WALL_GAP,
        f"{wg:.1f} mm, bay on {'+'.join(on)}; centre {math.hypot(b.x - k.x, b.y - k.y):.1f} mm from key {k.label_l} / {k.label_r}")
    from compose.case import gasket as C
    w = b.pocket.distance(C.O_WALL_IN)
    rec("B3 the pocket leaves the half's own wall whole", w >= PR.WALL_T - 0.01, f"{w:.2f} mm of wall (>= {PR.WALL_T})")
    rec("B4 a foot under the bay", b.pocket.buffer(-PR.FOOT_D / 2).contains(Point(b.x, b.y)), "at the bay's centre")
    g = B.bridge_gap(b)
    rec(f"B5 >= {PR.BAY_WALL_GAP} mm from the bridge", g >= PR.BAY_WALL_GAP, f"{g:.1f} mm")
    p = PL.bay_problems(fp)
    rec(f"B6 the bay's posts inside the pocket", not _by(p, "B6"), _by(p, "B6") or f"{len(S.get(fp).points)} posts")
    rec(f"B7 the lid's opening clear of the plate, >= {PR.BAY_FRAME_RIM} mm inside the case's edge", not _by(p, "B7"),
        _by(p, "B7") or "clear")
    return wg >= PR.BAY_WALL_GAP and g >= PR.BAY_WALL_GAP and not p


def check_footprint(ctx):
    fp = ctx["cfg"].mount
    ctx["fp_ok"] = (check_slot if S.kind(fp) == "slot" else check_bay)(ctx, fp)


# ---------------------------------------------------------------- the device on its carrier
def check_device(ctx):
    cfg = ctx["cfg"]
    try:
        dev = D.get(cfg.device)
    except KeyError as e:
        rec("M1 device known, with a carrier for the footprint", False, e.args[0])
        return
    if cfg.mount not in S.FOOTPRINTS:
        rec("M1 device known, with a carrier for the footprint", False, f"no footprint {cfg.mount!r} in the standard")
        return
    ok = cfg.mount in dev.footprints
    rec("M1 device known, with a carrier for the footprint", ok,
        f"{dev.name}: {dev.title}; footprints {', '.join(dev.footprints)}" + ("" if ok else f" (not {cfg.mount})"))
    if not ok or not ctx.get("fp_ok"):
        return
    pl = PL.place(cfg)
    ctx["pl"] = pl
    p = PL.device_problems(pl)
    rec(f"M2 board and carrier inside the {cfg.mount} window, under its top ({S.top(cfg.mount):g})", not _by(p, "M2"),
        _by(p, "M2") or f"top {pl.top_z:.2f} mm above the plate, board {pl.base_clear:.2f} mm over the base")
    rec(f"M3 the carrier screws to >= {S.MIN_POINTS} of the footprint's points", not _by(p, "M3"),
        f"{len(set(pl.uses))} of {len(pl.points)}")
    rec("M4 standard screws: the board's into the carrier, the carrier's into the footprint", not _by(p, "M4"),
        _by(p, "M4") or f"board M2 x {pl.dev_screw[0]} ({pl.dev_screw[1]:.2f} mm of thread), carrier "
                         f"{S.get(cfg.mount).screw} x {pl.fp_screw[0]} "
                         f"({pl.fp_screw[1]:.2f} mm of thread)")
    rec("M5 the cable drops from the pads (" + ("to the switch hole" if pl.kind == "slot" else "into the pocket")
        + ")", not _by(p, "M5"), _by(p, "M5") or "clear")
    rec(f"M6 touch surface near the suggested {PR.POINTER_BALL_TOP:g} mm above the plate",
        abs(pl.ball_top - PR.POINTER_BALL_TOP) <= 0.5,
        f"{pl.ball_top:.2f} mm" + (f", board tilted {pl.tilt:g} deg outward" if pl.tilt else ""), warn=True)
    if dev.bus == "i2c":
        a = dev.address
        rec("M7 I2C address clear of the other modules", a not in OTHER_I2C,
            f"0x{a:02X}" + (f" clashes with {OTHER_I2C[a]}" if a in OTHER_I2C else ""))
    rec("M8 part dimensions measured on a real part", dev.measured,
        f"from drawings and listings: measure before printing (pointers/{dev.name}/module.py)", warn=True)


# ---------------------------------------------------------------- assembled and wired
def check_solids(ctx):
    pl = ctx.get("pl")
    if pl is None:
        return
    import cadquery as cq
    import trimesh
    from compose.checks import gasket as CK
    parts, case, _, _ = CK.parts_world()
    ctx["parts"] = parts
    for a in ("pointer", "pointer carrier"):
        for b in ("plate", "frame", "case", "cover", "half pcb", "half parts", "jumpers"):
            v = CK.vol(parts[a], parts[b])
            rec(f"P1 no overlap: {a} / {b}", v < 1e-3, f"{v:.3f} mm3")
    v = CK.vol(parts["pointer"], parts["pointer carrier"])
    rec("P1 no overlap: pointer / pointer carrier", v < 1e-3, f"{v:.3f} mm3")
    d = CK.dist(parts["pointer"], parts["frame"])
    rec(f"P2 clearance pointer / frame >= {PR.KEY_OPENING_GAP}", d >= PR.KEY_OPENING_GAP - 0.01, f"{d:.2f} mm")
    c = D.carrier(pl.device.name).solid(pl.footprint)
    p = os.path.join(OUT, "_pointer_carrier.stl")
    os.makedirs(OUT, exist_ok=True)
    cq.exporters.export(cq.Workplane().add(c), p, tolerance=0.02, angularTolerance=0.1)
    m = trimesh.load(p)
    worst, n_br, n_thin, _ = CK.overhangs(m)
    rec("P3 carrier prints flat on its base: watertight, every layer supported", m.is_watertight and worst is None,
        f"{n_br} bridges, {n_thin} thin lips" + ("" if worst is None else f"; unsupported {worst}"))


def check_cable(ctx):
    pl, parts = ctx.get("pl"), ctx.get("parts")
    if pl is None or parts is None:
        return
    from compose.pointer import cable as PC
    r = PC.ROUTE[ctx["cfg"]]                     # solved by checks/gasket.py parts_world()
    pts, probs = r["pts"], r["problems"]
    rec("P4 cable route clear of everything (crossing solved)", not probs, "; ".join(probs) or
        f"crosses the bay at P y {r['y']:.1f} mm")
    L, stock = PC.length(pts), PC.stock_length(pts)
    rec(f"P5 cable length + {PR.POINTER_CABLE_SLACK:g} mm slack within a stock length", stock is not None,
        f"route {L:.0f} mm -> buy {stock} mm" if stock else f"route {L:.0f} mm: longer than the longest stock cable")
    if pl.device.bus == "i2c":
        c_pf = 10.0 + 5.0 + PR.POINTER_CABLE_PF_M * L / 1000.0 + 10.0
        rec("P6 I2C bus capacitance (pins 10 + board 5 + cable + device 10 pF) <= 100 pF (100 kHz)", c_pf <= 100.0,
            f"{c_pf:.0f} pF")
        rec("P6 ... <= 60 pF (400 kHz, not used)", c_pf <= 60.0, f"{c_pf:.0f} pF", warn=True)


def check_firmware(ctx):
    pl = ctx.get("pl")
    if pl is None:
        return
    from compose import firmware_rev2 as FW
    from compose import geom as G
    for rgb in (False, True):
        plain, ptr = FW.board(rgb), FW.board(rgb, pl)
        gone = FW.matrix_pos(G.LAYOUT.keys[pl.key_index], pl.side) if pl.key_index is not None else None
        m_plain = [e["matrix"] for e in plain["layouts"]["LAYOUT"]["layout"]]
        m_ptr = [e["matrix"] for e in ptr["layouts"]["LAYOUT"]["layout"]]
        ok = ((gone is None or (gone in m_plain and gone not in m_ptr))
              and sorted(m_ptr) == sorted(x for x in m_plain if x != gone)
              and ptr["features"].get("pointing_device") is True
              and FW.pointer_files(pl)["rules.mk"] == [f"POINTING_DEVICE_DRIVER = {pl.device.driver}"])
        what = f"key {gone} removed" if gone is not None else "every key kept"
        rec(f"P7 firmware {'rgb_' if rgb else ''}pointer: {what}, other keys unchanged, driver set", ok,
            f"{len(m_ptr)} keys, driver {pl.device.driver}")


FAST_CHECKS = [check_footprint, check_device]
FULL_CHECKS = [check_solids, check_cable, check_firmware]


def main():
    if PR.REV != 2:
        raise SystemExit("pointer modules are rev 2 only: set C58_REV=2")
    if "--list" in sys.argv:
        for n in D.names():
            d = D.get(n)
            print(f"{n:12s} {d.title}: footprints {', '.join(d.footprints)}; {d.bus}")
        return 0
    if "--suggest-bay" in sys.argv:                  # a position per bay size, for Layout.bays (layouts/<name>/layout.py)
        i, k = B.arc_anchor()
        found = {}
        on = ("R",) if "--one-sided" in sys.argv else ("L", "R")
        for fp in S.bays():
            try:
                b = B.suggest(fp, on)
            except ValueError as e:
                print(f"{fp}: {e}")
                continue
            found[fp] = b
            print(f"{fp} from key {i} ({k.label_l} / {k.label_r}): {B.gap(b, on):.1f} mm between the walls, "
                  f"{B.bridge_gap(b):.1f} mm from the bridge")
        print("    bays = {" + ", ".join(f'"{fp}": ({b.x:g}, {b.y:g}, {b.rot:g})' for fp, b in found.items()) + "}")
        return 0
    cfg = PT.active()
    if cfg is None and not B.enabled():
        print("neither C58_POINTER nor C58_THUMB_BAY is set: nothing to check")
        return 0
    ctx = {"cfg": cfg}
    if cfg is None:
        check_bay(ctx)
    else:
        if S.kind(cfg.mount) == "slot" and B.enabled():     # a device in the slot, and the case has a (empty) bay too
            check_bay(ctx)
        for f in FAST_CHECKS + ([] if FAST else FULL_CHECKS):
            f(ctx)
    os.makedirs(OUT, exist_ok=True)
    json.dump(RES, open(os.path.join(OUT, "pointer_checks.json"), "w"), indent=1)
    n_f = sum(r["result"] == "FAIL" for r in RES)
    print(f"\n{len(RES)} checks, {n_f} FAIL, {sum(r['result'] == 'WARN' for r in RES)} WARN")
    return n_f


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
