"""
Rev 2 flex jumper as an elastic strip:  C58_REV=2 python3 -m compose flex-sim OUT

compose.pcb.jumper designs the jumper along an ideal path (three r 2 mm bends). Here the real strip finds its
own shape: clamped at both ends by the connectors and left to settle, it takes the shape of least bending
energy. The strip is a thin sheet that doesn't stretch, so its shape is developable: a flat strip bent along
straight lines across it (rulings). It's modelled as exactly that: N rulings in the flat strip (each a
position and an angle), folded by a dihedral angle at each one. Every such shape is an exact isometry of the
flat strip, so the model can't stretch or bend in its own plane, and it twists only the way a real wide strip
does (rulings fanning out). Bending energy ~ sum over rulings of fold angle^2 * integral(1 / local spacing)
along the ruling (curvature^2 over the area); it is minimised with both clamps fixed (SLSQP).

Scenarios, each checked against the case model (the parts gasket-checks builds):
  seated        both ends home; the shape vs the design, clearances, smallest bend radius
  insertion     the controller end lifted 1..4.1 mm (the slot depth) while it's plugged in from above:
                the strip still reaches, the copper not strained past CU_INSERT
  gasket travel the half end moving with the plate on its foam: +-TRAVEL_CYCLE per keystroke (the copper's
                strain amplitude against its fatigue limit), and rare excursions (down 0.5 / 1.0, up 0.5 mm)
  length        the strip 0.5-1.5 mm longer or 0.5 mm shorter than designed (slack, and tolerance)
Curvature is judged where the copper is (V_CU): the bare polyimide edge takes far tighter bends.
Writes OUT/flex_sim/report.md and a JSON of every number.
"""
import json
import math
import os
import sys
import time
from types import SimpleNamespace

import numpy as np
from scipy.optimize import minimize

from compose import params as PR
from compose.pcb import jumper as J

OUT = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
W = PR.JUMPER_W
N_RUL = 42                     # rulings in the free part of the strip
H_MIN = 0.02                   # rulings never closer than this anywhere across the strip (mm)
CU_Y = 0.015                   # copper's distance from the neutral axis (mm): single-sided 0.11 mm stack, the
                               #   stiff copper pulls the neutral axis to ~11 um from its centre; 15 with margin
V_CU = np.array([-9.75, 0.0, 9.75])   # where copper is: the outer conductors' outer edges and the centre (the bare
                                      #   polyimide edge beyond takes far tighter bends; the copper is what cracks)
CU_SEATED = 0.015              # copper strain, seated for good (static)
CU_INSERT = 0.025              # ... momentarily while the controller end goes in: half rolled-annealed copper's
                               #   ~5 % minimum elongation (thin electro-deposited foil is closer to 2-3 %)
CU_FATIGUE = 0.002             # strain amplitude copper takes for >= 1e7 cycles (ED ~0.2 %, RA ~0.3 %)
TRAVEL_CYCLE = 0.2             # plate motion at the connector per keystroke, a generous bound: the connector sits by
                               #   the inner-edge pads, and the foam pads near it (~10 N/mm each at 25-35 % squeeze)
                               #   share a hard 2-5 N keypress. Larger moves (0.5, 1.0 mm) are rare: checked for room
                               #   and settling, their strain reported, not held to the fatigue limit
LENGTH_TOL = 0.5               # strip length variation that counts for clearance (cut +-0.1, seating depth +-0.3)
RAILS = {"GND": (1, 4, 20), "5 V": (2, 19)}   # slots in parallel: a rail is fine while one of its conductors is
SIGNALS = tuple(k for k in range(1, 21) if k not in (1, 2, 4, 19, 20))     # every other slot, each on its own
Z = np.array([0.0, 0.0, 1.0])
_V = np.linspace(-W / 2, W / 2, 9)
_SW = np.array([1, 4, 2, 4, 2, 4, 2, 4, 1]) * (W / 8) / 3          # Simpson weights across the strip


def _rod(a, th):
    a = a / np.linalg.norm(a)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


class Strip:
    """The jumper's flat strip of length L between a half-end clamp and a controller-end clamp.
    Flat coordinates: s along the strip from the half end's tip, v across (+ = left seen from the conductor
    side), z = the conductor side's normal. A clamp is a rigid map flat -> 3D (R, p)."""

    def __init__(self, g, L=None, half_move=np.zeros(3), ctrl_lift=0.0):
        self.g = g
        self.L = L if L is not None else g.length
        self.a = J.STIFF_HALF                                   # free part: between the two stiffeners
        self.b = self.L - J.STIFF_CTRL
        t0, w0 = g.F0[:, 0], g.F0[:, 1]
        self.R0 = np.column_stack([t0, w0, np.cross(t0, w0)])
        self.p0 = g.half.face + half_move - J.INS_HALF * t0     # flat s = INS_HALF lands on the connector face
        self.Rt = np.column_stack([-Z, [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
        tip = g.ctrl.top - J.INS_CTRL * Z + ctrl_lift * Z        # the controller-end tip
        self.pt = tip - self.Rt @ np.array([self.L, 0.0, 0.0])

    # ---- variables: z = [s_1..s_N, tau_1..tau_N, theta_1..theta_N]; ruling i: s = s_i + v * tau_i
    def unpack(self, z):
        n = len(z) // 3
        return z[:n], z[n:2 * n], z[2 * n:]

    def fold(self, z, upto=None):
        """Rigid maps of every piece: [(R, p)] for the piece before ruling 1, between 1 and 2, ..."""
        s, tau, th = self.unpack(z)
        R, p = self.R0.copy(), self.p0.copy()
        out = [(R, p)]
        for i in range(len(s)):
            q = R @ np.array([s[i], 0.0, 0.0]) + p
            d = R @ (np.array([tau[i], 1.0, 0.0]) / math.hypot(tau[i], 1.0))
            Rot = _rod(-d, th[i])
            R, p = Rot @ R, Rot @ (p - q) + q
            out.append((R, p))
        return out

    def end_resid(self, z):
        R, p = self.fold(z)[-1]
        return np.array([R[0, 0], R[1, 0], R[0, 1], *(p - self.pt)])

    def end_ok(self, z):
        R, p = self.fold(z)[-1]
        return np.abs(R - self.Rt).max() < 1e-5 and np.abs(p - self.pt).max() < 1e-5

    def xs(self, z):
        """x_i(v) for every ruling and sample v, with the two stiffener edges as rulings 0 and N+1."""
        s, tau, _ = self.unpack(z)
        x = s[:, None] + tau[:, None] * _V[None, :]
        return np.vstack([np.full(len(_V), self.a), x, np.full(len(_V), self.b)])

    def energy(self, z):
        s, tau, th = self.unpack(z)
        x = self.xs(z)
        h = (x[2:] - x[:-2]) / 2                                # each ruling's share of the strip, along s
        h = np.maximum(h, 1e-6)
        return float(np.sum(th ** 2 * (1 + tau ** 2) * ((1.0 / h) @ _SW)))

    def gaps(self, z):
        x = self.xs(z)
        return np.concatenate([(x[1:] - x[:-1])[:, [0, -1]].ravel() - H_MIN])

    def curvature(self, z, V=None):
        """Curvature across each ruling at points v across the strip (default: the copper, V_CU): fold angle /
        local spacing, measured square to the ruling."""
        V = V_CU if V is None else V
        s, tau, th = self.unpack(z)
        x = s[:, None] + tau[:, None] * V[None, :]
        x = np.vstack([np.full(len(V), self.a), x, np.full(len(V), self.b)])
        h = (x[2:] - x[:-2]) / 2 / np.sqrt(1 + tau[:, None] ** 2)
        return np.abs(th)[:, None] / np.maximum(h, 1e-6)

    def solve(self, z0, maxiter=400):
        n = len(z0) // 3
        bnd = [(self.a, self.b)] * n + [(-0.5, 0.5)] * n + [(-1.2, 1.2)] * n
        cons = [{"type": "eq", "fun": self.end_resid}, {"type": "ineq", "fun": self.gaps}]
        sc = self.energy(z0) or 1.0
        res = minimize(lambda z: self.energy(z) / sc, z0, method="SLSQP", bounds=bnd, constraints=cons,
                       options=dict(maxiter=maxiter, ftol=1e-10))
        z = res.x
        ok = self.end_ok(z) and self.gaps(z).min() >= -1e-6
        return z, ok, res

    # ---- geometry out
    def rulings_3d(self, z, n_between=1):
        """[(centre, along-ruling unit vector, normal, half length)] at every ruling and between them."""
        s, tau, _ = self.unpack(z)
        maps = self.fold(z)
        x = self.xs(z)
        out = []
        # cross-lines: the clamped pieces' ends, the rulings, and lines between them (on their piece)
        lines = [(0, J.INS_HALF, 0.0), (0, self.a, 0.0)]      # piece 0: from the connector face (s = INS_HALF)
        for i in range(len(s)):
            lines.append((i, s[i], tau[i]))                     # ruling i, end of piece i
            lines.append((i + 1, s[i], tau[i]))                 # ruling i, start of piece i + 1 (same line)
        lines += [(len(s), self.b, 0.0), (len(s), self.L - J.INS_CTRL, 0.0)]
        for k, sv, tv in lines:
            R, p = maps[k]
            c = R @ np.array([sv, 0.0, 0.0]) + p
            d = R @ (np.array([tv, 1.0, 0.0]) / math.hypot(tv, 1.0))
            out.append((c, d, R[:, 2], W / 2 * math.hypot(tv, 1.0)))
        return out

    def solid(self, z):
        import cadquery as cq
        T = J.T_SOLID
        wires = []
        for c, d, nrm, hl in self.rulings_3d(z):
            q = [c + a * hl * d + b * T / 2 * nrm for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            wires.append(cq.Wire.makePolygon([cq.Vector(*v) for v in q] + [cq.Vector(*q[0])]))
        # consecutive duplicate lines (a ruling seen from both pieces) are the same wire: keep one
        keep = [wires[0]]
        pts = [w.Center() for w in wires]
        for w, c, cp in zip(wires[1:], pts[1:], pts[:-1]):
            if (c - cp).Length > 1e-6:
                keep.append(w)
        return cq.Solid.makeLoft(keep, True)

    def centre_line(self, z, n=6):
        """Densely sampled 3D centre line (v = 0) from the half connector's face to the controller's slot."""
        s, tau, _ = self.unpack(z)
        maps = self.fold(z)
        knots = [J.INS_HALF] + list(s) + [self.L - J.INS_CTRL]
        pts = []
        for k in range(len(knots) - 1):
            R, p = maps[k]
            for u in np.linspace(knots[k], knots[k + 1], n, endpoint=False):
                pts.append(R @ np.array([u, 0.0, 0.0]) + p)
        R, p = maps[-1]
        pts.append(R @ np.array([knots[-1], 0.0, 0.0]) + p)
        return np.array(pts)


def initial(strip, n=N_RUL):
    """Rulings from the designed path: each r 2 mm bend split into folds along its skewed bend lines; rulings in
    the straights unfolded. Positions are rescaled into the strip's free part (a longer or shorter strip)."""
    g = strip.g
    pos = [J.STIFF_HALF + g.Ls[0]]
    marks = []
    for i, ((phi, beta), arc) in enumerate(zip(g.bends, g.arcs)):
        k = n // 3
        sg = J.SIGNS[i]
        for j in range(k):
            marks.append((pos[-1] + arc * (j + 0.5) / k, math.tan(beta), sg * phi / k))
        pos.append(pos[-1] + arc + (g.Ls[i + 1] if i + 1 < len(g.Ls) else 0.0))
    s = np.array([m[0] for m in marks]); tau = np.array([m[1] for m in marks]); th = np.array([m[2] for m in marks])
    a0, b0 = J.STIFF_HALF, g.length - J.STIFF_CTRL
    s = strip.a + (s - a0) * (strip.b - strip.a) / (b0 - a0)
    return np.concatenate([s, tau, th])


def run():
    t_start = time.time()
    g = J.solve()
    out = os.path.join(OUT, "flex_sim")
    os.makedirs(out, exist_ok=True)
    rep, data = [], {}

    def line(t):
        print(t, flush=True)
        rep.append(t)

    line("# Flex jumper: elastic strip simulation\n")
    line(f"Designed path: {J.describe(g)}.\n")
    # ---- seated, nominal
    st = Strip(g)
    z0 = initial(st)
    ok0 = st.end_ok(z0)
    line(f"Start: the design split into {len(z0) // 3} folds; meets both clamps: {ok0} "
         f"(residual {np.abs(st.end_resid(z0)).max():.2e}).")
    z, ok, res = st.solve(z0)
    if not ok:
        z, ok, res = st.solve(z, maxiter=800)
    seated = SimpleNamespace(z=z, ok=ok, strip=st)
    cl_d, cl_s = st.centre_line(z0), st.centre_line(z)
    dev = max(np.min(np.linalg.norm(cl_d - p, axis=1)) for p in cl_s)
    kmax = st.curvature(z).max()
    line(f"\n## Seated\n\nEquilibrium found: {ok} ({res.nit} iterations). Energy {st.energy(z):.4g} vs the design's "
         f"{st.energy(z0):.4g} (relative units).")
    line(f"- the settled centre line stays within {dev:.2f} mm of the designed one")
    line(f"- smallest bend radius at the copper {1 / kmax:.2f} mm (design 2.0): copper strain {CU_Y * kmax * 100:.2f} %; "
         f"at the bare edge {1 / st.curvature(z, np.array([-W / 2, W / 2])).max():.2f} mm")
    data["seated"] = dict(ok=bool(ok), dev=dev, r_min=1 / kmax, energy=st.energy(z), energy_design=st.energy(z0))
    np.save(os.path.join(out, "seated.npy"), z)

    # ---- insertion: the controller end lifted while it's pushed down into the slot
    line("\n## Insertion (controller end lifted above its seat, half end home)\n")
    line("| lift | reaches | smallest radius at the copper | copper strain | energy vs seated |")
    line("|---|---|---|---|---|")
    zi = z
    data["insertion"] = []
    for lift in (1.0, 2.0, 3.0, 4.1):
        sl = Strip(g, ctrl_lift=lift)
        zi, oki, _ = sl.solve(zi)
        r_i = 1 / sl.curvature(zi).max()
        line(f"| {lift:.1f} mm | {'yes' if oki else 'NO'} | {r_i:.2f} mm | {CU_Y / r_i * 100:.2f} % | {sl.energy(zi) / st.energy(z):.2f}x |")
        data["insertion"].append(dict(lift=lift, ok=bool(oki), r_min=r_i))

    # ---- gasket travel: the half end moves with the plate
    from compose import geom as G
    nP = G.M_LP[:3, :3] @ np.array([0, 0, 1.0])                 # plate normal, bridge frame (left half)
    nP = nP / np.linalg.norm(nP)
    line("\n## Gasket travel (half end moving with the plate along its normal)\n")
    line("| travel | settles | smallest radius | largest curvature change | copper strain amplitude (worst conductor) |")
    line("|---|---|---|---|---|")
    # each conductor's copper, at its outer edge; the right jumper is the mirror image, so slot k sits at the same
    # mirrored spot on both sides and one side's numbers hold for both
    ws = {k: J.conductor_w(k) for k in range(1, 21)}
    VK = np.array([ws[k] + 0.25 * np.sign(ws[k]) for k in range(1, 21)])
    per_slot = {}
    data["travel"] = []
    k_seat = st.curvature(z)
    travel_z = {}
    for d in (-1.0, -0.5, -TRAVEL_CYCLE, TRAVEL_CYCLE, 0.5):
        sv = Strip(g, half_move=d * nP)
        zt, okt, _ = sv.solve(z)
        k_t = sv.curvature(zt)
        # curvature change at the same material line: rulings move, so compare along the strip, not per ruling
        # curvature change at the same material point: rulings move between shapes, so compare along the strip
        grid = np.linspace(st.a, st.b, 600)
        s1, k1 = st.unpack(z)[0], st.curvature(z, VK)
        s2, k2 = sv.unpack(zt)[0], sv.curvature(zt, VK)
        dks = [np.abs(np.interp(grid, s2, k2[:, j]) - np.interp(grid, s1, k1[:, j])).max() for j in range(20)]
        dk = max(dks)
        eps = CU_Y * dk
        if abs(abs(d) - TRAVEL_CYCLE) < 1e-9:
            for j in range(20):
                per_slot[j + 1] = max(per_slot.get(j + 1, 0.0), CU_Y * dks[j])
        line(f"| {d:+.1f} mm | {'yes' if okt else 'NO'} | {1 / k_t.max():.2f} mm | {dk:.3f} /mm | {eps * 100:.3f} % |")
        data["travel"].append(dict(travel=d, ok=bool(okt), r_min=1 / k_t.max(), dk=dk, strain=eps))
        travel_z[d] = (sv, zt)
    data["per_slot_strain"] = per_slot
    line(f"\nPer keystroke (+-{TRAVEL_CYCLE} mm), copper strain amplitude by slot (%): "
         + " ".join(f"{k}:{per_slot[k] * 100:.3f}" for k in range(1, 21)))

    # ---- length: a hedge and the tolerance
    line("\n## Length (the same clamps, the strip longer or shorter than designed)\n")
    line("| length | settles | smallest radius at the copper | reaches the slot at a 4.1 mm lift |")
    line("|---|---|---|---|")
    data["length"] = []
    length_z = {}
    for dl in (-0.5, 0.5, 1.0):
        sL = Strip(g, L=g.length + dl)
        zl, okl, _ = sL.solve(initial(sL))
        zl2, okl2 = zl, False
        if okl:
            for lift in (1.0, 2.0, 3.0, 4.1):
                sLi = Strip(g, L=g.length + dl, ctrl_lift=lift)
                zl2, okl2, _ = sLi.solve(zl2)
                if not okl2:
                    break
        r_l = 1 / sL.curvature(zl).max() if okl else float("nan")
        line(f"| {g.length + dl:.1f} mm ({dl:+.1f}) | {'yes' if okl else 'NO'} | {r_l:.2f} mm | {'yes' if okl2 else 'NO'} |")
        data["length"].append(dict(dl=dl, ok=bool(okl), r_min=r_l, insert_ok=bool(okl2)))
        length_z[dl] = (sL, zl) if okl else None

    # ---- clearances against the case model
    line("\n## Clearances (settled shapes against the case model, mm)\n")
    print("building the case parts ...", flush=True)
    from compose.checks import gasket as GK
    parts, case, _, _ = GK.parts_world(jumpers=False)
    names = ("case", "plate", "frame", "cover", "half pcb", "standoffs", "pico", "ctrl board")
    touching = ("half parts", "top parts")          # its own two connectors are among these: overlap, not distance
    lim = {"plate": 1.0}
    shapes = [("seated", st, z, np.zeros(3))]
    shapes += [(f"travel {d:+.1f} mm", sv, zt, d * nP) for d, (sv, zt) in travel_z.items()]
    shapes += [(f"length {dl:+.1f} mm", *length_z[dl], np.zeros(3)) for dl in (-0.5, 0.5, 1.0) if length_z.get(dl)]
    line("| shape | " + " | ".join(names) + " | " + " | ".join(f"{n} overlap (mm3)" for n in touching) + " |")
    line("|---|" + "---|" * (len(names) + len(touching)))
    data["clearance"] = {}
    moving = ("plate", "half pcb", "half parts")                # these ride on the gasket with the half end
    for label, sx, zx, mv in shapes:
        sol = G.P2W(sx.solid(zx))
        mvw = G.M_PW[:3, :3] @ mv
        row = {}
        for nm in touching:
            other = parts[nm]
            if nm == "half parts" and np.linalg.norm(mvw) > 0:
                import cadquery as cq
                other = other.translate(cq.Vector(*mvw))
            row[nm + " overlap"] = GK.vol(sol, other)
        for nm in names:
            if nm not in parts:
                continue
            other = parts[nm]
            if nm in moving and np.linalg.norm(mvw) > 0:      # (both halves move; only the left jumper is checked)
                import cadquery as cq
                other = other.translate(cq.Vector(*mvw))
            row[nm] = G.distance(sol, other)
        data["clearance"][label] = row
        line(f"| {label} | " + " | ".join(f"{row[n]:.2f}" if n in row else "-" for n in names)
             + " | " + " | ".join(f"{row[n + ' overlap']:.3f}" for n in touching) + " |")
    counts = {k: v for k, v in data["clearance"].items()                     # length variants beyond the
              if not k.startswith("length") or abs(float(k.split()[1])) <= LENGTH_TOL + 1e-9}   # tolerance: info only
    worst = {n: min(r[n] for r in counts.values() if n in r) for n in names}
    data["worst_clearance"] = worst

    # ---- verdicts
    line("\n## Verdict\n")
    fails = []

    def verdict(ok_, txt):
        line(f"- {'ok  ' if ok_ else 'FAIL'} {txt}")
        if not ok_:
            fails.append(txt)
    verdict(seated.ok, f"the strip settles between the two connectors (within {dev:.2f} mm of the design)")
    verdict(CU_Y * kmax <= CU_SEATED, f"seated: copper strain {CU_Y * kmax * 100:.2f} % <= {CU_SEATED * 100:.1f} % "
                                     f"(smallest radius at the copper {1 / kmax:.2f} mm)")
    ins = data["insertion"]
    rin = min(i["r_min"] for i in ins)
    verdict(all(i["ok"] for i in ins) and CU_Y / rin <= CU_INSERT,
            f"insertion: the end reaches 4.1 mm above its seat; copper strain {CU_Y / rin * 100:.2f} % <= "
            f"{CU_INSERT * 100:.1f} % (radius {rin:.2f} mm at the copper)")
    tr = data["travel"]
    verdict(all(t["ok"] for t in tr), "gasket travel: settles at every travel from -1.0 to +0.5 mm")
    sig = max(per_slot[k] for k in SIGNALS)
    verdict(sig <= CU_FATIGUE, f"per keystroke (+-{TRAVEL_CYCLE} mm at the connector): every signal conductor's copper "
                               f"strain amplitude <= {CU_FATIGUE * 100:.1f} % (>= 1e7 cycles): worst {sig * 100:.3f} %")
    for rail, ks in RAILS.items():
        best = min(per_slot[k] for k in ks)
        verdict(best <= CU_FATIGUE, f"per keystroke: the {rail} rail keeps a conductor under the fatigue limit "
                                    f"({', '.join(f'slot {k} {per_slot[k] * 100:.3f} %' for k in ks)})")
    big = max(t["strain"] for t in tr if abs(t["travel"]) > TRAVEL_CYCLE + 1e-9)
    line(f"- info a rare 0.5-1.0 mm excursion strains the copper {big * 100:.2f} % (low-cycle; copper takes that "
         f"thousands of times)")
    verdict(worst["plate"] >= 1.0 and all(worst[n] >= 0.5 for n in names if n != "plate" and n in worst),
            f"clearances seated, over the travel and within +-{LENGTH_TOL} mm of length: plate >= 1.0, everything else >= 0.5 ("
            + ", ".join(f"{n} {worst[n]:.2f}" for n in names if n in worst) + ")")
    ov = max(r[n + " overlap"] for r in data["clearance"].values() for n in touching)
    verdict(ov < 1e-3, f"no overlap with the connectors or anything else on the boards ({ov:.3f} mm3)")
    line(f"\n{len(fails)} failure(s). {time.time() - t_start:.0f} s.")
    data["fails"] = fails
    open(os.path.join(out, "report.md"), "w").write("\n".join(rep) + "\n")
    json.dump(data, open(os.path.join(out, "flex_sim.json"), "w"), indent=1, default=float)
    return len(fails)


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
