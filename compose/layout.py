"""
Key layouts. A layout is a list of keys for the LEFT half in its local frame
(x toward the inner edge, y toward the back, origin at the centre of the
outer key of the top row), plus where the case hardware goes. The right half
is the mirror image.

Each key: x, y (mm), rot (deg, + = counter-clockwise), w, h (units),
row/col (matrix position), label_l / label_r (legends for renders),
grid (False for a key that is not one of the columns' keys: a thumb key, an extra key), accent (True for a
keycap in the renders' second colour).
Hardware positions are expressed relative to keys/outline so they follow
pitch and margin changes.

Each layout lives in layouts/<name>/layout.py and defines layout() -> Layout.
"""
import math
from dataclasses import dataclass, field
from compose import params as PR


@dataclass
class Key:
    x: float
    y: float
    rot: float = 0.0
    w: float = 1.0
    h: float = 1.0
    row: int = 0
    col: int = 0
    label_l: str = ""
    label_r: str = ""
    grid: bool = True       # one of the columns' keys. False: a thumb key or an extra key; rev 2's LED chain runs
    #                         through the columns first, then through these from the inner edge outwards
    accent: bool = False    # its keycap takes the second colour in the rev 2 renders


@dataclass
class Layout:
    name: str
    keys: list
    inner_col: int                  # column index on the inner edge
    inner_col_stagger: float        # its stagger (units), sets the splay pivot
    posts: list = field(default_factory=list)     # M2 plate supports (x, y)
    feet: list = field(default_factory=list)      # rubber feet (x, y)
    art: dict = None                # where the half boards' art goes (compose/pcb/art.py): for "title" (the logo and
    #                                 name in bare copper), "tagline" (silkscreen), "labels" (the lhs / rhs build labels)
    #                                 and, optionally, "board_id": an anchor (x, y), or several in order of preference.
    #                                 An anchor (x, y, 90) runs that piece up the board, along an edge


def key_point(k, dx, dy):
    """Point at (dx, dy) in a key's own rotated frame."""
    a = math.radians(k.rot)
    return (k.x + dx * math.cos(a) - dy * math.sin(a), k.y + dx * math.sin(a) + dy * math.cos(a))


def get(name=None):
    """The layout named by params.LAYOUT (or `name`): layouts/<name>/layout.py, function `layout()`."""
    import importlib
    import sys
    from compose import REPO_ROOT
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    return importlib.import_module(f"layouts.{name or PR.LAYOUT}.layout").layout()
