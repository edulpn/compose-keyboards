# Notices

Compose keyboards is © 2026 edulpn. The keyboard designs are licensed CC BY-NC-SA 4.0 (`LICENSE-CC-BY-NC-SA-4.0`); generic helpers are MIT (`LICENSE`). See "Licensing" in README.md.

It builds on the following work, each under its own license.

## Lily58 (key layout of Compose58)

Compose58 uses the key layout of the Lily58 by kata0510 (Naoki Katahira): https://github.com/kata0510/Lily58. Only the layout is used. The case, boards and firmware here are generated from scratch, and none of the Lily58's files are copied. Its license:

```
MIT License

Copyright (c) 2018 Naoki Katahira

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Lily58 Project contains changes to the original product and / or the original product.
Helix under the MIT license.

Copyright (c) 2018 MakotoKurauchi
https://github.com/MakotoKurauchi/helix

https://opensource.org/licenses/mit-license.php

Lily58 Project contains changes to the original product and / or the original product.
crkbd under the MIT license.

Copyright (c) 2018 foostan
https://github.com/foostan/crkbd

https://opensource.org/licenses/mit-license.php

Lily58 Project contains changes to the original product and / or the original product.
Ergo42 under the MIT license.

Copyright (c) 2017 Biacco42
https://github.com/Biacco42/Ergo42

https://opensource.org/licenses/mit-license.php```

## three.js (renders only)

`compose/render/web/three.module.js`, `compose/render/web/STLLoader.js` and `compose/render/web/BufferGeometryUtils.js` are from three.js (https://github.com/mrdoob/three.js), Copyright 2010-2023 Three.js Authors, MIT License.

## Tools and libraries used to generate the outputs (not bundled)

- **KiCad footprint libraries:** connector, socket and passive footprints placed on the generated boards. KiCad's library license (CC BY-SA 4.0 with an exception) lets designs that use them be released under any license.
- **DejaVu Sans:** the font of the board lettering and silkscreen, converted to outlines. DejaVu fonts license (Bitstream Vera derivative, free to embed).
- **Freerouting** (GPL-3.0): the autorouter, run as a separate program and not included.
- **CadQuery / OpenCascade, trimesh, manifold3d, shapely, ngspice, Playwright, pcb-stackup:** used as libraries and tools under their own licenses; not included.
