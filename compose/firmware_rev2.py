"""
QMK keyboard definition for rev 2 (controller rev 2):  C58_REV=2 python3 -m compose firmware-rev2 [outdir]
-> outdir/firmware/keyboard.json        plain half boards
   outdir/firmware/rgb/keyboard.json    RGB half boards (per-key SK6812 MINI-E, RGB Matrix)

Matrix (controller rev 2 standard, docs/controller-rev2.md): 6 rows x 14 columns, COL2ROW. Rows GP0-5 are shared
by both halves; columns left COL0-6 = GP6-12, right COL0-6 = GP22-16, so a left key sits at [row, col] and a
right key at [row, 13 - col] (COL0 is the outer column on both halves).
LEDs: one chain, controller -> left half (its chain order) -> back through the controller's buffer -> right half.
"""
import os
import sys
import json
from compose import params as PR
from compose import geom as G
from compose.pcb import rev2_half as H

OUT = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
ROWS = [f"GP{g}" for g in range(6)]
COLS_L = [f"GP{g}" for g in range(6, 13)]
COLS_R = [f"GP{g}" for g in (22, 21, 20, 19, 18, 17, 16)]
RGB_PIN = "GP13"
RGB_MAX_BRIGHTNESS = 32          # 58 LEDs at full white stay well under the 0.5 A polyfuse (controller rev 2 sim)


def matrix_pos(k, side):
    return [k.row, k.col if side == "L" else 13 - k.col]


def key_entries():
    P = PR.KEY_PITCH
    ents = []
    for side in ("L", "R"):
        for k in G.LAYOUT.keys:
            w = G.apply(G.M_LW, (k.x, k.y, 0.0))
            x, y = (w[0], w[1]) if side == "L" else (-w[0], w[1])
            rot = (PR.SPLAY_DEG - k.rot) if side == "L" else (k.rot - PR.SPLAY_DEG)
            ents.append(dict(side=side, label=k.label_l if side == "L" else k.label_r, matrix=matrix_pos(k, side),
                             cx=x / P, cy=-y / P, w=k.w, h=k.h, rot=round(rot, 1), k=k))
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


def led_layout():
    """RGB Matrix LEDs in chain order (left half, then right half), with QMK's 224 x 64 coordinates."""
    s = H.plan("hotswap", True)
    pts = []
    for side in ("L", "R"):
        for i in s.led_order:
            k = G.LAYOUT.keys[i]
            c = H.fp2local(k, *H.LED_AT)
            w = G.apply(G.M_LW, (c[0], c[1], 0.0))
            pts.append((side, k, w[0] if side == "L" else -w[0], w[1]))
    xs, ys = [p[2] for p in pts], [p[3] for p in pts]
    sx, sy = 224.0 / (max(xs) - min(xs)), 64.0 / (max(ys) - min(ys))
    return [{"matrix": matrix_pos(k, side), "x": round((x - min(xs)) * sx), "y": round((max(ys) - y) * sy), "flags": 4}
            for side, k, x, y in pts]


def board(rgb):
    kb = {
        "keyboard_name": PR.BOARD_NAME + (" RGB" if rgb else ""),
        "manufacturer": PR.HANDLE,
        "maintainer": PR.HANDLE,
        "processor": "RP2040",
        "bootloader": "rp2040",
        "usb": {"vid": "0xFEED", "pid": "0x4C59" if rgb else "0x4C58", "device_version": "2.0.0"},
        "diode_direction": "COL2ROW",
        "matrix_pins": {"rows": ROWS, "cols": COLS_L + COLS_R[::-1]},
        "features": {"bootmagic": False, "extrakey": True, "mousekey": False, "nkro": True},
        "layouts": {"LAYOUT": {"layout": key_entries()}},
    }
    if rgb:
        kb["features"]["rgb_matrix"] = True
        kb["ws2812"] = {"driver": "vendor", "pin": RGB_PIN}
        kb["rgb_matrix"] = {"driver": "ws2812", "max_brightness": RGB_MAX_BRIGHTNESS, "layout": led_layout(),
                            "animations": {"breathing": True, "cycle_left_right": True, "solid_reactive_simple": True}}
    return kb


def main():
    for rgb, sub in ((False, ""), (True, "rgb")):
        d = os.path.join(OUT, "firmware", sub)
        os.makedirs(d, exist_ok=True)
        kb = board(rgb)
        with open(os.path.join(d, "keyboard.json"), "w") as f:
            json.dump(kb, f, indent=2)
        n = len(kb["layouts"]["LAYOUT"]["layout"])
        print(f"{os.path.join(d, 'keyboard.json')}: {n} keys" + (f", {len(kb['rgb_matrix']['layout'])} LEDs" if rgb else ""))


if __name__ == "__main__":
    main()
