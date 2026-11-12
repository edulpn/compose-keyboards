# Pimoroni Trackball Breakout (PIM447)

[Home](../../README.md) › [Pointer modules](../../docs/pointer-modules.md) › PIM447

A 3–5 V I2C trackball (address 0x0A) with an RGBW LED under the ball. Its carriers fit two footprints of the [pointer mount standard](../../docs/pointer-modules.md#the-standard): `slot` (on the plate, in place of a 1.5u thumb key) and `bay30` (on the case).

| | |
|---|---|
| setting | `C58_POINTER=pim447:R` (slot) or `C58_POINTER=pim447:R:bay30` (bay); `L` for the left half |
| connects | I2C1 on the controller: J5 (Qwiic) or J4 (OLED header). QMK driver `pimoroni_trackball` |
| ball top | 13.0 mm above the plate, about the top of the keycaps |
| carrier | `rev2_pointer_carrier_pim447_slot.stl` or `…_bay30.stl` from `gasket-case`; prints flat on its base, no supports |
| status | the numbers come from a third-party drawing and retailer listings: measure a real part first (`module.py`) |

## What to buy

- The PIM447 breakout. It's reported retired; a replacement is listed as ADA5063. Check what's on sale and measure it.
- A Qwiic / STEMMA QT cable (4-wire JST SH): 200 mm for the slot, 300 mm for the bay (the checks print the route length). One end gets cut off.
- Four M2 × 5 button-head screws and four M2 heat-set inserts for the board on its carrier.
- Slot: two M2 × 4 button-head screws and four M2 heat-set inserts for the plate.
- Bay: four M3 × 5 button-head screws. The M3 inserts for the posts are the case's own (M3 × 5 × 4).

## Fitting: slot

1. Press the four M2 inserts into the plate's top face round the 1.5u thumb key, with the plate out of the case.
2. Leave that key's switch out. On a hotswap board, leave its socket off too. On an RGB board, still fit its LED (and capacitor, if it has one): the LED chain runs through it.
3. Press four M2 inserts into the carrier's bosses.
4. Thread the cable's cut end up through the half board's MX centre hole at that key and the plate's switch hole, then out along the carrier's channel. Solder it to the board: 3–5 V → VCC (3.3 V), SDA → SDA, SCL → SCL, GND → GND. Leave INT unconnected.
5. Screw the carrier to the plate (two M2 × 4, the inserts beside the board's header), then the board to the carrier (four M2 × 5).
6. Route the cable under the half board to the middle bay. Plug it into J5 with the cover off.

## Fitting: bay30

1. Press an M3 insert into the top of each of the four posts in the pocket, and four M2 inserts into the carrier's bosses.
2. Before the plate goes in, feed the cable's cut end from inside the half through the diamond hole in the wall into the pocket.
3. Screw the carrier to the four posts (M3 × 5).
4. Bring the cable up through the carrier's channel beside the board's header, solder it to the board as above, and screw the board to the carrier (four M2 × 5).
5. Route the cable under the half board to the middle bay. Plug it into J5 with the cover off.
