"""Decide whether a check suite has to run for a change set.

    python3 .github/ci/affected.py <deps.txt> <changed-files.txt>

<deps.txt> is what `traced.py` recorded while the suite ran on a known commit: every repository file it
imported or opened, and every directory it listed (ending in "/"). <changed-files.txt> lists the paths
that differ between that commit and the one under test (`git diff --name-only <traced> <head>`), added,
removed and renamed files included.

The suite can only produce different results if one of the files it read changed, or a file appeared in or
vanished from a directory it listed. Changes to the toolchain or to CI itself always run everything.
Prints "run" or "skip" on the first line, then the reasons; exits 0 either way.
"""
import sys

ALWAYS = ("requirements.txt", "Dockerfile", ".github/")


def module_name(path):
    """compose/pcb/kicad.py -> compose.pcb.kicad, layouts/lily58/__init__.py -> layouts.lily58; else None."""
    if not path.endswith(".py"):
        return None
    parts = path[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def decide(deps, changed):
    files = {d for d in deps if not d.endswith("/") and not d.startswith("import:")}
    dirs = {d for d in deps if d.endswith("/")}
    imports = {d[len("import:"):] for d in deps if d.startswith("import:")}
    why = []
    for c in changed:
        if c.startswith(ALWAYS):
            why.append(f"{c}: toolchain or CI changed")
        elif c in files:
            why.append(f"{c}: read by the suite")
        elif module_name(c) in imports:
            why.append(f"{c}: a module the suite imports (or tries to)")
        elif any("/".join(c.split("/")[:i]) + "/" in dirs for i in range(1, c.count("/") + 1)):
            why.append(f"{c}: under a folder the suite lists")       # a new or removed entry shows there
    return why


def main():
    deps = [l.strip() for l in open(sys.argv[1]) if l.strip()]
    changed = [l.strip() for l in open(sys.argv[2]) if l.strip()]
    if not deps:
        print("run\nno dependency record: running")
        return
    why = decide(deps, changed)
    print("run" if why else "skip")
    for w in why[:50]:
        print("  " + w)
    if not why:
        print(f"  none of the {len(changed)} changed files is among the {len(deps)} the suite reads")


if __name__ == "__main__":
    main()
