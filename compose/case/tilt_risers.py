"""
Tilt risers: printable spacers under the front feet that tip a finished case forward, so negative
(front-raised) typing tilt can be tried on any case without reprinting it.

    C58_SPLAY=.. C58_TENT=.. C58_TILT=..  python3 -m compose tilt-risers OUT DELTA_DEG [DELTA_DEG ...]

The case pivots on its back feet; each other foot gets a riser of height d * tan(delta), d = its distance
in front of the back-feet line. A riser plugs into the case's foot recess on top and takes the rubber
bumpon in a recess underneath. Output: OUT/print/tilt_risers_<delta>deg.stl (all risers laid out) and a
note with the heights.
"""
import os
import sys
import math
import cadquery as cq
from compose import params as PR
from compose import geom as G
from compose import layout as layouts  # noqa: F401  (L.feet via geom)

TOL = dict(tolerance=0.01, angularTolerance=0.1)
RISER_D = 14.0
PLUG_D, PLUG_H = PR.FOOT_D - 0.3, PR.FOOT_DEPTH - 0.15          # into the case's foot recess
POCKET_D, POCKET_H = PR.FOOT_D + 0.3, 1.0                      # the bumpon sits in here
MIN_BODY = 1.2


def feet_world():
    L = G.LAYOUT
    pts = []
    for x, y in L.feet:
        p = G.apply(G.M_LW, (x, y, 0))
        pts += [(p[0], p[1]), (-p[0], p[1])]
    yf = -PR.BRIDGE_LEN                     # same as parts.case_world's bridge front feet
    for sx in (-1, 1):
        y = yf + 8.0
        p = G.apply(G.M_PW, (sx * (abs(G.interface_x(y, G.Z0)) - 8.0), y, 0))
        pts.append((p[0], p[1]))
    return pts


def main(out, deltas):
    os.makedirs(os.path.join(out, "print"), exist_ok=True)
    feet = feet_world()
    y_back = max(y for _, y in feet)
    lines = []
    for d in deltas:
        t = math.tan(math.radians(abs(d)))
        hs = sorted(((y_back - y) * t, (x, y)) for x, y in feet)
        solids = []
        k = 0
        for h, (x, y) in hs:
            if h < MIN_BODY + POCKET_H:
                continue                      # back feet: the bumpon stays on the case
            body = (cq.Workplane("XY").circle(RISER_D / 2).extrude(h)
                    .faces(">Z").workplane().circle(PLUG_D / 2).extrude(PLUG_H)
                    .faces("<Z").workplane().circle(POCKET_D / 2).cutBlind(-POCKET_H))
            col, row = k % 4, k // 4
            solids.append(body.translate((col * (RISER_D + 4), row * (RISER_D + 4), 0)))
            lines.append(f"  {abs(d):.0f} deg forward: foot at ({x:6.1f}, {y:6.1f}) -> riser {h:5.1f} mm")
            k += 1
        if solids:
            u = solids[0]
            for s in solids[1:]:
                u = u.union(s)
            cq.exporters.export(u, os.path.join(out, "print", f"tilt_risers_{abs(d):.0f}deg.stl"), **TOL)
    note = (f"Tilt risers for splay {PR.SPLAY_DEG:g}, tent {PR.TENT_DEG:g}, built-in tilt {PR.TILT_DEG:+g} deg.\n"
            f"The case pivots on its back feet (no riser there); fit each riser by its height.\n" + "\n".join(lines) + "\n")
    open(os.path.join(out, "print", "tilt_risers.txt"), "w").write(note)
    print(note)


if __name__ == "__main__":
    main(sys.argv[1], [float(v) for v in sys.argv[2:]] or [5.0])
