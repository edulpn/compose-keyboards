# Rev 2

[Home](../README.md) › Docs › Rev 2

The platform's second generation: a gasket-mount case, a shared controller board, reversible half boards in four variants and a flex jumper per half, with the checks and simulations that go with them. Its commands select it (`gasket-*`, `half-rev2`, `flex-*`, `*-rev2`); rev 1 has its own commands and is untouched.

All of it is generated for the layout set in `compose/params.py`. So far that is one layout, Compose58. Where these pages quote a figure or show a picture of it they say so, and [Compose58's rev 2 page](../layouts/lily58/rev2.md) has that keyboard's sizes, parts and check results.

| part | page | code |
|---|---|---|
| Case | [the gasket-mount case](gasket-case.md) | `compose/case/gasket.py`, `compose/checks/gasket.py` |
| Controller | [controller rev 2](controller-rev2.md) | `compose/controller/` |
| Half boards, RGB, firmware | [rev 2 half boards](half-boards-rev2.md) | `compose/pcb/rev2_half.py`, `compose/firmware_rev2.py`, `compose/sim/half_rev2.py` |
| Jumpers | [flex jumpers](flex-jumper.md) | `compose/pcb/jumper.py`, `compose/checks/flex_sim.py` |
| Commands, routing, CI | [building from source](building.md) | |

## Design notes and ideas

Collected while building rev 1; none of them blocks a rev 1 build.

| idea | status | notes |
|---|---|---|
| Per-key diode placement | done | Through-hole diodes on the single reversible board. No single spot fits all 29 keys (LEDs, capacitors and both faces' sockets crowd each switch), so each diode takes the first spot that fits from a short fixed list: column gap first, then row gap. SMD diodes would force separate left and right boards (logistics, and harder for other builders); a diode bank was too dense to route. |
| Controller rev 2 first, then the half boards | done | See [controller rev 2](controller-rev2.md). The half-board side of the standard is done too: connector on the bottom face, same physical slot order. The halves join the controller through custom flex jumpers, so the controller stays the same whatever a layout's angles. |
| Bridge cover lifts off without touching the jumpers | done | The jumpers run below the cover's parting line; the cover never clamps, guides or closes over them. Cables to modules in the cover (OLED, pointing device) are long enough to set the cover beside the board, or unplug at the controller's front-edge connectors. |
| No perimeter screws through the half board | done | The plate edge is clamped in the gasket between frame and case: fewer parts than 14 through-screws. |
| Ergonomic defaults | provisional | Tent, splay plus separation (tied together on a unibody), front-to-back tilt (studies tend to favour flat or negative tilt over rev 1's 5°) and typing height, from a research pass; to be weighed against rev 1 daily use and the angle test prints. Other angles: regenerate from `compose/params.py` and order your own half boards and jumpers (the controller is unaffected). |
| Flex cuts in the half board | open | Paired with a thinner plate (a parametric web thickness, 5 mm only at the supports). Only meaningful with the gasket mount. |
