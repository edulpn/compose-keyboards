"""Checks the change detection in affected.py: python3 .github/ci/test_affected.py (exit 1 on a wrong decision)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from affected import decide, decide_pr, is_doc  # noqa: E402

FIRMWARE = ["compose/__init__.py", "compose/__main__.py", "compose/firmware_rev2.py", "compose/geom.py", "compose/params.py",
            "layouts/compose58/layout.py", "import:compose.firmware_rev2", "import:compose.optional_thing"]
POINTER = ["compose/checks/pointer.py", "pointers/", "pointers/pim447/module.py"]

CASES = [
    ("docs only", FIRMWARE, ["docs/building.md", "README.md"], False),
    ("modules the suite does not read", FIRMWARE, ["compose/case/gasket.py", "compose/pcb/jumper.py"], False),
    ("shared params", FIRMWARE, ["compose/params.py"], True),
    ("the entry module", FIRMWARE, ["compose/firmware_rev2.py"], True),
    ("a new module nothing imports", FIRMWARE, ["compose/pcb/newthing.py"], False),
    ("a new module an import looked for", FIRMWARE, ["compose/optional_thing.py"], True),
    ("CI changed", FIRMWARE, [".github/workflows/checks.yml"], True),
    ("toolchain changed", FIRMWARE, ["requirements.txt"], True),
    ("layout edited", FIRMWARE, ["layouts/compose58/layout.py"], True),
    ("another layout added", FIRMWARE, ["layouts/planck/layout.py"], False),
    ("a new pointer device", POINTER, ["pointers/trackpoint/module.py"], True),
    ("a pointer device edited", POINTER, ["pointers/pim447/module.py"], True),
]


# a pull request planned against a record older than its base: (name, deps, the pull request's own changes, what
# the base gained since the record, run?)
MAIN_MOVED = ["compose/firmware_rev2.py", ".github/workflows/checks.yml"]
PR_CASES = [
    ("pictures, record of the base", FIRMWARE, ["layouts/compose58/images/rev2_hero.png"], [], False),
    ("pictures, main moved on since the record", FIRMWARE, ["layouts/compose58/images/rev2_hero.png", "docs/images/top.png"], MAIN_MOVED, False),
    ("documents, main moved on since the record", FIRMWARE, ["README.md", "docs/building.md"], MAIN_MOVED, False),
    ("a module the suite reads, main moved on", FIRMWARE, ["compose/params.py"], MAIN_MOVED, True),
    ("a module the record doesn't list, main moved on where the suite reads", FIRMWARE, ["compose/pcb/newthing.py"], MAIN_MOVED, True),
    ("a module the record doesn't list, main moved on elsewhere", FIRMWARE, ["compose/pcb/newthing.py"], ["compose/case/gasket.py"], False),
    ("a module the record doesn't list, record of the base", FIRMWARE, ["compose/pcb/newthing.py"], [], False),
    ("a document and CI together", FIRMWARE, ["README.md", ".github/workflows/checks.yml"], [], True),
    ("a picture outside an images folder, main moved on", FIRMWARE, ["compose/pcb/logo.png"], MAIN_MOVED, True),
    ("a document the record lists", FIRMWARE + ["docs/building.md"], ["docs/building.md"], MAIN_MOVED, True),
]
DOCS = [("README.md", True), ("layouts/compose58/rev2.md", True), ("docs/images/controller_rev2_top.png", True),
        ("layouts/compose58/images/rev2_hero.png", True), ("compose/pcb/art.svg", False), ("compose/params.py", False),
        (".github/pull_request_template.md", False), ("requirements.txt", False)]


def main():
    bad = 0
    for name, deps, changed, want in CASES:
        got = bool(decide(deps, changed))
        bad += got != want
        print(("ok    " if got == want else "WRONG ") + f"{name}: {'run' if got else 'skip'}")
    for name, deps, own, since, want in PR_CASES:
        got = bool(decide_pr(deps, own, since))
        bad += got != want
        print(("ok    " if got == want else "WRONG ") + f"pull request, {name}: {'run' if got else 'skip'}")
    for path, want in DOCS:
        got = is_doc(path)
        bad += got != want
        print(("ok    " if got == want else "WRONG ") + f"{path}: {'a document or its picture' if got else 'not a document'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
