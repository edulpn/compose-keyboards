"""Checks imports.py on throwaway trees: python3 .github/ci/test_imports.py (exit 1 on a wrong verdict)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import imports  # noqa: E402

BASE = {
    "compose/__init__.py": "REPO_ROOT = '.'\n",
    "compose/__main__.py": "COMMANDS = {'build': ('compose.a', 'builds'), 'sim': ('compose.pkg.b', 'simulates')}\n",
    "compose/a.py": "import os\nX = 1\ntry:\n    import fast as speed\nexcept ImportError:\n    speed = None\n"
                    "if X:\n    Y, (Z, W) = 2, (3, 4)\ndef f():\n    global CACHE\n    CACHE = 1\nclass K:\n    pass\n",
    "compose/pkg/__init__.py": "",
    "compose/pkg/b.py": "from compose import a as A\nfrom compose.a import X, f, K, speed\nQ = A.X + A.Y + A.Z + A.W\n",
    "layouts/__init__.py": "",
    "layouts/one/__init__.py": "",
    "layouts/one/layout.py": "from compose.pkg import b\nfrom compose import pkg\nimport compose.pkg.b as B\nN = b.Q + B.Q + pkg.b.Q\n",
}
# (what is added to the tree, how many names should fail to resolve, a word the report must have)
CASES = [
    ("the tree as it is", {}, 0, ""),
    ("a module that is not there", {"compose/c.py": "import compose.nope\n"}, 1, "no such module"),
    ("a name its module does not have", {"compose/c.py": "from compose.a import nope\n"}, 1, "has no nope"),
    ("from a module that is not there", {"compose/c.py": "from compose.gone import X\n"}, 1, "no such module"),
    ("a name taken through an alias", {"compose/c.py": "from compose import a as A\nV = A.nope\n"}, 1, "A.nope"),
    ("the same inside a function", {"compose/c.py": "def g():\n    from compose import a as A\n    return A.nope\n"}, 1, "A.nope"),
    ("a module alias used in a method", {"compose/c.py": "from compose import a as A\nclass C:\n    def m(self):\n        return A.nope\n"}, 1, "A.nope"),
    ("a function's own variable of that name", {"compose/c.py": "from compose import a as A\ndef g(A):\n    return A.nope\ndef h():\n"
                                                             "    A = object()\n    return A.nope\n"}, 0, ""),
    ("a loop variable of that name", {"compose/c.py": "from compose import a as A\nV = [A.nope for A in ()]\nW = lambda A: A.nope\n"}, 0, ""),
    ("an alias only inside one function", {"compose/c.py": "def g():\n    from compose import a as A\n    return A.X\ndef h(A):\n    return A.nope\n"}, 0, ""),
    ("a name a function declares global", {"compose/c.py": "from compose import a as A\nV = A.CACHE\n"}, 0, ""),
    ("a name another module sets on it", {"compose/c.py": "from compose import a as A\nA.LATE = 1\n",
                                          "compose/d.py": "from compose import a as A\nV = A.LATE\n"}, 0, ""),
    ("a star import that brings the name", {"compose/c.py": "from compose.a import *\n", "compose/d.py": "from compose.c import X, K\n"}, 0, ""),
    ("a star import that does not", {"compose/c.py": "from compose.a import *\n", "compose/d.py": "from compose.c import nope\n"}, 1, "has no nope"),
    ("a module that makes its names at run time", {"compose/c.py": "globals().update(V=1)\n", "compose/d.py": "from compose.c import V\n"}, 0, ""),
    ("a command whose module is not there", {"compose/__main__.py": "COMMANDS = {'build': ('compose.gone', 'builds')}\n"}, 1, "command build"),
    ("a layout taking a name the platform lost", {"layouts/one/preroute.py": "from compose.pkg import b as H\nR = H.ROUTER\n"}, 1, "H.ROUTER"),
    ("a rev 2 command built on a shared module", {"compose/__main__.py": "COMMANDS = {'build': ('compose.a', ''), 'half-rev2': ('compose.c', '')}\n",
                                                  "compose/c.py": "from compose.pkg import shared\nV = shared.S\n",
                                                  "compose/pkg/shared.py": "S = 1\n"}, 0, ""),
    ("a rev 2 command that imports rev 1's module", {"compose/__main__.py": "COMMANDS = {'build': ('compose.a', ''), 'half-rev2': ('compose.c', '')}\n",
                                                     "compose/c.py": "def f():\n    from compose import a\n"}, 1, "reaches rev 1's compose.a"),
    ("the same through a module in between", {"compose/__main__.py": "COMMANDS = {'build': ('compose.a', ''), 'half-rev2': ('compose.c', '')}\n",
                                              "compose/c.py": "from compose.pkg import b\n"}, 1, "compose.a <- compose.pkg.b <- compose.c"),
    ("a controller command built on what is shared", {"compose/__main__.py": "COMMANDS = {'build': ('compose.a', ''), 'controller': ('compose.c', '')}\n",
                                                      "compose/c.py": "from compose.pkg import shared\nV = shared.S\n",
                                                      "compose/pkg/shared.py": "S = 1\n"}, 0, ""),
    ("a controller command that loads the layout", {"compose/__main__.py": "COMMANDS = {'build': ('compose.a', ''), 'sim-controller': ('compose.c', '')}\n",
                                                    "compose/c.py": "from compose.pkg import shared\n",
                                                    "compose/pkg/shared.py": "def f():\n    from compose import geom\n",
                                                    "compose/geom.py": "LAYOUT = 1\n"}, 1, "compose.geom <- compose.pkg.shared <- compose.c"),
    ("a controller command that imports a layout's module", {"compose/__main__.py": "COMMANDS = {'build': ('compose.a', ''), 'controller': ('compose.c', '')}\n",
                                                             "compose/c.py": "from layouts.one import extra\n",
                                                             "layouts/one/extra.py": "E = 1\n"}, 1, "reaches a layout (layouts.one <- compose.c)"),
    ("other packages' names are not ours to check", {"compose/c.py": "import numpy as np\nfrom shapely.geometry import Nope\nV = np.nope\n"}, 0, ""),
]
# the list of known ones: (tree, the list, how many problems)
KNOWN_CASES = [
    ("a listed one is left out of the count", {"compose/c.py": "from compose import a as A\nV = A.nope\n"}, {("compose/c.py", "A.nope"): "why"}, 0),
    ("another in the same file is still counted", {"compose/c.py": "from compose import a as A\nV = A.nope + A.gone\n"}, {("compose/c.py", "A.nope"): "why"}, 1),
    ("a listed one that resolves now has to come off", {"compose/c.py": "from compose import a as A\nV = A.X\n"}, {("compose/c.py", "A.X"): "why"}, 1),
]


def run(extra, known):
    with tempfile.TemporaryDirectory() as d:
        for path, text in {**BASE, **extra}.items():
            p = os.path.join(d, path)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(text)
        return imports.Repo(os.path.realpath(d)).problems(known)[0]


def main():
    bad = 0
    for name, extra, want, word in CASES:
        got = run(extra, {})
        ok = len(got) == want and all(word in g for g in got)
        bad += not ok
        print(("ok   " if ok else "FAIL ") + f"{name}: {len(got)} unresolved" + ("" if ok else f" (expected {want}): {got}"))
    for name, extra, known, want in KNOWN_CASES:
        got = run(extra, known)
        ok = len(got) == want
        bad += not ok
        print(("ok   " if ok else "FAIL ") + f"{name}: {len(got)} problems" + ("" if ok else f" (expected {want}): {got}"))
    n = len(CASES) + len(KNOWN_CASES)
    print(f"{n - bad}/{n} verdicts as expected")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
