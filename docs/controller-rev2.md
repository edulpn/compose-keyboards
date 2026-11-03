# Controller rev 2

[Home](../README.md) › Docs › Controller rev 2

The shared controller board for every Compose split layout: one board, one cable standard and one firmware pin map, so any layout's half boards plug into the same controller.

| top | bottom |
|---|---|
| ![top](images/controller_rev2_top.png) | ![bottom](images/controller_rev2_bottom.png) |

`python3 -m compose controller out` builds, routes and DRC-checks `out/pcb/controller_rev2.*` (KiCad board, JLCPCB Gerber zip, previews). `python3 -m compose sim-controller out` and `python3 -m compose spice-controller out` simulate it (below). It is a breaking change from rev 1 (PicoBlade, 10 × 12 matrix).

- **Board:** 43 × 56 mm, Pico centred (USB at the back); behind the cable connectors the board narrows to 33.2 mm (|x| ≤ 16.6) to clear the plates' inner gasket seats. The mechanical standard (outline, holes, heights, keep-outs) lives in `compose/controller/rev2_std.py`; cases read it from there.
- **Two faces:** the top carries only the Pico sockets, the two cable connectors and the front connector row. Every passive and the optional RGB buffer sit on the **bottom** face (through-hole, soldered from the top), so nothing there is limited by the Pico's 8.5 mm socket height (the rev 2 case leaves 24 mm under the board).
- **Mounting (part of the standard):** four M3 holes, (±17.75, +19.5) beside the Pico's front end and (±13.7, −22.5) beside its USB end (mm from the Pico centre). M3 × 12 male–female hex standoffs (5 or 5.5 mm across flats, 6 mm thread) screw through the board into M3 heat-set inserts in four case posts, clamping it; the cover drops onto the standoffs and takes four M3 × 6 screws. That's the same M3 × 6 screws and M3 × 5 × 4 inserts as the rev 2 frames, so the whole keyboard uses one screw size. Each hole keeps a 6.6 mm circle free of parts and copper on top; no bottom part over a post and no through-hole lead within 4.0 mm of one.
- **Silkscreen:** rev 1's art font (DejaVu Sans); the ∘ ring + "Compose" title standing up the left strip beside the Pico (mirrored on the bottom); "RGB" outline and labels on the bottom silk. Every label sits against what it names: `lhs` / `rhs` along each cable connector's contact row with "1" beside slot 1's contact; pin names standing on each header's outline; "OLED" centred over its header's pin names, "AUX" at the end of its own header row, "Qwiic" right behind its connector. `python3 -m compose controller out --resilk` redraws only the silkscreen on the routed board (DRC, Gerbers, no re-route).
- **Cable connectors:** two Molex 200528-0200 (20 positions, 1.0 mm pitch, bottom contact) on the top face, centred 1.6 mm forward of the Pico centre, cable side flush with the left and right edges. On a half board the connector goes on the bottom face. **Cable: 20-pin 1.0 mm FFC, contacts on opposite sides ("type B / reverse"), the same for both halves.** Length is set by the case: 50 mm for Compose58 rev 2.
- **Slot order** (slot 1 = back-most contact; the same physical order on both connectors, so the right connector is turned 180° and its pad numbers run backwards):

  | slot | 1 | 2 | 3 | 4 | 5–11 | 12–17 | 18 | 19 | 20 |
  |---|---|---|---|---|---|---|---|---|---|
  | line | GND | 5 V LED | RGB data to the half | GND | COL0–6 | ROW0–5 | RGB data back | 5 V LED | GND |

  The order is reversal-safe: a cable fitted flipped (slot k meets 21 − k) puts 5 V on 5 V, GND on GND and the two RGB data lines on each other through the 330 Ω; rows and columns just scramble. Never set `MATRIX_UNSELECT_DRIVE_HIGH` (slot 4 GND would meet ROW5 on a flipped cable). The RGB line into the half sits between 5 V and GND.
- **Pins (QMK `keyboard.json`, also written to `out/pcb/controller_rev2_qmk.json`):**
  - matrix 6 × 14, `COL2ROW`; rows GP0–5 (shared by both halves);
  - columns: left COL0–6 = GP6–12; right COL0–6 = GP22, 21, 20, 19, 18, 17, 16 (COL0 = the outer pinky column on both halves), so the matrix columns left to right are GP6–12, GP16–22;
  - RGB data GP13 (`ws2812` vendor driver), chain controller → left half → controller → right half;
  - I2C1: SDA GP14, SCL GP15, 4.7 kΩ pull-ups to 3.3 V;
  - AUX header: GP26, GP27, GP28 (ADC), 3.3 V, 5 V (VBUS), GND.
- **Connectors on the front edge:** OLED-style 4-pin header (GND, VCC = 3.3 V, SCL, SDA, printed on the board), AUX 6-pin header, Qwiic/STEMMA QT (JST SH 4-pin, top entry, so the cable rises straight to a module in the cover). Modules mount in the bridge cover and plug in with short cables.
- **PS/2 pointing stick** on the I2C header: power it from 3.3 V (the VCC pin), or remove the stick's own pull-ups. A 5 V stick with pull-ups would push the RP2040 pins past their 3.8 V limit.
- **Optional RGB** (outlined "RGB" on the bottom silkscreen; leave it empty for no RGB, firmware RGB off, and the cables' 5 V lines stay dead):
  - U2 74HCT125 (DIP-14) buffer, 3.3 → 5 V data, with C1 100 nF; R3 330 Ω series; R4 100 kΩ pull-down (keeps the data low before the Pico boots, so the LEDs don't latch noise at plug-in);
  - a second gate of the same 74HCT125 re-drives the chain on its way from the left half to the right half: R5 220 Ω in (limits clamp current), R6 100 kΩ pull-down, R7 330 Ω out. All of the RGB group except F1 sits in the box under the Pico on the bottom face; F1 stands on the bottom face beside the Pico, back right. Wired straight through, the two cable runs ring too much (see the simulation);
  - F1 Bourns MF-RHT050 polyfuse VBUS → LED 5 V; C2 10 µF bulk (with 100 µF the hot-plug dip on the USB port would be 1.7× a spec-limit device instead of 1.4×);
  - fit the whole group or none of it (a buffer without the fuse is back-fed through its input).
  - Firmware: `RGB_MATRIX_MAXIMUM_BRIGHTNESS 32` (84 LEDs at full white stay under 450 mA: the fuse holds 0.5 A and USB gives 0.5 A in total).
  - Rev 2 halves: DIN from slot 3 to the first LED, last DOUT back on slot 18; a pass-through link when a half has no LEDs; one 100 nF per 2–4 LEDs rather than per LED (hot-plug inrush).
- **Everything is through-hole** except the two FFC connectors and the Qwiic connector.

**Controller rev 2 BOM**

| ref | part | qty |
|---|---|---|
| U1 | Raspberry Pi Pico / Pico W / Pico 2 (W) or pin-compatible, on 2 × 1×20 female headers (8.5 mm) | 1 |
| JL, JR | Molex 200528-0200 FFC connector, 20 pos, 1.0 mm, bottom contact | 2 |
| — | FFC cable, 20 pin, 1.0 mm pitch, 0.3 mm, opposite-side contacts (type B) | 2 |
| J4 | 1×4 2.54 mm header (OLED / I2C) | 1 |
| J6 | 1×6 2.54 mm header (AUX) | 1 |
| J5 | JST BM04B-SRSS-TB (Qwiic, top entry) | 1 |
| R1, R2 | 4.7 kΩ axial | 2 |
| — | M3 × 12 male–female hex standoffs (5 or 5.5 mm AF, 6 mm thread) + M3 × 6 button-head screws for the cover + M3 × 5 × 4 heat-set inserts for the case posts | 4 + 4 + 4 |
| *RGB:* U2 | 74HCT125, DIP-14 | 1 |
| *RGB:* C1 | 100 nF ceramic, 2.5 mm pitch | 1 |
| *RGB:* R3, R7 / R4, R6 / R5 | 330 Ω / 100 kΩ / 220 Ω axial | 2 / 2 / 1 |
| *RGB:* F1 | Bourns MF-RHT050 polyfuse (bottom face, standing) | 1 |
| *RGB:* C2 | 10 µF 16 V electrolytic, 5 mm diameter, 2.0 mm pitch, up to 11 mm tall (bottom face) | 1 |

**Simulation** (`compose/sim/controller_copper.py`: copper level; `compose/sim/controller_spice.py`: ngspice, report in `out/sim_controller_rev2/report.md`): 0 failures.

- *Copper level:* the netlist rebuilt from the routed copper matches an independent pin-level spec (Pico, FFC slots, DIP pin 1 and its pin order as seen from the face the chip sits on, polarised C2, headers, Qwiic); silkscreen pin labels match the copper; the optional-RGB group's behaviour when fitted and empty; QMK COL2ROW scan through two cables into model halves: all 84 keys, 1000 random chords, no ghosting (including across the shared rows); a cable fitted flipped is harmless; negative controls (swapped firmware pin, unrotated right connector, reversed diodes, injected short, cut track) are all caught.
- *RGB data* (192 corners: drive strengths, cable 50–250 mm and 100–180 Ω, LED rail down to 4.3 V): clean single edges at the LED, '0' 337–366 ns and '1' 887–916 ns (spec 250–550 / 650–950), overshoot ≤ 0.3 V. Without the buffer, 3.3 V data passes in only 8 of 24 corners.
- *Chain hop* (96 corners): re-driven by gate 2, in spec everywhere, input clamp current ≤ 7 mA. Wired straight through it failed half the corners (0.95 V overshoot).
- *I2C:* 400 kHz with up to 60 pF of bus on the board's pull-ups, 100 kHz to 100 pF; modules with their own 2.2–10 k pull-ups stay in spec.
- *Power:* the far LED stays ≥ 3.85 V at 450 mA, even with a tripped-and-recovered fuse. Hot-plug dip with RGB fitted is 1.4× a USB spec-limit device, mostly from the halves' LED decoupling (warning).
- *Matrix:* pressed key reads 0.47 V (VIL 0.8 V), settles in 66 ns (QMK samples at ~250 ns), recovers in 4.1 µs (QMK waits 30 µs); worst cable/board crosstalk leaves idle lines ≥ 2.39 V (limit 2.0 V).
- *PS/2 stick:* fine from 3.3 V; a 5 V stick with its own pull-ups would exceed the RP2040's 3.8 V limit (warning, in the notes above).
- *With real halves:* `sim-half-rev2` scans this board's copper end to end with the Compose58 rev 2 half boards (see [rev 2](../layouts/lily58/rev2.md#the-rev-2-half-boards)). The 50 mm cable is inside the 50–250 mm the RGB data sweep covers.
