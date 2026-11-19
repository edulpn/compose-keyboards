"""The commit a pull request's run is compared with.

    python3 .github/ci/base.py        -> prints it

Actions checks out the merge of the base branch and the pull request, so what the run builds is the pull request
on top of that merge's first parent: that commit is the base, and plan.py plans from it too. The event's own
base (github.event.pull_request.base.sha, BASE_SHA here) can be an older commit of the base branch; compared with
that one, whatever the branch gained since would be read as this pull request's difference. It is the fallback
where the checkout is no merge and has no base branch to find.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from plan import base_of_head  # noqa: E402

if __name__ == "__main__":
    print(base_of_head() or os.environ.get("BASE_SHA", ""))
