"""Run one `python3 -m compose` command and record which repository files it depended on.

    python3 .github/ci/traced.py <deps.txt> <command> [args...]

Every module imported, file opened and directory listed inside the repository is recorded through Python's
audit hooks, then appended to <deps.txt> as repo-relative paths (directories end in "/"). Generated
outputs (out/, out_*/) and caches are left out. The command's exit code is passed through.

`affected.py` compares those paths with a change set: a run can only differ if one of them changed, or if a
file was added to or removed from a directory it listed.
"""
import atexit
import os
import runpy
import sys

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SKIP_TOP = ("out", ".git", ".github")
PACKAGES = ("compose", "layouts", "pointers")        # the repository's importable top-level packages
seen_files, seen_dirs, seen_imports = set(), set(), set()


def _rel(p):
    try:
        p = os.path.realpath(os.fsdecode(p))
    except (TypeError, ValueError):
        return None
    if not p.startswith(ROOT + os.sep):
        return None
    parts = os.path.relpath(p, ROOT).split(os.sep)
    if parts[0].startswith(SKIP_TOP):
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
