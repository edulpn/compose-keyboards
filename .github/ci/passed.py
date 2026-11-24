"""The checks-passed job: whether every check suite that had to run passed, and a list of every suite with its result.

    python3 .github/ci/passed.py

Reads from the environment:

    NEEDS       toJSON(needs) of the job: each job it waits on, with its result and (the plan's) outputs
    PICTURES    true when this is a manual run that asked for the docs' pictures
    GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID, GITHUB_API_URL
                to list this run's jobs by name. A matrix job's result in NEEDS is all its jobs together, so the
                listing is what tells one layout's suite from another's; without it (no token, the API not
                reached) each suite takes its jobs' result from NEEDS.

The suites are the plan job's (plan.py, its output "suites"): each one either runs, or is skipped with the plan's
reason. A suite that runs is passed when every job of it passed, and failed when any failed or was cancelled, or
when none of its jobs ran at all (a job condition that left out a suite the plan wanted). Its jobs, by name:

    rev2-<layout>     rev2 (<layout>)
    boards-<layout>   controller (it builds the board the halves are simulated against), half (<layout> ...),
                      boards-sim (<layout>)
    controller        controller, spice

A skipped job of a suite that runs (boards-sim when a half board failed) is the failed job's doing and changes
nothing. pictures is listed too, but it checks nothing and so never fails the run: skipped unless a manual run
asks for it.

Exit 1 when the plan job didn't pass, any suite failed, or any job waited on but pictures failed. The list goes to the job summary as a table, and to the
log as one line: "N passed, M skipped: ..." (and the failed ones first, when there are any).
"""
import json
import os
import sys
import urllib.request

OK = "success"
BAD = ("failure", "cancelled", "timed_out")


def jobs_of(suite, jobs):
    """The names in `jobs` that belong to `suite`."""
    if suite == "controller":
        return [j for j in jobs if j in ("controller", "spice")]
    kind, layout = suite.split("-", 1)
    if kind == "rev2":
        return [j for j in jobs if j == f"rev2 ({layout})"]
    return [j for j in jobs if j == "controller" or j == f"boards-sim ({layout})"
            or j.startswith(f"half ({layout} ") or j == f"half ({layout})"]


def needs_jobs(needs):
    """{job name: result} from NEEDS alone: a matrix job's one result stands for each of its layouts' names."""
    plan = needs.get("plan", {}).get("outputs", {})
    lists = {k: json.loads(plan.get(k) or "[]") for k in ("rev2", "boards")}
    names = {}
    for job, v in needs.items():
        r = v.get("result", "")
        if job == "rev2":
            names.update({f"rev2 ({l})": r for l in lists["rev2"]})
        elif job == "boards-sim":
            names.update({f"boards-sim ({l})": r for l in lists["boards"]})
        elif job == "half":
            names.update({f"half ({l})": r for l in lists["boards"]})
        elif job == "pictures":
            names.update({f"pictures ({l})": r for l in lists["boards"]} or {"pictures": r})
        else:
            names[job] = r
    return names


def listed_jobs():
    """{job name: conclusion} of this run's latest attempt at each job, from the API, or None when it can't say.
    A job still going (this one) has no conclusion and is left out."""
    env = os.environ
    if not all(env.get(k) for k in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")):
        return None
    api = env.get("GITHUB_API_URL", "https://api.github.com")
    out, page = {}, 1
    try:
        while True:
            req = urllib.request.Request(
                f"{api}/repos/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}/jobs?filter=latest&per_page=100&page={page}",
                headers={"Authorization": f"Bearer {env['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                got = json.load(r)["jobs"]
            out.update({j["name"]: j["conclusion"] for j in got if j.get("conclusion")})
            if len(got) < 100:
                return out
            page += 1
    except (OSError, ValueError, KeyError) as e:
        print(f"::notice::this run's jobs could not be listed ({e}): each suite takes its jobs' result from needs")
        return None


def verdict(needs, jobs, pictures):
    """(rows, ok): rows are (suite, result, why) in the plan's order, then pictures; ok is False when the run fails."""
    plan = needs.get("plan", {})
    if plan.get("result") != OK:
        return [("plan", "failed", f"the plan job's result is {plan.get('result') or 'missing'}: no suite list")], False
    rows, ok = [], True
    for s in json.loads(plan.get("outputs", {}).get("suites") or "[]"):
        name, skip = s["suite"], s["skip"]
        if skip:
            rows.append((name, "skipped", skip))
            continue
        mine = {j: jobs[j] for j in jobs_of(name, jobs)}
        bad = sorted(j for j, r in mine.items() if r in BAD)
        if bad:
            rows.append((name, "failed", ", ".join(f"{j}: {mine[j]}" for j in bad)))
        elif not any(r == OK for r in mine.values()):
            rows.append((name, "failed", "the plan runs it, but none of its jobs ran"))
        else:
            rows.append((name, "passed", ", ".join(sorted(j for j, r in mine.items() if r == OK))))
            continue
        ok = False
    # as before this list: any job waited on that failed fails the run, whichever suite it is or isn't listed under
    bad = sorted(j for j, v in needs.items() if j != "pictures" and v.get("result") in BAD)
    if bad and ok:
        rows.append(("other", "failed", ", ".join(f"{j}: {needs[j]['result']}" for j in bad)))
        ok = False
    pics ={j: r for j, r in jobs.items() if j == "pictures" or j.startswith("pictures (")}
    if not pictures:
        rows.append(("pictures", "skipped", "manual runs only (pictures=true); it checks nothing"))
    else:
        bad = sorted(j for j, r in pics.items() if r in BAD)
        rows.append(("pictures", "failed" if bad else "passed" if any(r == OK for r in pics.values()) else "skipped",
                     (", ".join(f"{j}: {pics[j]}" for j in bad) or ", ".join(sorted(pics)) or "did not run")
                     + " (it checks nothing: the run's result doesn't depend on it)"))
    return rows, ok


def line(rows):
    """The log's one line: the failed ones first, then 'N passed, M skipped: the skipped ones (why)'."""
    by = {k: [r for r in rows if r[1] == k] for k in ("failed", "passed", "skipped")}
    s = "; ".join(f"FAILED {n} ({why})" for n, _, why in by["failed"])
    s += ("; " if s else "") + f"{len(by['passed'])} passed, {len(by['skipped'])} skipped"
    if by["skipped"]:
        s += ": " + "; ".join(f"{n} ({why})" for n, _, why in by["skipped"])
    return s


def main():
    needs = json.loads(os.environ.get("NEEDS") or "{}")
    listed = listed_jobs()
    jobs = needs_jobs(needs) if listed is None else listed
    rows, ok = verdict(needs, jobs, os.environ.get("PICTURES") == "true")
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as o:
        o.write("## Suites\n\n| Suite | Result | Jobs, or why |\n|---|---|---|\n"
                + "".join(f"| {n} | {r} | {why} |\n" for n, r, why in rows))
    print(line(rows))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
