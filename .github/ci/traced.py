"""Run one `python3 -m compose` command and record which repository files it depended on.

    python3 .github/ci/traced.py <deps.txt> <command> [args...]

Every module imported, file opened and directory listed inside the repository is recorded through Python's
audit hooks, then appended to <deps.txt> as repo-relative paths (directories end in "/"). Only what git tracks
at the top level counts: the folder a command writes to and reads back from (out/, or whatever the run named),
caches and other checkouts are results or strangers, not inputs. The command's exit code is passed through.

`affected.py` compares those paths with a change set: a run can only differ if one of them changed, or if a
file was added to or removed from a directory it listed.
"""
import atexit
import os
import runpy
import subprocess
import sys

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SKIP_TOP = ("out", ".git", ".github")
PACKAGES = ("compose", "layouts", "pointers")        # the repository's importable top-level packages


def _tracked_tops():
    """The repository's top-level names as git has them (None when git can't say: then every folder counts)."""
    try:
        r = subprocess.run(["git", "-C", ROOT, "ls-tree", "--name-only", "HEAD"], capture_output=True, text=True, check=False)
    except OSError:
        return None
    return (set(r.stdout.split("\n")) - {""}) if r.returncode == 0 and r.stdout.strip() else None


TOPS = _tracked_tops()
seen_files, seen_dirs, seen_imports = set(), set(), set()
COMMAND = " ".join(sys.argv[2:])                     # as given: the command's module rewrites sys.argv


def _rel(p):
    try:
        p = os.path.realpath(os.fsdecode(p))
    except (TypeError, ValueError):
        return None
    if not p.startswith(ROOT + os.sep):
        return None
    parts = os.path.relpath(p, ROOT).split(os.sep)
    if parts[0].startswith(SKIP_TOP) or (TOPS is not None and parts[0] not in TOPS):
        return None
    if "__pycache__" in parts:                        # a compiled module: record its source
        i = parts.index("__pycache__")
        parts = parts[:i] + [parts[-1].split(".")[0] + ".py"]
    return "/".join(parts)


def _from_importlib():
    f = sys._getframe(2)                              # the frame that called os.listdir / os.scandir
    return f is not None and "importlib" in f.f_code.co_filename


def _hook(event, args):
    if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        r = _rel(args[0])
        if r and os.path.isfile(os.path.join(ROOT, r)):
            seen_files.add(r)
    elif event == "import" and args and isinstance(args[0], str) and args[0].split(".")[0] in PACKAGES:
        seen_imports.add(args[0])                     # attempted, found or not: a new file by that name matters
    elif event in ("os.listdir", "os.scandir") and args and not _from_importlib():
        r = _rel(args[0] if args[0] is not None else ".")
        if r:
            seen_dirs.add(r.rstrip("/") + "/")


def _write(path):
    for m in list(sys.modules.values()):
        f = _rel(getattr(m, "__file__", None) or "") if getattr(m, "__file__", None) else None
        if f:
            seen_files.add(f)
    if "layouts/" in seen_dirs:                       # every layout's change would then count as a change to this suite
        print(f"::warning::{COMMAND}: the run listed layouts/, so a change to any layout runs its suite")
    with open(path, "a") as fh:
        for r in sorted(seen_files | seen_dirs) + sorted("import:" + m for m in seen_imports):
            fh.write(r + "\n")


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    atexit.register(_write, out)
    sys.addaudithook(_hook)
    sys.argv = ["compose"] + sys.argv[2:]
    sys.path.insert(0, os.getcwd())
    runpy.run_module("compose", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
