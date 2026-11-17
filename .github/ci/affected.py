"""Decide whether a check suite has to run for a change set.

    python3 .github/ci/affected.py <deps.txt> <changed-files.txt>

<deps.txt> is what `traced.py` recorded while the suite ran on a known commit: every repository file it
imported or opened, and every directory it listed (ending in "/"). <changed-files.txt> lists the paths
that differ between that commit and the one under test (`git diff --name-only --no-renames <traced> <head>`):
added and removed files included, and a renamed file under both its old name and its new one.

The suite can only produce different results if one of the files it read changed, or a file appeared in or
vanished from a directory it listed. Changes to the toolchain or to CI itself always run everything.

A pull request is judged by what it changes itself (decide_pr): the record may be older than the commit the pull
request starts from, and what main gained in between is main's own run to check.
Prints "run" or "skip" on the first line, then the reasons; exits 0 either way.
"""
import sys

ALWAYS = ("requirements.txt", "Dockerfile", ".github/")
PICTURES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


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


def is_doc(path):
    """A document or one of its pictures: any *.md, or an image in a folder named images. Nothing under .github/."""
    if path.startswith(".github/"):
        return False
    return path.endswith(".md") or (path.lower().endswith(PICTURES) and "images" in path.split("/")[:-1])


def decide_pr(deps, own, since):
    """A pull request against a record that may be older than its base. own: the paths the pull request itself
    changes (its base to its head). since: the paths the base has gained since the record's commit (empty when
    the record is the base's own).

    The suite runs when the pull request changes something the record says it reads. It also runs when the
    record can't be trusted for the base: main has since changed something the suite reads, so the suite may
    read other files now than the record lists. Only a pull request of documents and their pictures is let
    through then: no suite reads those (a record that listed one would have caught it above)."""
    why = decide(deps, own)
    if why:
        return why
    stale = decide(deps, since)
    if stale and not all(is_doc(c) for c in own):
        more = f" and {len(stale) - 1} more" if len(stale) > 1 else ""
        return [f"the record is older than the base, where what this suite reads has changed since ({stale[0]}{more}): "
                f"its list of files may be out of date"]
    return []


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
