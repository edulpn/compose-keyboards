# Building from source

[Home](../README.md) › Docs › Building from source

You only need this to change the design. Ready-made files are on a layout's release, once it has one, linked from the layout's page.

## Requirements

| tool | version | needed for | notes |
|---|---|---|---|
| Python | 3.11+ (3.12 with apt's KiCad) | everything | packages in `requirements.txt`: CadQuery, trimesh, manifold3d, shapely, numpy, scipy, matplotlib, networkx, rtree |
| KiCad | **7** (developed on 7.0.11) | boards | its `pcbnew` module must import in that Python. KiCad 8 and 9 removed parts of the API the generators use (see [Porting to KiCad 8/9](#porting-to-kicad-89)). |
| Java + [Freerouting](https://github.com/freerouting/freerouting/releases) | Java **21+** and Freerouting **2.1.0**; beside them Java **25** and Freerouting **2.5.0**, for the boards that name it (see [Routing](#routing)) | routing | point `FREEROUTING` at the 2.1.0 jar, or put it at `../tools/freerouting.jar`. That jar has to be 2.1.0; 2.5.0 goes beside it as `freerouting-2.5.0.jar`. Compose58's half boards and the controller rev 2 name 2.5.0: without it they are routed with 2.1.0, which gives other boards than CI's. Freerouting 2.1.0 is built for Java 21: with an older `java` first on PATH the routing commands stop and say so. |
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

For Freerouting 2.5.0 as well (the router Compose58's boards and the controller rev 2 name): any Java 25, with `JAVA25` pointing at its `java`, and the jar beside the other one:

```sh
curl -fsSL -o ../tools/freerouting-2.5.0.jar \
    https://github.com/freerouting/freerouting/releases/download/v2.5.0/freerouting-2.5.0.jar
```

**Docker (macOS, or anywhere):** the repo's `Dockerfile` builds the same stack. On macOS this is the easy route: KiCad's macOS app bundles its own Python, and its `pcbnew` only loads in that interpreter.

```sh
docker build -t compose .               # give Docker all CPU cores and >= 8 GB of memory
docker run --rm -it -v "$PWD":/work/compose-keyboards -w /work/compose-keyboards compose
```

`FREEROUTING` and `NODE_PATH` are set inside the image. It builds natively on arm64 (Apple silicon). Colima shares only your home folder with containers, so keep the repo under it.

**Smoke test:**

```sh
python3 -c "import pcbnew, cadquery; print(pcbnew.Version())"      # 7.0.11
python3 -m compose half-rev2 --plan                        # placement drawing, about a minute
python3 -m compose gasket-case /tmp/r2 && python3 -m compose gasket-checks /tmp/r2      # Compose58: 133 checks, 0 FAIL, 0 WARN
```

The same code can give STLs that differ at tessellation level from one machine to the next (the Python and CadQuery versions, x86_64 or arm64): the same bounds, volumes a fraction of a mm³ apart. So a mismatch with someone else's files doesn't mean the geometry changed: compare the meshes (volume, bounds, symmetric difference), and check your own changes against a build of the unchanged code on the same machine (see [Checking a change](#checking-a-change)).

**Memory:** on 4 cores every command fits in 8 GB. The largest peaks: routing an RGB half board 5.4 GB, `gasket-checks` 2.6 GB. Routing runs one Freerouting job per two cores (see [Routing](#routing)), so more cores take more memory there.

## Commands

Everything runs from the repo root as `python3 -m compose <command> [outdir]`; `python3 -m compose --help` lists the commands.

```sh
# Controller rev 2 (docs/controller-rev2.md)                          -> out/controller
python3 -m compose controller         # route, DRC, Gerbers (add --resilk to redraw only the silkscreen)
python3 -m compose sim-controller     # copper-level simulation
python3 -m compose spice-controller   # ngspice simulation

# Rev 2 (docs/rev2.md; Compose58's own page: layouts/compose58/rev2.md) -> out/compose58/rev2
python3 -m compose half-rev2          # the four half boards: place, route, DRC, Gerbers
python3 -m compose half-rev2 --plan             # placement drawing only (fast)
python3 -m compose half-rev2 --preroute         # the layout's pre-routed copper only: laid, checked against the plan, drawn (no KiCad)
python3 -m compose flex-jumper        # the flex jumper (one part, both sides): shape solved from the case, DRC, Gerbers, flat drawing
python3 -m compose sim-half-rev2      # half boards + jumpers + controller rev 2, copper level (after all are built)
python3 -m compose flex-sim           # the jumper as an elastic strip: seated, insertion, gasket travel, length
python3 -m compose order-rev2         # every board's JLCPCB zip, checked against its board and its DRC report, in out/compose58/order + ORDER.md
python3 -m compose firmware-rev2      # QMK keyboard.json, plain and RGB
python3 -m compose gasket-case        # printable parts
python3 -m compose gasket-checks      # fit, gasket, assembly, jumper and printability checks
python3 -m compose gasket-sections    # cross-section drawings
python3 -m compose gasket-render      # renders (assembly views need the routed half boards and controller)
```

**Where a run writes.** A command writes to the folder named after it, as in `python3 -m compose gasket-case mine`. With none named, each keyboard has its own (`compose/outputs.py`):

| folder | what writes there |
|---|---|
| `out/<layout>/rev2` | the keyboard's commands |
| `out/<layout>/order` | `order-rev2` (set `ORDER_OUT` to change that) |
| `out/controller` | the controller rev 2's commands: it is one board under every layout |

The rev 2 commands that need the controller's board (`sim-half-rev2`, `gasket-render`, `order-rev2`) read it from `out/controller`; set `CTRL_OUT` if it was built elsewhere. In the order folder a keyboard's own boards carry its layout's name (`compose58_half_rev2_hotswap_JLCPCB.zip`); the controller's zip does not.

A run builds one keyboard. `--layout <name>`, before the command, names its layout: a folder of `layouts/` (Compose58's, `compose58`, when it is left out). The controller rev 2's three commands build no keyboard (one board under every layout) and take no `--layout`.

```bash
python3 -m compose --layout compose58 gasket-case      # writes out/compose58/rev2/print
```

The settings a run can change are environment variables: `COMPOSE_SPLAY`, `COMPOSE_TENT`, `COMPOSE_TILT`, `COMPOSE_GAP_TOP`, `COMPOSE_BRIDGE_LEN` (angles in degrees, lengths in mm) and `COMPOSE_PREROUTE=0` (below). They were `C58_...` before; a run that finds one of the old names set stops and names its replacement.

### Routing

How `route()` in `compose/pcb/toolbox.py` drives Freerouting:

- Each attempt runs `ROUTER_JOBS` Freerouting jobs side by side (default: half the CPU cores; each takes 3–4 GB) and keeps the first whose `.ses` is sound and fully routed.
- A job is dropped when it stalls (best unrouted count unchanged for 40 passes), or when its `.ses` isn't the board it finished with. Freerouting 2.1 sometimes logs "Restoring an earlier board" and then writes that one; on the RGB boards that happens in most runs.
- Attempts retry until DRC is clean. The router's output is kept as `<outdir>/pcb/<board>_freerouting.log`.
- On a 2-core machine, set `ROUTER_JOBS=1` and expect an RGB board routed with Freerouting 2.1.0 to need many attempts.
- The router is shown the RGB boards' LED pads without the 0.15 mm that reaches toward the cutout (`route_view()` in `compose/pcb/rev2_half.py`). No track can use that strip: it lies inside the margin the router keeps from an edge. Each pad's anchor, where tracks land, stays where it was, so the router's job is the same as with the shorter pads. The GND fanout, laid just before routing, is given the same view, so its stubs start at the anchors and its vias stay where they were.
- **Freerouting 2.1.0 is the default**, and what a new layout's boards are routed with. A layout can name Freerouting 2.5.0 for a board it has made routable for it (`ROUTER = {board: "2.5.0"}`, or `{board: ("2.5.0", seed)}`, in its `preroute.py`, below). 2.5.0 gives the same board every time it is put the same job, so such a board routes once, in one router run, instead of in attempts:
  - It needs Java 25 and its own jar: `JAVA25=/path/to/java` (or a `JAVA_HOME_25_<arch>`, or a `java` 25 on PATH) and `freerouting-2.5.0.jar` beside the default jar (or `FREEROUTING_2_5_0`). Where either is missing the board is routed with 2.1.0 as before, and says so.
  - Its fan-out stage is off (`--router.fanout.enabled=false`): left on, it lays 0.19 mm tracks at the connector pads, under the 0.2 mm minimum.
  - **Seeds.** Asking it the same job twice gives the same routing twice (its optimizer may finish one junction differently: see Continuous integration). So when an attempt isn't DRC-clean, the next one puts the job another way: the nets of the Specctra file listed in another order, and the routing outline moved in by 0.001 mm per seed. The board that is asked for stays the same; the board the router comes back with changes, the same way on every machine. Attempt n uses the seed the layout names (0 if it names none) plus n - 1, and seed 0 changes nothing. When a later attempt is the clean one, the build prints its seed: name it in `ROUTER` and the board routes in one attempt again. The attempts stay with 2.5.0; 2.1.0 steps in only where 2.5.0 isn't installed.
  - It can't route the thumb-row net (ROW4) on any rev 2 half board, plain ones included. With ROW4 pre-routed (below) it routes both plain boards and the solder RGB board in one attempt, in 35 to 216 s: Compose58 routes those three with it, with no seed.
  - The hotswap RGB board it routes with that board's 5 V rail and D nets pre-routed as well (below) and seed 8: the first that came out clean. Seeds 0 to 6 left 3 to 25 connections open; seed 7 was clean until the M2 holes got their no-copper areas and leaves 5 open since. An attempt on this board ends in 4 to 6 minutes, clean or not. Freerouting 2.1.0 hasn't routed this board with its rail laid. Where 2.5.0 isn't installed (the Docker image has 2.1.0 only), build it with `COMPOSE_PREROUTE=0`: 2.1.0 then routes everything, the rail included.
  - The controller rev 2 board it routes as it is, with nothing pre-routed and no seed, in one attempt: the whole `controller` command takes about 3½ minutes on CI's runners. The board names it itself (`ROUTER` in `compose/controller/rev2.py`). Freerouting 2.1.0 needed two or three attempts of about a minute each on this board, and still routes it where 2.5.0 isn't installed.

**Pre-routed nets.** Autorouting everything is the default, and a new layout needs nothing more. A layout can also lay chosen nets out itself before the router runs, in `layouts/<name>/preroute.py` (the mechanism is `compose/pcb/preroute.py`):

- The rev 2 half boards call the layout's `half_rev2(field, plan)`. `field` holds the board's pads with their nets, its holes, keep-outs and outline, built from the plan; the function adds tracks and vias to it. `field.route()` joins two points with a track that steps round whatever is in the way, and gives the same copper every time.
- The copper is checked before routing, against the plan and then against the KiCad board's own pads: clearance to other nets, holes, edges and keep-outs, no loose ends, each net in one piece on all its pads. A broken rule stops the build there. `half-rev2 --preroute` runs the plan-level check without KiCad and draws the copper.
- A pre-routed net leaves the router's job: the Specctra file carries its tracks as keep-outs and its vias as fixed vias, the same way the RGB boards' GND fan-out goes in. DRC and the simulations then see it like any other copper.
- With no `preroute.py`, or with `COMPOSE_PREROUTE=0`, the boards are built and routed exactly as without the mechanism.
- Compose58 pre-routes three kinds of net ([`layouts/compose58/preroute.py`](../layouts/compose58/preroute.py)): ROW4, the thumb row, on all four boards; the 5 V rail on both RGB boards; and on the hotswap RGB board every key's D net, from its socket pad on each face to its diode. That board's sockets have pads on both faces, so each key needs two links across the board (D and its column), and with the rail laid as well the router didn't finish it. The D nets are laid the way the router lays them on a board it does finish: the socket pad beside the diode goes straight to the anode on its own face, and on over the top of the switch on that face to a via above the other pad. That keeps the front copper at each key's right-hand edge free for the column's trunk, which the router runs there. What this gives: a 5 V rail of known resistance on both RGB boards (76 to 82 mΩ to the farthest LED, limit 150 mΩ), and four boards that Freerouting 2.5.0 routes in one attempt, the same on every run.

**Board previews** (realistic renders from a board's Gerbers, needs Node):

```sh
node compose/render/web/board_preview.js out/compose58/rev2/pcb/<board>_gerbers out/compose58/rev2/png/board_<board>   # _top.svg, _bottom.svg
node compose/render/web/svg2png.js out/compose58/rev2/png/board_<board>_bottom.svg out.png 1400     # 1400 px wide
node compose/render/web/svg2png.js out/compose58/rev2/png/board_<board>_bottom.svg big.png 1400 3   # 3x, for close-ups
```

Outputs go to `out/` (and `out_cache/`, what a slow solve leaves for the next run). Neither is committed: releases carry the files.

## Repository layout

```
compose/            the platform (Python package)
  params.py           every dimension: angles, thicknesses, gaps, pads, hardware
  geom.py, layout.py  frames and transforms; the Layout/Key types
  case/               the gasket-mount case (gasket.py) and the key holes it cuts (keyholes.py)
  pcb/                the KiCad toolbox every board is built with (toolbox.py), the switch as geometry (switch.py)
                      and as a KiCad footprint (switch_kicad.py), the half boards (rev2_half.py), the flex jumper
                      (jumper.py), text and logo as shapes (lettering.py), half-board art (art.py), nets laid out
                      before the router (preroute.py)
  controller/         controller rev 2 board and its mechanical standard (rev2_std.py)
  checks/             fit, assembly, gasket and printability checks (gasket.py), the section drawings
                      (gasket_sections.py), the flex jumper as an elastic strip (flex_sim.py)
  sim/                copper-level and ngspice simulations (copper.py: a board's copper as geometry)
  render/             renders and board previews (web/ holds the MIT render helpers)
  firmware_rev2.py    QMK keyboard definition, plain and RGB
  order_rev2.py       the order folder (out/<layout>/order)
  outputs.py          where a run writes when no folder is named
layouts/<name>/     one folder per layout: its keys and hardware positions (layout.py); what its keyboard is
                    called, its tent and tilt and its USB ids (keyboard.py); optionally the nets it routes
                    itself (preroute.py); and its own pages and pictures (README.md, rev2.md, images/)
docs/               the platform's pages and their pictures: the case, the controller, the half boards and the
                    jumpers each have one
.github/            CI: the workflow (workflows/checks.yml), its scripts and their tests (ci/), and the
                    runners' setup (actions/setup)
```

## Customising

- **All dimensions live in `compose/params.py`.** That covers:
  - the splay angle (tent and tilt are the keyboard's own, in `layouts/<name>/keyboard.py`);
  - plate and wall thicknesses;
  - fit gaps and lip/reveal sizes;
  - the gasket: flange, pads, ledge;
  - screw and insert sizes.

  Derived values are computed rather than typed in. That includes the inner-edge height, which `geom.solve_z0` derives from `WIRE_DEPTH`.
- **Layouts live in `layouts/<name>/layout.py`.** A layout is a list of keys plus its plate posts and feet expressed relative to keys. Add a folder with a `layout()` function in `layout.py` and a `keyboard.py` beside it, and build it with `--layout <name>`. `validate_layout()` flags:
  - keycaps closer than 0.5 mm;
  - a bridge that's too long for the inner edge.

- **What a keyboard is called lives in `layouts/<name>/keyboard.py`.** It holds plain constants: the keyboard's name, the credit for its key layout, its tent and tilt, and its USB ids. [Compose58's](../layouts/compose58/keyboard.py) shows what goes in it.

- **Routing is automatic.** A new layout's boards are placed and autorouted with no routing code of its own. `layouts/<name>/preroute.py` is optional: nets worth laying out by hand (a power rail whose resistance should be a design value, a net the router struggles with), see [Routing](#routing).

After a change, re-run the build, then the checks. The checks are what tell you the change still fits and prints.

## Checking a change

Every design change goes through the existing checks (case checks, DRC, the copper simulations) rather than being judged by eye. When a new kind of part or constraint appears, add a check for it.

- **A change that is not a design change** (a reorganisation, a new check) must leave the outputs identical. Compare against a build of the unchanged code on the same machine:

  ```sh
  git stash; python3 -m compose gasket-case /tmp/a; python3 -m compose firmware-rev2 /tmp/a; git stash pop
  python3 -m compose gasket-case /tmp/b && python3 -m compose firmware-rev2 /tmp/b
  for f in /tmp/a/print/*.stl; do cmp $f /tmp/b/print/$(basename $f); done
  cmp /tmp/a/firmware/keyboard.json /tmp/b/firmware/keyboard.json; cmp /tmp/a/firmware/rgb/keyboard.json /tmp/b/firmware/rgb/keyboard.json
  ```

  The boards can't be compared byte for byte (KiCad gives every item a new id on every build): `.github/ci/sameboard.py` compares two boards item by item, and CI runs it against the base (see [Continuous integration](#continuous-integration)).
- **Moving code between modules:** `python3 .github/ci/imports.py` checks, without running anything, that every name the code takes from another of its modules exists. It covers the commands no job runs (the renders). It also checks that the controller rev 2's commands (`controller`, `sim-controller`, `spice-controller`) reach no layout through their imports: it is the same board under every layout.
- **Controller rev 2:** DRC clean; `sim-controller` and `spice-controller` pass.
- **Rev 2:** `gasket-checks` all pass; half-board and jumper DRC end at 0 errors and 0 unconnected (`half-rev2` and `flex-jumper` fail otherwise); `sim-half-rev2` passes for all four boards (on the RGB boards it also reads the 5 V rail's resistance and the return's through the GND pour from the copper, and holds a pre-routed rail and its return to 150 mΩ together; `python3 -m compose.sim.sheet` checks the method it reads the pour with, without KiCad); `flex-sim` passes. After a change to a layout's `preroute.py`, or to the placement under it, `half-rev2 --preroute` shows in seconds whether the pre-routed copper still clears everything. A change to the case or its angles moves the half's jumper connector (`jumper_row_y()` re-derives its row; the result is cached in `out_cache/<layout>/`, keyed by the sources and the parameter values it depends on) and the jumper: rebuild the half boards and the jumper (`flex-jumper`) before `sim-half-rev2`, which reads both. Then `order-rev2` for the order folder.

## Continuous integration

`.github/workflows/checks.yml` runs the suites above on GitHub's standard runners (4 cores, 16 GB) for every pull request and every push to `main`, as parallel jobs. Each layout in `layouts/` gets its own: the case and firmware (`gasket-case`, `gasket-checks`, `firmware-rev2`, the section drawings, and one command run with no folder named), the boards (the four half boards, the jumper, then `sim-half-rev2` and `order-rev2`), and the controller, which belongs to no layout, runs once (its board, copper simulation and SPICE). A new layout needs nothing in the workflow: the `plan` job lists the layouts and hands every job its own. The `checks-passed` job sums them up: it's the one status to require.

Every download and install in the jobs' setup step has a time limit of 3 to 5 minutes. One that stalls, which the runners' Ubuntu mirror does now and then, is stopped and fails the job with a "Setup stalled" error naming it: that is the runner, not the change, and running the job again answers it.

A design change moves the outputs on purpose, so the comparison with the base is reported in the run summary and fails nothing: the case STLs and both `keyboard.json` files against a build of the base, the jumper and the controller against the base's, and each half board that routes against the board routed before, with `.github/ci/sameboard.py`. The base is the commit of `main` the run is merged with (`.github/ci/base.py`), which can be newer than the one the pull request was opened on. That compares the job the router was handed (its `.dsn` byte for byte and the way it was called), then the boards item by item, leaving out only the ids KiCad gives every item on every build. It has three verdicts. "The same board": every item the same. "The same routing, finished another way by the router's optimizer": Freerouting 2.5.0 routes a job the same way pass for pass, but its optimizer can end on one of a few boards (seen on Compose58's plain hotswap board, which comes out with 684 or 685 track segments: one junction of one net, a quarter of a millimetre of track); the router's log shows the routing passes are the same and which optimizer pass parted, and only tracks of the nets that pass moved may differ. "Differs": anything else, with the reason. A change that is meant to leave the design alone, a reorganisation or a new check, has to read "identical" on every line and "the same job" with "the same board" or "the same routing" for every half board and for the controller.

Compose58's four half boards route with Freerouting 2.5.0, which routes the same way on every run (its optimizer's finish aside, above): one job and one attempt each. On CI's runners a plain board's build takes about a minute, the solder RGB board's 2½ to 4 and the hotswap RGB board's 5½, after about 1½ minutes of setup. A board that finds no clean route fails its job: after 10 attempts (30 for an RGB board) or 55 minutes, whichever comes first. Routed with 2.1.0, which is random, an RGB half board could miss a clean route for 30 attempts in a row on 4 cores. The workflow races such a board: three jobs of four Freerouting runs per attempt, up to 55 minutes each, with `sim-half-rev2` taking the first that comes out DRC-clean. Which boards race follows from the layout: a board its `preroute.py` gives a router that routes the same way every run (`ROUTER`) gets one job, a board on the default router gets three. The bar is the same as on your machine.

A half board is routed only when something its routing reads has changed. Every clean route is cached with a record of what it read: the files it imported or opened, the folders it listed and the module names it looked for, plus the setup action (which pins the router), `requirements.txt` and the workflow (`.github/ci/routed.py`). When none of those has changed, KiCad is the same version and the cached board still passes DRC on the runner, that board is used instead; `sim-half-rev2` and `order-rev2` then run on it as on a fresh one. The run summary says for each board whether it was routed or reused, and why.

A pull request runs only the suites its changes can reach:

- **The record.** Each full run on `main` records the repository files every suite read: modules imported (and module names it tried to import), files opened, folders listed (`.github/ci/traced.py`). Only what git tracks counts, so a command's own output folder is not in it. The `plan` job compares the record with the files the pull request changes (`.github/ci/plan.py`) and lists the reasons in the run summary.
- **What runs.** A docs-only change runs nothing. A change to one layout's files runs that layout's suites and no other's, and a new layout, having no record, runs its own. The controller belongs to no keyboard, so it is a suite of its own: when it runs, every layout's boards run with it, because the half boards are simulated against its board. A change to the boards alone still builds the controller's board for that simulation and skips its SPICE job. Changes to `requirements.txt`, the `Dockerfile` or `.github/` run everything, and so does a pull request opened before `main` has a record.
- **Whose changes.** Only the pull request's own changes count, from the commit on `main` it starts from. The record can be older than that commit, since a full run on `main` takes a while: if `main` has since changed something a suite reads, that suite runs to be safe, unless the pull request holds only documents and their pictures (`*.md`, images in an `images` folder). Past three merges behind, the plan says so in a warning: that means `main`'s runs are not saving the record.

The renders (`gasket-render`) are not run by CI, by choice: they need Node and a browser, and they check nothing. `imports.py` covers the names they take from other modules; run them yourself after a change to what they draw.

## Notes for working on the code

- Freerouting 2.1 is randomized; the board builders retry until DRC is clean. It logs `NullPointerException` / `ArrayIndexOutOfBounds` in `maze_search_algo` on every board, including ones that route clean: that's noise. Its "MB memory" figure is cumulative allocation, not resident memory. If the unrouted count stays flat over passes, the board is congested: more time won't help, reduce the load.
- A check that is part of a build is written `must(condition, why)` (`from compose import must`), not `assert`: an assert statement is dropped under `python3 -O`, and with it the check, or whatever the asserted expression did.
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

- `compose/pcb/toolbox.py`: `add_pad`, `silk_poly`, `drc`;
- `compose/pcb/rev2_half.py`: `led_fp`, `gnd_pour`, `gnd_fanout`;
- `compose/pcb/jumper.py`: `build_board`;
- `compose/controller/rev2.py`, `compose/checks/gasket.py`, `compose/sim/controller_copper.py`.

After porting, every DRC and simulation must still pass.
