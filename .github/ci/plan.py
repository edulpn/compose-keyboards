"""Which check suites a CI run needs.

    python3 .github/ci/plan.py <deps-dir>

<deps-dir> holds what the last full run on main recorded: SHA (the commit it ran on) and <suite>.txt for every
suite (the files each suite read, from traced.py). On a pull request a suite runs if the pull request itself
changes anything the suite read (see affected.py); everywhere else, and whenever a record is missing, every
suite runs. Writes run_<suite>=true|false to $GITHUB_OUTPUT and the reasons to the job summary.

The record can be older than the pull request's base: a full run on main takes a while, and a pull request opened
meanwhile is planned against the record before it. What main gained in between is not the pull request's to
check, so the changes are split in two: base to head (the pull request's own) and record to base.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from affected import decide_pr  # noqa: E402

SUITES = ("rev1", "rev2", "boards")


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
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
    traced = open(sha_f).read().strip() if os.path.exists(sha_f) else None
    lines, run = [], {}
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
            lines.append(f"The pull request changes {len(own)} files" + (f" from its base {base[:9]}" if base else "")
                         + f". The record is of {traced[:9]}, the last full run on main"
                         + (f", {len(since)} changed files behind the base.\n" if since else ".\n"))
            for s in SUITES:
                f = os.path.join(d, s + ".txt")
                deps = [l.strip() for l in open(f) if l.strip()] if os.path.exists(f) else []
                why = decide_pr(deps, own, since) if deps else ["no dependency record for this suite"]
                run[s] = bool(why)
                lines.append(f"- **{s}**: " + ("runs: " + "; ".join(why[:8]) + (" ..." if len(why) > 8 else "")
                                               if why else f"skipped: the pull request changes none of the {len(deps)} "
                                                           f"files it reads"))
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as o:
        for s in SUITES:
            o.write(f"run_{s}={'true' if run[s] else 'false'}\n")
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as o:
        o.write("## Check suites\n\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
