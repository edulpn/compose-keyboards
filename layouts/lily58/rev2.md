# Compose58 rev 2

[Compose58](README.md) › rev 2 · **Status: in progress.** The case, cover and controller are designed and checked; the half boards are next.

![rev 2](images/rev2_hero.png)

**On this page:** [The rev 2 case](#the-rev-2-case-gasket-mount) · [Design notes and ideas](#design-notes-and-ideas)

## The rev 2 case: gasket mount

`compose/case/gasket.py` builds the rev 2 parts: `C58_REV=2 python3 -m compose gasket-case out_r2t`. `gasket-checks` checks them, `gasket-sections` draws cross-sections and `gasket-render` renders them (all with `C58_REV=2`). Rev 1 is untouched (`C58_REV` defaults to 1).

The controller is the shared [controller rev 2](../../docs/controller-rev2.md).

- **Defaults:** splay 10°, tent 12°, tilt 0° (from the ergonomics research, provisional until the angle test prints are tried), 62 mm bridge with 2.5 mm end walls. Every angle still overrides with `C58_SPLAY` / `C58_TENT` / `C58_TILT`.
- **Parts:** one tub (both halves and the open middle bay, one print, 332 × 161 mm on the 350 mm bed), two plates, two frames, the middle cover. `C58_REV=2 python3 -m compose gasket-case out_r2t` writes them to `out_r2t/print/` in print orientation, all printable without supports:
  - tub: on its floor; the pad ledge steps back to the wall at 60° underneath instead of hanging off it;
  - plates: switch side down, as on rev 1, so the flange (flush with the top face) lies flat on the bed and the switch-clip pockets open upward;
  - frames and cover: upside down, visible tops on the bed (their bevels are 56° from the bed).
  Every mesh is checked watertight with no non-manifold edges, and sliced layer by layer for overhangs (see the checks).
- **Look:** rev 1's bevelled frames (6 mm tall, 4 mm inset) and reveal line over the tub's top edge; the outer corners are rounded at 4.5 mm so the bevel stays clean all the way round.
- **Gasket mount:** each plate is a 5 mm core holding the switches plus a thin 2 mm flange round its edge, flush with the plate's top face. The flange is pinched between foam pads: pads on a ledge in the tub below, pads under the frame above. Nothing screws through the plate or the half board. Each frame screws to the tub from below with six M3 screws into heat-set inserts and bottoms out on the tub's bosses, so the squeeze is set by geometry, not by how hard the screws are tightened. The plate floats 0.6 mm clear of the walls and frame sideways.
- **Pads = ordinary foam weatherstrip tape.** Self-adhesive closed-cell EPDM or neoprene sponge, 1/8″ (3 mm) thick, 3/8″ or 10 mm wide, cut across into 4 mm slices with scissors. The pads are 10 mm along the edge and 4 mm inward, stuck to the ledge and to the frame's underside. They are installed at 2.1 mm, which is 30–34 % squeeze for 3.0–3.2 mm tape (that foam is happy at 25–50 %). There are 20 pad pairs per half: 18 found by scanning the plate edge for every spot where a slice fits between the plate edge and the half board, plus one pair at each end of the inner (bridge) edge on seats that stand straight up from the floor, so they don't lean into the controller.
- **Middle bay:** the controller sits on four floor posts (M3 inserts) and is clamped by its four M3 standoffs; the cover drops onto the standoffs and takes four M3 × 6 screws, so it comes off without touching the ribbons. The bay is open from wall to wall below the plates' inner edges, so the ribbons run straight out from the board's side edges to the halves. There are 24 mm under the board.
- **Checked (`gasket-checks`, all passing):**
  - no overlap between any two parts that mustn't touch (tub, plates, frames, cover, controller board and the parts on both its faces, Pico stack, standoffs, half-board proxies, pads);
  - clearances: plate to tub 0.6 mm, plate to frame 0.58 mm, cover to frames 0.3 mm, board to tub 0.5 mm, Pico to cover 0.7 mm;
  - the pad gap measured on the solids along the plate normal at every pad (2.10 mm everywhere, top and bottom);
  - assembly paths: plates and frames drop in along the plate normal, the controller and the cover drop straight down;
  - hardware engagement: cover screws 2.95 mm into the standoffs, standoff threads 4.4 mm into the inserts; Pico gap 0.96 mm, header plugs under the cover;
  - printability: each exported part is sliced at 0.2 mm in its print orientation and every layer must rest on the one below within 45°. Short bridges over hole ceilings and lips up to 1.2 mm are allowed. A plate with the flange halfway up its edge (the earlier design) fails this check.
- **Still to do:** the rev 2 half boards (FFC connector on the bottom face, outline 5 mm inside the plate), then fixing the cable length.

**Rev 2 hardware (case)**

| part | qty |
|---|---|
| M3 × 6 button-head screws (12 for the frames, driven up from under the case through the bosses; 4 for the cover) | 16 |
| M3 × 5 × 4 heat-set inserts (12 in the frames, 4 in the controller posts) | 16 |
| M3 × 12 male–female hex standoffs, 5 or 5.5 mm across flats (controller) | 4 |
| foam weatherstrip tape, closed-cell EPDM/neoprene, self-adhesive, 1/8″ × 3/8″ (3 × 10 mm), ~0.4 m | 1 roll |
| rubber bumpons, 10 mm | as rev 1 |

![gasket stack, exploded](images/rev2_gasket.png)

## Design notes and ideas

These are collected while building rev 1. None of them blocks a rev 1 build.

- **Diodes: optimised per-key placement (decided).** Keep through-hole diodes and the single reversible board. Put each diode in the same spot and orientation at every key, clear of the socket pads, so soldering order doesn't matter. Surface-mount diodes were ruled out because they'd force separate left and right PCBs, which is a logistics problem and harder for other builders. A diode bank was ruled out because of routing density.
- **Plan: lock down and design the controller rev 2 board first, then the rev 2 half boards (focused on a gasket mount).**
- **Before the rev 2 release: research ergonomic defaults.** Research tent, splay plus separation (tied together on a unibody), front-to-back tilt (rev 1's 5° deserves a second look: studies tend to favour flat or negative tilt) and typing height. Choose a well-sourced middle-of-the-road release set. Weigh it against daily-use feedback from rev 1, and render and fit-check alternative sets. Anyone who wants other angles regenerates from `compose/params.py` and orders their own half PCBs (the controller is unaffected).
- **Controller rev 2: designed** (see [Controller rev 2](../../docs/controller-rev2.md)). The half-board side of the standard is still to do: connector on the bottom face, same physical slot order, angle from the case transforms, straight-ribbon check.
- **Rev 2 bridge cover (decided): lifts off without touching the ribbons.** The ribbons run entirely below the cover's parting line, from the controller's connectors through slots in the case's side walls. The cover never clamps, guides or closes over them. Cables to modules mounted in the cover (OLED, pointing device) are long enough to set the cover beside the board, or unplug at the controller's front-edge connectors.
- **Flex cuts in the half PCB.** These pair with a thinner plate (a parametric web thickness, keeping 5 mm only at the supports). On rev 1 the plate is screwed solid, so there's nothing to flex; this only matters for a gasket-mounted revision.
- **No perimeter screw holes through the half PCB.** The plate edge would then be clamped in a continuous gasket strip between frame and case. That needs fewer parts than 14 through-screws.
