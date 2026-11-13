"""Which check suites a CI run needs.

    python3 .github/ci/plan.py <deps-dir>

<deps-dir> holds what the last full run on main recorded: SHA (the commit it ran on) and <suite>.txt for every
suite (the files each suite read, from traced.py). On a pull request a suite runs if anything it read
differs between that commit and the one under test (see affected.py); everywhere else, and whenever a record
is missing, every suite runs. Writes run_<suite>=true|false to $GITHUB_OUTPUT and the reasons to the job
summary.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from affected import decide  # noqa: E402

SUITES = ("rev1", "rev2", "boards")


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
        r = subprocess.run(["git", "diff", "--name-only", traced, "HEAD"], capture_output=True, text=True)
        if r.returncode != 0:
            run = {s: True for s in SUITES}
            lines.append(f"All suites run: can't diff against {traced[:9]} ({r.stderr.strip()}).")
        else:
            changed = [c for c in r.stdout.split("\n") if c]
            lines.append(f"{len(changed)} files differ from {traced[:9]}, the last full run on main.\n")
            for s in SUITES:
                f = os.path.join(d, s + ".txt")
                deps = [l.strip() for l in open(f) if l.strip()] if os.path.exists(f) else []
                why = decide(deps, changed) if deps else ["no dependency record for this suite"]
                run[s] = bool(why)
                lines.append(f"- **{s}**: " + ("runs: " + "; ".join(why[:8]) + (" ..." if len(why) > 8 else "")
                                               if why else f"skipped: none of the {len(deps)} files it reads changed"))
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as o:
        for s in SUITES:
            o.write(f"run_{s}={'true' if run[s] else 'false'}\n")
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as o:
        o.write("## Check suites\n\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
