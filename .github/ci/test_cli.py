"""Checks what python3 -m compose does with its command line and with old settings, as far as it goes without
the toolchain: python3 .github/ci/test_cli.py (exit 1 on a wrong outcome).

Every case here stops before a command's module runs, or only reads compose/params.py, which imports nothing.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SAY = "import compose.params as P; print(P.REV, getattr(P, 'LAYOUT', None), getattr(P, 'TENT_DEG', None))"
# (what is tried, the arguments after `python3`, the environment added, the exit code, a word the output must have)
CASES = [
    ("the help lists the layouts", ["-m", "compose", "--help"], {}, 0, "layouts: "),
    ("no arguments: the help", ["-m", "compose"], {}, 0, "commands:"),
    ("a command there is not", ["-m", "compose", "nope"], {}, 2, "commands:"),
    ("a layout there is not", ["-m", "compose", "--layout", "nope", "firmware"], {}, 2, "no layouts/nope/layout.py"),
    ("the same with =", ["-m", "compose", "--layout=nope", "firmware"], {}, 2, "no layouts/nope/layout.py"),
    ("--layout with no name", ["-m", "compose", "--layout"], {}, 2, "needs a name"),
    ("a layout and no command: the help", ["-m", "compose", "--layout", "lily58"], {}, 0, "commands:"),
    ("the controller takes no layout", ["-m", "compose", "--layout", "lily58", "controller", "out"], {}, 2, "takes no --layout"),
    ("its simulation neither", ["-m", "compose", "--layout=lily58", "spice-controller", "out"], {}, 2, "takes no --layout"),
    ("params with no keyboard", ["-c", SAY], {}, 0, "None None None"),
    ("params for rev 1", ["-c", SAY], {"COMPOSE_REV": "1", "COMPOSE_LAYOUT": "lily58"}, 0, "1 lily58 6.0"),
    ("params for rev 2", ["-c", SAY], {"COMPOSE_REV": "2", "COMPOSE_LAYOUT": "lily58"}, 0, "2 lily58 12.0"),
    ("a setting by its new name", ["-c", SAY], {"COMPOSE_REV": "2", "COMPOSE_LAYOUT": "lily58", "COMPOSE_TENT": "9"}, 0, "2 lily58 9.0"),
    ("a rev with no layout", ["-c", SAY], {"COMPOSE_REV": "2"}, 1, "come together"),
    ("a layout with no rev", ["-c", SAY], {"COMPOSE_LAYOUT": "lily58"}, 1, "come together"),
    ("a rev there is not", ["-c", SAY], {"COMPOSE_REV": "3", "COMPOSE_LAYOUT": "lily58"}, 1, "a rev 1 and a rev 2"),
    ("the old name of the rev", ["-c", SAY], {"C58_REV": "2"}, 1, "follows from the command"),
    ("the old name of a setting", ["-c", SAY], {"COMPOSE_REV": "2", "COMPOSE_LAYOUT": "lily58", "C58_TENT": "9"}, 1, "COMPOSE_TENT now"),
    ("the old name of the pre-route switch", ["-c", SAY], {"C58_PREROUTE": "0"}, 1, "COMPOSE_PREROUTE now"),
    ("an old name there never was", ["-c", SAY], {"C58_NOPE": "1"}, 1, "no setting of that name"),
    ("a value only a keyboard has, read with none", ["-c", "import compose.params as P; P.TENT_DEG"], {}, 1, "this run builds none"),
    ("the layout read with none", ["-c", "import compose.params as P; P.LAYOUT"], {}, 1, "this run builds none"),
]


SETTINGS = {"COMPOSE_REV", "COMPOSE_LAYOUT", "COMPOSE_SPLAY", "COMPOSE_TENT", "COMPOSE_TILT", "COMPOSE_GAP_TOP", "COMPOSE_BRIDGE_LEN",
            "COMPOSE_PREROUTE"}


def named():
    """Every COMPOSE_... or C58_... name written in the code, the layouts and the docs: {name: a file that has it}."""
    out = {}
    for top in ("compose", "layouts", "docs", "CLAUDE.md", "README.md", ".github/workflows"):
        path = os.path.join(ROOT, top)
        files = [path] if os.path.isfile(path) else [os.path.join(d, f) for d, _, fs in os.walk(path) for f in fs
                                                      if f.endswith((".py", ".md", ".yml"))]
        for f in files:
            for name in re.findall(r"\b(?:COMPOSE|C58)_[A-Za-z0-9_\\]*", open(f, encoding="utf-8").read()):
                out.setdefault(name, os.path.relpath(f, ROOT))
    return out


def main():
    bad = 0
    old = {"C58_" + n[len("COMPOSE_"):] for n in SETTINGS} - {"C58_LAYOUT"}
    stray = {n: f for n, f in named().items() if n not in SETTINGS and not (n in old | {"C58_"} and f == "compose/params.py")
             and not (n == "C58_" and f.startswith("docs/"))}
    bad += bool(stray)
    print(("ok   " if not stray else "FAIL ") + "the settings named in the code and the docs are the ones there are"
          + ("" if not stray else f": {stray}"))
    base = {k: v for k, v in os.environ.items() if not k.startswith(("C58_", "COMPOSE_"))}
    for name, args, env, code, word in CASES:
        r = subprocess.run([sys.executable] + args, cwd=ROOT, env={**base, **env}, capture_output=True, text=True)
        out = r.stdout + r.stderr
        ok = r.returncode == code and word in out
        bad += not ok
        print(("ok   " if ok else "FAIL ") + f"{name}: exit {r.returncode}" + ("" if ok else f" (expected {code} and {word!r}): {out.strip()[-300:]}"))
    print(f"{len(CASES) + 1 - bad}/{len(CASES) + 1} outcomes as expected")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
