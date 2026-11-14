"""
Compose58 rev 2 half boards: the copper laid out by hand before the autorouter runs (compose/pcb/preroute.py).
Optional: delete this file, or set C58_PREROUTE=0, and the autorouter routes everything, as on a new layout.

  ROW4   the thumb row, on all four boards: the one net Freerouting 2.5 can't finish. From its connector slot
         it runs under the connector's cable side, down the inner edge and along the front of the thumb keys,
         on the back copper, with a short spur up to each diode.
  +5V    the LED rail, on the solder RGB board: a 0.5 mm trunk along every key row, in the gap between each
         switch's centre hole and its LED cutout, with a spur to each LED and capacitor (a via where the pad is
         on the back). Under a key the trunk is on the front copper; it crosses each column gap on the back,
         through a via at either end, so the front copper stays open in the column gaps and the back copper
         under the keys for everything that has to cross a row. The rows are tied into a mesh: a 1 mm spine
         down the outer edge, a 0.8 mm one down the inner edge from connector slot 19, slot 2 straight into the
         top row, and the thumb row joined at both ends.
         Not on the hotswap RGB board: with the rail laid (this way, or all on the front copper) Freerouting 2.1
         didn't finish that board in 55 minutes in any of four tries, and with ROW4 alone it routes in one
         attempt. The likely reason, not confirmed: its sockets' pads sit on both faces, and each key's links
         between them want the same gap under the switch the trunk takes. There the router lays +5V, as before.

Everything is placed from the plan (key frames, the connector's slots, the diodes), and every stretch between
two such points goes through Field.route, which steps round whatever the plan put in the way.
"""
import math
import numpy as np
from compose.pcb import rev2_half as H

ROW = "ROW4"
ROW_W = 0.25                 # signal width
ROW_FY = 10.5                # the thumb-row track under each thumb key: footprint y (in front of its LED and its
                             #   GND vias)
RAIL = "+5V"
TRUNK_W = 0.5
TRUNK_FY = 2.725             # row trunk: footprint y, midway between the centre hole and the LED cutout (0.475 mm
                             #   of clearance to each)
TRUNK_X = 6.6                # ... from -TRUNK_X to +TRUNK_X in each key, joined across the column gaps
CAP_VIA_X = 7.3              # ... or to here on a key with capacitors, so the vias at its ends stand clear of their
                             #   pads; the one at +CAP_VIA_X also feeds the back-face capacitor
GAP_FACE = "B"               # the face the trunk crosses the column gaps on. "B": a via at each end of every key's
                             #   stretch, so the front copper is open in the column gaps and the back copper under
                             #   the keys; "F": no vias in the trunk, and the front copper walled off along every row
RAIL_ON = ("solder",)        # the RGB boards whose rail is laid here (see above for the hotswap one)
SPUR_W = 0.4                 # trunk to an LED or capacitor pad; connector pad to its via (the pads are 0.4 wide)
SPINE_OUT_W = 1.0            # the spine down the outer edge
SPINE_IN_W = 0.8             # the spine down the inner edge
LANE = 1.45                  # a connector pad's via: this far from the pad's centre, on the board side of the row
UNDER = 1.3                  # ... or under the connector, on the cable side


def _fp(k, p):
    """Plate-local point -> key k's footprint coordinates (x right, y down)."""
    a = math.radians(k.rot)
    dx, dy = p[0] - k.x, p[1] - k.y
    return (dx * math.cos(a) + dy * math.sin(a), dx * math.sin(a) - dy * math.cos(a))


def half_rev2(f, s):
    """f: the board's Field (compose.pcb.rev2_half.field), s: its plan."""
    slot = {v: np.array(k) for k, v in H.slot_of_pad_xy(s).items()}
    row4(f, s, slot)
    if s.rgb and s.variant in RAIL_ON:
        rail(f, s, slot)


def row4(f, s, slot):
    L = lambda k, x, y: H.fp2local(k, x, y)
    n = np.array(s.ffc.n)
    keys = [ks for ks in s.keys if ks.row == 4]
    inner = max(keys, key=lambda ks: ks.k.x)                       # the key beside the inner column
    thumbs = sorted((ks for ks in keys if ks is not inner), key=lambda ks: -ks.k.x)
    side = max((ks for ks in s.keys if ks.row < 4 and ks.cathode[0] > ks.k.x), key=lambda ks: (ks.cathode[0], -ks.row))
    # connector: both faces' pads to one via under the cable side, then out past the mounting pad to the edge strip
    p = slot[12 + 4]
    via = tuple(p + n * UNDER)
    f.via(ROW, via)
    f.track(ROW, "F", [p, via], ROW_W)
    f.track(ROW, "B", [p, via], ROW_W)
    lane = (float(s.ffc.c[0] + H.FFC_MP[0] + H.FFC_MP[2] / 2 + 0.725), float(p[1]))
    k = inner.k
    down = [via, lane, (lane[0], side.cathode[1] - 1.6), L(k, -9.3, -16.3), L(k, -9.3, ROW_FY - 0.6)]
    f.through(ROW, "B", down, ROW_W)
    # the inner key's diode, along the front of the key
    cx, cy = _fp(k, inner.cathode)
    f.through(ROW, "B", [down[-1], L(k, cx, ROW_FY - 0.6), inner.cathode], ROW_W)
    # the thumb keys, inner one first: round the first one's diode, then along the front of each
    at = down[-1]
    for i, ks in enumerate(thumbs):
        k = ks.k
        cx, cy = _fp(k, ks.cathode)
        foot = L(k, cx, ROW_FY)                                     # in front of this key's diode
        if i == 0:
            f.through(ROW, "B", [at, L(k, cx + 1.4, -8.0), L(k, cx + 1.4, cy), ks.cathode], ROW_W)
        else:
            f.route(ROW, "B", at, foot, ROW_W)
        f.track(ROW, "B", [ks.cathode, foot], ROW_W)
        if i < len(thumbs) - 1:
            at = L(k, -8.5, ROW_FY)
            f.track(ROW, "B", [foot, at], ROW_W)


def rail(f, s, slot):
    L = lambda k, x, y: H.fp2local(k, x, y)
    n = np.array(s.ffc.n)
    px, py = H.LED_PAD_X, H.LED_AT[1] - H.LED_PAD_Y               # the LEDs' 5 V pads: +px on F, -px on B
    capx, capy = H.CAP_AT[0], H.CAP_AT[1] - 1.475                 # the capacitors' 5 V pads: +capx on B, -capx on F
    last = max((ks for ks in s.keys if ks.row == 4), key=lambda ks: ks.k.x)       # the key beside the inner column:
    cap = lambda ks: ks.i in s.caps                                               #   nothing joins its far end
    xr = lambda ks: CAP_VIA_X if cap(ks) else px if ks is last else TRUNK_X
    end = lambda ks, sg: L(ks.k, xr(ks) if sg > 0 else -(CAP_VIA_X if cap(ks) else TRUNK_X), TRUNK_FY)
    vias = set()

    def via(p):
        if p not in vias:
            vias.add(p)
            f.via(RAIL, p)
    for ks in s.keys:                                             # every key: its stretch of trunk and its spurs
        k = ks.k
        f.track(RAIL, "F", [end(ks, -1), end(ks, 1)], TRUNK_W)
        f.track(RAIL, "F", [L(k, px, TRUNK_FY), L(k, px, py)], SPUR_W)
        via(L(k, -px, TRUNK_FY))
        f.track(RAIL, "B", [L(k, -px, TRUNK_FY), L(k, -px, py)], SPUR_W)
        if cap(ks):
            f.track(RAIL, "F", [L(k, -capx, TRUNK_FY), L(k, -capx, capy)], SPUR_W)
            via(end(ks, 1))
            f.track(RAIL, "B", [end(ks, 1), L(k, capx, capy)], SPUR_W)
    rows = {r: sorted((ks for ks in s.keys if ks.row == r), key=lambda ks: ks.k.x) for r in range(5)}
    inner = rows[4].pop()                                         # the key beside the inner column
    thumbs = rows[4]
    for r in range(5):                                            # along each row, across the column gaps
        for a, b in zip(rows[r][:-1], rows[r][1:]):
            if GAP_FACE == "B":
                via(end(a, 1))
                via(end(b, -1))
            f.route(RAIL, GAP_FACE, end(a, 1), end(b, -1), TRUNK_W)
    # the outer edge: a spine joining the four rows' outer ends
    xo = s.outline.bounds[0] + 2.9
    tops = [end(rows[r][0], -1) for r in range(4)]
    for (x, y) in tops:
        f.route(RAIL, "F", (x, y), (xo, y), TRUNK_W)
    f.track(RAIL, "F", [(xo, y) for _, y in tops], SPINE_OUT_W)
    # the connector: slot 2 into the top row, slot 19 into the second; a via beside each pad joins the two faces' pads
    for sl, r in ((2, 0), (19, 1)):
        p = slot[sl]
        via = tuple(p - n * LANE)
        f.route(RAIL, "F", end(rows[r][-1], 1), via, TRUNK_W)
        f.via(RAIL, via)
        f.track(RAIL, "F", [via, p], SPUR_W)
        f.track(RAIL, "B", [via, p], SPUR_W)
    # the inner edge: from slot 19 under the connector's cable side, down past rows 2 and 3 to the inner key
    p = slot[19]
    under = tuple(p + n * UNDER)
    f.track(RAIL, "F", [p, under], SPUR_W)
    k2, ki = rows[2][-1].k, inner.k
    x2 = _fp(k2, (max(ks.cathode[0] for ks in s.keys if ks.row < 4) + 1.85, 0))[0]     # clear of the inner column's diode
    xi = -8.3
    j3 = (L(ki, xi, 0)[0], end(rows[3][-1], 1)[1])                # where row 3's trunk meets the spine
    spine = [under, (under[0], s.ffc.c[1] - 15.0), L(k2, x2, -7.5), L(k2, x2, TRUNK_FY), L(k2, x2, 9.0),
             L(ki, xi, -12.0), j3, L(ki, xi, TRUNK_FY)]
    f.through(RAIL, "F", spine, SPINE_IN_W)
    f.route(RAIL, "F", end(rows[2][-1], 1), spine[3], TRUNK_W)
    f.route(RAIL, "F", end(rows[3][-1], 1), j3, TRUNK_W)
    f.route(RAIL, "F", spine[-1], end(inner, -1), TRUNK_W)
    # the thumb row: its inner end from the spine, its outer end from row 3
    f.through(RAIL, "F", [spine[-1], L(ki, xi, 9.0), end(thumbs[-1], 1)], TRUNK_W)
    k0 = thumbs[0].k
    above = max((ks for ks in rows[3] if ks.k.x + 7.45 < k0.x - 9.5), key=lambda ks: ks.k.x)
    xt = L(above.k, max(xr(above), 7.45), 0)[0]
    f.through(RAIL, "F", [end(above, 1), (xt, end(above, 1)[1] - 1.5), (xt, end(thumbs[0], -1)[1]), end(thumbs[0], -1)], TRUNK_W)
