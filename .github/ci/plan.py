"""Which check suites a CI run needs.

    python3 .github/ci/plan.py <deps-dir>

The suites follow from the layouts there are (the folders of layouts/ with a layout.py): rev2-<layout>, the case
and firmware, and boards-<layout>, plus controller. A new layout needs nothing here or in the workflow.

<deps-dir> holds what the last full run on main recorded: SHA (the commit it ran on) and <suite>.txt for every
suite (the files each suite read, from traced.py). On a pull request a suite runs if the pull request itself
changes anything the suite read (see affected.py); everywhere else, and whenever a record is missing (a new
layout has none), every suite runs. The reasons go to the job summary, and to $GITHUB_OUTPUT what the workflow
builds its jobs from:

    run_rev2, run_boards, run_controller    true | false: any job of that kind at all
    rev2, boards                            the layouts whose suite of that kind runs, as a JSON list
    half                                    the half-board jobs of those layouts, as a JSON list of
                                            {layout, board, shard, shards}

A half board is one job when its layout names a router that routes the same job the same way every time (ROUTER
in layouts/<layout>/preroute.py), and three racing jobs under the default router, which is random.

The controller is a suite of its own: it has no keyboard, and every keyboard's boards are simulated against its
board. So when the controller suite runs, every layout's boards suite runs with it. The other way round is the
workflow's: it builds the controller's board whenever boards run, and leaves the controller's circuit simulation
out.

The record can be older than the pull request's base: a full run on main takes a while, and a pull request opened
meanwhile is planned against the record before it. What main gained in between is not the pull request's to
check, so the changes are split in two: base to head (the pull request's own) and record to base.
"""
import pathlib
import ast
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from affected import decide_pr  # noqa: E402

KINDS = ("rev2", "boards")                       # a layout's suites: its case and firmware, and its boards
SAME_EVERY_RUN = ("2.5.0",)                      # the routers with seeds=True in compose/pcb/toolbox.py's ROUTERS
RACING = 3                                       # jobs per board under a random router: the first clean one is taken
BEHIND = 3                                       # merges the record may lag the base by before the plan says so aloud


def constant(path, name, default=None):
    """The value a module gives a name at its top level, read without importing it (None-like default when the
    file or the name is missing). Stops when the value is not a plain constant: the plan can't run the module."""
    if not os.path.isfile(path):
        return default
    for node in ast.parse(pathlib.Path(path).read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except (ValueError, TypeError):
                sys.exit(f"{path}: {name} has to be a plain constant (the CI plan reads it without running the file).")
    return default


def layouts(root="."):
    """The layouts there are: every folder of layouts/ that holds a layout.py (what the command line takes for a
    layout)."""
    d = os.path.join(root, "layouts")
    return [name for name in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, name, "layout.py"))] if os.path.isdir(d) else []


def suites(lay):
    """Every suite there is, in the order the summary lists them."""
    return [f"{k}-{name}" for name in lay for k in KINDS] + ["controller"]


def half_jobs(names, root="."):
    """The half-board jobs of the layouts named: one per board, or RACING per board under a random router."""
    boards = constant(os.path.join(root, "compose", "pcb", "rev2_half.py"), "BOARDS")
    if not isinstance(boards, dict) or not boards:
        sys.exit("compose/pcb/rev2_half.py: BOARDS, the half boards there are, was not found as a plain constant.")
    jobs = []
    for name in names:
        router = constant(os.path.join(root, "layouts", name, "preroute.py"), "ROUTER", {})
        if not isinstance(router, dict):
            sys.exit(f"layouts/{name}/preroute.py: ROUTER has to be {{board name: Freerouting version}}.")
        for b in boards:
            v = router.get(b)
            n = 1 if (v[0] if isinstance(v, tuple) else v) in SAME_EVERY_RUN else RACING
            jobs += [{"layout": name, "board": b, "shard": i, "shards": n} for i in range(1, n + 1)]
    return jobs


def outputs(run, lay):
    """The lines for $GITHUB_OUTPUT (see the top of this file) from {suite: runs or not}."""
    lines, names = [], {}
    for k in KINDS:
        names[k] = [name for name in lay if run.get(f"{k}-{name}")]
        lines += [f"run_{k}={'true' if names[k] else 'false'}", f"{k}={json.dumps(names[k])}"]
    lines.append(f"run_controller={'true' if run['controller'] else 'false'}")
    lines.append("half=" + json.dumps(half_jobs(names["boards"])))
    return lines


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def names(a, b):
    """Paths that differ between two commits, or None when git can't say.
    --no-renames: a renamed file is listed under its old name and its new one. With rename detection only the new
    name shows, and a suite that read the old one would be skipped."""
    code, out, _ = git("diff", "--name-only", "--no-renames", a, b)
    return None if code else [c for c in out.split("\n") if c]


def base_of_head():
    """The commit the pull request starts from. Actions checks out the merge of the base branch and the pull
    request: its first parent is the base. Otherwise the merge base with the base branch, or None."""
    if git("rev-parse", "--verify", "-q", "HEAD^2")[0] == 0:
        return git("rev-parse", "HEAD^1")[1]
    ref = os.environ.get("GITHUB_BASE_REF", "")
    code, out, _ = git("merge-base", "HEAD", f"origin/{ref}") if ref else (1, "", "")
    return out if code == 0 and out else None


def main():
    d = sys.argv[1]
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    sha_f = os.path.join(d, "SHA")
    traced = pathlib.Path(sha_f).read_text().strip() if os.path.exists(sha_f) else None
    lines, run = [], {}
    lay = layouts()
    SUITES = suites(lay)
    if event != "pull_request" or not traced:
        why = "not a pull request" if event != "pull_request" else "no dependency record from main yet"
        run = {s: True for s in SUITES}
        lines.append(f"All suites run: {why}.")
    else:
        base = base_of_head()
        own = names(base, "HEAD") if base else None
        since = names(traced, base) if base else None
        if own is None or since is None:                 # no base to split at: everything since the record counts
            own, since, base = names(traced, "HEAD"), [], None
        if own is None:
            run = {s: True for s in SUITES}
            lines.append(f"All suites run: can't diff against {traced[:9]}.")
        else:
            code, n, _ = git("rev-list", "--count", "--first-parent", f"{traced}..{base}") if base else (1, "", "")
            if code == 0 and n.isdigit() and int(n) > BEHIND:
                # one or two behind is a run on main still going; more means main's runs are not saving the record
                print(f"::warning title=The record is {n} merges behind::The record of what the suites read is of {traced[:9]}, "
                      f"{n} commits of the base branch behind this pull request's base {base[:9]}: see whether the "
                      f"record-deps job of the runs on that branch ran")
            lines.append(f"The pull request changes {len(own)} files" + (f" from its base {base[:9]}" if base else "")
                         + f". The record is of {traced[:9]}, the last full run on main"
                         + (f", {len(since)} changed files behind the base.\n" if since else ".\n"))
            found = {}
            for s in SUITES:
                f = os.path.join(d, s + ".txt")
                deps = [l.strip() for l in pathlib.Path(f).read_text().split("\n") if l.strip()] if os.path.exists(f) else []
                found[s] = (decide_pr(deps, own, since) if deps else ["no dependency record for this suite"]), deps
            for s in SUITES:
                if s.startswith("boards-") and found["controller"][0] and not found[s][0]:
                    found[s] = (["the controller suite runs, and the half boards are simulated against its board"],
                                found[s][1])
            for s in SUITES:
                why, deps = found[s]
                run[s] = bool(why)
                lines.append(f"- **{s}**: " + ("runs: " + "; ".join(why[:8]) + (" ..." if len(why) > 8 else "")
                                               if why else f"skipped: the pull request changes none of the {len(deps)} "
                                                           f"files it reads"))
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as o:
        o.write("\n".join(outputs(run, lay)) + "\n")
    jobs = half_jobs([name for name in lay if run.get(f"boards-{name}")])
    if jobs:
        per = {}
        for j in jobs:
            per.setdefault((j["layout"], j["shards"]), []).append(j["board"])
        lines.append("\nHalf-board jobs: " + "; ".join(
            f"{name}: {len(set(b))} boards, " + ("one job each" if n == 1 else f"{n} racing jobs each (a random router)")
            for (name, n), b in per.items()) + ".")
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as o:
        o.write("## Check suites\n\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
