"""
QMK keyboard definition for rev 2 (controller rev 2):  C58_REV=2 python3 -m compose firmware-rev2 [outdir]
-> outdir/firmware/keyboard.json        plain half boards
   outdir/firmware/rgb/keyboard.json    RGB half boards (per-key SK6812 MINI-E, RGB Matrix)
   outdir/firmware/pointer/, rgb_pointer/   with C58_POINTER set: the same plus the pointer module (keyboard.json,
                                        rules.mk, config.h, halconf.h, mcuconf.h; docs/pointer-modules.md)

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
POINTER_PID = {False: "0x4C5A", True: "0x4C5B"}   # plain / RGB boards with a pointer module
I2C_SDA, I2C_SCL = "GP14", "GP15"                  # controller rev 2 I2C1 (J4 and J5)
I2C_CLOCK = 100000                                 # inside the simulated 100 pF budget (spice-controller section C)


def matrix_pos(k, side):
    return [k.row, k.col if side == "L" else 13 - k.col]


def key_entries(skip=None):
    """QMK layout entries for both halves; `skip` = (side, key index) of a key that isn't there (a pointer module)."""
    P = PR.KEY_PITCH
    ents = []
    for side in ("L", "R"):
        for i, k in enumerate(G.LAYOUT.keys):
            if skip == (side, i):
                continue
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


def board(rgb, pointer=None):
    """keyboard.json; `pointer` is a compose.pointer.place.Placement when the board has a pointer module (in place of
    its 1.5u thumb key, or in the thumb bay with every key kept)."""
    skip = (pointer.side, pointer.key_index) if pointer is not None and pointer.key_index is not None else None
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
        "layouts": {"LAYOUT": {"layout": key_entries(skip)}},
    }
    if rgb:
        kb["features"]["rgb_matrix"] = True
        kb["ws2812"] = {"driver": "vendor", "pin": RGB_PIN}
        kb["rgb_matrix"] = {"driver": "ws2812", "max_brightness": RGB_MAX_BRIGHTNESS, "layout": led_layout(),
                            "animations": {"breathing": True, "cycle_left_right": True, "solid_reactive_simple": True}}
    if pointer is not None:
        kb["keyboard_name"] += " pointer"
        kb["usb"]["pid"] = POINTER_PID[rgb]
        kb["features"].update(pointing_device=True, mousekey=True)
        if rgb and skip is not None:  # the LED under the module stays in the chain, but no key is there any more
            gone = matrix_pos(G.LAYOUT.keys[pointer.key_index], pointer.side)
            for led in kb["rgb_matrix"]["layout"]:
                if led.get("matrix") == gone:
                    del led["matrix"]
    return kb


def pointer_files(pl):
    """rules.mk, config.h, halconf.h, mcuconf.h for the pointer variants: the driver (QMK has no keyboard.json key
    for it), I2C1 on GP14/GP15 and the device's own settings. The standard leaves the connection to the device: this
    generator knows I2C devices so far."""
    m = pl.device
    if m.bus != "i2c":
        raise SystemExit(f"{m.name}: firmware-rev2 doesn't know {m.bus!r} devices yet (only i2c)")
    config = ["#pragma once", "", "// generated by compose firmware-rev2 (C58_POINTER): docs/pointer-modules.md",
              "#define I2C_DRIVER I2CD1", f"#define I2C1_SDA_PIN {I2C_SDA}", f"#define I2C1_SCL_PIN {I2C_SCL}",
              f"#define I2C1_CLOCK_SPEED {I2C_CLOCK}"] + [f"#define {k} {v}" for k, v in m.qmk_defines]
    halconf = ["#pragma once", "", "#define HAL_USE_I2C TRUE", "", "#include_next <halconf.h>"]
    mcuconf = ["#pragma once", "", "#include_next <mcuconf.h>", "", "#undef RP_I2C_USE_I2C1",
               "#define RP_I2C_USE_I2C1 TRUE"]
    rules = [f"POINTING_DEVICE_DRIVER = {m.driver}"]
    return {"rules.mk": rules, "config.h": config, "halconf.h": halconf, "mcuconf.h": mcuconf}


def main():
    from compose import pointer as PT
    from compose.pointer import place as PPL
    cfg = PT.active()
    pl = PPL.place(cfg) if cfg is not None else None
    variants = [(False, "", None), (True, "rgb", None)]
    if pl is not None:
        variants += [(False, "pointer", pl), (True, "rgb_pointer", pl)]
    for rgb, sub, ptr in variants:
        d = os.path.join(OUT, "firmware", sub)
        os.makedirs(d, exist_ok=True)
        kb = board(rgb, ptr)
        with open(os.path.join(d, "keyboard.json"), "w") as f:
            json.dump(kb, f, indent=2)
        if ptr is not None:
            for name, lines in pointer_files(ptr).items():
                with open(os.path.join(d, name), "w") as f:
                    f.write("\n".join(lines) + "\n")
        n = len(kb["layouts"]["LAYOUT"]["layout"])
        print(f"{os.path.join(d, 'keyboard.json')}: {n} keys" + (f", {len(kb['rgb_matrix']['layout'])} LEDs" if rgb else ""))


if __name__ == "__main__":
    main()
