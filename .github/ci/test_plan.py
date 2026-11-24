"""Checks plan.py end to end on a throwaway repository: python3 .github/ci/test_plan.py (exit 1 on a wrong plan).

The repository is built the way a pull request reaches the plan job: main with a recorded commit, a commit main
gained after the record, a branch from there, and HEAD on the merge of the two (what Actions checks out). It holds
two layouts: compose58 (its half boards on a router that routes the same way every run) and other40 (the default
router). Each case names the suites that have to run, all others skipped."""
import pathlib
import ast
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PLAN = os.path.join(HERE, "plan.py")
BASE = os.path.join(HERE, "base.py")
sys.path.insert(0, HERE)
import plan as P  # noqa: E402

BOARDS = ("half_rev2_hotswap", "half_rev2_solder", "half_rev2_hotswap_rgb", "half_rev2_solder_rgb")
FILES = {
    "compose/params.py": "A = 1\n", "compose/firmware_rev2.py": "1\n",
    "compose/sim/half.py": "1\n", "compose/controller/rev2.py": "1\n",
    "compose/__main__.py": 'COMMANDS = {"firmware-rev2": ("compose.firmware_rev2", True, "x"), "controller": ("compose.controller.rev2", False, "x")}\n',
    "compose/pcb/rev2_half.py": "import os\nBOARDS = {" + ", ".join(f'"{b}": ("x", False)' for b in BOARDS) + "}\n",
    "layouts/__init__.py": "",
    "layouts/compose58/layout.py": "1\n", "layouts/other40/layout.py": "1\n", "layouts/images/top.png": "not a layout\n",
    "layouts/compose58/keyboard.py": 'NAME = "Compose58"\n',
    "layouts/compose58/preroute.py": "import math\nROUTER = {" + ", ".join(
        f'"{b}": ("2.5.0", 8)' if b.endswith("hotswap_rgb") else f'"{b}": "2.5.0"' for b in BOARDS) + "}\n",
    "layouts/other40/keyboard.py": 'NAME = "Other40"\n',
    "README.md": "one\n", "docs/images/top.png": "png 1\n",
}
DEPS = {
    "rev2-compose58": ["compose/params.py", "compose/firmware_rev2.py", "layouts/compose58/keyboard.py"],
    "boards-compose58": ["compose/params.py", "compose/sim/half.py", "layouts/compose58/keyboard.py", "layouts/compose58/preroute.py"],
    "rev2-other40": ["compose/params.py", "compose/firmware_rev2.py", "layouts/other40/keyboard.py"],
    "boards-other40": ["compose/params.py", "compose/sim/half.py", "layouts/other40/keyboard.py"],
    "controller": ["compose/params.py", "compose/controller/rev2.py"],
}
C58 = {"rev2-compose58", "boards-compose58"}
O40 = {"rev2-other40", "boards-other40"}
ALL = C58 | O40 | {"controller"}


def git(repo, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                       cwd=repo, capture_output=True, text=True, check=False)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout.strip()


def commit(repo, files, msg):
    for path, text in files.items():
        full = os.path.join(repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        pathlib.Path(full).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def plan(repo, deps_dir, record, event="pull_request", base_ref="main"):
    """What plan.py hands the workflow: (the suites that run, the half-board jobs as {layout: jobs per board}).
    Stops when the true|false switches and the lists disagree."""
    pathlib.Path(os.path.join(deps_dir, "SHA")).write_text(record + "\n")
    out = os.path.join(deps_dir, "out.txt")
    open(out, "w").close()
    env = dict(os.environ, GITHUB_EVENT_NAME=event, GITHUB_BASE_REF=base_ref, GITHUB_OUTPUT=out, GITHUB_STEP_SUMMARY=os.devnull)
    r = subprocess.run([sys.executable, PLAN, deps_dir], cwd=repo, env=env, capture_output=True, text=True, check=True)
    plan.said = r.stdout
    got = dict(l.strip().split("=", 1) for l in pathlib.Path(out).read_text().split("\n") if l.strip())
    runs = set()
    for k in ("rev2", "boards"):
        names = json.loads(got[k])
        assert (got[f"run_{k}"] == "true") == bool(names), (k, got)
        runs |= {f"{k}-{name}" for name in names}
    if got["run_controller"] == "true":
        runs.add("controller")
    half = {}
    for j in json.loads(got["half"]):
        assert j["board"] in BOARDS and 1 <= j["shard"] <= j["shards"], j
        half.setdefault(j["layout"], {}).setdefault(j["board"], []).append(j["shards"])
    for name, per in half.items():
        assert set(per) == set(BOARDS) and all(len(v) == v[0] for v in per.values()), (name, per)
        half[name] = sorted({v[0] for v in per.values()})
    assert set(half) == {s.split("-", 1)[1] for s in runs if s.startswith("boards-")}, (half, runs)
    # the list checks-passed reports from: every suite, a reason for exactly the ones that don't run
    suites = json.loads(got["suites"])
    assert [s["suite"] for s in suites] == P.suites(P.layouts(repo)), suites
    assert {s["suite"] for s in suites if s["skip"] is None} == runs, (suites, runs)
    assert all(s["skip"] is None or s["skip"].startswith("not affected") for s in suites), suites
    return runs, half


def same_every_run():
    """The routers compose/pcb/toolbox.py says route the same job the same way every time (seeds=True)."""
    tree = ast.parse(pathlib.Path(os.path.join(ROOT, "compose", "pcb", "toolbox.py")).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "ROUTERS" for t in node.targets):
            return {k.value for k, v in zip(node.value.keys, node.value.values, strict=True)
                    if any(kw.arg == "seeds" and kw.value.value is True for kw in v.keywords)}
    return None


def main():
    bad = 0

    def check(name, got, want):
        nonlocal bad
        bad += got != want
        print(("ok    " if got == want else "WRONG ") + f"{name}: " + (", ".join(sorted(got[0])) or "nothing runs")
              + ("" if got == want else f" | half-board jobs per board {got[1]} | wanted {sorted(want[0])}, {want[1]}"))

    def want(runs):
        return set(runs), {name: [1 if name == "compose58" else P.RACING]
                           for name in ("compose58", "other40", "new42") if f"boards-{name}" in runs}

    with tempfile.TemporaryDirectory() as tmp:
        repo, deps = os.path.join(tmp, "repo"), os.path.join(tmp, "deps")
        os.makedirs(repo); os.makedirs(deps)
        for s, files in DEPS.items():
            pathlib.Path(os.path.join(deps, s + ".txt")).write_text("\n".join(files) + "\n")
        git(repo, "init", "-q", "-b", "main")
        recorded = commit(repo, FILES, "recorded")
        moved = commit(repo, {"compose/firmware_rev2.py": "2\n"}, "main gains a rev 2 change after the record")

        def pull_request(files):
            """HEAD on the merge of main (at `moved`) and a branch from it that changes `files`; returns to main after."""
            git(repo, "checkout", "-q", "-B", "pr", moved)
            commit(repo, files, "the pull request")
            git(repo, "checkout", "-q", "--detach", moved)
            git(repo, "merge", "-q", "--no-ff", "-m", "merge", "pr")

        doc = {"docs/images/top.png": "png 2\n", "README.md": "two\n"}
        rev2s = {"rev2-compose58", "rev2-other40"}
        cases = [
            ("pictures and a document, record behind the base", doc, recorded, set()),
            ("pictures and a document, record of the base", doc, moved, set()),
            ("a file no suite reads, record behind the base: rev 2 can't vouch for its lists", {"compose/new.py": "1\n"}, recorded, rev2s),
            ("a file no suite reads, record of the base", {"compose/new.py": "1\n"}, moved, set()),
            ("a platform file every suite reads", {"compose/params.py": "A = 2\n"}, moved, ALL),
            ("a CI file: every suite", {".github/workflows/checks.yml": "x\n"}, moved, ALL),
            ("a controller file: every layout's boards run with it", {"compose/controller/rev2.py": "2\n"}, moved,
             {"controller", "boards-compose58", "boards-other40"}),
            ("a half-board file: the controller suite is skipped", {"compose/sim/half.py": "2\n"}, moved,
             {"boards-compose58", "boards-other40"}),
            ("one layout's file: that layout only", {"layouts/other40/keyboard.py": 'NAME = "Other 40"\n'}, moved, O40),
            ("the other layout's file: that layout only", {"layouts/compose58/keyboard.py": 'NAME = "C58"\n'}, moved, C58),
            ("one layout's routing: its boards only", {"layouts/compose58/preroute.py": "ROUTER = {}\n"}, moved, {"boards-compose58"}),
            ("a new layout: its suites run, having no record, and no other's", {"layouts/new42/layout.py": "1\n", "layouts/new42/keyboard.py": 'NAME = "New42"\n'},
             moved, {"rev2-new42", "boards-new42"}),
        ]
        for name, files, record, runs in cases:
            pull_request(files)
            w = want(runs)
            if "preroute.py" in "".join(files):                      # that layout no longer names a router: it races
                w[1]["compose58"] = [P.RACING]
            check(name, plan(repo, deps, record), w)
        # a record that main's runs have stopped saving falls behind: the plan says so aloud past a few merges
        pull_request(doc)
        plan(repo, deps, moved)
        quiet = "::warning" not in plan.said
        git(repo, "checkout", "-q", "-B", "main", moved)
        for i in range(P.BEHIND + 1):
            ahead = commit(repo, {"docs/notes.md": f"{i}\n"}, f"main moves on {i}")
        git(repo, "checkout", "-q", "-B", "pr", ahead)
        commit(repo, doc, "the pull request")
        git(repo, "checkout", "-q", "--detach", ahead)
        git(repo, "merge", "-q", "--no-ff", "-m", "merge", "pr")
        plan(repo, deps, moved)
        loud = f"::warning title=The record is {P.BEHIND + 1} merges behind" in plan.said
        bad += not (quiet and loud)
        print(("ok    " if quiet and loud else "WRONG ") + f"a record of the base says nothing; one {P.BEHIND + 1} merges behind is called out")
        git(repo, "checkout", "-q", "-B", "main", moved)
        # base.py, which the comparisons with the base go by: the merge's first parent, not the commit the event
        # names (here an older one, as GitHub's can be); the event's only where there is no merge and no branch
        pull_request(doc)
        env = dict(os.environ, GITHUB_BASE_REF="main", BASE_SHA=recorded)
        got = subprocess.run([sys.executable, BASE], cwd=repo, env=env, capture_output=True, text=True, check=False).stdout.strip()
        bad += got != moved
        print(("ok    " if got == moved else "WRONG ") + "the base of a merge is its first parent, whatever the event says")
        git(repo, "checkout", "-q", "--detach", "pr")
        env = dict(os.environ, GITHUB_BASE_REF="", BASE_SHA=recorded)
        got = subprocess.run([sys.executable, BASE], cwd=repo, env=env, capture_output=True, text=True, check=False).stdout.strip()
        bad += got != recorded
        print(("ok    " if got == recorded else "WRONG ") + "no merge and no base branch: the event's base")
        # not on a merge and no base branch to find: everything since the record counts, as it did before
        git(repo, "checkout", "-q", "-B", "pr", moved)
        commit(repo, {"README.md": "three\n"}, "a document")
        check("no merge to split at, record behind", plan(repo, deps, recorded, base_ref=""), want(rev2s))
        check("a push of a document: every suite", plan(repo, deps, recorded, event="push"), want(ALL))
        check("a run started by hand: every suite", plan(repo, deps, recorded, event="workflow_dispatch"), want(ALL))
        # a record from before a suite existed has no list for it: it runs (and with the controller, the boards)
        os.remove(os.path.join(deps, "controller.txt"))
        pull_request({"compose/new.py": "2\n"})
        check("a record with no controller list", plan(repo, deps, moved),
              want({"controller", "boards-compose58", "boards-other40"}))

    # the real repository: its layouts read, and the routers taken for one-job routers are the ones toolbox says
    lay = P.layouts(ROOT)
    jobs = P.half_jobs(lay, ROOT)
    ok = bool(lay) and bool(jobs)
    bad += not ok
    print(("ok    " if ok else "WRONG ") + "this repository: " + ", ".join(lay) + f"; {len(jobs)} half-board jobs")
    ok = same_every_run() == set(P.SAME_EVERY_RUN)
    bad += not ok
    print(("ok    " if ok else "WRONG ") + f"one job per board for the routers toolbox.py gives seeds=True: {sorted(P.SAME_EVERY_RUN)}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
