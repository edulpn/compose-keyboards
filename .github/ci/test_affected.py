"""Checks the change detection in affected.py: python3 .github/ci/test_affected.py (exit 1 on a wrong decision)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from affected import decide  # noqa: E402

REV1 = ["compose/__init__.py", "compose/__main__.py", "compose/firmware.py", "compose/geom.py", "compose/params.py",
        "layouts/lily58/layout.py", "import:compose.firmware", "import:compose.optional_thing"]
POINTER = ["compose/checks/pointer.py", "pointers/", "pointers/pim447/module.py"]

CASES = [
    ("docs only", REV1, ["docs/building.md", "README.md"], False),
    ("rev 2 modules don't touch rev 1", REV1, ["compose/case/gasket.py", "compose/firmware_rev2.py"], False),
    ("shared params", REV1, ["compose/params.py"], True),
    ("the entry module", REV1, ["compose/firmware.py"], True),
    ("a new module nothing imports", REV1, ["compose/pcb/newthing.py"], False),
    ("a new module an import looked for", REV1, ["compose/optional_thing.py"], True),
    ("CI changed", REV1, [".github/workflows/checks.yml"], True),
    ("toolchain changed", REV1, ["requirements.txt"], True),
    ("layout edited", REV1, ["layouts/lily58/layout.py"], True),
    ("another layout added", REV1, ["layouts/planck/layout.py"], False),
    ("a new pointer device", POINTER, ["pointers/trackpoint/module.py"], True),
    ("a pointer device edited", POINTER, ["pointers/pim447/module.py"], True),
]


def main():
    bad = 0
    for name, deps, changed, want in CASES:
        got = bool(decide(deps, changed))
        bad += got != want
        print(("ok    " if got == want else "WRONG ") + f"{name}: {'run' if got else 'skip'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
