"""
Compose58 rev 2 order folder:  C58_REV=2 python3 -m compose order-rev2 OUT

Collects every rev 2 board's JLCPCB zip into a clean folder, ORDER_OUT (default out_order/), with ORDER.md (what to pick on JLCPCB's form for
each), after checking that each board's DRC report (<board>_drc.txt, beside it) ends at 0 errors and 0
unconnected, and that each zip is what its routed board exports today: the Gerbers are exported again
from the .kicad_pcb into a scratch folder and compared file by file (KiCad's date and version comment lines
aside). It reads the boards the build commands left: the half boards and the jumper from OUT, the controller
from CTRL_OUT (default out). It doesn't re-route anything; run the build commands and their checks first
(docs/building.md, "Checking a change").
"""
import os
import shutil
import sys
import tempfile
import zipfile

OUT = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
CTRL_OUT = os.environ.get("CTRL_OUT", "out")
ORDER_OUT = os.environ.get("ORDER_OUT", "out_order")      # wiped and rebuilt on every run: only the zips + ORDER.md

FR4 = ("FR-4, 2 layers, 1.6 mm, 1 oz outer copper, any solder mask colour, HASL (with lead: the easiest to "
       "hand-solder; lead-free if you prefer; OSP works too if you solder within a few months, but the unused pads "
       "tarnish), remove the order mark")
BOARDS = [
    # (zip stem, board folder, export kwargs, qty per keyboard, JLCPCB notes)
    ("controller_rev2", CTRL_OUT, {}, "1", FR4),
    ("half_rev2_hotswap", OUT, {}, "2 (pick one of the four half boards)", FR4),
    ("half_rev2_solder", OUT, {}, "2", FR4),
    ("half_rev2_hotswap_rgb", OUT, {}, "2", FR4),
    ("half_rev2_solder_rgb", OUT, {}, "2", FR4),
    ("jumper_rev2", OUT, None, "2 (the same part on both sides)",
     "Flex, 25 um dielectric, 2 layers (back copper empty), 0.11 mm, yellow coverlay PI 12.5/AD 15, ENIG 1 U\", "
     "gold fingers No, EDA software Other, stiffener Polyimide 0.20 mm, confirm production file Yes. Remark: "
     "\"PI stiffener 0.20 mm on the bottom side, areas in the Stiffener_PI_bottom file (one under each finger field). "
     "Finished thickness at the fingers 0.30 +-0.05 mm (FPC connectors Molex 200528 and 52610). Bottom copper is "
     "intentionally empty.\" Copper: rolled annealed (the gasket mount flexes it with every keystroke)."),
]


def _lines(data):
    out = []
    for ln in data.decode("latin-1").splitlines():
        if ln.startswith(("G04 Created by", "G04 #@! TF.CreationDate", "%TF.CreationDate", "; DRILL file", "; FORMAT",
                          ";#@! TF.CreationDate", "G04 Created", "%TF.GenerationSoftware", ";#@! TF.GenerationSoftware")):
            continue
        if "CreationDate" in ln or "GenerationSoftware" in ln:
            continue
        out.append(ln)
    return out


def main():
    from compose.pcb import kicad as PK
    from compose.pcb import jumper as J
    dst = ORDER_OUT
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst)
    bad = []
    rows = []
    for stem, folder, kw, qty, notes in BOARDS:
        board = os.path.join(folder, "pcb", stem + ".kicad_pcb")
        z = os.path.join(folder, "pcb", stem + "_JLCPCB.zip")
        if not (os.path.exists(board) and os.path.exists(z)):
            bad.append(f"{stem}: not built ({board})")
            continue
        # the board's own DRC report, left beside it by the command that built it: a board from a route attempt
        # that didn't end clean still has a zip that matches it
        rep = os.path.join(folder, "pcb", stem + "_drc.txt")
        if not os.path.exists(rep):
            print(f"  FAIL  {stem}: no DRC report beside the board ({rep})")
            bad.append(f"{stem}: no DRC report ({rep})")
            continue
        counts = J.drc_counts(rep) if kw is None else PK.drc_counts(rep)     # the jumper's: less its finger fields
        if counts[0] > 0 or counts[2] > 0:
            print(f"  FAIL  {stem}: DRC {counts[0]} errors, {counts[2]} unconnected ({rep})")
            bad.append(f"{stem}: DRC not clean ({counts[0]} errors, {counts[2]} unconnected)")
            continue
        kw = J.EXPORT if kw is None else kw
        tmp = tempfile.mkdtemp()
        keep = PK.PCB_OUT
        try:
            PK.PCB_OUT = tmp
            fresh = PK.export(board, stem, **kw)
        finally:
            PK.PCB_OUT = keep
        a, b = zipfile.ZipFile(z), zipfile.ZipFile(fresh)
        na, nb = sorted(a.namelist()), sorted(b.namelist())
        diff = [n for n in sorted(set(na) | set(nb)) if n not in na or n not in nb
                or _lines(a.read(n)) != _lines(b.read(n))]
        shutil.rmtree(tmp, ignore_errors=True)
        ok = not diff
        print(f"  {'ok  ' if ok else 'FAIL'}  {stem}_JLCPCB.zip {'matches' if ok else 'differs from'} {board} "
              f"({len(na)} files{'; DRC clean' if ok else ': ' + ', '.join(diff[:4])})")
        if not ok:
            bad.append(f"{stem}: zip differs from the board ({', '.join(diff[:4])})")
            continue
        shutil.copy(z, dst)
        rows.append((stem, qty, notes))
    md = ["# Compose58 rev 2: what to order\n",
          "Every zip here was checked against its routed board when this folder was made, and that board's DRC",
          "report shows 0 errors and 0 unconnected. Order the controller,",
          "one of the four half boards, and the jumper. Parts: see the BOM in layouts/lily58/rev2.md and",
          "docs/controller-rev2.md.\n",
          "| zip | per keyboard | JLCPCB |", "|---|---|---|"]
    md += [f"| `{s}_JLCPCB.zip` | {q} | {n} |" for s, q, n in rows]
    open(os.path.join(dst, "ORDER.md"), "w").write("\n".join(md) + "\n")
    print(f"\n{dst}: {len(rows)} zips + ORDER.md" + ("" if not bad else f"; {len(bad)} problem(s): " + "; ".join(bad)))
    return len(bad)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
