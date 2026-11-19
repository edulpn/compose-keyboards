"""
Where a run writes. Every command takes its folder as its first argument; when none is named, python3 -m compose
names one, so that two keyboards, or the two revs of one, never write over each other:

    out/<layout>/rev1     a keyboard's rev 1 commands
    out/<layout>/rev2     its rev 2 commands
    out/<layout>/order    its rev 2 order folder (order-rev2; ORDER_OUT names another)
    out/controller        the controller rev 2's commands: one board under every layout, so one folder
                          (a keyboard's commands read it from there; CTRL_OUT names another)
    out_cache/<layout>    what a slow solve leaves for the next run
"""
import os

CONTROLLER = os.path.join("out", "controller")


def default(rev, layout):
    """The folder of a command of this rev (None: the controller rev 2's) for this layout."""
    return CONTROLLER if rev is None else os.path.join("out", layout, f"rev{rev}")


def controller():
    """Where a keyboard's commands find the controller rev 2's boards."""
    return os.environ.get("CTRL_OUT", CONTROLLER)


def order(layout):
    """The order folder of this layout's keyboard."""
    return os.environ.get("ORDER_OUT", os.path.join("out", layout, "order"))


def cache(layout):
    return os.path.join("out_cache", layout)
