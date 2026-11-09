"""
Copper-level simulation of the routed controller rev 2:   python3 -m compose sim-controller [outdir]

Independent of the net names the board was built with:
  1. Copper connectivity is rebuilt from geometry (pads, tracks and vias that touch on a layer).
  2. Parts are placed the way a builder would, from their datasheets:
       Pico       pinout at its mechanical pin positions (pin 1 top-left seen from above, USB at the back)
       FFC        Molex 52610 vertical: contacts at the physical slots (slot 1 = the back-most), whatever the pad
                  numbers; each terminal's two tails on one copper node; the contact face toward the Pico
       74HCT125   DIP-14 pinout from pin 1 = the square pad, counter-clockwise seen from the side its body is on
       C2         + lead = square pad;  headers pin 1 = square pad;  Qwiic pins in a row from pin 1
  3. The netlist those parts make is compared with the spec below (written from the README, not from
     compose/controller/rev2.py), for the fully populated board and with the optional RGB parts left out.
  4. Silkscreen labels are checked against what the copper under them does.
  5. Two model halves (42 keys each, diode per key, reversible board = right half mirrored) are joined by
     20-way jumpers (same physical slot order at both ends); the QMK COL2ROW scan runs with the rev 2 pin
     config: every key alone, random chords, the ghosting square, and a cable fitted flipped (the pinout's
     reversal safety).
  6. Negative controls: a swapped firmware pin, a reversed right connector, reversed diodes, an injected
     short and a cut track must all be caught.
"""
import os
import sys
import json
import random
import itertools
import pcbnew
from shapely.geometry import Point

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
sys.argv = sys.argv[:1] + [OUT]
from compose.sim import matrix as SP                                         # Copper class (geometry-only connectivity)

ToMM = pcbnew.ToMM
FAIL = []
CX, CY = 100.0, 100.0


def ok(cond, msg):
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        FAIL.append(msg)
    return cond


# ---------------------------------------------------------------- the spec (README "Controller rev 2")
PICO_PINOUT = {1: "GP0", 2: "GP1", 3: "GND", 4: "GP2", 5: "GP3", 6: "GP4", 7: "GP5", 8: "GND", 9: "GP6", 10: "GP7",
               11: "GP8", 12: "GP9", 13: "GND", 14: "GP10", 15: "GP11", 16: "GP12", 17: "GP13", 18: "GND", 19: "GP14",
               20: "GP15", 21: "GP16", 22: "GP17", 23: "GND", 24: "GP18", 25: "GP19", 26: "GP20", 27: "GP21",
               28: "GND", 29: "GP22", 30: "RUN", 31: "GP26", 32: "GP27", 33: "AGND", 34: "GP28", 35: "ADC_VREF",
               36: "3V3", 37: "3V3_EN", 38: "GND", 39: "VSYS", 40: "VBUS"}            # Raspberry Pi Pico datasheet
HCT125 = {1: "1OE", 2: "1A", 3: "1Y", 4: "2OE", 5: "2A", 6: "2Y", 7: "GND", 8: "3Y", 9: "3A", 10: "3OE", 11: "4Y",
          12: "4A", 13: "4OE", 14: "VCC"}                                                 # 74HCT125 datasheet
SLOTS = {1: "GND", 2: "5V_LED", 3: "RGB_TO_HALF", 4: "GND",
         5: "COL0", 6: "COL1", 7: "COL2", 8: "COL3", 9: "COL4", 10: "COL5", 11: "COL6",
         12: "ROW0", 13: "ROW1", 14: "ROW2", 15: "ROW3", 16: "ROW4", 17: "ROW5",
         18: "RGB_FROM_HALF", 19: "5V_LED", 20: "GND"}
ROW_GPIO = ["GP0", "GP1", "GP2", "GP3", "GP4", "GP5"]
COL_GPIO = {"L": ["GP6", "GP7", "GP8", "GP9", "GP10", "GP11", "GP12"],
            "R": ["GP22", "GP21", "GP20", "GP19", "GP18", "GP17", "GP16"]}      # half COL0 (outer) .. COL6 (inner)
QMK_V2 = {"matrix_pins": {"rows": ROW_GPIO, "cols": COL_GPIO["L"] + COL_GPIO["R"][::-1]},
          "diode_direction": "COL2ROW", "ws2812": {"driver": "vendor", "pin": "GP13"},
          "i2c": {"driver": "I2CD1", "sda": "GP14", "scl": "GP15"}}


def spec_nets(rgb=True):
    """Expected nets as sets of physical part pins; RGB parts absent when rgb=False."""
    n = {}

    def add(net, *pins):
        n.setdefault(net, set()).update(pins)
    for pin, f in PICO_PINOUT.items():
        if f in ("GND", "AGND"):
            add("GND", ("pico", pin))
        elif f == "3V3":
            add("3V3", ("pico", pin))
        elif f == "VBUS":
            add("VBUS", ("pico", pin))
        elif f.startswith("GP"):
            add(f, ("pico", pin))
        else:
            add("NC_" + f, ("pico", pin))                     # RUN, ADC_VREF, 3V3_EN, VSYS: must stay unconnected
    for side in ("L", "R"):
        for s, f in SLOTS.items():
            pin = ("ffc" + side, s)
            if f == "GND":
                add("GND", pin)
            elif f == "5V_LED":
                add("5V_LED", pin)
            elif f.startswith("ROW"):
                add(ROW_GPIO[int(f[3])], pin)
            elif f.startswith("COL"):
                add(COL_GPIO[side][int(f[3])], pin)
            elif f == "RGB_TO_HALF":
                add("RGB_L_IN" if side == "L" else "RGB_R_IN", pin)
            elif f == "RGB_FROM_HALF":
                add("RGB_L_RET" if side == "L" else "NC_RGB_END", pin)
        # (the Molex 52610 has no mounting tabs)
    # I2C + AUX
    add("GND", ("J4", 1)); add("3V3", ("J4", 2)); add("GP15", ("J4", 3)); add("GP14", ("J4", 4))
    add("GND", ("J5", 1)); add("3V3", ("J5", 2)); add("GP14", ("J5", 3)); add("GP15", ("J5", 4)); add("GND", ("J5", "MP"))
    for i, f in enumerate(("GP26", "GP27", "GP28", "3V3", "VBUS", "GND")):
        add(f, ("J6", i + 1))
    add("GP14", ("R1", 1)); add("3V3", ("R1", 2)); add("GP15", ("R2", 1)); add("3V3", ("R2", 2))
    # optional RGB group: footprints exist either way (copper), parts only when rgb=True
    add("GP13", ("U2", 2), ("R4", 1))
    add("GND", ("U2", 1), ("U2", 4), ("U2", 7), ("U2", 9), ("U2", 12), ("R4", 2), ("R6", 2))
    add("5V_LED", ("U2", 14), ("U2", 10), ("U2", 13), ("C1", "+"), ("C2", "+"), ("F1", "out"))
    add("RGB_L_RET", ("R5", "a"))
    add("RGB_HOP_IN", ("R5", "b"), ("U2", 5), ("R6", 1))
    add("RGB_HOP_BUF", ("U2", 6), ("R7", "a"))
    add("RGB_R_IN", ("R7", "b"))
    add("GND", ("C1", "-"), ("C2", "-"))
    add("RGB_BUF", ("U2", 3), ("R3", "a"))
    add("RGB_L_IN", ("R3", "b"))
    add("VBUS", ("F1", "in"))
    for p in (8, 11):
        add(f"NC_U2_{p}", ("U2", p))                          # unused buffer outputs: unconnected
    return n


# ---------------------------------------------------------------- physical part pins on the copper
class Board:
    def __init__(self, path):
        self.cu = SP.Copper(path)
        self.b = self.cu.b
        self.fp = {f.GetReference(): f for f in self.b.GetFootprints()}

    def pad_xy(self, ref, num):
        return [(ToMM(p.GetPosition().x), ToMM(p.GetPosition().y), p) for p in self.fp[ref].Pads() if p.GetNumber() == str(num)]

    def node(self, xy, layer=pcbnew.F_Cu):
        return self.cu.node_at(xy, layer)


def place_parts(B):
    """Map every physical part pin to a copper group, from mechanical positions and datasheet pinouts."""
    pins, notes = {}, []
    # the Molex 52610's terminals each have two tails (a pad either side of the body): the part joins them, so
    # join their copper first (before any node is looked up)
    cu = B.cu
    for side in ("L", "R"):
        fp = B.fp["J" + side]
        for y in {round(ToMM(p.GetPosition().y), 2) for p in fp.Pads()}:
            idx = []
            for p in fp.Pads():
                if abs(ToMM(p.GetPosition().y) - y) < 0.01:
                    q = Point(ToMM(p.GetPosition().x), ToMM(p.GetPosition().y))
                    idx += [i for i, (g, lay, lab) in enumerate(cu.items) if lay == pcbnew.F_Cu
                            and lab not in ("track", "zone") and g.contains(q)][:1]
            for i in idx[1:]:
                cu.union(idx[0], i)
    # Pico: pin 1 top-left seen from above with USB at the back (-y); 2.54 mm pitch, rows 17.78 mm apart
    for p in range(1, 41):
        x = -8.89 if p <= 20 else 8.89
        y = -24.13 + (p - 1) * 2.54 if p <= 20 else 24.13 - (p - 21) * 2.54
        pins[("pico", p)] = B.node((CX + x, CY + y))
    # cable connectors (Molex 52610, vertical): contacts at the physical slots, slot 1 = the back-most (each
    # terminal's two tails joined above, so they're one node)
    for side in ("L", "R"):
        fp = B.fp["J" + side]
        ys = sorted({round(ToMM(p.GetPosition().y), 2) for p in fp.Pads()})
        ok(len(ys) == 20, f"FFC {side}: 20 contact positions")
        rows = {}
        for i, y in enumerate(ys):
            tails = [p for p in fp.Pads() if abs(ToMM(p.GetPosition().y) - y) < 0.01]
            nodes = {B.node((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y))) for p in tails}
            ok(len(tails) == 2 and len(nodes) == 1, f"FFC {side} slot {i + 1}: two tails, one terminal")
            pins[("ffc" + side, i + 1)] = nodes.pop()
            for p in tails:
                rows.setdefault(round(ToMM(p.GetSize().x if p.GetSize().x > p.GetSize().y else p.GetSize().y), 2),
                                []).append(ToMM(p.GetPosition().x) - CX)
        # Molex's pattern: the contact-face row has the longer pads (1.85 vs 1.65); it must face the Pico (inboard)
        long_x = sum(rows[max(rows)]) / len(rows[max(rows)]); short_x = sum(rows[min(rows)]) / len(rows[min(rows)])
        ok(abs(long_x) < abs(short_x), f"FFC {side}: contact face toward the Pico (the jumper's conductors face inboard)")
    # DIP-14: pin 1 = the square pad; the rest counter-clockwise seen from above
    u = B.fp["U2"]
    pads = [p for p in u.Pads()]
    sq = [p for p in pads if p.GetShape() in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT)]
    ok(len(sq) == 1, "U2: exactly one square (pin 1) pad")
    p1 = sq[0].GetPosition()
    col1 = sorted([p for p in pads if abs(p.GetPosition().x - p1.x) < 1000], key=lambda p: abs(p.GetPosition().y - p1.y))
    col2 = sorted([p for p in pads if abs(p.GetPosition().x - p1.x) >= 1000], key=lambda p: -abs(p.GetPosition().y - p1.y))
    order = col1 + col2                                       # down the pin-1 row, back up the other
    # counter-clockwise check (seen from above, KiCad y down): pin 1 -> 7 then across -> 8 ... 14
    v1 = order[6].GetPosition() - order[0].GetPosition()
    v2 = order[7].GetPosition() - order[6].GetPosition()
    cross = v1.x * v2.y - v1.y * v2.x                          # < 0 = counter-clockwise on a y-down screen
    if u.IsFlipped():                                          # body on the bottom face: the builder sees it from below
        ok(cross > 0, "U2 (bottom face): pins run counter-clockwise from pin 1 seen from below (clockwise from above)")
    else:
        ok(cross < 0, "U2: pins run counter-clockwise from pin 1 (top view)")
    for i, p in enumerate(order):
        pins[("U2", i + 1)] = B.node((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)))
    # two-lead parts
    for ref, names in (("R1", (1, 2)), ("R2", (1, 2)), ("R3", ("a", "b")), ("R4", (1, 2)), ("R5", ("a", "b")),
                       ("R6", (1, 2)), ("R7", ("a", "b")), ("C1", ("+", "-")),
                       ("F1", ("in", "out"))):
        ps = sorted(B.fp[ref].Pads(), key=lambda p: p.GetNumber())
        for nm, p in zip(names, ps):
            pins[(ref, nm)] = B.node((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)))
    c2 = list(B.fp["C2"].Pads())
    plus = [p for p in c2 if p.GetShape() in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT)]
    ok(len(plus) == 1, "C2: polarity marked by one square (+) pad")
    minus = [p for p in c2 if p not in plus]
    pins[("C2", "+")] = B.node((ToMM(plus[0].GetPosition().x), ToMM(plus[0].GetPosition().y)))
    pins[("C2", "-")] = B.node((ToMM(minus[0].GetPosition().x), ToMM(minus[0].GetPosition().y)))
    # headers: pin 1 = square pad, then in a line
    for ref in ("J4", "J6"):
        ps = list(B.fp[ref].Pads())
        s1 = [p for p in ps if p.GetShape() in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT)]
        ok(len(s1) == 1, f"{ref}: one square pin-1 pad")
        o = s1[0].GetPosition()
        for i, p in enumerate(sorted(ps, key=lambda p: (p.GetPosition() - o).EuclideanNorm())):
            pins[(ref, i + 1)] = B.node((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)))
    # Qwiic (JST SH, keyed; cables are 1:1): pin 1 = footprint pad 1; Qwiic: 1 GND (black), 2 3V3, 3 SDA, 4 SCL
    ps = [p for p in B.fp["J5"].Pads() if p.GetNumber() != "MP"]
    by = {p.GetNumber(): p for p in ps}
    xs = [by[str(i)].GetPosition().x for i in range(1, 5)]
    ok(all(a < b for a, b in zip(xs, xs[1:])) or all(a > b for a, b in zip(xs, xs[1:])), "J5: contacts in order 1-4")
    for i in range(1, 5):
        p = by[str(i)]
        pins[("J5", i)] = B.node((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y)))
    mp = [B.node((ToMM(p.GetPosition().x), ToMM(p.GetPosition().y))) for p in B.fp["J5"].Pads() if p.GetNumber() == "MP"]
    pins[("J5", "MP")] = mp[0] if len(set(mp)) == 1 else ("split", tuple(mp))
    return pins


def compare(pins, spec, label):
    print(f"\n== netlist from copper vs spec ({label})")
    bad = []
    group_of = {}
    for net, members in spec.items():
        nodes = {pins.get(m) for m in members}
        if None in nodes:
            bad.append(f"{net}: pin(s) not on copper {[m for m in members if pins.get(m) is None]}")
        nodes.discard(None)
        if net.startswith("NC_"):
            for m in members:
                nd = pins.get(m)
                others = [k for k, v in pins.items() if v == nd and k != m]
                if nd is not None and others:
                    bad.append(f"{m} should be unconnected but joins {others[:4]}")
            continue
        if len(nodes) != 1:
            bad.append(f"{net}: split into {len(nodes)} copper islands")
        for nd in nodes:
            group_of.setdefault(nd, set()).add(net)
    shorts = {nd: nets for nd, nets in group_of.items() if len(nets) > 1}
    for nd, nets in shorts.items():
        bad.append(f"short between {sorted(nets)}")
    ok(not bad, f"every spec net is one copper island, no shorts, unused pins isolated"
       + (": " + "; ".join(bad[:6]) if bad else f" ({len([n for n in spec if not n.startswith('NC_')])} nets)"))
    return not bad


def electrical_variants(pins):
    """Behaviour with the optional RGB group fitted / left empty, from the copper groups."""
    print("\n== RGB group fitted / empty")
    g = lambda m: pins[m]
    # empty: no F1 -> 5V_LED is its own island, nothing drives it; nothing else depends on it
    ok(g(("F1", "in")) != g(("F1", "out")), "without F1 the cable 5 V lines are isolated from VBUS (dead)")
    ok(g(("F1", "in")) == g(("pico", 40)), "F1 is fed from Pico VBUS (pin 40)")
    ok(g(("U2", 14)) == g(("F1", "out")), "the buffer runs from the fused LED rail (its output high = LED supply)")
    ok(g(("U2", 1)) == g(("pico", 3)), "buffer 1 is always enabled (1OE to GND)")
    ok(g(("U2", 2)) == g(("pico", 17)), "buffer 1 input = GP13 (Pico pin 17)")
    ok(g(("U2", 4)) == g(("pico", 3)), "buffer 2 always enabled (2OE to GND)")
    ok(all(g(("U2", p)) == g(("pico", 3)) for p in (9, 12)) and all(g(("U2", p)) == g(("U2", 14)) for p in (10, 13)),
       "unused buffers 3/4: inputs grounded, outputs disabled (OE high)")
    ok(g(("R4", 1)) == g(("U2", 2)) and g(("R4", 2)) == g(("pico", 3)), "100k pull-down holds the buffer input low before the Pico boots")
    ok(g(("R3", "a")) == g(("U2", 3)) and g(("R3", "b")) == g(("ffcL", 3)), "data: buffer -> 330 ohm -> left FFC slot 3")
    ok(g(("ffcL", 18)) == g(("R5", "a")) and g(("R5", "b")) == g(("U2", 5)) and g(("R6", 1)) == g(("U2", 5))
       and g(("R6", 2)) == g(("pico", 3)), "chain return: left slot 18 -> 220 ohm -> buffer 2 input, 100k pull-down")
    ok(g(("U2", 6)) == g(("R7", "a")) and g(("R7", "b")) == g(("ffcR", 3)), "buffer 2 -> 330 ohm -> right FFC slot 3")
    ok(g(("ffcL", 18)) != g(("ffcR", 3)), "the hop is re-driven, not wired straight through")
    others = [k for k, v in pins.items() if v == g(("ffcR", 18)) and k != ("ffcR", 18)]
    ok(not others, "right slot 18 (end of chain) left open")
    # with the group empty, which Pico pins see anything new? GP13 only sees R4/U2 pads -> unloaded
    gp13 = [k for k, v in pins.items() if v == g(("pico", 17)) and k[0] not in ("pico",)]
    ok(set(k[0] for k in gp13) <= {"U2", "R4"}, f"GP13 reaches only the optional parts ({sorted(set(k[0] for k in gp13))}) - "
       "with RGB empty it is a free pin")


def silk_truth(B, pins):
    """Silkscreen pin labels must name what the copper under them carries."""
    print("\n== silkscreen vs copper")
    # labels are font outlines (polygons); the builder records what it printed where, and every record must
    # sit on actual silkscreen ink so the record can't drift from the artwork
    recs = json.load(open(os.path.join(OUT, "pcb", "controller_rev2_silk.json")))
    ink = []
    for d in B.b.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS and d.GetClass() == "PCB_SHAPE" and d.GetShape() == pcbnew.SHAPE_T_POLY:
            bb = d.GetBoundingBox()
            ink.append((ToMM(bb.GetLeft()), ToMM(bb.GetTop()), ToMM(bb.GetRight()), ToMM(bb.GetBottom())))
    texts = [(r["text"], CX + r["x"], CY + r["y"]) for r in recs]
    near = lambda x, y, bb: max(bb[0] - x, 0, x - bb[2]) ** 2 + max(bb[1] - y, 0, y - bb[3]) ** 2 <= 0.35 ** 2
    orphan = [t for t, x, y in texts if not any(near(x, y, bb) for bb in ink)]     # (glyph gaps < 0.35 mm)
    ok(not orphan, f"{len(texts)} recorded labels all sit on printed silkscreen" + (f": missing {orphan}" if orphan else ""))
    want = {"GND": "GND", "VCC": "3V3", "SCL": "GP15", "SDA": "GP14", "26": "GP26", "27": "GP27", "28": "GP28",
            "3V3": "3V3", "5V": "VBUS"}
    net_of = {}
    for net, mem in spec_nets().items():
        for m in mem:
            net_of[pins.get(m)] = net
    bad, n = [], 0
    for txt, x, y in texts:
        if txt not in want:
            continue
        cands = [(ref, i) for ref in ("J4", "J6") for i in range(1, 7) if (ref, i) in pins]
        best = min(cands, key=lambda k: min(((px - x) ** 2 + (py - y) ** 2) for px, py, _ in B.pad_xy(k[0], pad_number(B, k))))
        n += 1
        got = net_of.get(pins[best])
        if got != want[txt]:
            bad.append(f"'{txt}' sits on {best} = {got}")
    ok(not bad and n >= 10, f"{n} header labels name the net of the pin they sit on" + (f": {bad}" if bad else ""))
    # FFC "1" marks and L/R
    for side, sx, nm in (("L", -1, "lhs"), ("R", 1, "rhs")):
        ones = [(x, y) for t, x, y in texts if t == "1" and (x - CX) * sx > 0]
        s1 = B.cu.items  # noqa
        fp = B.fp["J" + side]
        y1 = min(ToMM(p.GetPosition().y) for p in fp.Pads())
        ok(ones and abs(ones[0][1] - y1) < 1.0, f"FFC {side}: the '1' mark is level with slot 1")
        lr = [(x, y) for t, x, y in texts if t == nm]
        ok(lr and (lr[0][0] - CX) * sx > 0, f"'{nm}' printed beside the {'left' if sx < 0 else 'right'} connector")


def pad_number(B, key):
    """Header pin index (from the square pad) -> footprint pad number."""
    ref, i = key
    ps = list(B.fp[ref].Pads())
    s1 = [p for p in ps if p.GetShape() in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT)][0].GetPosition()
    return sorted(ps, key=lambda p: (p.GetPosition() - s1).EuclideanNorm())[i - 1].GetNumber()


# ---------------------------------------------------------------- halves, cables, QMK scan
def half(side):
    """Model half board: key (r, c) = switch from COL c to the diode anode, cathode on ROW r (COL2ROW).
    Returns the connector: physical lateral position index (0 = back) -> half net."""
    conn = {}
    for s, f in SLOTS.items():
        conn[s - 1] = f                                      # left half: slot k at lateral position k (back first)
    if side == "R":
        # the right half is the same reversible board flipped: its connector is the mirror image, so lateral
        # positions keep the same order (mirroring across the keyboard's centre line keeps back = back)
        conn = {i: conn[i] for i in conn}
    return conn


def assemble(pins, cable_flip=None, right_conn_reversed=False):
    """Global graph: controller copper groups + cables + model halves."""
    edges = {}

    def link(a, b):
        edges.setdefault(a, set()).add(b)
        edges.setdefault(b, set()).add(a)
    keys, diodes = [], []
    for side in ("L", "R"):
        hc = half(side)
        for lat in range(20):
            # controller contact at lateral position lat (slot lat+1, back first)
            c_slot = lat + 1
            if right_conn_reversed and side == "R":
                c_slot = 20 - lat
            h_lat = 19 - lat if cable_flip == side else lat          # a flipped cable reverses the order
            cn = pins[("ffc" + side, c_slot)]
            link(("C", cn), (side, hc[h_lat]))
        for r in range(6):
            for c in range(7):
                k = (side, r, c)
                a = (side, "K", r, c)
                keys.append((k, (side, f"COL{c}"), a))
                diodes.append((a, (side, f"ROW{r}")))
    return edges, keys, diodes


def scanner(pins, edges, keys, diodes, qmk):
    gp = {f: ("C", pins[("pico", p)]) for p, f in PICO_PINOUT.items() if f.startswith("GP")}
    rows, cols = qmk["matrix_pins"]["rows"], qmk["matrix_pins"]["cols"]
    dmap = {}
    for a, c in diodes:
        dmap.setdefault(a, set()).add(c)
    kmap = {k: (col, a) for k, col, a in keys}

    def scan(pressed):
        adj = {a: set(b) for a, b in edges.items()}
        for k in pressed:
            col, a = kmap[k]
            adj.setdefault(col, set()).add(a)
            adj.setdefault(a, set()).add(col)
        found = set()
        for ci, cn in enumerate(cols):
            seen, st = {gp[cn]}, [gp[cn]]
            while st:
                u = st.pop()
                for v in itertools.chain(adj.get(u, ()), dmap.get(u, ())):
                    if v not in seen:
                        seen.add(v)
                        st.append(v)
            for ri, rn in enumerate(rows):
                if gp[rn] in seen:
                    found.add((ri, ci))
        return found
    return scan


def expected(k):
    side, r, c = k
    return (r, c) if side == "L" else (r, 13 - c)            # unibody matrix: right half mirrored, outer col = 13


def run_scan(pins, qmk=QMK_V2, cable_flip=None, right_conn_reversed=False, quiet=False):
    edges, keys, diodes = assemble(pins, cable_flip, right_conn_reversed)
    scan = scanner(pins, edges, keys, diodes, qmk)
    allk = [k for k, _, _ in keys]
    single = [k for k in allk if scan([k]) != {expected(k)}]
    random.seed(7)
    wrong = 0
    for n in (2, 3, 4, 6, 10):
        for _ in range(200):
            ch = random.sample(allk, n)
            if scan(ch) != {expected(k) for k in ch}:
                wrong += 1
    sq = [("L", 0, 0), ("L", 0, 1), ("L", 1, 0)]
    sq2 = [("L", 2, 3), ("R", 2, 3), ("R", 4, 3)]             # rows are shared across the halves
    res = dict(single=single, wrong=wrong, sq=scan(sq) == {expected(k) for k in sq},
               sq2=scan(sq2) == {expected(k) for k in sq2}, idle=scan([]) == set(), n=len(allk))
    if not quiet:
        ok(not single, f"every key alone reads at its matrix position ({res['n'] - len(single)}/{res['n']})")
        ok(res["idle"], "nothing reads with no key down")
        ok(wrong == 0, f"1000 random 2/3/4/6/10-key chords read exactly the keys pressed: {wrong} wrong")
        ok(res["sq"], "3 corners of a rectangle on one half don't ghost the 4th")
        ok(res["sq2"], "3 corners of a rectangle spanning both halves (shared rows) don't ghost the 4th")
    return res, edges


def flipped_cable_safety(pins):
    """A type A cable fitted with one end flipped to make contact reverses the slot order: controller slot k
    meets half slot 21-k. Classify what meets what (both ends: either end can be the flipped one)."""
    print("\n== cable fitted flipped (slot k meets slot 21-k)")
    # controller side drives: GND, 5V rail, RGB_TO (buffer via 330 ohm), ROW (GPIO: low when selected, weak
    # pull-up otherwise in QMK's default), COL (GPIO input + pull-up), RGB_FROM (just a wire to the other half)
    # half side: GND, 5V, RGB_TO (LED input), RGB_FROM (LED output, push-pull 5 V), ROW/COL (switch matrix)
    bad, info = [], []
    for k, cf in SLOTS.items():
        hf = SLOTS[21 - k]
        if "5V_LED" in (cf, hf) and cf != hf:
            bad.append(f"slot {k}: controller {cf} meets half {hf} (5 V on a non-5 V line)")
        if hf == "RGB_FROM_HALF" and (cf.startswith("ROW") or cf.startswith("COL")):
            bad.append(f"slot {k}: the half's LED output (5 V push-pull) drives GPIO {cf}")
        if hf == "RGB_FROM_HALF" and cf == "GND":
            bad.append(f"slot {k}: the half's LED output shorted to GND")
        if cf == "RGB_TO_HALF" and hf != "RGB_FROM_HALF":
            info.append(f"slot {k}: buffer (via 330 ohm) meets half {hf}")
        if cf == "GND" and hf.startswith("ROW"):
            info.append(f"slot {k}: GND meets {hf} (fine with QMK's default unselect; never set MATRIX_UNSELECT_DRIVE_HIGH)")
    ok(not bad, "flipped cable: 5 V only meets 5 V, GND only meets GND/inputs, the two RGB data lines meet each "
       "other (through 330 ohm), the LED output never drives a GPIO" + (f": {bad}" if bad else ""))
    for s_ in info:
        print("  info  " + s_)
    res, _ = run_scan(pins, cable_flip="L", quiet=True)
    ok(len(res["single"]) > 0, f"a flipped left cable scrambles the left half's keys ({len(res['single'])} wrong) - "
       "the scan sees it, and nothing is damaged")


def negative_controls(pins):
    print("\n== negative controls (each broken build must be caught)")
    # firmware: two columns swapped
    q = json.loads(json.dumps(QMK_V2))
    c = q["matrix_pins"]["cols"]
    c[2], c[3] = c[3], c[2]
    r1, _ = run_scan(pins, qmk=q, quiet=True)
    ok(len(r1["single"]) > 0, "two column pins swapped in the firmware is caught")
    r2, _ = run_scan(pins, right_conn_reversed=True, quiet=True)
    ok(len(r2["single"]) > 0, "right FFC numbered by pad instead of by slot (not turned 180 deg) is caught")
    # diodes reversed
    edges, keys, diodes = assemble(pins)
    scan = scanner(pins, edges, keys, [(c_, a) for a, c_ in diodes], QMK_V2)
    rev = sum(scan([k]) == {expected(k)} for k, _, _ in keys)
    ok(rev == 0, f"diodes reversed: no key reads ({rev}) - the scan is polarity-aware")
    # injected short: join GP3's island to GP4's
    p2 = dict(pins)
    a, b = p2[("pico", 5)], p2[("pico", 6)]
    p2 = {k: (a if v == b else v) for k, v in p2.items()}
    ok(not quiet_compare(p2), "an injected short (GP3-GP4) is caught by the netlist compare")
    # cut track: give one FFC contact its own island
    p3 = dict(pins)
    p3[("ffcL", 8)] = ("cut", 1)
    ok(not quiet_compare(p3), "a cut track (left slot 8, COL3) is caught by the netlist compare")
    r4, _ = run_scan(p3, quiet=True)
    ok(len(r4["single"]) > 0, "... and by the scan (that column's keys go dead)")


def quiet_compare(p):
    import io
    import contextlib
    saved = list(FAIL)
    with contextlib.redirect_stdout(io.StringIO()):
        r = compare(p, spec_nets(), "neg")
    FAIL[:] = saved
    return r


def main():
    path = os.path.join(OUT, "pcb", "controller_rev2.kicad_pcb")
    print(f"== controller rev 2 copper: {path}")
    B = Board(path)
    pins = place_parts(B)
    compare(pins, spec_nets(rgb=True), "populated")
    electrical_variants(pins)
    silk_truth(B, pins)
    print("\n== QMK COL2ROW scan through two FFCs into model halves (rev 2 pin config)")
    run_scan(pins)
    flipped_cable_safety(pins)
    negative_controls(pins)
    json.dump(QMK_V2, open(os.path.join(OUT, "pcb", "controller_rev2_qmk.json"), "w"), indent=1)
    print("\n" + ("SIMULATION PASSED" if not FAIL else f"{len(FAIL)} SIMULATION CHECK(S) FAILED"))
    return len(FAIL)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
