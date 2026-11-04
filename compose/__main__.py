"""
python3 -m compose <command> [outdir] [args...]

Every command runs one module of the platform as if it were a script: the arguments after the
command are passed through unchanged (most take the output folder first). Environment variables
(C58_REV, C58_SPLAY, C58_TENT, C58_TILT, FREEROUTING, ...) work as before.
"""
import runpy
import sys

COMMANDS = {
    # Compose58 rev 1 (sandwich mount, controller rev 1): the default build
    "build":            ("compose.case.build",           "case, plates, frames, cover (print/, step/, world/) + BOM"),
    "pcb":              ("compose.pcb.kicad",            "half boards + controller rev 1: place, route, DRC, Gerbers"),
    "firmware":         ("compose.firmware",             "QMK keyboard.json"),
    "model":            ("compose.render.model",         "assembled model for the checks and renders"),
    "checks":           ("compose.checks.sandwich",      "fit / assembly / print checks (after build + model)"),
    "sim":              ("compose.sim.matrix",           "copper-level matrix simulation of the routed boards"),
    "render":           ("compose.render.sandwich",      "renders and board previews"),
    "coupons":          ("compose.case.coupons",         "test-print coupons cut from the real parts"),
    "tilt-risers":      ("compose.case.tilt_risers",     "printable risers for trying negative tilt"),
    # controller rev 2
    "controller":       ("compose.controller.rev2",        "controller rev 2: place, route, DRC, Gerbers (--resilk: silkscreen only)"),
    "sim-controller":   ("compose.sim.controller_copper", "controller rev 2 copper-level simulation"),
    "spice-controller": ("compose.sim.controller_spice", "controller rev 2 ngspice simulation"),
    # rev 2 (gasket mount): set C58_REV=2
    "gasket-case":      ("compose.case.gasket",          "rev 2 printable parts (print/)"),
    "gasket-checks":    ("compose.checks.gasket",        "rev 2 fit, gasket, assembly and printability checks"),
    "gasket-sections":  ("compose.checks.gasket_sections", "rev 2 cross-section drawings"),
    "gasket-render":    ("compose.render.gasket",        "rev 2 renders"),
    "firmware-rev2":    ("compose.firmware_rev2",         "rev 2 QMK keyboard.json (plain and RGB)"),
    "sim-half-rev2":    ("compose.sim.half_rev2",         "rev 2 half boards + controller rev 2: copper-level simulation"),
    "flex-jumper":      ("compose.pcb.jumper",             "rev 2 flex jumpers (half <-> controller): solve the path, flex boards, DRC, Gerbers"),
    "half-rev2":        ("compose.pcb.rev2_half",        "rev 2 half boards (hotswap/solder, +rgb): place, route, DRC, Gerbers (--plan: drawing only)"),
}


def usage():
    print(__doc__.strip() + "\n\ncommands:")
    for k, (_, d) in COMMANDS.items():
        print(f"  {k:<17} {d}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help") or sys.argv[1] not in COMMANDS:
        usage()
        sys.exit(0 if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help") else 2)
    mod = COMMANDS[sys.argv[1]][0]
    sys.argv = [mod] + sys.argv[2:]
    runpy.run_module(mod, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
