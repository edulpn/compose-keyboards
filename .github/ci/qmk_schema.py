"""Validate generated QMK keyboard definitions against QMK's own schema.

    python3 .github/ci/qmk_schema.py SCHEMAS_DIR keyboard.json [keyboard.json ...]

SCHEMAS_DIR is data/schemas of a qmk_firmware checkout. The schemas are loaded and joined the way QMK does it
(lib/python/qmk/json_schema.py): read as hjson, kept by "$id" and by file name, validated as draft 2020-12.
Needs hjson and jsonschema. Exits 1 when a definition doesn't validate, 0 otherwise."""
import sys
import json
import warnings
from pathlib import Path


def problems(schemas_dir, paths, schema="qmk.keyboard.v1"):
    import hjson
    import jsonschema
    warnings.filterwarnings("ignore", category=DeprecationWarning)      # RefResolver: what QMK itself uses
    store = {}
    for f in sorted(Path(schemas_dir).glob("*.jsonschema")):
        data = hjson.load(f.open(encoding="utf-8"))
        if isinstance(data, dict):
            store[data["$id"]] = data
            store[f.name] = data
    validator = jsonschema.Draft202012Validator(store[schema], resolver=jsonschema.RefResolver.from_schema(store[schema], store=store))
    out = {}
    for p in paths:
        errs = sorted(validator.iter_errors(json.load(open(p))), key=lambda e: list(e.absolute_path))
        out[p] = [f"{'/'.join(str(q) for q in e.absolute_path) or '(top level)'}: {e.message}" for e in errs]
    return out


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    bad = 0
    for p, errs in problems(argv[1], argv[2:]).items():
        print(f"{p}: " + ("valid against QMK's keyboard schema" if not errs else f"{len(errs)} problems"))
        for e in errs[:20]:
            print(f"  {e}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
