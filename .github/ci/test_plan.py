"""Checks plan.py end to end on a throwaway repository: python3 .github/ci/test_plan.py (exit 1 on a wrong plan).

The repository is built the way a pull request reaches the plan job: main with a recorded commit, a commit main
gained after the record, a branch from there, and HEAD on the merge of the two (what Actions checks out)."""
import os
import subprocess
import sys
import tempfile

PLAN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plan.py")
SUITES = ("rev1", "rev2", "boards")
DEPS = {"rev1": ["compose/params.py", "compose/firmware.py"], "rev2": ["compose/params.py", "compose/firmware_rev2.py"],
        "boards": ["compose/params.py", "compose/sim/half.py"]}


def git(repo, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                       cwd=repo, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout.strip()


def commit(repo, files, msg):
    for path, text in files.items():
        full = os.path.join(repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def plan(repo, deps_dir, record, event="pull_request", base_ref="main"):
    open(os.path.join(deps_dir, "SHA"), "w").write(record + "\n")
    out = os.path.join(deps_dir, "out.txt")
    open(out, "w").close()
    env = dict(os.environ, GITHUB_EVENT_NAME=event, GITHUB_BASE_REF=base_ref, GITHUB_OUTPUT=out, GITHUB_STEP_SUMMARY=os.devnull)
    subprocess.run([sys.executable, PLAN, deps_dir], cwd=repo, env=env, capture_output=True, text=True, check=True)
    got = dict(l.strip().split("=") for l in open(out) if l.strip())
    return tuple(got[f"run_{s}"] == "true" for s in SUITES)


def main():
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        repo, deps = os.path.join(tmp, "repo"), os.path.join(tmp, "deps")
        os.makedirs(repo); os.makedirs(deps)
        for s, files in DEPS.items():
            open(os.path.join(deps, s + ".txt"), "w").write("\n".join(files) + "\n")
        git(repo, "init", "-q", "-b", "main")
        recorded = commit(repo, {"compose/params.py": "A = 1\n", "compose/firmware.py": "1\n", "compose/firmware_rev2.py": "1\n",
                                 "compose/sim/half.py": "1\n", "README.md": "one\n", "docs/images/top.png": "png 1\n"}, "recorded")
        moved = commit(repo, {"compose/firmware_rev2.py": "2\n"}, "main gains a rev 2 change after the record")

        def pull_request(files):
            """HEAD on the merge of main (at `moved`) and a branch from it that changes `files`; returns to main after."""
            git(repo, "checkout", "-q", "-B", "pr", moved)
            commit(repo, files, "the pull request")
            git(repo, "checkout", "-q", "--detach", moved)
            git(repo, "merge", "-q", "--no-ff", "-m", "merge", "pr")

        cases = [
            ("pictures and a document, record behind the base", {"docs/images/top.png": "png 2\n", "README.md": "two\n"}, recorded, (False, False, False)),
            ("pictures and a document, record of the base", {"docs/images/top.png": "png 2\n", "README.md": "two\n"}, moved, (False, False, False)),
            ("a file no suite reads, record behind the base: rev2 can't vouch for its list", {"compose/new.py": "1\n"}, recorded, (False, True, False)),
            ("a file no suite reads, record of the base", {"compose/new.py": "1\n"}, moved, (False, False, False)),
            ("a rev 1 file, record behind the base", {"compose/firmware.py": "2\n"}, recorded, (True, True, False)),
            ("shared params", {"compose/params.py": "A = 2\n"}, moved, (True, True, True)),
            ("a CI file", {".github/workflows/checks.yml": "x\n"}, moved, (True, True, True)),
        ]
        for name, files, record, want in cases:
            pull_request(files)
            got = plan(repo, deps, record)
            bad += got != want
            print(("ok    " if got == want else "WRONG ") + f"{name}: " + ", ".join(f"{s} {'runs' if r else 'skipped'}" for s, r in zip(SUITES, got)))
        # not on a merge and no base branch to find: everything since the record counts, as it did before
        git(repo, "checkout", "-q", "-B", "pr", moved)
        commit(repo, {"README.md": "three\n"}, "a document")
        got = plan(repo, deps, recorded, base_ref="")
        bad += got != (False, True, False)
        print(("ok    " if got == (False, True, False) else "WRONG ") + f"no merge to split at, record behind: rev2 {'runs' if got[1] else 'skipped'}")
        got = plan(repo, deps, recorded, event="push")
        bad += got != (True, True, True)
        print(("ok    " if got == (True, True, True) else "WRONG ") + "a push: everything runs")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
