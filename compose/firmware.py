"""
QMK keyboard definition for the PCB build:  python3 -m compose firmware [outdir]
-> outdir/firmware/keyboard.json  (drop into qmk_firmware/keyboards/<name>/)

Matrix: each half has its own 5 rows and 6 columns on the Pico (see
compose.pcb.layout LEFT_GPIO / RIGHT_GPIO), so the unibody scans as 10 rows x 12
columns: left keys at [row, col], right keys at [5 + row, 6 + col].
"""
import os
import sys
import json
import math
from compose import params as PR
from compose import geom as G
from compose.pcb import layout as PL

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"


def key_entries():
    P = PR.KEY_PITCH
    ents = []
    for side in ("L", "R"):
        for k in G.LAYOUT.keys:
            # world-ish top view: left half as laid out, right half mirrored, both rotated by splay
            local = (k.x, k.y)
            w = G.apply(G.M_LW, (local[0], local[1], 0.0))
            x, y = (w[0], w[1]) if side == "L" else (-w[0], w[1])
            # QMK/KLE rotation is clockwise-positive on screen; layout rot is CCW-positive (y up)
            rot = (PR.SPLAY_DEG - k.rot) if side == "L" else (k.rot - PR.SPLAY_DEG)
            r = k.row + (0 if side == "L" else 5)
            c = k.col + (0 if side == "L" else 6)
            ents.append(dict(side=side, label=k.label_l if side == "L" else k.label_r, matrix=[r, c],
                             cx=x / P, cy=-y / P, w=k.w, h=k.h, rot=round(rot, 1)))
    x0 = min(e["cx"] - e["w"] / 2 for e in ents)
    y0 = min(e["cy"] - e["h"] / 2 for e in ents)
    out = []
    for e in sorted(ents, key=lambda e: (round(e["cy"] * 2), e["cx"])):
        d = {"label": e["label"], "matrix": e["matrix"], "x": round(e["cx"] - e["w"] / 2 - x0, 2),
             "y": round(e["cy"] - e["h"] / 2 - y0, 2)}
        if e["w"] != 1:
            d["w"] = e["w"]
        if e["h"] != 1:
            d["h"] = e["h"]
        if abs(e["rot"]) > 0.05:
            d.update(r=e["rot"], rx=round(e["cx"] - x0, 2), ry=round(e["cy"] - y0, 2))
        out.append(d)
    return out


def main():
    rows = [f"GP{g}" for g in PL.LEFT_GPIO["ROW"]] + [f"GP{g}" for g in PL.RIGHT_GPIO["ROW"]]
    cols = [f"GP{g}" for g in PL.LEFT_GPIO["COL"]] + [f"GP{g}" for g in PL.RIGHT_GPIO["COL"]]
    kb = {
        "keyboard_name": PR.BOARD_NAME,
        "manufacturer": PR.HANDLE,
        "maintainer": PR.HANDLE,
        "processor": "RP2040",
        "bootloader": "rp2040",
        "usb": {"vid": "0xFEED", "pid": "0x4C58", "device_version": "1.0.0"},
        "diode_direction": "COL2ROW",
        "matrix_pins": {"rows": rows, "cols": cols},
        "features": {"bootmagic": False, "extrakey": True, "mousekey": False, "nkro": True},
        "layouts": {"LAYOUT": {"layout": key_entries()}},
    }
    d = os.path.join(OUT, "firmware")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "keyboard.json"), "w") as f:
        json.dump(kb, f, indent=2)
    print("rows", rows)
    print("cols", cols)
    print("keys", len(kb["layouts"]["LAYOUT"]["layout"]))


if __name__ == "__main__":
    main()
