# How the parts fit together

[Home](../README.md) › Docs › Case geometry

No notches, by construction. This applies to every Compose case.

Each half has an interface plane: the plane through its inner edge, perpendicular to its plate.

- The bridge side, plate edge, frame inner face and cover side all lie on that plane, separated by `FIT_GAP`.
- The plate and frame install along the plate normal, which lies in the plane. So they slide past the bridge instead of swinging into it.
- The cover drops straight down in the bridge frame into a slot that only widens upward.
- The trim lip and its reveal stop at the bridge faces on surfaces that also run along the install direction. The lip ends `REVEAL_SIDE_GAP` short of the reveal ends, the same clearance it has along its sides.

Assembly order:

1. Carrier or controller board, plus the Pico (screws from above).
2. Plates with switches and wiring, or with their PCB.
3. Frames.
4. Sandwich and post screws from under the case.
5. Cover.

`python3 -m compose checks` sweeps each part along its real install direction, in that order, from 0.3 to 30 mm, and fails on any contact. Negative controls (parts pushed the wrong way) prove the test can see a collision.
