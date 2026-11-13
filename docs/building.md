# Building from source

[Home](../README.md) › Docs › Building from source

You only need this to change the design. Ready-made files for each layout's recommended configuration are on its release, linked from the layout's page.

## Requirements

| tool | version | needed for | notes |
|---|---|---|---|
| Python | 3.11+ (3.12 with apt's KiCad) | everything | packages in `requirements.txt`: CadQuery, trimesh, manifold3d, shapely, numpy, scipy, matplotlib, networkx, rtree |
| KiCad | **7** (developed on 7.0.11) | boards | its `pcbnew` module must import in that Python. KiCad 8 and 9 removed parts of the API the generators use (see [Porting to KiCad 8/9](#porting-to-kicad-89)). |
| Java + [Freerouting](https://github.com/freerouting/freerouting/releases) | Java **21+**, Freerouting **2.1.0** | routing | point `FREEROUTING` at the jar, or put it at `../tools/freerouting.jar`. Not 2.5.0 (see [Routing](#routing)). Freerouting 2.1.0 is built for Java 21: with an older `java` first on PATH the routing commands stop and say so. |
| ngspice | any recent | controller simulation only | |
| Node | 20+ | renders and board previews only | Playwright needs 20; Ubuntu 24.04's apt Node is 18. Run `npm install` in `compose/render/web/`, then `npx playwright install chromium`. |

## Setting up

The safest route is the stack everything was developed on: Ubuntu 24.04 with apt's KiCad 7.0.11 and its Python 3.12, OpenJDK 21, Freerouting 2.1.0.

**Ubuntu 24.04, natively or in WSL2** (on Windows: `wsl --install -d Ubuntu-24.04` first, and keep the repo inside the WSL filesystem, not under `/mnt/c`, where file access is slow):

```sh
sudo apt update
sudo apt install -y kicad kicad-footprints kicad-symbols python3-pip python3-dev \
    openjdk-21-jre-headless ngspice fonts-dejavu-core git curl zip unzip
kicad-cli version                       # expect 7.0.11

git clone https://github.com/edulpn/compose-keyboards.git && cd compose-keyboards
mkdir -p ../tools
curl -fsSL -o ../tools/freerouting.jar \
    https://github.com/freerouting/freerouting/releases/download/v2.1.0/freerouting-2.1.0.jar
pip3 install --break-system-packages -r requirements.txt cairosvg pillow
# renders only: Node 20+ (e.g. Node 22 from nodejs.org or NodeSource), then
(cd compose/render/web && npm install && npx playwright install --with-deps chromium)
```

**Docker (macOS, or anywhere):** the repo's `Dockerfile` builds the same stack. On macOS this is the easy route: KiCad's macOS app bundles its own Python, and its `pcbnew` only loads in that interpreter.

```sh
docker build -t compose .               # give Docker all CPU cores and >= 8 GB of memory
docker run --rm -it -v "$PWD":/work/compose-keyboards -w /work/compose-keyboards compose
```

`FREEROUTING` and `NODE_PATH` are set inside the image. It builds natively on arm64 (Apple silicon).

**Smoke test:**

```sh
python3 -c "import pcbnew, cadquery; print(pcbnew.Version())"      # 7.0.11
C58_REV=2 python3 -m compose half-rev2 out_r2t --plan                # placement drawing, about a minute
python3 -m compose build /tmp/r1 && python3 -m compose model /tmp/r1 && python3 -m compose checks /tmp/r1   # ALL CHECKS PASSED
```

Then compare `/tmp/r1/print/*.stl` with the STLs in the `compose58-rev1` release:

| environment | release STLs |
|---|---|
| x86_64, Python 3.13 with the release's packages* | all six byte-identical |
| Docker image (Python 3.12) on x86_64 | five of six; `case.stl` differs by a few triangles |
| Docker on arm64 (Apple silicon) | all six differ at tessellation level only: same bounds, volumes within 0.02 mm³ |

\* cadquery 2.8.0, cadquery-ocp 7.9.3.1.1, numpy 2.5.3, trimesh 5.1.1, manifold3d 3.5.4, shapely 2.2.0, scipy 1.18.1.

A mismatch doesn't mean the geometry changed: compare the meshes (volume, bounds, symmetric difference). Check your own changes against a build of the unchanged code on the same machine (see [Checking a change](#checking-a-change)).

**Memory:** on 4 cores every command fits in 8 GB. The largest peaks: routing an RGB half board 5.4 GB, rev 1's `checks` 4.1 GB, `gasket-checks` 2.6 GB. Routing runs one Freerouting job per two cores (see [Routing](#routing)), so more cores take more memory there. Colima shares only your home folder with containers, so keep the repo under it.

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

# Controller rev 2 (docs/controller-rev2.md)
python3 -m compose controller out       # route, DRC, Gerbers (add --resilk to redraw only the silkscreen)
python3 -m compose sim-controller out   # copper-level simulation
python3 -m compose spice-controller out # ngspice simulation

# Compose58 rev 2 (layouts/lily58/rev2.md): set C58_REV=2
C58_REV=2 python3 -m compose half-rev2 out_r2t       # the four half boards: place, route, DRC, Gerbers
C58_REV=2 python3 -m compose half-rev2 out_r2t --plan            # placement drawing only (fast)
C58_REV=2 python3 -m compose flex-jumper out_r2t     # the flex jumper (one part, both sides): shape solved from the case, DRC, Gerbers, flat drawing
C58_REV=2 python3 -m compose sim-half-rev2 out_r2t   # half boards + jumpers + controller rev 2, copper level (after all are built)
C58_REV=2 python3 -m compose flex-sim out_r2t        # the jumper as an elastic strip: seated, insertion, gasket travel, length
C58_REV=2 python3 -m compose order-rev2 out_r2t      # every board's JLCPCB zip, checked against its board, in out_order/ + ORDER.md
C58_REV=2 python3 -m compose firmware-rev2 out_r2t   # QMK keyboard.json, plain and RGB
C58_REV=2 python3 -m compose gasket-case out_r2t     # printable parts
C58_REV=2 python3 -m compose gasket-checks out_r2t   # fit, gasket, assembly, jumper and printability checks
C58_REV=2 python3 -m compose gasket-render out_r2t   # renders (assembly views need the routed half boards and controller)
C58_REV=2 C58_POINTER=pim447:R python3 -m compose pointer-checks out_r2t      # a pointer device's checks (--fast: 2D only)
C58_REV=2 C58_POINTER=pim447:R:bay30 python3 -m compose gasket-case out_r2t   # a trackball in the right half's thumb bay (the left has none)
C58_REV=2 python3 -m compose pointer-checks --list                         # the devices in pointers/
C58_REV=2 python3 -m compose pointer-checks --suggest-bay                  # thumb bay positions for a new layout
```

`sim-half-rev2` reads the controller from `out/` (set `CTRL_OUT` to change that).

### Routing

How `route()` in `compose/pcb/kicad.py` drives Freerouting:

- Each attempt runs `ROUTER_JOBS` Freerouting jobs side by side (default: half the CPU cores; each takes 3–4 GB) and keeps the first whose `.ses` is sound and fully routed.
- A job is dropped when it stalls (best unrouted count unchanged for 40 passes), or when its `.ses` isn't the board it finished with. Freerouting 2.1 sometimes logs "Restoring an earlier board" and then writes that one; on the RGB boards that happens in most runs.
- Attempts retry until DRC is clean. The router's output is kept as `<outdir>/pcb/<board>_freerouting.log`.
- On a 2-core machine, set `ROUTER_JOBS=1` and expect the RGB boards to need many attempts.
- **Stay on Freerouting 2.1.0.** 2.5.0 has no restore problem and routes much faster, but it is deterministic and can't route the thumb-row net (ROW4) on any rev 2 half board, plain ones included.

**Board previews** (realistic renders from a board's Gerbers, needs Node):

```sh
node compose/render/web/board_preview.js out_r2t/pcb/<board>_gerbers out_r2t/png/board_<board>   # _top.svg, _bottom.svg
node compose/render/web/svg2png.js out_r2t/png/board_<board>_bottom.svg out.png 1400             # 1400 px wide
node compose/render/web/svg2png.js out_r2t/png/board_<board>_bottom.svg big.png 1400 3           # 3x, for close-ups
```

Outputs go to `out*/`, which is not committed: releases carry them.

## Repository layout

```
compose/            the platform (Python package)
  params.py           every dimension: angles, thicknesses, gaps, pads, hardware
  geom.py, layout.py  frames and transforms; the Layout/Key types
  case/               sandwich.py (rev 1 case), gasket.py (rev 2 case), build, coupons, tilt risers
  pcb/                rev 1 half boards + controller rev 1 (layout.py, kicad.py), rev 2 half boards (rev2_half.py),
                      the rev 2 flex jumper (jumper.py), board art
  controller/         controller rev 2 board and its mechanical standard (rev2_std.py)
  checks/             fit, assembly, gasket and printability checks; the flex jumper as an elastic strip (flex_sim.py)
  pointer/            pointer mount standard (rev 2): std.py, devices, placement, solids, cable
  sim/                copper-level and ngspice simulations
  render/             renders and board previews (web/ holds the MIT render helpers)
  firmware.py         QMK keyboard definition (rev 1); firmware_rev2.py for rev 2
  order_rev2.py       the rev 2 order folder (out_order/)
layouts/<name>/     one folder per layout: its key list and hardware positions
pointers/             pointer devices: one folder each (module.py, carrier.py, README.md)
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

## Checking a change

Every design change goes through the existing checks (case checks, DRC, the copper simulations) rather than being judged by eye. When a new kind of part or constraint appears, add a check for it.

- **Released revisions must not change.** Code shared between revisions (`kicad.py`, `art.py`, `params.py`, `geom.py`, `sim/matrix.py`) must leave rev 1's outputs byte-identical: build STLs, BOM and `keyboard.json`. Compare against a build of the unchanged code:

  ```sh
  git stash; python3 -m compose build /tmp/r1a; python3 -m compose firmware /tmp/r1a; git stash pop
  python3 -m compose build /tmp/r1b && python3 -m compose firmware /tmp/r1b && python3 -m compose model /tmp/r1b && python3 -m compose checks /tmp/r1b
  for f in /tmp/r1a/print/*.stl; do cmp $f /tmp/r1b/print/$(basename $f); done
  cmp /tmp/r1a/bom.txt /tmp/r1b/bom.txt; cmp /tmp/r1a/firmware/keyboard.json /tmp/r1b/firmware/keyboard.json
  ```

  Half-board Gerbers can't be compared byte for byte: routing is randomized. Rev 1's release carries the exact Gerbers that were ordered, so it is never rebuilt.
- **Controller rev 2:** DRC clean; `sim-controller` and `spice-controller` pass.
- **Rev 2:** `gasket-checks` all pass; half-board and jumper DRC end at 0 errors and 0 unconnected; `sim-half-rev2` passes for all four boards; `flex-sim` passes. A change to the case or its angles moves the half's jumper connector (`jumper_row_y()` re-derives its row; the result is cached in `out_cache/`, keyed by the sources it depends on) and the jumper: rebuild the half boards and the jumper (`flex-jumper`) before `sim-half-rev2`, which reads both. Then `order-rev2` for the order folder.

## Continuous integration

`.github/workflows/checks.yml` runs the suites above on GitHub's standard runners (4 cores, 16 GB) for every pull request and every push to `main`, as parallel jobs: rev 1 (build, model, checks, and the byte-for-byte comparison with the pull request's base), rev 2 (case, `gasket-checks`, firmware), the pointer configurations, and the boards (controller, the four half boards, the jumper, then `sim-half-rev2` and `order-rev2`). The `checks-passed` job sums them up: it's the one status to require.

A pull request runs only the suites its changes can reach. Each full run on `main` records the repository files every suite read: modules imported (and module names it tried to import), files opened, folders listed (`.github/ci/traced.py`). The `plan` job compares those with the files the pull request changes (`.github/ci/plan.py`) and lists the reasons in the run summary. A docs-only change runs nothing; a change to rev 2 code alone skips rev 1. Changes to `requirements.txt`, the `Dockerfile` or `.github/` run everything, and so does a pull request opened before `main` has a record.

## Notes for working on the code

- Freerouting 2.1 is randomized; the board builders retry until DRC is clean. It logs `NullPointerException` / `ArrayIndexOutOfBounds` in `maze_search_algo` on every board, including ones that route clean: that's noise. Its "MB memory" figure is cumulative allocation, not resident memory. If the unrouted count stays flat over passes, the board is congested: more time won't help, reduce the load.
- SWIG pad objects don't compare equal (`p in list` is always false): compare by number, shape or position.
- `pcbnew.FromMM` rejects numpy floats: convert to `float` first.
- KiCad's `Flip(pos, True)` mirrors left-right **and** rotates 180°: rotate relative to that afterwards.
- Zones must be filled (`pcbnew.ZONE_FILLER(board).Fill(board.Zones())`) before saving for DRC; the copper simulation reads the filled polygons. The filler segfaults on a board made with `pcbnew.BOARD()` (no project): fill a board that was saved and loaded back.
- Delete board items with `board.Delete(item)`, not `Remove`: a removed item's Python wrapper owns it, the garbage collector frees it, and KiCad 7's SWIG then starts returning bare `VECTOR2<int>*` pointers (even `GetTracks()` fails).
- Calling `GetStart()` / `GetEnd()` in tight inner loops is slow and fragile: read each track's ends once into tuples.
- A CadQuery `fuse` of pieces meeting along a twisted (lofted) face can silently drop a piece: keep a compound when the result is only for interference checks.
- `art.widest_box` searches near fixed anchors tuned for the Lily58; other layouts may need their own.

## Porting to KiCad 8/9

Only needed if KiCad 7 isn't an option.

| KiCad 7 | KiCad 8/9 |
|---|---|
| `FP_SHAPE` inside footprints | `PCB_SHAPE` |
| `SetPos0`, `SetStart0`, `SetEnd0`, `SetDrawCoord` | gone: set positions in board coordinates |
| `EDA_UNITS_MILLIMETRES` | renamed |
| some zone and pad setters | changed |

The calls live in:

- `compose/pcb/kicad.py`: `add_pad`, `silk_poly`, `drc`;
- `compose/pcb/rev2_half.py`: `led_fp`, `gnd_pour`, `gnd_fanout`;
- `compose/pcb/jumper.py`: `build_board`;
- `compose/controller/rev2.py`, `compose/checks/gasket.py`, `compose/render/model.py`, `compose/sim/controller_copper.py`.

After porting, every DRC, simulation and the rev 1 byte-identical check must still pass.
