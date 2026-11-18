"""
python3 -m compose <command> [outdir] [args...]

Every command runs one module of the platform as if it were a script: the arguments after the
command are passed through unchanged (most take the output folder first). The rev of the keyboard follows
from the command: each one belongs to rev 1 or to rev 2, and the controller rev 2's to neither. Environment
variables (C58_SPLAY, C58_TENT, C58_TILT, FREEROUTING, ...) work as before.
"""
import os
import runpy
import sys

# command: (the module it runs, the rev of the keyboard it builds, what it does). The rev reaches the modules
# through compose/params.py; None is a command of the controller rev 2, one board under every keyboard.
COMMANDS = {
    # rev 1 (sandwich mount, controller rev 1)
    "build":            ("compose.case.build",           1, "case, plates, frames, cover (print/, step/, world/) + BOM"),
    "pcb":              ("compose.pcb.kicad",            1, "half boards + controller rev 1: place, route, DRC, Gerbers"),
    "firmware":         ("compose.firmware",             1, "QMK keyboard.json"),
    "model":            ("compose.render.model",         1, "assembled model for the checks and renders"),
    "checks":           ("compose.checks.sandwich",      1, "fit / assembly / print checks (after build + model)"),
    "sim":              ("compose.sim.matrix",           1, "copper-level matrix simulation of the routed boards"),
    "render":           ("compose.render.sandwich",      1, "renders and board previews"),
    "coupons":          ("compose.case.coupons",         1, "test-print coupons cut from the real parts"),
    "tilt-risers":      ("compose.case.tilt_risers",     1, "printable risers for trying negative tilt"),
    # controller rev 2: no rev, and no layout
    "controller":       ("compose.controller.rev2",        None, "controller rev 2: place, route, DRC, Gerbers (--resilk: silkscreen only)"),
    "sim-controller":   ("compose.sim.controller_copper", None, "controller rev 2 copper-level simulation"),
    "spice-controller": ("compose.sim.controller_spice", None, "controller rev 2 ngspice simulation"),
    # rev 2 (gasket mount, controller rev 2)
    "gasket-case":      ("compose.case.gasket",          2, "rev 2 printable parts (print/)"),
    "gasket-checks":    ("compose.checks.gasket",        2, "rev 2 fit, gasket, assembly and printability checks"),
    "gasket-sections":  ("compose.checks.gasket_sections", 2, "rev 2 cross-section drawings"),
    "gasket-render":    ("compose.render.gasket",        2, "rev 2 renders"),
    "firmware-rev2":    ("compose.firmware_rev2",         2, "rev 2 QMK keyboard.json (plain and RGB)"),
    "sim-half-rev2":    ("compose.sim.half_rev2",         2, "rev 2 half boards + controller rev 2: copper-level simulation"),
    "flex-jumper":      ("compose.pcb.jumper",             2, "rev 2 flex jumper (half <-> controller, one part for both sides): solve the path, board, DRC, Gerbers"),
    "order-rev2":       ("compose.order_rev2",             2, "Compose58 rev 2 order folder: every board's JLCPCB zip, checked against its board and its DRC report, + ORDER.md"),
    "flex-sim":         ("compose.checks.flex_sim",        2, "rev 2 flex jumper as an elastic strip: seated, insertion, gasket travel, length; clearances"),
    "half-rev2":        ("compose.pcb.rev2_half",        2, "rev 2 half boards (hotswap/solder, +rgb): place, route, DRC, Gerbers (--plan: drawing only; --preroute: pre-routed copper only)"),
}


def usage():
    print(__doc__.strip() + "\n\ncommands:")
    for k, (_, rev, d) in COMMANDS.items():
        print(f"  {k:<17} {'rev ' + str(rev) if rev else '-':<6} {d}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help") or sys.argv[1] not in COMMANDS:
        usage()
        sys.exit(0 if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help") else 2)
    mod, rev, _ = COMMANDS[sys.argv[1]]
    os.environ.pop("COMPOSE_REV", None)                 # the command decides, never what the shell was left with
    if rev is not None:
        os.environ["COMPOSE_REV"] = str(rev)
    sys.argv = [mod] + sys.argv[2:]
    runpy.run_module(mod, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
