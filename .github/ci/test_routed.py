"""Checks the reuse decision in routed.py: python3 .github/ci/test_routed.py (exit 1 on a wrong decision)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import routed  # noqa: E402

DEPS = ["compose/pcb/rev2_half.py", "compose/params.py", "layouts/lily58/layout.py", "layouts/",
        "import:layouts.lily58.preroute", "import:compose.pcb.rev2_half",
        "o2/pcb/half.ses", "o2/pcb/", "out_cache/jumper_row_y.json"]         # what the command wrote and read back
FILES = {"compose/pcb/rev2_half.py": "board", "compose/params.py": "params", "layouts/lily58/layout.py": "keys",
         "compose/sim/half_rev2.py": "sim", "docs/building.md": "docs",
         ".github/actions/setup/action.yml": "freerouting-2.1.0", ".github/workflows/checks.yml": "jobs", "requirements.txt": "shapely",
         "o2/pcb/half.ses": "routes"}
TOPS = {"compose", "layouts", "docs", ".github", "requirements.txt"}


def write(root, path, text):
    p = os.path.join(root, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)


# (what happens after the route, extra at verify, reused?)
CASES = [
    ("nothing changed", lambda r: None, {}, True),
    ("docs and the simulation changed", lambda r: (write(r, "docs/building.md", "x"), write(r, "compose/sim/half_rev2.py", "x")), {}, True),
    ("the board builder changed", lambda r: write(r, "compose/pcb/rev2_half.py", "board 2"), {}, False),
    ("a parameter changed", lambda r: write(r, "compose/params.py", "params 2"), {}, False),
    ("a file it read is gone", lambda r: os.remove(os.path.join(r, "layouts/lily58/layout.py")), {}, False),
    ("a layout folder appeared in a folder it listed", lambda r: write(r, "layouts/planck/layout.py", "keys"), {}, False),
    ("a file appeared deeper, in a folder it didn't list", lambda r: write(r, "layouts/lily58/notes.txt", "x"), {}, True),
    ("a module it looked for appeared", lambda r: write(r, "layouts/lily58/preroute.py", "copper"), {}, False),
    ("its own output differs (another run's .ses)", lambda r: write(r, "o2/pcb/half.ses", "other routes"), {}, True),
    ("its own output is gone", lambda r: os.remove(os.path.join(r, "o2/pcb/half.ses")), {}, True),
    ("the router version changed", lambda r: write(r, ".github/actions/setup/action.yml", "freerouting-2.5.0"), {}, False),
    ("the workflow changed", lambda r: write(r, ".github/workflows/checks.yml", "jobs 2"), {}, False),
    ("requirements changed", lambda r: write(r, "requirements.txt", "shapely>=3"), {}, False),
    ("same KiCad", lambda r: None, {"kicad": "7.0.11"}, True),
    ("another KiCad", lambda r: None, {"kicad": "7.0.12"}, False),
]


def main():
    bad = 0
    routed.tracked_tops = lambda root=None: TOPS             # the temporary trees below aren't git checkouts
    for name, change, extra, want in CASES:
        with tempfile.TemporaryDirectory() as r:
            for p, text in FILES.items():
                write(r, p, text)
            m = {"inputs": routed.inputs(DEPS, r), "extra": {"kicad": "7.0.11", "commit": "abc", "run": "1"}}
            change(r)
            got = not routed.compare(m, extra, r)
        bad += got != want
        print(("ok    " if got == want else "WRONG ") + f"{name}: {'reuse' if got else 'route'}")
    with tempfile.TemporaryDirectory() as r:
        for p, text in FILES.items():
            write(r, p, text)
        got = sorted(routed.inputs(DEPS, r))
        want = sorted(set(DEPS[:6]) | set(routed.TOOLCHAIN))
        bad += got != want
        print(("ok    " if got == want else "WRONG ") + "the command's own outputs aren't recorded as inputs")
    with tempfile.TemporaryDirectory() as r:                 # a manifest without the toolchain can't be trusted
        got = not routed.compare({"inputs": {}, "extra": {}}, {}, r)
        bad += got
        print(("ok    " if not got else "WRONG ") + f"an empty record: {'reuse' if got else 'route'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
