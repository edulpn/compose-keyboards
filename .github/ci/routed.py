"""Reuse a routed board when nothing that determines it has changed.

    python3 .github/ci/routed.py record <deps.txt> <manifest.json> [key=value ...]   after a clean route
    python3 .github/ci/routed.py verify <manifest.json> [key=value ...]              before routing again

Routing a rev 2 half board takes from a few minutes to most of an hour, and its result depends only on what
the routing command read: the repository files it imported or opened, the folders it listed, the module names
it looked for (traced.py records all three while it runs), and the toolchain (the setup action, which pins the
router, and requirements.txt; the workflow itself, which sets the command's environment).

`record` writes those inputs with a fingerprint of each to the manifest, which is cached with the routed
board (key=value pairs go in too: kicad=<version> is compared later, commit= and run= only say where the board
came from). `verify` reads a restored manifest and fingerprints the same inputs in the checkout: if every one
is unchanged, the command would read the same files again, so the cached board is the board it would be
judged by, and routing can be skipped. Anything else (no manifest, an input changed, added or removed, a
different kicad=) routes as before. With deps=<deps.txt>, a reused board's inputs are written there, so the
run's dependency record is the same as if it had routed. Prints the verdict and the reasons, writes
reuse=true|false to $GITHUB_OUTPUT and a line to the job summary (quiet=1: only if it won't be reused); exits
0 either way.
"""
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOOLCHAIN = (".github/actions/setup/action.yml", ".github/workflows/checks.yml", "requirements.txt")


def fingerprint(entry, root=ROOT):
    """What a recorded dependency looks like now: a file's content hash, a folder's listing, for a module name
    the file it would load from. 'absent' if it isn't there."""
    if entry.startswith("import:"):
        base = os.path.join(root, *entry[len("import:"):].split("."))
        got = [fingerprint(os.path.relpath(p, root), root) for p in (base + ".py", os.path.join(base, "__init__.py"))]
        return "|".join(got)
    p = os.path.join(root, entry)
    if entry.endswith("/"):
        if not os.path.isdir(p):
            return "absent"
        names = sorted(n for n in os.listdir(p) if n != "__pycache__")
        return "dir:" + hashlib.sha256("\n".join(names).encode()).hexdigest()[:16]
    if not os.path.isfile(p):
        return "absent"
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]


def tracked_tops(root=ROOT):
    """The repository's top-level names (git's, else whatever is there but out*/ and the hidden folders)."""
    try:
        r = subprocess.run(["git", "-C", root, "ls-tree", "--name-only", "HEAD"], capture_output=True, text=True)
        names = set(r.stdout.split("\n")) - {""} if r.returncode == 0 else set()
    except OSError:
        names = set()
    return names or {n for n in os.listdir(root) if not n.startswith((".", "out"))} | {".github"}


def is_input(entry, tops):
    """A recorded path that belongs to the repository. The record also holds what the command itself wrote
    and read back (its output folder: the .dsn, the router's .ses): those are results, not inputs."""
    path = entry[len("import:"):].replace(".", "/") if entry.startswith("import:") else entry
    return path.split("/")[0] in tops or path.split("/")[0] + ".py" in tops


def inputs(deps, root=ROOT):
    tops = tracked_tops(root)
    return {e: fingerprint(e, root) for e in sorted({d for d in deps if is_input(d, tops)} | set(TOOLCHAIN))}


def compare(manifest, extra, root=ROOT):
    """Reasons the manifest's board can't stand in for a fresh route (empty: it can)."""
    why = []
    for k, v in sorted(extra.items()):
        if manifest.get("extra", {}).get(k) != v:
            why.append(f"{k}: {manifest.get('extra', {}).get(k)} when routed, {v} now")
    tops = tracked_tops(root)
    for e, was in sorted(manifest.get("inputs", {}).items()):
        if not is_input(e, tops) and e not in TOOLCHAIN:
            continue
        now = fingerprint(e, root)
        if now != was:
            why.append(f"{e}: " + ("gone" if now == "absent" else "new" if was == "absent" else "changed"))
    for e in TOOLCHAIN:
        if e not in manifest.get("inputs", {}):
            why.append(f"{e}: not in the record")
    return why


def _out(reuse, line):
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as o:
        o.write(f"reuse={'true' if reuse else 'false'}\n")
    if line:
        with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as o:
            o.write(line + "\n")
        print(line)


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    extra = dict(a.split("=", 1) for a in args if "=" in a)
    args = [a for a in args if "=" not in a]
    if cmd == "record":
        deps = [l.strip() for l in open(args[0]) if l.strip()]
        m = {"inputs": inputs(deps), "extra": extra}
        os.makedirs(os.path.dirname(os.path.abspath(args[1])), exist_ok=True)
        json.dump(m, open(args[1], "w"), indent=1, sort_keys=True)
        same = {"inputs": m["inputs"], "extra": {k: v for k, v in extra.items() if k not in ("commit", "run")}}
        key = hashlib.sha256(json.dumps(same, sort_keys=True).encode()).hexdigest()[:20]
        with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as o:
            o.write(f"key={key}\n")
        print(f"recorded {len(m['inputs'])} inputs, key {key}")
    elif cmd == "verify":
        what, deps_out, quiet = extra.pop("board", "the board"), extra.pop("deps", None), extra.pop("quiet", None)
        if not os.path.exists(args[0]):
            return _out(False, f"**{what}**: routed (no routed board in the cache)")
        m = json.load(open(args[0]))
        why = compare(m, extra)
        src = m.get("extra", {}).get("commit", "?")[:9]
        if why:
            return _out(False, f"**{what}**: routed (the cached board from {src} no longer matches: "
                               + "; ".join(why[:6]) + (" ..." if len(why) > 6 else "") + ")")
        if deps_out:
            os.makedirs(os.path.dirname(os.path.abspath(deps_out)), exist_ok=True)
            with open(deps_out, "a") as o:
                o.write("".join(e + "\n" for e in sorted(m["inputs"]) if e not in TOOLCHAIN))
        if quiet:                                            # a later call, with the toolchain's versions, reports it
            return _out(True, "")
        _out(True, f"**{what}**: reused the board routed at {src} (run {m.get('extra', {}).get('run', '?')}): "
                   f"none of its {len(m['inputs'])} inputs changed")
    else:
        sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
