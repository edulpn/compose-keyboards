"""Checks passed.py, the checks-passed job's verdict and list: python3 .github/ci/test_passed.py (exit 1 when wrong)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import passed as P  # noqa: E402

AFFECTED = "not affected by this pull request's changes (none of the 40 files it reads)"


def needs(suites, rev2_layouts=(), board_layouts=(), **results):
    """NEEDS as Actions hands it: the plan's outputs, and each job's result (skipped unless named)."""
    plan = {"result": results.pop("plan", "success"),
            "outputs": {"suites": json.dumps([{"suite": s, "skip": why} for s, why in suites]),
                        "rev2": json.dumps(list(rev2_layouts)), "boards": json.dumps(list(board_layouts))}}
    jobs = {j: {"result": results.get(j.replace("-", "_"), "skipped"), "outputs": {}}
            for j in ("rev2", "controller", "spice", "half", "boards-sim", "pictures")}
    return {"plan": plan, **jobs}


def main():
    bad = 0

    def check(name, got, want):
        nonlocal bad
        bad += got != want
        print(("ok    " if got == want else "WRONG ") + name + ("" if got == want else f"\n      got  {got}\n      want {want}"))

    def results(rows):
        return {n: r for n, r, _ in rows}

    ALL58 = [("rev2-compose58", None), ("boards-compose58", None), ("controller", None)]
    ran58 = {"rev2 (compose58)": "success", "controller": "success", "spice": "success",
             "half (compose58 half_rev2_hotswap)": "success", "half (compose58 half_rev2_solder)": "success",
             "boards-sim (compose58)": "success"}
    n = needs(ALL58, ["compose58"], ["compose58"], rev2="success", controller="success", spice="success",
              half="success", boards_sim="success")

    rows, ok = P.verdict(n, ran58, pictures=False)
    check("a full run that passes", (results(rows), ok),
          ({"rev2-compose58": "passed", "boards-compose58": "passed", "controller": "passed", "pictures": "skipped"}, True))
    check("its log line", P.line(rows),
          "3 passed, 1 skipped: pictures (manual runs only (pictures=true); it checks nothing)")

    # a docs-only pull request: the plan skips everything, and the line says so instead of "all passed"
    rows, ok = P.verdict(needs([(s, AFFECTED) for s, _ in ALL58]), {}, pictures=False)
    check("a docs-only pull request", (results(rows), ok),
          ({"rev2-compose58": "skipped", "boards-compose58": "skipped", "controller": "skipped", "pictures": "skipped"}, True))
    check("its log line starts with the count", P.line(rows).split(":")[0], "0 passed, 4 skipped")

    # the boards change alone: the controller job builds the board for them, the controller suite is skipped
    boards = [("rev2-compose58", AFFECTED), ("boards-compose58", None), ("controller", AFFECTED)]
    got = {j: r for j, r in ran58.items() if j not in ("rev2 (compose58)", "spice")}
    rows, ok = P.verdict(needs(boards, [], ["compose58"], controller="success", half="success", boards_sim="success"),
                         got, pictures=False)
    check("boards only", (results(rows), ok),
          ({"rev2-compose58": "skipped", "boards-compose58": "passed", "controller": "skipped", "pictures": "skipped"}, True))

    # two layouts in one matrix: the job listing tells their suites apart
    two = [("rev2-compose58", None), ("boards-compose58", AFFECTED), ("rev2-other40", None),
           ("boards-other40", AFFECTED), ("controller", AFFECTED)]
    listing = {"rev2 (compose58)": "success", "rev2 (other40)": "failure"}
    n2 = needs(two, ["compose58", "other40"], rev2="failure")
    rows, ok = P.verdict(n2, listing, pictures=False)
    check("one layout's rev2 fails, the other's passes", (results(rows)["rev2-compose58"], results(rows)["rev2-other40"], ok),
          ("passed", "failed", False))
    check("the failed one leads the log line", P.line(rows).split(";")[0], "FAILED rev2-other40 (rev2 (other40): failure)")
    # without the listing, the matrix's one result is each layout's
    rows, ok = P.verdict(n2, P.needs_jobs(n2), pictures=False)
    check("no listing: the matrix's result for each layout", (results(rows)["rev2-compose58"], results(rows)["rev2-other40"], ok),
          ("failed", "failed", False))

    # racing shards: one that found no route ends in success (its notice), so the suite passes on the others
    racing = {"controller": "success", "boards-sim (other40)": "success",
              **{f"half (other40 half_rev2_solder {i}/3)": "success" for i in (1, 2, 3)}}
    rows, ok = P.verdict(needs([("boards-other40", None)], [], ["other40"], controller="success", half="success",
                               boards_sim="success"), racing, pictures=False)
    check("racing half-board shards", (results(rows)["boards-other40"], ok), ("passed", True))
    check("their names are the suite's jobs", len(P.jobs_of("boards-other40", racing)), 5)
    check("another layout's prefix isn't", P.jobs_of("boards-other4", racing), ["controller"])

    # the plan wants a suite, but no job of it ran (a job condition that left it out): failed, not a silent skip
    rows, ok = P.verdict(needs(ALL58, ["compose58"], ["compose58"], controller="success", spice="success", half="success",
                               boards_sim="success"),
                         {j: r for j, r in ran58.items() if j != "rev2 (compose58)"}, pictures=False)
    check("a planned suite whose jobs didn't run", (results(rows)["rev2-compose58"], ok), ("failed", False))

    # a half board fails: boards-sim is skipped behind it, the suite names the failed job
    hf = dict(ran58, **{"half (compose58 half_rev2_solder)": "failure"})
    del hf["boards-sim (compose58)"]
    rows, ok = P.verdict(needs(ALL58, ["compose58"], ["compose58"], rev2="success", controller="success", spice="success",
                               half="failure"), hf, pictures=False)
    check("a failed half board", ([r for r in rows if r[0] == "boards-compose58"][0][1:], ok),
          (("failed", "half (compose58 half_rev2_solder): failure"), False))

    # the plan failed: nothing to list, the run fails
    rows, ok = P.verdict(needs([], plan="failure"), {}, pictures=False)
    check("the plan job failed", (results(rows), ok), ({"plan": "failed"}, False))

    # pictures: a manual run that asks reports it, but its failure doesn't fail the run
    n = needs(ALL58, ["compose58"], ["compose58"], rev2="success", controller="success", spice="success",
              half="success", boards_sim="success", pictures="failure")
    rows, ok = P.verdict(n, dict(ran58, **{"pictures (compose58)": "failure"}), pictures=True)
    check("failed pictures don't fail the run", (results(rows)["pictures"], ok), ("failed", True))
    rows, ok = P.verdict(n, dict(ran58, **{"pictures (compose58)": "success"}), pictures=True)
    check("pictures that ran", results(rows)["pictures"], "passed")

    # a job waited on fails outside every suite listed (a stale suite list): still fails the run, as before
    n = needs([("rev2-compose58", None)], ["compose58"], rev2="success", spice="failure")
    rows, ok = P.verdict(n, {"rev2 (compose58)": "success", "spice": "failure"}, pictures=False)
    check("a failed job no suite lists", (results(rows).get("other"), ok), ("failed", False))

    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
