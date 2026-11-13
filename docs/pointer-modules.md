# Pointer modules

[Home](../README.md) › Docs › Pointer modules

A pointer module is a pointing device on a rev 2 Compose keyboard, with its own cable to the controller. It works like the controller does: a standard fixes the mechanical interface, so one plate or case print takes any device that meets it. The half boards and the controller don't change.

## The standard

`compose/pointer/std.py` is a list of named footprints. The plate and the case are built from it alone, never from a device. The standard fixes only the physical footprint: how a device connects (I2C, PS/2, SPI) is up to the device. This round defines two:

| | `slot` | `bay30` |
|---|---|---|
| where | on the plate, in place of a half's 1.5u thumb key | on the case, in the thumb bay: a pocket the case grows on that half where the layout declares it; every key stays |
| setting | `C58_POINTER=<device>:R` | `C58_POINTER=<device>:R:bay30` |
| window | 22.5 × 28.5 mm, centred on the key | 30 × 30 mm, centred on the bay |
| fixing | 4 M2 heat-set inserts in the plate at (±8, ±11) | 4 posts with M3 heat-set inserts at (±12, ±12) |
| seat | the plate top | the post tops, 3 mm below the plate top |
| cable | down the switch hole and the half board's MX centre hole | down into the pocket, through a diamond hole in the half's wall |
| moves with | the plate (it floats on the gaskets) | the case (rigid) |
| frame | its key opening grows to the window on that side | it covers the pocket as a lid, opened to the window on that side |

**Sizes.** A bigger device gets a new entry, say `bay40`, beside the existing ones. An entry never changes once parts are printed against it, and adding one changes nothing that exists: cases are built from the footprint they use, devices name the footprints they fit, and layouts declare a position per bay size.

A device stands on a printed **carrier**. The carrier stays inside the window and below 16 mm above the plate, screw heads included, and screws to at least two of the footprint's points. The bay's posts and wall hole are always there on a half that has the bay, so a bay case prints the same whatever goes in it.

**Tilt.** A carrier may tilt its board outward, away from the keys, so the thumb meets a ball with the pad of the thumb and not the side of it. The tilt belongs to the carrier, not the standard: the posts and the seat stay flat and parallel to the plate (so one printed case still takes any device), and the carrier is a wedge, its base flat on the posts, its bosses running along the board's normal up to the tilted underside, and the insert holes coaxial with them. The device's carrier sets it per footprint (`TILT` in `pointers/<name>/carrier.py`: angle, and the direction the board's normal leans in the footprint's frame; 0° is outward, away from the keys, 180° toward them). The turn is about the device's touch point (on the board's top face), so the ball barely moves: its top drops 0.3 mm at 15°. `C58_POINTER_TILT=<deg>` overrides the angle (`0` is flat, a positive angle leans outward, a negative one toward the keys; it needs `C58_POINTER` and is ignored without it). The checks measure what the tilt does: the touch surface's height (M6), the board and housing inside the window and under the footprint's top, 0.8 mm between the lowest point under the board and the carrier's base, a standard screw length (M2, M4), a wall round every insert hole (P3), and the cable's drop from the raised pads (P4, P5). On the PIM447 they pass up to 18°; from 19° no standard M2 screw fits the shallower insert holes, and from 20° the parts under the board come within 0.8 mm of the base; toward the keys the checks fail from about −16°. A carrier that never tilts on a footprint (the PIM447 slot) refuses an angle other than 0. The PIM447's bay30 carrier tilts 15°; its slot carrier stays flat, because the base on the plate is too thin for a wedge.

- **The slot** needs a layout with a 1.5u thumb key and a little room beside it. On Compose58 it's Space / Enter.
- **A bay** needs a layout that declares a position for its size: `bays = {"bay30": (x, y, rot)}` in `layouts/<name>/layout.py`, the centre and turn of its square in the left half's frame. `C58_REV=2 python3 -m compose pointer-checks --suggest-bay` prints the line to paste in, one entry per bay size. It goes round the thumb arc from the 1.5u thumb key, or from the innermost bottom-row key if there's none, to the first spot that leaves 5 mm to the other half and to the bridge. `--one-sided` suggests a spot for a bay on one half only, which leaves more room (the distance is then to the other half's plain wall, not to its lobe).
- **Compose58's bay** is 46.0 mm from the 1.5u key's centre: the thumb leaves the key to reach it. The slot puts the device right under the thumb.
- **Only the side you configure gets the bay.** `C58_POINTER=pim447:R:bay30` gives the right half a lobe and the left half the plain case wall and frame, with no pocket and no foot under it. A lobe fuses into its own half's wall and the case stays one solid.
- **An empty bay,** for a case printed ahead of the device: `C58_THUMB_BAY=bay30:R` (or `:L`) grows the lobe on that half with its lid closed. `C58_THUMB_BAY=bay30:LR` forces a symmetric case with both lobes. The side is always named: a bare `bay30` is an error. A device bay plus `C58_THUMB_BAY` gives the union (a device on the right and `bay30:LR` gives both lobes, the module on the right).
- **The gap between two lobes** (a symmetric case) has to be at least 5 mm (check B2). With a lobe on one half only, B2 measures from the lobe to the other half's plain wall instead.

## Devices

Each device is a folder in `pointers/`, like layouts in `layouts/`:

| file | what |
|---|---|
| `module.py` | the part as data: outline, holes, heights, cable pads, how it connects, each number with its source |
| `carrier.py` | its carrier for each footprint it supports |
| `README.md` | what to buy and how to fit it |
| `pcb.py` | optional: a board of its own, generated like the half and controller boards |

`C58_REV=2 python3 -m compose pointer-checks --list` lists them.

| device | footprints | connects | |
|---|---|---|---|
| [pim447](../pointers/pim447/README.md) | slot, bay30 | I2C (Qwiic J5 or J4) | Pimoroni Trackball Breakout |

## Build it

```sh
export C58_REV=2 C58_POINTER=pim447:R          # or: export C58_REV=2 C58_POINTER=pim447:R:bay30
python3 -m compose pointer-checks out_r2t     # its checks (--fast: 2D only, seconds)
python3 -m compose gasket-case out_r2t        # case, plates, frames and the device's carrier
python3 -m compose firmware-rev2 out_r2t      # adds firmware/pointer/ and firmware/rgb_pointer/
```

`C58_POINTER` is device:side[:footprint]: the device's folder name, `L` or `R`, then a footprint from the standard, `slot` (the default) or `bay30`. Leave `C58_POINTER` and `C58_THUMB_BAY` unset and every output is exactly as before.

### Ports

An I2C device's cable plugs into one of two controller connectors. `C58_POINTER_PORT` picks it:

| port | what | when |
|---|---|---|
| `J5` (default) | the Qwiic connector, JST SH 4-pin, top entry | the standard: pointer on Qwiic, the OLED header J4 stays free for an OLED |
| `J4` | the OLED header, a 2.54 mm 1×4 | no OLED, or Qwiic is taken. The header goes on the controller's **underside**: the plug is 12.5 mm tall under a 13 mm gap, so no cable fits on top. It is through-hole, so the same holes take it from below (no board change); its pin tails come out on top. The bottom silkscreen names the pins and outlines the header |

J4 and J5 are the same I2C1 bus (GP14 SDA, GP15 SCL), so a pointer on one and an OLED on the other work together. I2C is multi-drop, so for more devices fan out with a Qwiic hub; nothing in the case holds one yet. The AUX header (GP26–28, 3.3 V, 5 V, GND) is not an I2C port: GP26 and GP27 are I2C1's alternate pins, so using them would take the bus away from J4 and J5, and a second bus isn't reachable on this board. AUX is not offered as a pointer port.

**Soldering straight to the controller.** J4 and AUX are through-hole, so if you are tight on space, or don't need the plug, solder the device's wires directly into their holes (no header, no plug). It is less modular, and the checks model a plug, so a direct solder has more clearance than they show. Both headers also have bottom silkscreen, so you can fit them from either face.

**Cable** (an I2C device: a Qwiic cable with one end cut off and soldered to the device). It runs under the half board and across the middle bay to the controller. `pointer-checks` prints the route and the stock length to buy (P5); on Compose58, with 30 mm of slack:

| device in | to J5: route / buy | to J4: route / buy |
|---|---|---|
| right slot | 124 mm / 200 mm | 162 mm / 200 mm |
| right `bay30` | 167 mm / 200 mm | 206 mm / 300 mm |
| left slot | 189 mm / 300 mm | 98 mm / 150 mm |
| left `bay30` | 232 mm / 300 mm | 141 mm / 200 mm |

**Firmware:** `firmware/pointer/` and `firmware/rgb_pointer/`. For an I2C device: QMK's driver on I2C1 (GP14/GP15, 100 kHz), the same for either port. In the slot, the device's key is dropped from the layout; in the bay, every key stays.

## Checks (`pointer-checks`)

| ids | what |
|---|---|
| S1–S5 | the slot on this layout: a 1.5u thumb key; the window 0.5 mm clear of every other keycap and inside the plate's core; the inserts' walls to switch holes, the core's edge and what's cut from below |
| B1–B7 | the bay on this layout: declared; 5 mm between the walls (lobe to lobe, or lobe to the other half's plain wall when only one half has a bay); the half's own wall whole; a foot under it; 5 mm from the bridge; the posts inside the pocket; the lid's opening clear of the plate and the case's edge |
| M1–M8 | the device on its carrier: known, with a carrier for the footprint; board, housing, carrier and screw heads inside the window and under its top, and the board's low side 0.8 mm above the carrier's base (the tilt); screwed to at least two points; standard screw lengths; the cable's way down; touch height; I2C address; measured on a real part (a warning until then) |
| P1–P7 | assembled: nothing overlaps (and the solids turn as the carrier's maths says); 0.5 mm from the frame; the carrier prints without supports and keeps a wall round each insert hole; the cable route, its length and stock cable; I2C bus capacitance; the firmware variants |

`gasket-checks` also includes the device, its carrier and the cable when `C58_POINTER` is set, and the bay's case and frames whenever the bay is on.

## Adding a device

1. Make `pointers/<name>/module.py` with `DEVICE = Device(...)` (`compose/pointer/device.py` says what each field means). Give every number its source, and leave `measured=False` until a real part has been measured.
2. Make `carrier.py` for each footprint it supports. `POSE` places the device in the footprint's frame, and `USES` picks the points it screws to (at least two). `BASE_T` and `BOARD_Z` set its heights, and `outline(fp, tilt=None)` and `solid(fp, tilt=None)` draw it (`tilt` is an angle in degrees or None for the carrier's own; a carrier that never tilts ignores it). A carrier that tilts its board adds `TILT[fp] = (angle, azimuth)`: the helpers `compose/pointer/device.py` has (`tilt_of`, `holes`, `pad_points`, `normal`, `insert_depth`, `board_low`) take the carrier module and do the maths, so a carrier only draws its wedge. The right half is the left one mirrored, so the device (outline, holes, pads, envelopes) and its carrier must be mirror-symmetric about the device's own y axis; one that isn't needs its own right-hand variant first. `pointers/pim447/carrier.py` is the example.
3. Add a `README.md`: what to buy, how to fit it.
4. Run `pointer-checks --fast`, then the full `pointer-checks` and `gasket-checks`, for each footprint.
5. If it connects other than by I2C, `firmware-rev2` needs to learn its bus first.

## Other devices (not built)

Not built yet:
- **A Cirque 23 mm trackpad:** a bay device.
- **A Sprintek SK8707-01 pointing stick:** the one-piece -005 fits `bay30` (not the slot); the -008, with its sensor apart from its control board, fits both. The 3.3 V variants bring their own PS/2 pull-ups, so they can use the AUX header (GP26 data, GP27 clock) and leave I2C free. In the bay a stick sits on the case, which is what a force sensor wants.
- **A custom trackball** with a PMW3360 sensor: it would need a bigger bay, a new entry in the standard such as `bay40`.
