"""Does every name the repository's code takes from its own modules exist?

    python3 .github/ci/imports.py [root]         exit 1 if one does not

Reads the source of compose/ and layouts/ without running any of it (so it needs no KiCad, CadQuery or
ngspice) and checks, wherever they are written, at the top of a file or inside a function:

  import compose.x.y                  the module exists
  from compose.x import a, b          the module exists, and each name is one of its modules or is bound at its
                                      top level (assigned, defined, or imported there)
  from compose.x import y as Y
  ... Y.name ...                      `name` is bound at the top level of compose.x.y, wherever Y means that
                                      module (not where a function has its own variable of that name)
  COMMANDS in compose/__main__.py     every command's module exists, no command but rev 1's own reaches one of
                                      rev 1's modules through its imports (REV1 below), and the controller
                                      rev 2's commands reach no layout (NO_LAYOUT below)

This is what breaks when code moves between modules, and it covers the commands no CI job runs (rev 1's
boards, simulation and renders, which are released and not rebuilt). It does not check calls, arguments or
names built at run time (importlib.import_module with a computed name).
"""
import ast
import os
import sys

PACKAGES = ("compose", "layouts")
# Names known not to resolve, with the reason they are left: (file, name as written) -> why. One that starts
# resolving, or goes away, has to be taken off this list: the check fails until it is.
KNOWN = {}
# Rev 1 is released and kept as it is; the controller rev 2 and rev 2 are built on what is shared, not on rev 1's
# modules, so a change to rev 1's code cannot reach them (nor theirs it). Rev 1's commands, and the modules that
# are rev 1's without being a command's:
REV1 = ("build", "pcb", "firmware", "model", "checks", "sim", "render", "coupons", "tilt-risers")
REV1_ALSO = ("compose.pcb.layout", "compose.case.sandwich", "compose.case.assembly")
# The controller rev 2 is one board under every layout: its build and its simulations load none. A layout is
# loaded by compose.geom (when it is imported), read through compose.layout, and kept in layouts/.
NO_LAYOUT = ("controller", "sim-controller", "spice-controller")
LAYOUT = ("compose.geom", "compose.layout", "layouts")
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef,
          ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def modules(root):
    """{dotted name: path} for every module and package under the repository's packages."""
    found = {}
    for pkg in PACKAGES:
        for d, dirs, files in os.walk(os.path.join(root, pkg)):
            dirs[:] = [x for x in dirs if x != "__pycache__" and x != "node_modules"]
            dotted = os.path.relpath(d, root).replace(os.sep, ".")
            if "__init__.py" in files:
                found[dotted] = os.path.join(d, "__init__.py")
            for f in files:
                if f.endswith(".py") and f != "__init__.py":
                    found[dotted + "." + f[:-3]] = os.path.join(d, f)
    return found


def targets(t):
    if isinstance(t, ast.Name):
        yield t.id
    elif isinstance(t, (ast.Tuple, ast.List)):
        for e in t.elts:
            yield from targets(e)
    elif isinstance(t, ast.Starred):
        yield from targets(t.value)


def bound(body, into_scopes=False):
    """Names a block binds: assignments, definitions, imports, loop and `with` targets. Statements nested in
    if / for / try / with count; the bodies of functions and classes do not (unless into_scopes: then only
    what they declare `global`)."""
    names, stars = set(), []
    todo = list(body)
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
            if into_scopes:
                for m in ast.walk(n):
                    if isinstance(m, ast.Global):
                        names.update(m.names)
            continue
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                names.update(targets(t))
        elif isinstance(n, (ast.For, ast.AsyncFor)):
            names.update(targets(n.target))
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            for i in n.items:
                if i.optional_vars is not None:
                    names.update(targets(i.optional_vars))
        elif isinstance(n, ast.Import):
            names.update(a.asname or a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                if a.name == "*":
                    stars.append(n)
                else:
                    names.add(a.asname or a.name)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        for field in ("body", "orelse", "finalbody", "handlers"):
            todo.extend(getattr(n, field, []) or [])
        if hasattr(ast, "Match") and isinstance(n, ast.Match):
            for c in n.cases:
                todo.extend(c.body)
    return names, stars


def source_of(node, here, mods):
    """The dotted module an `from ... import` statement names, relative ones resolved against `here`."""
    if not node.level:
        return node.module or ""
    base = here.split(".")
    if mods.get(here, "").endswith("__init__.py"):
        base.append("")
    base = base[:len(base) - node.level]
    return ".".join(base + ([node.module] if node.module else []))


class Repo:
    def __init__(self, root):
        self.root = root
        self.mods = modules(root)
        self.trees = {m: ast.parse(open(p, encoding="utf-8").read(), p) for m, p in self.mods.items()}
        self.names, self.open = {}, set()
        for m in self.mods:
            self._names(m, ())
        for m, tree in self.trees.items():               # a name another module sets on it: PK.PCB_OUT = ...
            for n, env in self._walk(m, tree):
                if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) and isinstance(n.value, ast.Name):
                    tgt = env.get(n.value.id)
                    if tgt in self.names:
                        self.names[tgt].add(n.attr)

    def ours(self, dotted):
        return dotted.split(".")[0] in PACKAGES

    def _names(self, m, seen):
        if m in self.names or m in seen:
            return self.names.get(m, set())
        tree = self.trees[m]
        names, stars = bound(tree.body, into_scopes=True)
        for s in stars:
            src = source_of(s, m, self.mods)
            if src in self.mods:
                names |= {x for x in self._names(src, seen + (m,)) if not x.startswith("_")}
            else:
                self.open.add(m)                         # a star import from outside: anything may be there
        if any(isinstance(n, ast.FunctionDef) and n.name == "__getattr__" for n in tree.body):
            self.open.add(m)                             # names made on demand
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "globals" for n in ast.walk(tree)):
            self.open.add(m)                             # names made at run time
        names |= {x[len(m) + 1:] for x in self.mods if x.startswith(m + ".") and "." not in x[len(m) + 1:]}
        self.names[m] = names
        return names

    def _aliases(self, body, m):
        """{local name: module} for the imports a block makes of the repository's modules."""
        out = {}
        for n in self._own(body):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if self.ours(a.name) and a.asname:
                        out[a.asname] = a.name
            elif isinstance(n, ast.ImportFrom):
                src = source_of(n, m, self.mods)
                if self.ours(src):
                    for a in n.names:
                        if src + "." + a.name in self.mods:
                            out[a.asname or a.name] = src + "." + a.name
        return out

    def _own(self, body):
        """Every node of a block that is not inside a nested function, class, lambda or comprehension."""
        todo = list(body)
        while todo:
            n = todo.pop()
            yield n
            if isinstance(n, SCOPES):
                continue
            todo.extend(ast.iter_child_nodes(n))

    def _locals(self, scope):
        """Names a scope binds for itself: its arguments, what it assigns, its loop and comprehension targets."""
        names = set()
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = scope.args
            names.update(x.arg for x in a.posonlyargs + a.args + a.kwonlyargs)
            names.update(x.arg for x in (a.vararg, a.kwarg) if x)
        if isinstance(scope, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for g in scope.generators:
                names.update(targets(g.target))
            return names
        body = scope.body if isinstance(scope.body, list) else [scope.body]
        for n in self._own(body):
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                names.add(n.id)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(n.name)
            elif isinstance(n, ast.Import):
                names.update(x.asname or x.name.split(".")[0] for x in n.names)
            elif isinstance(n, ast.ImportFrom):
                names.update(x.asname or x.name for x in n.names)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                names.add(n.name)
            elif isinstance(n, ast.NamedExpr):
                names.update(targets(n.target))
        return names

    def _walk(self, m, tree):
        """(node, {name: module it means there}) for every node of a module."""
        def visit(body, env):
            for n in self._own(body):
                yield n, env
                if isinstance(n, SCOPES):
                    inner = dict(env)
                    glob = {g for x in ast.walk(n) if isinstance(x, (ast.Global, ast.Nonlocal)) for g in x.names}
                    for name in self._locals(n) - glob:
                        inner.pop(name, None)
                    kids = n.body if isinstance(getattr(n, "body", None), list) else list(ast.iter_child_nodes(n))
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        inner.update(self._aliases(n.body, m))
                        yield from visit(n.decorator_list, env)
                    yield from visit(kids, inner)
        yield from visit(tree.body, self._aliases(tree.body, m))

    def problems(self, known=None):
        """(problems, known ones met): every name that does not resolve, less those listed in `known`; a listed
        one that was not met is a problem itself."""
        known = KNOWN if known is None else known
        found, met = [], set()
        for line in self._problems():
            hit = next((k for k in known if line.startswith(k[0] + ":") and f": {k[1]}: " in line), None)
            if hit:
                met.add(hit)
            else:
                found.append(line)
        found += [f"{f}: {name}: listed as known not to resolve, but it is not there or resolves now: take it off the list"
                  for f, name in sorted(set(known) - met)]
        return found, sorted(met)

    def _problems(self):
        out = []
        for m, tree in sorted(self.trees.items()):
            rel = os.path.relpath(self.mods[m], self.root).replace(os.sep, "/")
            for n, env in self._walk(m, tree):
                at = f"{rel}:{getattr(n, 'lineno', 0)}"
                if isinstance(n, ast.Import):
                    for a in n.names:
                        if self.ours(a.name) and a.name not in self.mods:
                            out.append(f"{at}: import {a.name}: no such module")
                elif isinstance(n, ast.ImportFrom):
                    src = source_of(n, m, self.mods)
                    if not self.ours(src):
                        continue
                    if src not in self.mods:
                        out.append(f"{at}: from {src} import ...: no such module")
                        continue
                    for a in n.names:
                        if a.name != "*" and src not in self.open and a.name not in self.names[src]:
                            out.append(f"{at}: from {src} import {a.name}: {src} has no {a.name}")
                elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load) and isinstance(n.value, ast.Name):
                    tgt = env.get(n.value.id)
                    if tgt and tgt not in self.open and n.attr not in self.names[tgt] and not n.attr.startswith("__"):
                        out.append(f"{at}: {n.value.id}.{n.attr}: {tgt} has no {n.attr}")
        cmds = self.commands()
        out += [f"compose/__main__.py: command {cmd}: no module {mod}" for cmd, mod in cmds.items() if mod not in self.mods]
        rev1 = {mod for cmd, mod in cmds.items() if cmd in REV1} | set(REV1_ALSO)
        for cmd, mod in cmds.items():
            if cmd in REV1 or mod not in self.mods:
                continue
            via = self.reached(mod)
            for hit in sorted(rev1 & set(via)):
                out.append(f"compose/__main__.py: command {cmd}: reaches rev 1's {hit} ({self._chain(via, hit, mod)}): what both "
                           f"generations use belongs in a module of its own")
        for cmd, mod in cmds.items():
            if cmd not in NO_LAYOUT or mod not in self.mods:
                continue
            via = self.reached(mod)
            hits = [self._chain(via, x, mod) for x in set(via) | {mod} if x in LAYOUT or x.split(".")[0] in LAYOUT]
            if hits:                                             # one line a command: the shortest way there
                out.append(f"compose/__main__.py: command {cmd}: reaches a layout ({min(hits, key=lambda c: (c.count(' <- '), c))}): "
                           f"the controller rev 2 is the same board under every layout")
        return out

    @staticmethod
    def _chain(via, hit, mod):
        chain, x = [], hit
        while x != mod:
            chain.append(x)
            x = via[x]
        return " <- ".join(chain + [mod])

    def commands(self):
        """{command: module} from COMMANDS in compose/__main__.py."""
        main = self.trees.get("compose.__main__")
        for n in (main.body if main else []):
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "COMMANDS" for t in n.targets):
                return {cmd: mod for cmd, (mod, _) in ast.literal_eval(n.value).items()}
        return {}

    def imported(self, m):
        """The repository's modules a module imports, anywhere in its file."""
        deps = set()
        for n in ast.walk(self.trees[m]):
            if isinstance(n, ast.Import):
                deps |= {a.name for a in n.names if a.name in self.mods}
            elif isinstance(n, ast.ImportFrom):
                src = source_of(n, m, self.mods)
                if src in self.mods:
                    deps.add(src)
                    deps |= {src + "." + a.name for a in n.names if src + "." + a.name in self.mods}
        return deps

    def reached(self, m):
        """{module: the module that imports it} for everything a module's imports lead to."""
        via, todo = {}, [m]
        while todo:
            x = todo.pop()
            for d in sorted(self.imported(x)):
                if d not in via and d != m:
                    via[d] = x
                    todo.append(d)
        return via


def main():
    root = os.path.realpath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", ".."))
    repo = Repo(root)
    bad, met = repo.problems()
    for b in bad:
        print(b)
    for k in met:
        print(f"known: {k[0]}: {k[1]} ({KNOWN[k]})")
    print(f"{len(repo.mods)} modules: " + (f"{len(bad)} problems" if bad else "every name taken from another module resolves")
          + (f", but for {len(met)} known" if met else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
