"""
Compose controller rev 2: the shared controller board for all Compose split layouts.

    python3 -m compose controller [outdir]      -> outdir/pcb/controller_rev2.*  (KiCad board, DRC, Gerbers, previews)

Interface (the standard; see README "Controller rev 2"):
  - Raspberry Pi Pico footprint (socketed on 2x 1x20 female headers, 8.5 mm), USB end = back (-y here).
  - Two 20-position 1.0 mm FFC/FPC connectors (Molex 52610-2072, vertical, slider latch), top face, square to
    the side edges at fixed positions (rev2_std: VFFC_*), contact face toward the Pico, so the board doesn't
    depend on any layout's angles: each layout's flex jumpers take them up. Slot order back -> front, the same on both sides:
        1 GND, 2 5V_LED, 3 RGB data to the half, 4 GND (guard), 5-11 COL0-6, 12-17 ROW0-5,
        18 RGB data back from the half, 19 5V_LED, 20 GND
    Reversal-safe: a cable fitted flipped (slot k meets 21-k) puts 5 V on 5 V, GND on GND, the two RGB data
    lines on each other (through the 330 ohm) and rows on columns - nothing is damaged, keys just scramble.
    (the right connector is turned 180 deg, so its pad numbers run the other way; nets follow the slot).
    The halves join through custom flex jumpers (compose/pcb/jumper.py): conductors on one face, the same
    physical slot order at both ends.
  - Matrix: 6 rows shared by both halves (GP0-5), 7 columns per half
    (left GP6-12, right GP22, 21, 20, 19, 18, 17, 16 = COL0-6). QMK: 6 x 14.
  - I2C1 on GP14 (SDA) / GP15 (SCL), 4.7k pull-ups to 3.3 V: 4-pin OLED-style header + Qwiic.
    Consecutive pins, so a PS/2 pointing stick also works there (QMK RP2040 PS/2 driver; 5 V from AUX).
  - AUX header: GP26, GP27, GP28 (ADC pins), 3.3 V, 5 V (VBUS), GND.
  - Optional RGB, all on the BOTTOM face (outlined "RGB" on the bottom silkscreen; the case has ~24 mm under
    the board, so nothing is limited by the Pico's 8.5 mm socket height): 74HCT125 buffer (3.3 V -> 5 V data, in spec for WS2812),
    100 nF, 330 ohm series resistor, MF-RHT050 polyfuse VBUS -> LED 5 V, 10 uF bulk (hot-plug friendly, see the sim).
    A second gate of the 74HCT125 (220 ohm in, 100k pull-down, 330 ohm out) re-drives the chain from the
    left half to the right half. Leave it all empty and the cables' 5 V lines stay dead; firmware RGB off.
  - Mounting: four M3 holes, (+-17.75, +19.5) beside the Pico's front end and (+-13.7, -22.5) beside its
    USB end. M3 x 12 male-female hex standoffs screw through the board into M3 heat-set inserts in four
    case posts, clamping it; the cover drops onto them and takes four M3 x 6 screws.
    Copper- and part-free circles around them on top; no bottom part or lead over the posts.
  - Top face: Pico sockets, the two FFC connectors and the front connector row only. Bottom face: every
    passive and the RGB buffer (through-hole, soldered from the top), I2C pull-ups.
Everything is through-hole except the two FFC connectors and the Qwiic connector.
"""
import os
import json
from shapely.geometry import box as sbox, Point
from shapely.affinity import scale, translate, rotate
from shapely.ops import unary_union
import pcbnew
from compose import params as PR
from compose.pcb import kicad as PK
from compose.pcb import art as PA

V, MM, DEG = PK.V, PK.MM, PK.DEG
NAME = "controller_rev2"
CX, CY = 100.0, 100.0                      # Pico centre in KiCad coordinates (y down = toward the front)
from compose.controller.rev2_std import (W2, Y_BACK, Y_FRONT, CORNER_R, PICO_X, PICO_Y, STANDOFF_HOLES,
                         M_CLEAR, STANDOFF_KEEP, CLIP_X, CLIP_Y, POST_R,
                         VFFC_SLOT_X, VFFC_Y0, VFFC_SLOT_IN, VFFC_L, VFFC_D)
COVER_HOLES = STANDOFF_HOLES
BOTTOM = ("U2", "C1", "C2", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "F1")
LABEL_EM = PR.ART_MIN_TEXT_EM              # same font and minimum size as the rev 1 boards
ROW_Y = 27.8                               # front connector row (header pins)

PICO_GPIO = {1: 0, 2: 1, 4: 2, 5: 3, 6: 4, 7: 5, 9: 6, 10: 7, 11: 8, 12: 9, 14: 10, 15: 11, 16: 12, 17: 13,
             19: 14, 20: 15, 21: 16, 22: 17, 24: 18, 25: 19, 26: 20, 27: 21, 29: 22, 31: 26, 32: 27, 34: 28}
PICO_GND = (3, 8, 13, 18, 23, 28, 33, 38)
PICO_PWR = {36: "+3V3", 40: "VBUS"}

ROWS = [0, 1, 2, 3, 4, 5]
COLS = {"L": [6, 7, 8, 9, 10, 11, 12], "R": [22, 21, 20, 19, 18, 17, 16]}
RGB_GPIO, SDA, SCL = 13, 14, 15
AUX = [26, 27, 28]
POWER_NETS = ("GND", "VBUS", "+5V_LED", "+3V3")
POWER_W = 0.4


def slot_nets(side):
    """Net for each FFC slot 1..20 (slot 1 at the back), same order on both connectors."""
    s = {1: "GND", 2: "+5V_LED", 4: "GND", 19: "+5V_LED", 20: "GND"}
    for i, g in enumerate(COLS[side]):
        s[5 + i] = f"GP{g}"
    for i, g in enumerate(ROWS):
        s[12 + i] = f"GP{g}"
    s[3] = "RGB_L_IN" if side == "L" else "RGB_R_IN"      # data into the half: between 5 V (AC ground) and GND
    s[18] = "RGB_L_RET" if side == "L" else None           # data back from the left half (right: end of the chain)
    return s


def C(x, y):
    return (CX + x, CY + y)


def add(b, lib, name, ref, value):
    fp = PK.lib_fp(b, lib, name)
    fp.SetReference(ref)
    fp.SetValue(value)
    return fp


def put(fp, pos, angle=0.0, pad="1"):
    """Rotate by angle (deg, KiCad sense) and move pad `pad` onto pos."""
    fp.SetPosition(V(0, 0))
    if angle:
        fp.Rotate(V(0, 0), DEG(angle))
    q = PK.pad_pos(fp, pad)
    fp.Move(V(pos[0] - q[0], pos[1] - q[1]))


def crt(fp):
    """Courtyard bbox (its own face) in board-centred mm (x0, y0, x1, y1)."""
    fp.BuildCourtyardCaches()
    bb = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
    return (pcbnew.ToMM(bb.GetLeft()) - CX, pcbnew.ToMM(bb.GetTop()) - CY,
            pcbnew.ToMM(bb.GetRight()) - CX, pcbnew.ToMM(bb.GetBottom()) - CY)


def to_bottom(fp):
    """Put a placed part on the bottom face, mirrored left-right about its own position (it stays in place)."""
    fp.BuildCourtyardCaches()
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    fp.Flip(bb.GetCenter(), True)


def setnets(fp, table, net):
    for p in fp.Pads():
        n = table.get(p.GetNumber())
        if n:
            p.SetNet(net(n))


def silk_rect(b, x0, y0, x1, y1, w=0.15):
    for a, c in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*C(*a)))
        s.SetEnd(V(*C(*c)))
        s.SetLayer(pcbnew.F_SilkS)
        s.SetWidth(MM(w))
        b.Add(s)


def label(b, msg, x, y, em=None, angle=0.0, font=None, anchor="c", records=None):
    """Silkscreen text as outlines in the rev 1 art font (DejaVu Sans), centred (or left-anchored) at x, y."""
    g = PA.text_shape(msg, font or PR.ART_TEXT_FONT, em or LABEL_EM)
    if angle:
        g = rotate(g, angle, origin=(0, 0))
    bx0, by0, bx1, by1 = g.bounds
    dx = x - (bx0 if anchor == "l" else (bx0 + bx1) / 2)
    dy = (-y - by0) if anchor == "b" else (-y - (by0 + by1) / 2)   # "b": text ends at board y (its lowest point)
    g = translate(g, dx, dy)                                 # y-up frame for PK.add_poly
    PK.add_poly(b, g, pcbnew.F_SilkS, CX, CY)
    if records is not None:
        records.append(dict(text=msg, x=round(x, 3), y=round(y, 3)))
    return g


def silk_circle(b, x, y, r, w=0.15):
    s = pcbnew.PCB_SHAPE(b)
    s.SetShape(pcbnew.SHAPE_T_CIRCLE)
    s.SetCenter(V(*C(x, y)))
    s.SetEnd(V(*C(x + r, y)))
    s.SetLayer(pcbnew.F_SilkS)
    s.SetWidth(MM(w))
    b.Add(s)


def outline_poly():
    from compose.controller import rev2_std as CS
    return CS.outline()


VFFC_PAD_A = (1.85, -0.025)                # contact-face row: length (across), centre from the contact face (into the body +)
VFFC_PAD_B = (1.65, 3.725)                 # far row
VFFC_PAD_W = 0.6


def vffc_x(side):
    """x (board frame) of the connector's contact face; the body goes outward from it, toward the edge."""
    sx = -1 if side == "L" else 1
    return sx * (VFFC_SLOT_X - VFFC_SLOT_IN)


def vffc_fp(b, side, net):
    """Molex 52610-2072 (Easy-On, vertical, 20 pos, 1.0 mm), Molex's recommended pattern: two pad rows per
    contact (the terminal's two tails), 0.6 mm wide. Placed for `side`: contact face (pin 1 notch side) toward
    the Pico, slot k at y = VFFC_Y0 - 9.5 + (k - 1) (slot 1 at the back). Built in board-centred mm
    (origin = Pico centre), then moved there."""
    sx = -1 if side == "L" else 1
    fp = pcbnew.FOOTPRINT(b)
    fp.SetFPID(pcbnew.LIB_ID("compose", "Molex_52610-2072_1x20_P1.00mm_Vertical"))
    fp.SetReference(f"J{side}")
    fp.SetValue("Molex 52610-2072")
    fp.Value().SetVisible(False)
    xc = vffc_x(side)
    sn = slot_nets(side)
    for k in range(1, 21):
        y = VFFC_Y0 - 9.5 + (k - 1)
        pin = str(k if side == "L" else 21 - k)                # pin 1 at the notch end: back on the left, front on the right
        for ln, off in (VFFC_PAD_A, VFFC_PAD_B):
            PK.add_pad(fp, pin, "smd", "rect", (xc + sx * off, y), (ln, VFFC_PAD_W))
        for p in fp.Pads():
            if p.GetNumber() == pin and sn.get(k):
                p.SetNet(net(sn[k]))
    x_far = xc + sx * VFFC_D
    y0, y1 = VFFC_Y0 - VFFC_L / 2, VFFC_Y0 + VFFC_L / 2
    PK.silk_poly(fp, [(xc, y0), (x_far, y0), (x_far, y1), (xc, y1)], pcbnew.F_Fab, 0.1)
    for yy in (y0, y1):                                      # body ends on the silk (the sides carry pads)
        s_ = pcbnew.FP_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
        s_.SetStart0(V(xc, yy)); s_.SetEnd0(V(x_far, yy))
        s_.SetLayer(pcbnew.F_SilkS); s_.SetWidth(MM(0.15))
        s_.SetDrawCoord()
        fp.Add(s_)
    yn = y0 if side == "L" else y1                           # pin 1 notch end: a small triangle at the contact face
    tri = [(xc - sx * 0.2, yn + (1 if side == "L" else -1) * 0.2), (xc - sx * 0.9, yn + (1 if side == "L" else -1) * 0.2),
           (xc - sx * 0.55, yn + (1 if side == "L" else -1) * 0.8)]
    PK.silk_poly(fp, tri, pcbnew.F_SilkS, 0.15)
    xa = xc - sx * (VFFC_PAD_A[0] / 2 - VFFC_PAD_A[1])
    xb = xc + sx * (VFFC_PAD_B[1] + VFFC_PAD_B[0] / 2)
    PK.courtyard(fp, min(xa, xb) - 0.25, y0 - 0.25, max(xa, xb) + 0.25, y1 + 0.25, pcbnew.F_CrtYd)
    fp.Move(V(CX, CY))                                       # built relative to the Pico centre
    return fp


def build():
    b = PK.new_board()
    net = PK.Nets(b)
    ol = outline_poly()
    ol_up = translate(scale(ol, 1.0, -1.0, origin=(0, 0)), CX, -CY)     # PK.K maps (x, y) -> (x, -y)
    b.kb2_outline = (ol_up, 0.0, 0.0)
    PK.outline(b, ol_up, 0.0, 0.0)
    fps = {}
    # power nets: 0.4 mm tracks (0.5 A LED rail + return; still fits between 2.54 mm pins)
    pw = pcbnew.NETCLASS("Power")
    pw.SetTrackWidth(MM(POWER_W))
    pw.SetClearance(MM(PR.CLEARANCE))
    pw.SetViaDiameter(MM(PR.VIA_D + 0.2))
    pw.SetViaDrill(MM(PR.VIA_DRILL + 0.1))
    b.GetDesignSettings().m_NetSettings.m_NetClasses["Power"] = pw
    for n in POWER_NETS:
        net(n).SetNetClass(pw)

    def keep(fp):
        fp.Reference().SetVisible(False)
        b.Add(fp)
        fps[fp.GetReference()] = fp
        return fp

    # ---- Pico sockets
    pin_net = {pin: f"GP{g}" for pin, g in PICO_GPIO.items()}
    pin_net.update({pin: "GND" for pin in PICO_GND})
    pin_net.update(PICO_PWR)
    for side, first in (("L", 1), ("R", 40)):
        h = add(b, "Connector_PinSocket_2.54mm", "PinSocket_1x20_P2.54mm_Vertical", f"U1{side}", "Pico socket")
        x = -PICO_X if side == "L" else PICO_X
        PK.place_by_pads(h, "1", C(x, -PICO_Y), "20", C(x, PICO_Y))
        for p in h.Pads():
            pin = first + (int(p.GetNumber()) - 1) * (1 if side == "L" else -1)
            if pin in pin_net:
                p.SetNet(net(pin_net[pin]))
        keep(h)

    # ---- cable connectors: Molex 52610 vertical, square to the side edges, contact face toward the Pico;
    #      slot 1 at the back (nets by physical position, so the right one's pad numbers run the other way)
    for side, sx in (("L", -1), ("R", 1)):
        j = vffc_fp(b, side, net)
        keep(j)

    # ---- cover standoff holes (M3) in the corners, with copper keep-outs for the standoff / case boss
    for i, (x, y) in enumerate(COVER_HOLES):
        PK.hole_fp(b, f"H{i + 1}", C(x, y), M_CLEAR)
        PK.add_keepout(b, Point(x, -y).buffer(STANDOFF_KEEP, resolution=16).intersection(
            translate(scale(ol, 1.0, -1.0, origin=(0, 0)), 0, 0)), CX, CY)

    # ---- under the Pico: optional RGB buffer + I2C pull-ups
    u = add(b, "Package_DIP", "DIP-14_W7.62mm", "U2", "74HCT125")
    PK.place_by_pads(u, "1", C(-3.81, -12.7), "7", C(-3.81, 2.54))
    # gate 1: GP13 -> left half; gate 2 re-drives the chain from the left half to the right half (the hop
    # through two cables rings too much straight through, see compose/sim/controller_spice.py, B); gates 3/4 unused
    setnets(u, {"1": "GND", "2": f"GP{RGB_GPIO}", "3": "RGB_BUF", "4": "GND", "5": "RGB_HOP_IN", "6": "RGB_HOP_BUF",
                "7": "GND",
                "9": "GND", "10": "+5V_LED", "12": "GND", "13": "+5V_LED", "14": "+5V_LED"}, net)
    keep(u)
    c1 = add(b, "Capacitor_THT", "C_Disc_D3.0mm_W1.6mm_P2.50mm", "C1", "100nF")
    PK.place_by_pads(c1, "1", C(1.25, -15.9), "2", C(-1.25, -15.9))
    setnets(c1, {"1": "+5V_LED", "2": "GND"}, net)
    keep(c1)
    c2 = add(b, "Capacitor_THT", "CP_Radial_D5.0mm_P2.00mm", "C2", "10uF")
    put(c2, C(0, 0))
    x0, y0, x1, y1 = crt(c2)
    c2.Move(V(-(x0 + x1) / 2, -21.0 - (y0 + y1) / 2))          # 5 x 11 mm radial, standing under the board
    setnets(c2, {"1": "+5V_LED", "2": "GND"}, net)
    keep(c2)
    r3 = add(b, "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "R3", "330")
    PK.place_by_pads(r3, "1", C(-3.81, 5.6), "2", C(3.81, 5.6))
    setnets(r3, {"1": "RGB_BUF", "2": "RGB_L_IN"}, net)
    keep(r3)
    r4 = add(b, "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "R4", "100k")
    PK.place_by_pads(r4, "1", C(-3.81, 8.7), "2", C(3.81, 8.7))
    setnets(r4, {"1": f"GP{RGB_GPIO}", "2": "GND"}, net)       # buffer input defined before the Pico boots
    keep(r4)
    r5 = add(b, "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "R5", "220")
    PK.place_by_pads(r5, "1", C(-3.81, 11.8), "2", C(3.81, 11.8))
    setnets(r5, {"1": "RGB_L_RET", "2": "RGB_HOP_IN"}, net)    # limits clamp current from the ringing return run
    keep(r5)
    r7 = add(b, "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "R7", "330")
    PK.place_by_pads(r7, "1", C(-3.81, 14.9), "2", C(3.81, 14.9))
    setnets(r7, {"1": "RGB_HOP_BUF", "2": "RGB_R_IN"}, net)
    keep(r7)
    # ---- under the Pico, front end: hop input pull-down (left half without LEDs / unplugged), I2C pull-ups
    for ref, y, n, val, n2 in (("R6", 17.9, "RGB_HOP_IN", "100k", "GND"), ("R1", 20.95, f"GP{SDA}", "4.7k", "+3V3"),
                               ("R2", 24.0, f"GP{SCL}", "4.7k", "+3V3")):
        r = add(b, "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", ref, val)
        PK.place_by_pads(r, "1", C(-3.81, y), "2", C(3.81, y))
        setnets(r, {"1": n, "2": n2}, net)
        keep(r)

    # ---- bottom, back-right strip beside the Pico (next to VBUS, Pico pin 40): optional polyfuse, standing
    f1 = add(b, "Fuse", "Fuse_Bourns_MF-RHT050", "F1", "MF-RHT050")
    put(f1, C(0, 0), angle=90)
    x0, y0, x1, y1 = crt(f1)
    f1.Move(V(13.0 - (x0 + x1) / 2, -14.6 - (y0 + y1) / 2))         # its top-side joints clear of JR
    setnets(f1, {"1": "VBUS", "2": "+5V_LED"}, net)
    keep(f1)

    # ---- front row: OLED-style I2C header (GND, VCC, SCL, SDA), AUX, Qwiic (top entry, for cover modules)
    j4 = add(b, "Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical", "J4", "OLED I2C")
    put(j4, C(-18.7, ROW_Y), angle=90)
    if PK.pad_pos(j4, "4")[0] < PK.pad_pos(j4, "1")[0]:
        put(j4, C(-18.7, ROW_Y), angle=-90)
    setnets(j4, {"1": "GND", "2": "+3V3", "3": f"GP{SCL}", "4": f"GP{SDA}"}, net)
    keep(j4)
    j5 = add(b, "Connector_JST", "JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical", "J5", "Qwiic")
    put(j5, C(0, 0))
    x0, y0, x1, y1 = crt(j5)
    j5.Move(V(15.8 - (x0 + x1) / 2, Y_FRONT - 0.05 - y1))
    setnets(j5, {"1": "GND", "2": "+3V3", "3": f"GP{SDA}", "4": f"GP{SCL}", "MP": "GND"}, net)
    keep(j5)

    # ---- front strip below the Pico: AUX (GP26, GP27, GP28, 3V3, 5V, GND)
    j6 = add(b, "Connector_PinHeader_2.54mm", "PinHeader_1x06_P2.54mm_Vertical", "J6", "AUX")
    put(j6, C(-6.6, ROW_Y), angle=90)
    if PK.pad_pos(j6, "6")[0] < PK.pad_pos(j6, "1")[0]:
        put(j6, C(-6.6, ROW_Y), angle=-90)
    setnets(j6, {"1": f"GP{AUX[0]}", "2": f"GP{AUX[1]}", "3": f"GP{AUX[2]}", "4": "+3V3", "5": "VBUS", "6": "GND"},
            net)
    keep(j6)

    for ref in BOTTOM:
        to_bottom(fps[ref])
    labels = art(b)
    b.kb2_layout = check_layout(fps)
    json.dump(labels, open(os.path.join(PK.PCB_OUT, NAME + "_silk.json"), "w"), indent=1)
    return b


def check_layout(fps):
    """Courtyards inside the board and clear of each other (per face); bottom parts clear of the top parts'
    pin tails and of the case posts; top connectors clear of the Pico; standoffs clear of everything."""
    from shapely.geometry import box
    from compose.controller import rev2_std as CS
    ol = outline_poly()
    boxes = {ref: box(*crt(fp)) for ref, fp in fps.items()}
    bottom = {r for r, fp in fps.items() if fp.IsFlipped()}
    assert bottom == set(BOTTOM), bottom
    for ref, g in boxes.items():
        assert ol.buffer(1e-3).contains(g), f"{ref} courtyard leaves the board {g.bounds}"
    refs = sorted(boxes)
    for i, a in enumerate(refs):
        for c in refs[i + 1:]:
            if (a in bottom) != (c in bottom):
                continue
            ov = boxes[a].intersection(boxes[c]).area
            assert ov < 1e-6, f"courtyards {a} / {c} overlap ({ov:.2f} mm2)"

    def pth(fp, r=False):
        return [((pcbnew.ToMM(p.GetPosition().x) - CX, pcbnew.ToMM(p.GetPosition().y) - CY),
                 pcbnew.ToMM(max(p.GetSize().x, p.GetSize().y)) / 2) if r else
                (pcbnew.ToMM(p.GetPosition().x) - CX, pcbnew.ToMM(p.GetPosition().y) - CY)
                for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
    for a in refs:                                             # a part's body never sits on another face's pin tails
        for c in refs:                                         # or solder joints (the pad's copper on a's face)
            if (a in bottom) == (c in bottom):
                continue
            for q, r in pth(fps[c], r=True):
                assert not boxes[a].intersects(Point(q).buffer(r - 1e-3)), f"{a} courtyard over {c}'s joint at {q}"
    pico = box(-10.5, -25.5, 10.5, 25.5)
    for ref in ("J4", "J5", "J6", "JL", "JR"):
        assert boxes[ref].intersection(pico).area < 1e-6, f"{ref} is under the Pico"
    for x, y in COVER_HOLES:
        keep = Point(x, y).buffer(STANDOFF_KEEP)              # standoff hex on top
        post = Point(x, y).buffer(POST_R + 0.3)                # case post under the board
        assert ol.contains(Point(x, y).buffer(M_CLEAR / 2 + 1.2)), f"standoff hole at {x, y} too near the edge"
        for ref, g in boxes.items():
            if ref.startswith("U1"):                           # Pico sockets: their bodies (courtyard less its 0.5 mm
                g = g.buffer(-0.5, join_style=2)               #   margin); the keep circle carries its own margin
            assert not (keep if ref not in bottom else post).intersects(g), f"standoff/post at {x, y} hits {ref}"
        for ref, fp in fps.items():                            # top parts' lead tails clear the post
            if ref in bottom:
                continue
            for q in pth(fp):
                assert Point(q).distance(Point(x, y)) >= CS.BOSS_KEEP, f"{ref} lead within the post at {x, y}"
        if abs(x) > VFFC_SLOT_X - 1.0:                         # the jumpers come over the edge strip, 21 mm wide
            assert abs(y - VFFC_Y0) - STANDOFF_KEEP > 10.5 + 1.0, "standoff in the jumper's path"
    return {r: [round(v, 2) for v in g.bounds] + (["B"] if r in bottom else []) for r, g in boxes.items()}


TITLE_Y0, TITLE_Y1 = -18.9, -11.4         # title window up the left strip: between the back standoff's keep-out
                                           #   and the cable connector's back end


def art(b):
    rec = []
    L = lambda *a, **k: label(b, *a, records=rec, **k)
    # title: the composition ring + "Compose" (rev 1 style), standing up the left strip beside the Pico's
    # back half (the back is narrowed there for the plates' inner seats), behind the cable connector
    x_mid = -(10.5 + CLIP_X) / 2

    def title(xm):
        g = unary_union([
            PA.ring_logo(0.0, 0.0, 1.0),
            PA.fit(PA.text_shape("Compose", PR.ART_TITLE_FONT), 1.35, -1.0, 7.0, 2.0, "left")[0],
            PA.fit(PA.text_shape(f"controller · rev 2 · {PR.HANDLE}", PR.ART_TEXT_FONT), -1.0, -2.25, 10.0, 0.85)[0]])
        g = rotate(g, 90, origin=(0, 0))                        # reads bottom -> top along the strip
        bx0, by0, bx1, by1 = g.bounds
        k = min(1.0, (TITLE_Y1 - TITLE_Y0) / (by1 - by0))       # scaled down to fit the window if needed
        g = scale(g, k, k, origin=((bx0 + bx1) / 2, (by0 + by1) / 2))
        bx0, by0, bx1, by1 = g.bounds
        return translate(g, xm - (bx0 + bx1) / 2, -((TITLE_Y0 + TITLE_Y1) / 2) - (by0 + by1) / 2)
    PK.add_poly(b, title(x_mid), pcbnew.F_SilkS, CX, CY)
    rec.append(dict(text="Compose", x=round(x_mid, 2), y=round((TITLE_Y0 + TITLE_Y1) / 2, 2)))
    # bottom face (it faces the case floor): the same title, mirrored so it reads from below
    PK.add_poly(b, PA.mirror_about(title(x_mid), x_mid), pcbnew.B_SilkS, CX, CY)
    # cover standoffs
    for x, y in COVER_HOLES:
        silk_circle(b, x, y, 2.2)
    # optional RGB parts (bottom): boxed under the Pico, F1 back-right; "RGB" on the bottom silk
    bsilk_rect(b, -5.4, -24.4, 5.4, 19.42)
    blabel(b, "RGB", 4.55, -21.0, angle=-90)
    blabel(b, "RGB", 13.0, -7.9)
    # connectors (front row): every name sits against the thing it names
    # J4 (OLED / I2C): pin names standing on the header's outline, the group name centred right over them
    em = LABEL_EM
    j4_x = [-18.7 + i * 2.54 for i in range(4)]
    for x, t in zip(j4_x, ("GND", "VCC", "SCL", "SDA")):     # upright: four 3-letter names don't fit 2.54 mm side by side
        L(t, x, 26.3, angle=90, anchor="b")
    top = 26.3 - max(PA.text_shape(t, PR.ART_TEXT_FONT, em).bounds[2] - PA.text_shape(t, PR.ART_TEXT_FONT, em).bounds[0]
                     for t in ("GND", "VCC", "SCL", "SDA"))
    L("OLED", (j4_x[0] + j4_x[-1]) / 2, top - 0.45, anchor="b")
    # J6 (AUX): pin names over the pins, the group name at the end of its own row, against the outline
    for i, t in enumerate(("26", "27", "28", "3V3", "5V", "GND")):
        L(t, -6.6 + i * 2.54, 25.9)
    L("AUX", 7.49 + 0.5, ROW_Y, anchor="l")
    # J4 and J6 take their header from either side (J4's goes on the underside for a pointer's cable, pointers/):
    # the same names and an outline on the bottom face, mirrored so they read from below
    for x, t in zip(j4_x, ("GND", "VCC", "SCL", "SDA")):
        blabel(b, t, x, 26.3, angle=90, anchor="b")
    blabel(b, "OLED", (j4_x[0] + j4_x[-1]) / 2, top - 0.45, anchor="b")
    bsilk_header(b, j4_x[0] - 1.27, ROW_Y - 1.27, j4_x[-1] + 1.27, ROW_Y + 1.27)       # pin 1 = GND, the cut corner
    for i, t in enumerate(("26", "27", "28", "3V3", "5V", "GND")):
        blabel(b, t, -6.6 + i * 2.54, 25.9)
    bsilk_header(b, -6.6 - 1.27, ROW_Y - 1.27, -6.6 + 5 * 2.54 + 1.27, ROW_Y + 1.27)   # pin 1 = GP26, the cut corner
    ab = PA.text_shape("AUX", PR.ART_TEXT_FONT, LABEL_EM).bounds
    blabel(b, "AUX", 7.49 + 0.5 + (ab[2] - ab[0]) / 2, ROW_Y)
    # J5 (Qwiic): centred right behind the connector body
    L("Qwiic", 15.8, 24.75, anchor="b")
    # cable connectors: the side name along the contact row, centred on it; "1" right beside slot 1's contact
    for sx, s in zip((-1, 1), PR.HALF_NAMES):                 # lhs / rhs, read from the outside, as on rev 1:
        x_in = abs(vffc_x("R")) - VFFC_PAD_A[0] / 2 + VFFC_PAD_A[1]   # in the strip between the Pico's socket
        L(s, sx * (x_in - 1.5), VFFC_Y0, angle=90 * sx)              #   and the connector's contact-face pads
        L("1", sx * (x_in - 0.9), VFFC_Y0 - 9.5)
    return rec


def bsilk_header(b, x0, y0, x1, y1, w=0.15, ch=0.9):
    """Bottom-face outline of a 1-row header whose pin 1 is at the low-x end (x0): the corner at (x0, y1) is cut off,
    the way a pin-1 mark is drawn on a header footprint."""
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0 + ch, y1), (x0, y1 - ch)]
    bsilk_poly(b, pts, w)


def bsilk_poly(b, pts, w=0.15):
    for a, c in zip(pts, pts[1:] + pts[:1]):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*C(*a)))
        s.SetEnd(V(*C(*c)))
        s.SetLayer(pcbnew.B_SilkS)
        s.SetWidth(MM(w))
        b.Add(s)


def bsilk_rect(b, x0, y0, x1, y1, w=0.15):
    for a, c in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*C(*a)))
        s.SetEnd(V(*C(*c)))
        s.SetLayer(pcbnew.B_SilkS)
        s.SetWidth(MM(w))
        b.Add(s)


def blabel(b, msg, x, y, angle=0.0, anchor="c"):
    """Bottom-face label (mirrored so it reads from below), centred at x, y ("b": its lowest point at y, as label())."""
    g = PA.text_shape(msg, PR.ART_TEXT_FONT, LABEL_EM)
    if angle:
        g = rotate(g, angle, origin=(0, 0))
    bx0, by0, bx1, by1 = g.bounds
    g = translate(g, x - (bx0 + bx1) / 2, (-y - by0) if anchor == "b" else (-y - (by0 + by1) / 2))
    PK.add_poly(b, PA.mirror_about(g, x), pcbnew.B_SilkS, CX, CY)


_export_dsn = pcbnew.ExportSpecctraDSN


def _export_dsn_power(board, path):
    """KiCad 7 keeps net-class membership in the project file, which these generated boards don't have, so the
    DSN puts every net in the default class: move the power nets into the Power class for the router."""
    okx = _export_dsn(board, path)
    import re
    t = open(path).read()
    m = re.search(r"\(class kicad_default ([^(]*)", t)
    names = m.group(1).split()
    keep = [n for n in names if n.strip('"') not in POWER_NETS]
    t = t[:m.start(1)] + " ".join(keep) + "\n      " + t[m.end(1):]
    t = t.replace("(class Power\n", "(class Power " + " ".join(POWER_NETS) + "\n", 1)
    open(path, "w").write(t)
    return okx


def resilk():
    """Re-draw the board-level silkscreen on the routed board (copper untouched), then DRC, Gerbers, previews."""
    path = os.path.join(PK.PCB_OUT, NAME + ".kicad_pcb")
    b = pcbnew.LoadBoard(path)
    for d in list(b.GetDrawings()):
        if d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            b.Remove(d)
    labels = art(b)
    json.dump(labels, open(os.path.join(PK.PCB_OUT, NAME + "_silk.json"), "w"), indent=1)
    pcbnew.SaveBoard(path, b)
    b = pcbnew.LoadBoard(path)
    err, warn, unc, rep = PK.drc(b, NAME)
    z = PK.export(path, NAME)
    print(f"{NAME}: resilk | DRC {err} errors, {warn} warnings, {unc} unconnected | {os.path.basename(z)}")
    return err, warn, unc


def main():
    os.makedirs(PK.PCB_OUT, exist_ok=True)
    pcbnew.ExportSpecctraDSN = _export_dsn_power
    return PK.make(NAME, build)


if __name__ == "__main__":
    import sys
    resilk() if "--resilk" in sys.argv else main()
