# Building from source

[Home](../README.md) › Docs › Building from source

You only need this to change the design. Ready-made files for each layout's recommended configuration are on its release, linked from the layout's page.

## Requirements

- **Python 3.11+** with the packages in `requirements.txt`: CadQuery, trimesh, manifold3d, shapely, numpy, scipy, matplotlib, networkx, rtree.
- **KiCad 7+.** Its `pcbnew` Python module must be importable from that Python.
- **Java 17+** and [Freerouting](https://github.com/freerouting/freerouting/releases). Point `FREEROUTING` at the jar, or put it at `../tools/freerouting.jar`.
- **ngspice:** only for the controller simulation.
- **Node 18+:** only for renders and board previews. Run `npm install` in `compose/render/web/`, then `npx playwright install chromium`.

## Commands

Everything runs from the repo root as `python3 -m compose <command> [outdir]`; `python3 -m compose --help` lists the commands.

```sh
# Compose58 rev 1 (the default; see layouts/lily58/rev1.md)
python3 -m compose build out            # case, plates, frames, cover (out/print, out/step), BOM
python3 -m compose pcb out              # half boards + controller rev 1: route, DRC, Gerbers
python3 -m compose firmware out         # QMK keyboard.json
python3 -m compose model out            # assembled model (the checks and renders use it)
python3 -m compose checks out           # fit / assembly / print checks
python3 -m compose sim out              # copper-level matrix simulation
python3 -m compose render out           # images

# Controller rev 2 (docs/controller-rev2.md) and the rev 2 case (layouts/lily58/rev2.md)
python3 -m compose controller out       # route, DRC, Gerbers (add --resilk to redraw only the silkscreen)
python3 -m compose sim-controller out   # copper-level simulation
python3 -m compose spice-controller out # ngspice simulation
C58_REV=2 python3 -m compose gasket-case out_r2t     # rev 2 printable parts
C58_REV=2 python3 -m compose gasket-checks out_r2t   # rev 2 fit, gasket, assembly and printability checks
C58_REV=2 python3 -m compose gasket-render out_r2t   # rev 2 renders
```

Outputs go to `out*/`, which is not committed: releases carry them.

## Repository layout

```
compose/            the platform (Python package)
  params.py           every dimension: angles, thicknesses, gaps, pads, hardware
  geom.py, layout.py  frames and transforms; the Layout/Key types
  case/               sandwich.py (rev 1 case), gasket.py (rev 2 case), build, coupons, tilt risers
  pcb/                half boards + controller rev 1 (placement, KiCad, routing), board art
  controller/         controller rev 2 board and its mechanical standard (rev2_std.py)
  checks/             fit, assembly, gasket and printability checks
  sim/                copper-level and ngspice simulations
  render/             renders and board previews (web/ holds the MIT render helpers)
  firmware.py         QMK keyboard definition
layouts/<name>/     one folder per layout: its key list and hardware positions
docs/               platform docs (this wiki), images
  layouts/<name>/README.md   each layout's own pages: revisions, build guides, releases
```

## Customising

- **All dimensions live in `compose/params.py`.** That covers:
  - angles (splay, tent, tilt);
  - plate and wall thicknesses;
  - fit gaps and lip/reveal sizes;
  - Pico, header and perfboard stack heights;
  - screw and insert sizes;
  - bed size.

  Derived values are computed rather than typed in. That includes the inner-edge height, which `geom.solve_z0` derives from `WIRE_DEPTH`, plus the cover pillar positions, window, clamp tab and screw lengths.
- **Layouts live in `layouts/<name>/layout.py`.** A layout is a list of keys plus its screws, posts and feet expressed relative to keys. Add a folder with a `layout()` function and set `LAYOUT` in `compose/params.py`. `validate_layout()` flags:
  - keycaps closer than 0.5 mm;
  - a bridge that's too long for the inner edge;
  - screws too close to the edge.

After a change, re-run the build, then the checks. The checks are what tell you the change still fits and prints.
