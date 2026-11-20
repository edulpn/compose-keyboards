"""
python3 -m compose [--layout <name>] <command> [outdir] [args...]

Every command runs one module of the platform as if it were a script: the arguments after the
command are passed through unchanged, the output folder first. When no folder is named the run writes to
out/<layout>/rev2, and the controller rev 2's commands to out/controller (compose/outputs.py). A run builds
one keyboard: --layout names its layout, a folder of layouts/ (Compose58's when it is left out). The
controller rev 2's commands build no keyboard: it is one board under every layout, and they take no --layout.
Settings a run can change are environment variables (COMPOSE_SPLAY, COMPOSE_TENT, COMPOSE_TILT, ...:
compose/params.py; FREEROUTING, ...).
"""
import os
import runpy
import sys

from compose import outputs

LAYOUT = "compose58"         # the layout a run builds when no --layout names another: Compose58's

# command: (the module it runs, whether it builds a keyboard, what it does). A keyboard's layout reaches the
# modules through compose/params.py; False is a command of the controller rev 2, one board under every keyboard.
COMMANDS = {
    # controller rev 2: no layout
    "controller":       ("compose.controller.rev2",        False, "controller rev 2: place, route, DRC, Gerbers (--resilk: silkscreen only)"),
    "sim-controller":   ("compose.sim.controller_copper", False, "controller rev 2 copper-level simulation"),
    "spice-controller": ("compose.sim.controller_spice", False, "controller rev 2 ngspice simulation"),
    # a keyboard (gasket mount, controller rev 2)
    "gasket-case":      ("compose.case.gasket",          True, "rev 2 printable parts (print/)"),
    "gasket-checks":    ("compose.checks.gasket",        True, "rev 2 fit, gasket, assembly and printability checks"),
    "gasket-sections":  ("compose.checks.gasket_sections", True, "rev 2 cross-section drawings"),
    "gasket-render":    ("compose.render.gasket",        True, "rev 2 renders"),
    "firmware-rev2":    ("compose.firmware_rev2",         True, "rev 2 QMK keyboard.json (plain and RGB)"),
    "sim-half-rev2":    ("compose.sim.half_rev2",         True, "rev 2 half boards + controller rev 2: copper-level simulation"),
    "flex-jumper":      ("compose.pcb.jumper",             True, "rev 2 flex jumper (half <-> controller, one part for both sides): solve the path, board, DRC, Gerbers"),
    "order-rev2":       ("compose.order_rev2",             True, "rev 2 order folder: every board's JLCPCB zip, checked against its board and its DRC report, + ORDER.md"),
    "flex-sim":         ("compose.checks.flex_sim",        True, "rev 2 flex jumper as an elastic strip: seated, insertion, gasket travel, length; clearances"),
    "half-rev2":        ("compose.pcb.rev2_half",        True, "rev 2 half boards (hotswap/solder, +rgb): place, route, DRC, Gerbers (--plan: drawing only; --preroute: pre-routed copper only)"),
}


ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "layouts")


def layouts():
    """The layouts there are: the folders of layouts/ that hold a layout.py."""
    return sorted(d for d in os.listdir(ROOT) if is_layout(d))


def is_layout(name):
    """Whether layouts/ holds a layout by that name. Asked of the one folder: a run that names its layout does not
    look at the others, so CI does not count another layout's change as a change to this one's checks."""
    return name.isidentifier() and os.path.isfile(os.path.join(ROOT, name, "layout.py"))


def usage():
    print(__doc__.strip() + "\n\nlayouts: " + ", ".join(layouts()) + "\n\ncommands:")
    for k, (_, _, d) in COMMANDS.items():
        print(f"  {k:<17} {d}")


def passed(rest, layout):
    """The arguments a command's module gets: the ones given, with the folder it writes to put first when none was
    named (nothing given, or flags only). layout: the keyboard's, or None for a command of the controller rev 2."""
    return rest if rest and not rest[0].startswith("-") else [outputs.default(layout)] + rest


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
        if not is_layout(layout):
            stop(f"--layout {layout}: there is no layouts/{layout}/layout.py. The layouts: {', '.join(layouts())}."
                 if layout else f"--layout needs a name. The layouts: {', '.join(layouts())}.")
    if not args or args[0] in ("-h", "--help", "help") or args[0] not in COMMANDS:
        usage()
        sys.exit(0 if not args or args[0] in ("-h", "--help", "help") else 2)
    mod, keyboard, _ = COMMANDS[args[0]]
    if not keyboard and layout is not None:
        stop(f"{args[0]} takes no --layout: the controller rev 2 is the same board under every layout.")
    os.environ.pop("COMPOSE_LAYOUT", None)              # the command line decides, never what the shell was left with
    if keyboard:
        os.environ["COMPOSE_LAYOUT"] = layout or LAYOUT
    sys.argv = [mod] + passed(args[1:], (layout or LAYOUT) if keyboard else None)
    runpy.run_module(mod, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
