# How the parts fit together

[Home](../README.md) › Docs › Case geometry

No notches, by construction. This applies to every Compose case.

Each half has an interface plane: the plane through its inner edge, perpendicular to its plate.

- The bridge side, plate edge, frame inner face and cover side all lie on that plane, separated by `FIT_GAP`.
- The plate and frame install along the plate normal, which lies in the plane. So they slide past the bridge instead of swinging into it.
- The cover drops straight down in the bridge frame into a slot that only widens upward.
- The trim lip and its reveal stop at the bridge faces on surfaces that also run along the install direction. The lip ends `REVEAL_SIDE_GAP` short of the reveal ends, the same clearance it has along its sides.

Assembly order:

1. Controller board onto its posts, clamped by its standoffs, then the Pico.
2. Each half board onto its plate, its two cables plugged into it first (the connectors face down, under the board).
3. The cables into the controller.
4. Plates, with their boards, onto the pads, the cables' slack folded into the bay.
5. Frames, then their screws from under the case.
6. The cover.

`python3 -m compose gasket-checks` sweeps each part along its real install direction (plates and frames along the plate normal, the controller and the cover straight down) and fails on any contact with what is already in place.
