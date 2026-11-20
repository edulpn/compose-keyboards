"""
Compose: the platform behind the Compose keyboards. One case generator, one controller standard,
one set of checks and simulations, shared by every layout in layouts/.

Run things with `python3 -m compose <command> [outdir] ...` (see `python3 -m compose --help`).
"""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def must(ok, why=""):
    """A check that is part of a build: stops it when the condition does not hold. Unlike an assert statement it
    still runs under `python3 -O`."""
    if not ok:
        raise AssertionError(why)
