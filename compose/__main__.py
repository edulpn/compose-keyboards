"""
python3 -m compose [--layout <name>] <command> [outdir] [args...]

Every command runs one module of the platform as if it were a script: the arguments after the
command are passed through unchanged, the output folder first. When no folder is named the run writes to
out/<layout>/rev1 or out/<layout>/rev2, and the controller rev 2's commands to out/controller
(compose/outputs.py). A run builds one keyboard:
--layout names its layout, a folder of layouts/ (Compose58's when it is left out), and its rev follows from
the command, each of which belongs to rev 1 or to rev 2. The controller rev 2's commands build no keyboard:
it is one board under every layout, and they take no --layout. Settings a run can change are environment
variables (COMPOSE_SPLAY, COMPOSE_TENT, COMPOSE_TILT, ...: compose/params.py; FREEROUTING, ...).
"""
import os
import runpy
import sys

from compose import outputs

LAYOUT = "compose58"         # the layout a run builds when no --layout names another: Compose58's

# command: (the module it runs, the rev of the keyboard it builds, what it does). The rev and the layout reach
# the modules through compose/params.py; None is a command of the controller rev 2, one board under every
# keyboard.
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
    "order-rev2":       ("compose.order_rev2",             2, "rev 2 order folder: every board's JLCPCB zip, checked against its board and its DRC report, + ORDER.md"),
    "flex-sim":         ("compose.checks.flex_sim",        2, "rev 2 flex jumper as an elastic strip: seated, insertion, gasket travel, length; clearances"),
    "half-rev2":        ("compose.pcb.rev2_half",        2, "rev 2 half boards (hotswap/solder, +rgb): place, route, DRC, Gerbers (--plan: drawing only; --preroute: pre-routed copper only)"),
}


def layouts():
    """The layouts there are: the folders of layouts/ that hold a layout.py."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "layouts")
    return sorted(d for d in os.listdir(root) if os.path.isfile(os.path.join(root, d, "layout.py")))


def usage():
    print(__doc__.strip() + "\n\nlayouts: " + ", ".join(layouts()) + "\n\ncommands:")
    for k, (_, rev, d) in COMMANDS.items():
        print(f"  {k:<17} {'rev ' + str(rev) if rev else '-':<6} {d}")


def passed(rest, rev, layout):
    """The arguments a command's module gets: the ones given, with the folder it writes to put first when none was
    named (nothing given, or flags only)."""
    return rest if rest and not rest[0].startswith("-") else [outputs.default(rev, layout)] + rest


def stop(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def main():
    args, layout = sys.argv[1:], None
    if args and (args[0] == "--layout" or args[0].startswith("--layout=")):
        if "=" in args[0]:
            layout, args = args[0].split("=", 1)[1], args[1:]
        else:
            layout, args = (args[1] if len(args) > 1 else ""), args[2:]
        if layout not in layouts():
            stop(f"--layout {layout}: there is no layouts/{layout}/layout.py. The layouts: {', '.join(layouts())}."
                 if layout else f"--layout needs a name. The layouts: {', '.join(layouts())}.")
    if not args or args[0] in ("-h", "--help", "help") or args[0] not in COMMANDS:
        usage()
        sys.exit(0 if not args or args[0] in ("-h", "--help", "help") else 2)
    mod, rev, _ = COMMANDS[args[0]]
    if rev is None and layout is not None:
        stop(f"{args[0]} takes no --layout: the controller rev 2 is the same board under every layout.")
    for name in ("COMPOSE_REV", "COMPOSE_LAYOUT"):      # the command line decides, never what the shell was left with
        os.environ.pop(name, None)
    if rev is not None:
        os.environ["COMPOSE_REV"], os.environ["COMPOSE_LAYOUT"] = str(rev), layout or LAYOUT
    sys.argv = [mod] + passed(args[1:], rev, layout or LAYOUT)
    runpy.run_module(mod, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
