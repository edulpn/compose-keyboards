"""Checks what python3 -m compose does with its command line and with old settings, as far as it goes without
the toolchain: python3 .github/ci/test_cli.py (exit 1 on a wrong outcome).

Every case here stops before a command's module runs, or only reads compose/params.py, which imports nothing but
the layout's keyboard.py (plain constants; the layouts made up for the test are written to a temporary folder).
"""
import pathlib
import ast
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SAY = "import compose.params as P; print(getattr(P, 'LAYOUT', None), getattr(P, 'TENT_DEG', None))"
SAY_OUT = ("from compose.__main__ import passed; from compose import outputs as O; "
           "print(passed([], 'a'), passed(['--plan'], 'a'), passed(['--resilk'], None), passed(['mine', '--plan'], 'a'), "
           "'|', O.controller(), O.order('a'), O.cache('a'))")
SAY_KB = ("import compose.params as P; print(P.BOARD_NAME, P.CREDIT, P.REVISION, f'{P.TENT_DEG} {P.TILT_DEG}', "
          "f'{P.USB_VID} {P.USB_PID} {P.USB_PID_RGB}', sep=' | ')")
# (what is tried, the arguments after `python3`, the environment added, the exit code, a word the output must have)
CASES = [
    ("the help lists the layouts", ["-m", "compose", "--help"], {}, 0, "layouts: "),
    ("no arguments: the help", ["-m", "compose"], {}, 0, "commands:"),
    ("a command there is not", ["-m", "compose", "nope"], {}, 2, "commands:"),
    ("a layout there is not", ["-m", "compose", "--layout", "nope", "firmware-rev2"], {}, 2, "no layouts/nope/layout.py"),
    ("the same with =", ["-m", "compose", "--layout=nope", "firmware-rev2"], {}, 2, "no layouts/nope/layout.py"),
    ("--layout with no name", ["-m", "compose", "--layout"], {}, 2, "needs a name"),
    ("the folder's old name", ["-m", "compose", "--layout", "lily58", "firmware-rev2"], {}, 2, "no layouts/lily58/layout.py"),
    ("a path for a layout", ["-m", "compose", "--layout", "../layouts/compose58", "firmware-rev2"], {}, 2, "no layouts/../layouts/compose58/layout.py"),
    ("a layout and no command: the help", ["-m", "compose", "--layout", "compose58"], {}, 0, "commands:"),
    ("the controller takes no layout", ["-m", "compose", "--layout", "compose58", "controller", "out"], {}, 2, "takes no --layout"),
    ("its simulation neither", ["-m", "compose", "--layout=compose58", "spice-controller", "out"], {}, 2, "takes no --layout"),
    ("params with no keyboard", ["-c", SAY], {}, 0, "None None"),
    ("params for a keyboard", ["-c", SAY], {"COMPOSE_LAYOUT": "compose58"}, 0, "compose58 6.0"),
    ("a setting by its new name", ["-c", SAY], {"COMPOSE_LAYOUT": "compose58", "COMPOSE_TENT": "9"}, 0, "compose58 9.0"),
    ("the old name of the rev", ["-c", SAY], {"C58_REV": "2"}, 1, "one rev, and nothing to set"),
    ("the old name of a setting", ["-c", SAY], {"COMPOSE_LAYOUT": "compose58", "C58_TENT": "9"}, 1, "COMPOSE_TENT now"),
    ("the old name of the pre-route switch", ["-c", SAY], {"C58_PREROUTE": "0"}, 1, "COMPOSE_PREROUTE now"),
    ("an old name there never was", ["-c", SAY], {"C58_NOPE": "1"}, 1, "no setting of that name"),
    ("a value only a keyboard has, read with none", ["-c", "import compose.params as P; P.TENT_DEG"], {}, 1, "this run builds none"),
    ("the layout read with none", ["-c", "import compose.params as P; P.LAYOUT"], {}, 1, "this run builds none"),
    ("no folder named: one per keyboard, and the controller's; a folder named: that one", ["-c", SAY_OUT], {}, 0,
     "['out/a/rev2'] ['out/a/rev2', '--plan'] ['out/controller', '--resilk'] ['mine', '--plan'] | out/controller out/a/order out_cache/a"),
    ("the controller's and the order folder named by the environment", ["-c", SAY_OUT], {"CTRL_OUT": "c", "ORDER_OUT": "o"}, 0,
     "| c o out_cache/a"),
    ("the keyboard's name read with none", ["-c", "import compose.params as P; P.BOARD_NAME"], {}, 1, "this run builds none"),
    ("what the layout says of its keyboard", ["-c", SAY_KB], {"COMPOSE_LAYOUT": "compose58"}, 0,
     "Compose58 | layout: Lily58 by kata0510 | rev 2 | 6.0 0.0 | 0xFEED 0x4C58 0x4C59"),
]

# layouts made up for the test, each a keyboard.py: (what is tried, the file or None for no file, the exit code,
# a word the output must have)
TWO = 'NAME = "Two"\nCREDIT = "layout: nobody"\nTENT_DEG = 8.0\nTILT_DEG = 1.0\n' \
      'USB_VID = "0xFEED"\nUSB_PID = "0x0001"\nUSB_PID_RGB = "0x0002"\n'
MADE_UP = [
    ("a layout made up here", TWO, 0, "Two | layout: nobody | rev 2 | 8.0 1.0 | 0xFEED 0x0001 0x0002"),
    ("a layout with no keyboard.py", None, 1, "layouts/made_up/keyboard.py is missing"),
    ("a keyboard.py that leaves two things out", TWO.replace("CREDIT", "CREDITS").replace("USB_PID_RGB", "USB_RGB"), 1,
     "does not say CREDIT, USB_PID_RGB"),
    ("an angle that is not a number", TWO.replace("TENT_DEG = 8.0", "TENT_DEG = {2: 8.0}"), 1, "TENT_DEG has to be a number of degrees"),
]


SETTINGS = {"COMPOSE_LAYOUT", "COMPOSE_SPLAY", "COMPOSE_TENT", "COMPOSE_TILT", "COMPOSE_GAP_TOP", "COMPOSE_BRIDGE_LEN",
            "COMPOSE_PREROUTE"}


def named():
    """Every COMPOSE_... or C58_... name written in the code, the layouts and the docs: {name: a file that has it}."""
    out = {}
    for top in ("compose", "layouts", "docs", "CLAUDE.md", "README.md", ".github/workflows"):
        path = os.path.join(ROOT, top)
        files = [path] if os.path.isfile(path) else [os.path.join(d, f) for d, _, fs in os.walk(path) for f in fs
                                                      if f.endswith((".py", ".md", ".yml"))]
        for f in files:
            for name in re.findall(r"\b(?:COMPOSE|C58)_[A-Za-z0-9_\\]*", pathlib.Path(f).read_text(encoding="utf-8")):
                out.setdefault(name, os.path.relpath(f, ROOT))
    return out


def keyboard_files():
    """Every layout's keyboard.py against what compose/params.py asks of one: [(layout, what is wrong with it)]."""
    src = pathlib.Path(os.path.join(ROOT, "compose", "params.py")).read_text(encoding="utf-8")
    want = ast.literal_eval(re.search(r"^_KB_NAMES = (\(.*\))$", src, re.M).group(1))
    out = []
    for name in sorted(os.listdir(os.path.join(ROOT, "layouts"))):
        if not os.path.isfile(os.path.join(ROOT, "layouts", name, "layout.py")):
            continue
        path = os.path.join(ROOT, "layouts", name, "keyboard.py")
        if not os.path.isfile(path):
            out.append((name, "no keyboard.py"))
            continue
        has = set()
        for node in ast.parse(pathlib.Path(path).read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue                                                  # the docstring
            try:
                assert isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets)
                ast.literal_eval(node.value)
                has |= {t.id for t in node.targets}
            except (AssertionError, ValueError):
                out.append((name, f"line {node.lineno} is not a plain constant"))
        if set(want) - has:
            out.append((name, "does not say " + ", ".join(n for n in want if n not in has)))
    return out


def main():
    bad = 0
    wrong = keyboard_files()
    bad += bool(wrong)
    print(("ok   " if not wrong else "FAIL ") + "every layout's keyboard.py is plain constants and says what params.py asks"
          + ("" if not wrong else f": {wrong}"))
    old = {"C58_" + n[len("COMPOSE_"):] for n in SETTINGS} - {"C58_LAYOUT"} | {"C58_REV"}
    stray = {n: f for n, f in named().items() if n not in SETTINGS and not (n in old | {"C58_"} and f == "compose/params.py")
             and not (n == "C58_" and f.startswith("docs/"))}
    bad += bool(stray)
    print(("ok   " if not stray else "FAIL ") + "the settings named in the code and the docs are the ones there are"
          + ("" if not stray else f": {stray}"))
    base = {k: v for k, v in os.environ.items() if not k.startswith(("C58_", "COMPOSE_")) and k not in ("CTRL_OUT", "ORDER_OUT")}
    for name, args, env, code, word in CASES:
        r = subprocess.run([sys.executable] + args, cwd=ROOT, env={**base, **env}, capture_output=True, text=True, check=False)
        out = r.stdout + r.stderr
        ok = r.returncode == code and word in out
        bad += not ok
        print(("ok   " if ok else "FAIL ") + f"{name}: exit {r.returncode}" + ("" if ok else f" (expected {code} and {word!r}): {out.strip()[-300:]}"))
    with tempfile.TemporaryDirectory() as tmp:                 # the made-up layouts: `layouts` found here, `compose` in ROOT
        for i, (name, text, code, word) in enumerate(MADE_UP):
            d = os.path.join(tmp, str(i), "layouts", "made_up")
            os.makedirs(d)
            for f in (os.path.join(d, "..", "__init__.py"), os.path.join(d, "__init__.py")):
                open(f, "w").close()
            if text is not None:
                with open(os.path.join(d, "keyboard.py"), "w") as fh:
                    fh.write(text)
            r = subprocess.run([sys.executable, "-c", SAY_KB], cwd=os.path.join(tmp, str(i)), capture_output=True, text=True,
                               env={**base, "PYTHONPATH": ROOT, "COMPOSE_LAYOUT": "made_up"}, check=False)
            out = r.stdout + r.stderr
            ok = r.returncode == code and word in out
            bad += not ok
            print(("ok   " if ok else "FAIL ") + f"{name}: exit {r.returncode}" + ("" if ok else f" (expected {code} and {word!r}): {out.strip()[-300:]}"))
    n = len(CASES) + len(MADE_UP) + 2
    print(f"{n - bad}/{n} outcomes as expected")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
