"""
Circuit simulation of the controller rev 2 (ngspice), worst-case corners swept:

    python3 -m compose spice-controller [outdir]   -> outdir/sim_controller_rev2/{report.md, *.png, decks/}

  A  RGB data, controller -> first LED of the left half (74HCT125 buffer, 330 ohm, PCB + flex jumper + half traces),
     and the same with GP13 driving the LEDs directly (no buffer), for comparison.
  B  RGB chain hop: last LED of the left half -> controller -> first LED of the right half (two jumper runs).
  C  I2C rise time / low level on GP14/GP15 with the board's 4.7k pull-ups plus module pull-ups and bus C.
  D  PS/2 pointing stick on the I2C pins: pin voltage with a 5 V stick and its own pull-ups.
  E  Power: USB hot-plug inrush with the RGB rail populated (C2 options), DC drop to the far LED,
     brightness cap for the polyfuse.
  F  Matrix (QMK COL2ROW, rows strobed, columns read with the RP2040 pull-ups): low level through the diode,
     select / unselect timing against QMK's delays, jumper and controller-trace crosstalk into the columns.

Track lengths, widths and parallel runs come from the routed board (out/pcb/controller_rev2.kicad_pcb);
parts are modelled from their datasheet limits (sources in the report). Jumper and half-board values are
swept over generous ranges (the jumper up to 100 mm, so other layouts' jumpers are covered too).
"""
import os
import sys
import math
import json
import itertools
import subprocess
import numpy as np

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
SIM = os.path.join(OUT, "sim_controller_rev2")
DECKS = os.path.join(SIM, "decks")
os.makedirs(DECKS, exist_ok=True)
REPORT = []
FAILS = []
WARNS = []


def rep(s=""):
    print(s)
    REPORT.append(s)


def verdict(cond, msg, warn_only=False):
    tag = "ok  " if cond else ("WARN" if warn_only else "FAIL")
    rep(f"- **{tag}** {msg}")
    if not cond:
        (WARNS if warn_only else FAILS).append(msg)
    return cond


# ------------------------------------------------------------------ ngspice runner
def spice(name, body, vecs, tran=None, op=False):
    """Run a deck; return dict of numpy arrays (time + vecs) or op values."""
    deck = os.path.join(DECKS, name + ".cir")
    data = os.path.join(DECKS, name + ".dat")
    ctl = ["set wr_singlescale", "set wr_vecnames", "option numdgt=7"]
    if op:
        ctl += ["op", "print " + " ".join(vecs) + f" > {data}"]
    else:
        ctl += [f"tran {tran}", f"wrdata {data} " + " ".join(vecs)]
    txt = f"* {name}\n{body}\n.control\n" + "\n".join(ctl) + "\nquit\n.endc\n.end\n"
    open(deck, "w").write(txt)
    r = subprocess.run(["ngspice", "-b", deck], capture_output=True, text=True, timeout=60)
    if not os.path.exists(data) or "error" in r.stdout.lower() and "no error" not in r.stdout.lower():
        if not os.path.exists(data):
            raise RuntimeError(f"ngspice failed on {name}:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    if op:
        vals = {}
        for line in open(data):
            if "=" in line:
                k, v = line.split("=")
                vals[k.strip()] = float(v)
        os.remove(data)
        return vals
    arr = np.loadtxt(data, skiprows=1)
    os.remove(data)
    out = {"t": arr[:, 0]}
    for i, v in enumerate(vecs):
        out[v] = arr[:, i + 1]
    return out


def crossings(t, v, level):
    """Times where v crosses level (linear interpolation), with direction (+1 rising, -1 falling)."""
    s = v - level
    idx = np.where(np.sign(s[:-1]) * np.sign(s[1:]) < 0)[0]
    res = []
    for i in idx:
        tc = t[i] - s[i] * (t[i + 1] - t[i]) / (s[i + 1] - s[i])
        res.append((tc, 1 if s[i + 1] > s[i] else -1))
    return res


# ------------------------------------------------------------------ board facts (from the routed copper)
def board_facts():
    import pcbnew
    path = os.path.join(OUT, "pcb", "controller_rev2.kicad_pcb")
    b = pcbnew.LoadBoard(path)
    segs = []
    for t in b.GetTracks():
        if t.GetClass() != "PCB_TRACK":
            continue
        a, c = t.GetStart(), t.GetEnd()
        segs.append(dict(net=t.GetNetname(), lay=t.GetLayer(), w=pcbnew.ToMM(t.GetWidth()),
                         a=np.array([pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)]), b=np.array([pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)])))
    length, res = {}, {}
    for s in segs:
        L = float(np.linalg.norm(s["b"] - s["a"]))
        length[s["net"]] = length.get(s["net"], 0) + L
        # 1 oz (35 um) copper, 1.72e-8 ohm m, +20 % for temperature / plating tolerance
        res[s["net"]] = res.get(s["net"], 0) + 1.2 * 1.72e-8 * (L * 1e-3) / (s["w"] * 1e-3 * 35e-6)
    vias = {}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias[t.GetNetname()] = vias.get(t.GetNetname(), 0) + 1
    return segs, length, res, vias


def coupled_runs(segs, max_gap=0.6):
    """Parallel overlap length (mm) and mean edge gap for every pair of nets on the same layer."""
    pairs = {}
    for i, s in enumerate(segs):
        d1 = s["b"] - s["a"]
        L1 = np.linalg.norm(d1)
        if L1 < 0.2:
            continue
        u1 = d1 / L1
        for s2 in segs[i + 1:]:
            if s2["lay"] != s["lay"] or s2["net"] == s["net"]:
                continue
            d2 = s2["b"] - s2["a"]
            L2 = np.linalg.norm(d2)
            if L2 < 0.2 or abs(np.dot(u1, d2 / L2)) < 0.97:          # parallel within ~14 deg
                continue
            # project s2 onto s1's line
            p = [np.dot(s2["a"] - s["a"], u1), np.dot(s2["b"] - s["a"], u1)]
            lo, hi = max(0, min(p)), min(L1, max(p))
            if hi - lo <= 0.1:
                continue
            nrm = np.array([-u1[1], u1[0]])
            dist = abs(np.dot((s2["a"] + s2["b"]) / 2 - s["a"], nrm))
            gap = dist - (s["w"] + s2["w"]) / 2
            if gap > max_gap:
                continue
            k = tuple(sorted((s["net"], s2["net"])))
            e = pairs.setdefault(k, [0.0, []])
            e[0] += hi - lo
            e[1].append(gap)
    return {k: (v[0], float(np.mean(v[1]))) for k, v in pairs.items()}


# ------------------------------------------------------------------ shared models
MODELS = """
.model D1N4148 D(IS=2.52n RS=0.568 N=1.752 CJO=4p M=0.4 TT=20n BV=100 IBV=100u)
.model DCLAMP D(IS=1e-14 N=1.0 RS=10 CJO=1p)
.model DSCH D(IS=3e-6 RS=0.05 N=1.05 CJO=50p)
"""

# datasheet numbers used below (the report prints them too)
RP = dict(VIH=2.0, VIL=0.8, VABS=3.3 + 0.5, RPU=(50e3, 80e3), CIN=5e-12, R_DRV=(50.0, 170.0))
#   RP2040 datasheet 5.5.3: VIH 2.0 / VIL 0.8 at IOVDD 3.3, pull-up 50-80k, VOH >= 2.62 V at 4 mA (-> <= 170 ohm)
HCT = dict(VTH=1.4, VIH=2.0, VIL=0.8, R_OUT=(30.0, 110.0), TPD=(10e-9, 25e-9))
#   74HCT125 (Nexperia): VIH 2.0 / VIL 0.8, VOH 3.84 V at -6 mA, VCC 4.5 V, 85 C (-> ~110 ohm worst)
WS = dict(VIH_K=0.7, VIL_K=0.3, CIN=10e-12, T0H=(0.25e-6, 0.55e-6), T1H=(0.65e-6, 0.95e-6))
#   WS2812B: VIH 0.7 VDD, VIL 0.3 VDD, T0H 0.4 +-0.15 us, T1H 0.8 +-0.15 us (SK6812: same thresholds)
QMK = dict(T0H=0.35e-6, T1H=0.90e-6, TBIT=1.25e-6, SELECT=0.25e-6, IO_DELAY=30e-6)
#   QMK ws2812 timing defaults (350 / 900 / 1250 ns), waitInputPinDelay ~ 1/4 us on RP2040, MATRIX_IO_DELAY 30 us
FFC = dict(Z0=(100.0, 180.0), TD_PER_M=4.8e-9, R_PER_M=3.0, C_PER_M=(30e-12, 60e-12), CM_PER_M=(10e-12, 30e-12),
           LEN=(0.02, 0.10), I_MAX=1.0)
#   the flex jumper (compose.pcb.jumper; 26 mm on Compose58 rev 2): 20 x 0.5 mm conductors at 1.0 mm on polyimide,
#   no plane, so Z0 / C / mutual C as a 1.0 mm FFC over a wide band; 3 ohm/m = 0.5 mm x 12 um (1/3 oz), the
#   thinnest flex copper. Length swept 20 / 100 mm.
LEN_TXT = f"{FFC['LEN'][0] * 1e3:.0f}/{FFC['LEN'][1] * 1e3:.0f} mm"
PCBZ = dict(Z0=(90.0, 150.0), TD_PER_M=5.8e-9, C_PER_MM=(0.05e-12, 0.10e-12), CM_PER_MM_AT=lambda g: 0.03e-12 * (0.2 / max(g, 0.1)) ** 0.6)
#   two-layer board without a plane: 0.25 mm traces 90-150 ohm, edge-coupled mutual C ~0.03 pF/mm at 0.2 mm gap


def bit_pwl(bits, vhigh, t_r=4e-9, t0=50e-9):
    pts = [(0, 0)]
    t = t0
    for bt in bits:
        th = QMK["T1H"] if bt else QMK["T0H"]
        pts += [(t, 0), (t + t_r, vhigh), (t + th, vhigh), (t + th + t_r, 0)]
        t += QMK["TBIT"]
    pts.append((t + 0.5e-6, 0))
    return "PWL(" + " ".join(f"{a:.4e} {b:.4e}" for a, b in pts) + ")"


def tline(name, a, b, z0, td, r_series=0.0, gnd="0"):
    """Transmission line as an LC ladder (sections of <= 0.1 ns, well under the 3-6 ns edges) with its DC
    resistance spread along it. ngspice's ideal T element collapses the timestep on chains of sub-ns lines."""
    n = max(2, int(math.ceil(td / 0.1e-9)))
    L, Cc = z0 * td / n, td / z0 / n
    out, prev = [], a
    for i in range(n):
        mid = f"{name}_m{i}"
        nxt = b if i == n - 1 else f"{name}_n{i}"
        if r_series > 1e-6:
            out.append(f"R{name}_{i} {prev} {mid} {r_series / n:.5f}")
            out.append(f"L{name}_{i} {mid} {name}_l{i} {L:.4e}")
            prev2 = f"{name}_l{i}"
        else:
            out.append(f"L{name}_{i} {prev} {mid} {L:.4e}")
            prev2 = mid
        out.append(f"C{name}_{i} {nxt} {gnd} {Cc:.4e}")
        if prev2 != nxt:
            out.append(f"R{name}_j{i} {prev2} {nxt} 1u")
        prev = nxt
    return "\n".join(out) + "\n"


def led_input(node, vdd_node, tag):
    return (f"C{tag} {node} 0 {WS['CIN']}\nDH{tag} {node} {vdd_node} DCLAMP\nDL{tag} 0 {node} DCLAMP\n"
            f"RL{tag} {node} 0 10meg\n")


def analyse_bits(t, v, vdd, bits, label):
    """Receiver-side pulse widths at the WS2812 thresholds; returns (ok, details)."""
    vih, vil = WS["VIH_K"] * vdd, WS["VIL_K"] * vdd
    up = crossings(t, v, vih)
    dn = crossings(t, v, vil)
    rises = [c for c in up if c[1] > 0]
    falls_vih = [c for c in up if c[1] < 0]
    falls = [c for c in dn if c[1] < 0]
    rises_vil = [c for c in dn if c[1] > 0]
    n = len(bits)
    clean = len(rises) == n and len(falls_vih) == n and len(falls) == n and len(rises_vil) == n
    widths = []
    if clean:
        for i, bt in enumerate(bits):
            w_min = falls_vih[i][0] - rises[i][0]           # high above VIH
            w_max = falls[i][0] - rises_vil[i][0]          # not below VIL
            widths.append((bt, w_min, w_max))
    ok = clean
    for bt, wmin, wmax in widths:
        lo, hi = WS["T1H"] if bt else WS["T0H"]
        ok &= (wmin >= lo) and (wmax <= hi)
    return ok, dict(clean=clean, widths=widths, vmax=float(v.max()), vmin=float(v.min()), vih=vih, vil=vil,
                    n_cross=(len(rises), len(falls_vih), len(falls), len(rises_vil)))


# ------------------------------------------------------------------ A: controller -> first LED
def sim_rgb_first(facts):
    rep("\n## A. RGB data: GP13 -> 74HCT125 -> 330 ohm -> left half, first LED\n")
    _, length, _, _ = facts
    L_ctrl = length.get("RGB_L_IN", 0) * 1e-3 + length.get("RGB_BUF", 0) * 1e-3
    L_in = length.get("GP13", 0) * 1e-3
    rep(f"Routed lengths: GP13 {L_in * 1e3:.1f} mm, RGB_BUF + RGB_L_IN {L_ctrl * 1e3:.1f} mm (controller).")
    rep("Swept: GPIO drive 50/170 ohm, HCT output 30/110 ohm and 10/25 ns delay, PCB Z0 90/150, jumper Z0 100/180 "
        f"and {LEN_TXT}, half trace 30/150 mm, LED rail (controller/far LED) 5.25/5.25, 5.0/4.8, 4.6/4.3 V. "
        "Bits sent: 0 1 0 1 1 0 (QMK 350/900 ns in a 1250 ns slot).\n")
    bits = [0, 1, 0, 1, 1, 0]
    rails = [(5.25, 5.25), (5.0, 4.8), (4.6, 4.3)]
    worst = None
    results = []
    n = 0
    for (vc, vf), rg, (rh, tpd), zp, zf, lf, lh in itertools.product(
            rails, RP["R_DRV"], [(30.0, 10e-9), (110.0, 25e-9)], PCBZ["Z0"], FFC["Z0"], FFC["LEN"], (0.03, 0.15)):
        n += 1
        body = MODELS + f"""
VCC vcc 0 {vc}
VFAR vfar 0 {vf}
VG g 0 {bit_pwl(bits, 3.3)}
RG g gp {rg}
{tline('gp', 'gp', 'u_in', zp, L_in * PCBZ['TD_PER_M'])}
CIN u_in 0 3.5p
R4 u_in 0 100k
BBUF u_int 0 V = V(vcc) * 0.5 * (1 + tanh((V(u_in) - {HCT['VTH']}) / 0.08))
RDA u_int u_d1 1k
CDA u_d1 0 {tpd / 0.693 / 1e3:.4e}
BREG u_dly 0 V = V(vcc) * 0.5 * (1 + tanh((V(u_d1) - V(vcc) / 2) / 0.05))
RIS u_dly u_rc 50
CIS u_rc 0 40p
EOUT u_e 0 u_rc 0 1
ROUT u_e buf {rh}
COUT buf 0 5p
R3 buf r3o 330
{tline('pc', 'r3o', 'jl', zp, L_ctrl * PCBZ['TD_PER_M'])}
CJ jl 0 1.5p
{tline('ffc', 'jl', 'hj', zf, lf * FFC['TD_PER_M'], lf * FFC['R_PER_M'])}
CJH hj 0 1.5p
{tline('hp', 'hj', 'din', 120, lh * PCBZ['TD_PER_M'])}
{led_input('din', 'vfar', 'led')}
"""
        res = spice("A_rgb", body, ["v(din)", "v(buf)", "v(u_in)"], tran="0.5n 8.2u")
        ok, d = analyse_bits(res["t"], res["v(din)"], vf, bits, "A")
        over = d["vmax"] - vf
        under = -d["vmin"]
        okc = ok and over < 0.5 and under < 0.5
        results.append((okc, (vc, vf), rg, rh, zp, zf, lf, lh, d))
        if worst is None or (not okc and worst[0]) or (okc == worst[0] and max(over, under) > worst[1]):
            worst = (okc, max(over, under), (vc, vf, rg, rh, zp, zf, lf, lh), d, res)
    n_ok = sum(r[0] for r in results)
    rep(f"{n} corners simulated, {n_ok} clean.")
    allw = [(bt, wmin, wmax) for r in results for (bt, wmin, wmax) in r[8]["widths"]]
    if allw:
        for bt in (0, 1):
            ws = [w for w in allw if w[0] == bt]
            lo, hi = WS["T1H"] if bt else WS["T0H"]
            rep(f"  - '{bt}' bit high time at the LED: {min(w[1] for w in ws) * 1e9:.0f}-{max(w[2] for w in ws) * 1e9:.0f} ns "
                f"(spec {lo * 1e9:.0f}-{hi * 1e9:.0f})")
    vmax = max(r[8]["vmax"] - r[1][1] for r in results)
    vmin = min(r[8]["vmin"] for r in results)
    rep(f"  - worst overshoot above the LED's VDD {vmax:+.2f} V, worst undershoot {vmin:+.2f} V (abs max +-0.5 V)")
    verdict(n_ok == n, f"buffered RGB data meets VIH/VIL, single clean edges and WS2812 timing at every corner ({n_ok}/{n})")
    plot_wave(worst[4], ["v(u_in)", "v(buf)", "v(din)"], "A_rgb_worst.png",
              f"RGB data, worst corner (rail {worst[2][0]}/{worst[2][1]} V, HCT {worst[2][3]:.0f} ohm, jumper Z0 {worst[2][5]:.0f}, {worst[2][6] * 1e3:.0f} mm)",
              hlines=[(WS['VIH_K'] * worst[2][1], "VIH"), (WS['VIL_K'] * worst[2][1], "VIL")])

    # comparison: GP13 straight into the LED (no buffer)
    rep("\nFor comparison, GP13 straight to the LEDs (3.3 V data, no buffer):")
    nd, okd = 0, 0
    for (vc, vf), rg, zf, lf in itertools.product(rails, RP["R_DRV"], FFC["Z0"], FFC["LEN"]):
        nd += 1
        body = MODELS + f"""
VFAR vfar 0 {vf}
VG g 0 {bit_pwl(bits, 3.3)}
RG g gp {rg}
R3 gp r3o 330
{tline('pc', 'r3o', 'jl', 120, (L_in + L_ctrl) * PCBZ['TD_PER_M'])}
{tline('ffc', 'jl', 'hj', zf, lf * FFC['TD_PER_M'], lf * FFC['R_PER_M'])}
{tline('hp', 'hj', 'din', 120, 0.08 * PCBZ['TD_PER_M'])}
{led_input('din', 'vfar', 'led')}
"""
        res = spice("A_direct", body, ["v(din)"], tran="0.5n 8.2u")
        ok, d = analyse_bits(res["t"], res["v(din)"], vf, bits, "A2")
        okd += ok
    rep(f"- (comparison only) without the buffer, 3.3 V data meets the LED's 0.7 x VDD threshold in just {okd}/{nd} "
        f"corners - the ones where the LED rail has sagged to 4.3 V. The 74HCT125 is what makes the RGB option in spec.")
    return results


# ------------------------------------------------------------------ B: hop left half -> right half
HCT_GATE = """
BBUF{g} {g}_int 0 V = V(vcc) * 0.5 * (1 + tanh((V({inp}) - {vth}) / 0.08))
RDA{g} {g}_int {g}_d1 1k
CDA{g} {g}_d1 0 {cd:.4e}
BREG{g} {g}_dly 0 V = V(vcc) * 0.5 * (1 + tanh((V({g}_d1) - V(vcc) / 2) / 0.05))
RIS{g} {g}_dly {g}_rc 50
CIS{g} {g}_rc 0 40p
EOUT{g} {g}_e 0 {g}_rc 0 1
ROUT{g} {g}_e {out} {rh}
COUT{g} {out} 0 5p
"""


def sim_rgb_hop(facts):
    rep("\n## B. RGB chain hop: left half's last LED -> controller -> right half's first LED\n")
    _, length, _, _ = facts
    L_ret = length.get("RGB_L_RET", 0) * 1e-3
    L_out = (length.get("RGB_HOP_BUF", 0) + length.get("RGB_R_IN", 0)) * 1e-3
    rep(f"The chain comes back from the left half's last LED through its jumper and goes out through the right one: "
        f"two jumper runs. On the controller, gate 2 of the 74HCT125 re-drives it (220 ohm in, 100k pull-down, "
        f"330 ohm out). Routed: return {L_ret * 1e3:.1f} mm, out {L_out * 1e3:.1f} mm. Swept: LED DOUT 30/200 ohm, "
        f"left half return trace 50/300 mm, jumper Z0 100/180 and {LEN_TXT} (both jumpers), HCT 30/110 ohm and "
        f"10/25 ns, right half trace 150 mm, rails 5.25, 4.8, 4.3 V (left/right LEDs and buffer alike).\n")
    bits = [0, 1, 0, 1, 1, 0]
    rails = (5.25, 4.8, 4.3)
    n = n_in = n_out = 0
    worst_i, worst_v, worst_res = 0.0, 0.0, None
    widths = []
    for v, rd, lr, zf, lf, (rh, tpd) in itertools.product(rails, (30.0, 200.0), (0.05, 0.30), FFC["Z0"], FFC["LEN"],
                                                         [(30.0, 10e-9), (110.0, 25e-9)]):
        n += 1
        gate = HCT_GATE.format(g="g2", inp="hin", vth=HCT["VTH"], cd=tpd / 0.693 / 1e3, out="hbuf", rh=rh)
        body = MODELS + f"""
VCC vcc 0 {v}
VG g 0 {bit_pwl(bits, v, t_r=6e-9)}
RD g dout {rd}
CD dout 0 3p
{tline('ret', 'dout', 'jl', 120, lr * PCBZ['TD_PER_M'])}
{tline('ffl', 'jl', 'c1', zf, lf * FFC['TD_PER_M'], lf * FFC['R_PER_M'])}
{tline('pcr', 'c1', 'c2', 120, L_ret * PCBZ['TD_PER_M'])}
R5 c2 hin 220
CIN hin 0 3.5p
R6 hin 0 100k
DH hin vcc DCLAMP
DL 0 hin DCLAMP
{gate}
R7 hbuf r7o 330
{tline('pco', 'r7o', 'c3', 120, L_out * PCBZ['TD_PER_M'])}
{tline('ffr', 'c3', 'hr', zf, lf * FFC['TD_PER_M'], lf * FFC['R_PER_M'])}
{tline('hp', 'hr', 'din', 120, 0.15 * PCBZ['TD_PER_M'])}
{led_input('din', 'vcc', 'led')}
"""
        res = spice("B_hop", body, ["v(din)", "v(hin)", "v(c2)", "v(dout)"], tran="0.5n 8.2u")
        t = res["t"]
        hin = res["v(hin)"]
        # HCT input: one clean crossing of 2.0 V and 0.8 V per edge
        c_hi, c_lo = crossings(t, hin, HCT["VIH"]), crossings(t, hin, HCT["VIL"])
        ok_in = len(c_hi) == 2 * len(bits) and len(c_lo) == 2 * len(bits)
        i_clamp = float(np.max(np.abs(res["v(c2)"] - hin)) / 220.0)          # upper bound on clamp current
        ok, d = analyse_bits(t, res["v(din)"], v, bits, "B")
        over, under = d["vmax"] - v, -d["vmin"]
        ok_out = ok and over < 0.5 and under < 0.5
        n_in += ok_in
        n_out += ok_out
        widths += d["widths"]
        if i_clamp > worst_i:
            worst_i = i_clamp
        if max(over, under) >= worst_v:
            worst_v, worst_res = max(over, under), res
    rep(f"{n} corners.")
    verdict(n_in == n, f"the ringing return run crosses the buffer's 2.0 / 0.8 V thresholds once per edge ({n_in}/{n})")
    verdict(worst_i < 20e-3, f"input clamp current <= {worst_i * 1e3:.1f} mA, inside the 74HCT125's 20 mA rating (220 ohm limits it)")
    for bt in (0, 1):
        ws = [w for w in widths if w[0] == bt]
        lo, hi = WS["T1H"] if bt else WS["T0H"]
        if ws:
            rep(f"  - '{bt}' bit high time at the right half's first LED: {min(w[1] for w in ws) * 1e9:.0f}-"
                f"{max(w[2] for w in ws) * 1e9:.0f} ns (spec {lo * 1e9:.0f}-{hi * 1e9:.0f})")
    verdict(n_out == n, f"right half's first LED gets clean, in-spec data at every corner ({n_out}/{n}); "
                        f"worst over/undershoot {worst_v:.2f} V")
    plot_wave(worst_res, ["v(dout)", "v(hin)", "v(din)"], "B_hop_worst.png",
              "RGB hop through the controller's second buffer gate, worst corner",
              hlines=[(HCT["VIH"], "HCT VIH"), (HCT["VIL"], "HCT VIL")])
    # comparison: the same two cable runs wired straight through (what rev 2 would be without gate 2)
    nd = okd = 0
    worst_d = 0
    for v, rd, lr, zf, lf in itertools.product(rails, (30.0, 200.0), (0.05, 0.30), FFC["Z0"], FFC["LEN"]):
        nd += 1
        body = MODELS + f"""
VCC vcc 0 {v}
VG g 0 {bit_pwl(bits, v, t_r=6e-9)}
RD g dout {rd}
{tline('ret', 'dout', 'jl', 120, lr * PCBZ['TD_PER_M'])}
{tline('ffl', 'jl', 'c1', zf, lf * FFC['TD_PER_M'], lf * FFC['R_PER_M'])}
{tline('pc', 'c1', 'c3', 120, (L_ret + L_out) * PCBZ['TD_PER_M'])}
{tline('ffr', 'c3', 'hr', zf, lf * FFC['TD_PER_M'], lf * FFC['R_PER_M'])}
{tline('hp', 'hr', 'din', 120, 0.15 * PCBZ['TD_PER_M'])}
{led_input('din', 'vcc', 'led')}
"""
        res = spice("B_direct", body, ["v(din)"], tran="0.5n 8.2u")
        ok, d = analyse_bits(res["t"], res["v(din)"], v, bits, "B2")
        o = max(d["vmax"] - v, -d["vmin"])
        okd += ok and o < 0.5
        worst_d = max(worst_d, o)
    rep(f"- (comparison only) wired straight through without gate 2: {okd}/{nd} corners clean, worst over/undershoot "
        f"{worst_d:.2f} V at the LED - why the hop is re-driven on the controller.")


# ------------------------------------------------------------------ C: I2C
def sim_i2c():
    rep("\n## C. I2C (GP14 SDA / GP15 SCL, 4.7k to 3.3 V on the board)\n")
    rep("Open-drain low side 25-100 ohm (RP2040 4 mA drive: VOL <= 0.4 V at 4 mA). Module pull-ups in parallel; "
        "bus C = pins + traces + Qwiic cable + modules. Rise time 30 % -> 70 % (I2C spec definition).\n")
    rows = []
    for rx, cb in itertools.product((None, 10e3, 4.7e3, 2.2e3), (30e-12, 60e-12, 100e-12, 200e-12)):
        rpar = 4.7e3 if rx is None else 1 / (1 / 4.7e3 + 1 / rx)
        body = f"""
VDD vdd 0 3.3
RPU vdd sda {rpar}
CB sda 0 {cb}
SW sda 0 ctl 0 SWMOD
VCTL ctl 0 PULSE(1 0 1u 1n 1n 20u 40u)
.model SWMOD SW(RON=60 ROFF=1e9 VT=0.5 VH=0.1)
"""
        res = spice("C_i2c", body, ["v(sda)"], tran="2n 6u")
        t, v = res["t"], res["v(sda)"]
        c30 = [c[0] for c in crossings(t, v, 0.3 * 3.3) if c[1] > 0]
        c70 = [c[0] for c in crossings(t, v, 0.7 * 3.3) if c[1] > 0]
        tr = (c70[0] - c30[0]) if c30 and c70 else float("inf")
        vol = float(v[(t > 0.5e-6) & (t < 0.9e-6)].mean())
        isink = 3.3 / rpar
        rows.append((rx, cb, rpar, tr, vol, isink))
    rep("| extra pull-up | bus C | total R | rise time | VOL | sink current | 100 kHz | 400 kHz |")
    rep("|---|---|---|---|---|---|---|---|")
    for rx, cb, rpar, tr, vol, isink in rows:
        rep(f"| {'none' if rx is None else f'{rx / 1e3:.1f}k'} | {cb * 1e12:.0f} pF | {rpar / 1e3:.2f}k | {tr * 1e9:.0f} ns | "
            f"{vol:.3f} V | {isink * 1e3:.2f} mA | {'ok' if tr <= 1000e-9 and vol <= 0.4 else 'no'} | "
            f"{'ok' if tr <= 300e-9 and vol <= 0.4 and isink <= 3e-3 else 'no'} |")
    base = [r for r in rows if r[0] is None and r[1] <= 100e-12]
    verdict(all(r[3] <= 300e-9 for r in base if r[1] <= 60e-12),
            "board pull-ups alone: 400 kHz rise time met up to 60 pF of bus (OLED + short Qwiic run)")
    verdict(all(r[3] <= 1000e-9 for r in base), "board pull-ups alone: 100 kHz met up to 100 pF")
    verdict(all(r[4] <= 0.4 and r[5] <= 3e-3 for r in rows if r[0] in (None, 10e3, 4.7e3)),
            "VOL <= 0.4 V and sink <= 3 mA (I2C Fm limit) with one extra 4.7k/10k module pull-up")
    verdict(all(r[5] <= 3e-3 for r in rows), "even a module with its own 2.2k pull-ups keeps the sink current under "
            "the 3 mA I2C limit", warn_only=True)
    return rows


# ------------------------------------------------------------------ D: PS/2 stick on the I2C pins
def sim_ps2():
    rep("\n## D. PS/2 pointing stick on the I2C header (clock/data on GP14/GP15)\n")
    rep("RP2040 GPIO is not 5 V tolerant (abs max IOVDD + 0.5 V = 3.8 V). The board pulls up to 3.3 V; "
        "a stick powered from 5 V may add its own pull-ups to 5 V.\n")
    res_rows = []
    for vtp, rtp in itertools.product((5.0, 3.3), (None, 10e3, 4.7e3)):
        body = MODELS + f"""
VIO vio 0 3.3
VTP vtp 0 {vtp}
RPU vio pin 4.7k
{'RTP vtp pin ' + str(rtp) if rtp else ''}
DCL pin vio DCLAMP
RIN pin 0 10meg
"""
        r = spice("D_ps2", body, ["v(pin)", "i(vio)"], op=True)
        vpin = r.get("v(pin)")
        res_rows.append((vtp, rtp, vpin))
        rep(f"- stick at {vtp:.1f} V, stick pull-up {('none' if rtp is None else f'{rtp / 1e3:.1f}k')}: "
            f"idle pin voltage {vpin:.2f} V {'(over 3.8 V abs max)' if vpin > RP['VABS'] else ''}")
    verdict(all(v <= RP["VABS"] for vt, rt, v in res_rows if rt is None or vt == 3.3),
            "a stick without its own pull-ups, or powered from 3.3 V, keeps the pins within the RP2040 limits")
    verdict(all(v <= RP["VABS"] for vt, rt, v in res_rows),
            "a 5 V stick with its own pull-ups lifts the pins past 3.8 V: power it from 3.3 V (VCC pin) or remove "
            "its pull-ups; with a 5 V CMOS stick, 3.3 V highs are also below its 0.7 x 5 V = 3.5 V input threshold",
            warn_only=True)
    return res_rows


# ------------------------------------------------------------------ E: power
def sim_power(facts):
    rep("\n## E. Power: USB hot-plug, LED rail drop, brightness cap\n")
    _, length, res, vias = facts
    r5 = res.get("+5V_LED", 0)
    rv = res.get("VBUS", 0)
    rg = res.get("GND", 0)
    rep(f"Routed copper (whole net, 0.4 mm power tracks): +5V_LED {length.get('+5V_LED', 0):.0f} mm / {r5 * 1e3:.0f} mohm, "
        f"VBUS {length.get('VBUS', 0):.0f} mm / {rv * 1e3:.0f} mohm, GND {length.get('GND', 0):.0f} mm / {rg * 1e3:.0f} mohm "
        f"(upper bounds: whole-net length in series).")

    # E1: hot-plug inrush
    rep("\n**E1 hot-plug.** Host port: 5.0 V regulator behind 0.1 ohm / 5 uH (it can't react in microseconds) "
        "with the 120 uF the USB 2.0 spec requires per port; 2 m cable 0.25 ohm / 2 uH. Pico: Schottky into ~10 uF on VSYS "
        "+ 30 mA. RGB rail: MF-RHT050 (0.5-1.17 ohm cold), C2 (ESR 0.3 ohm), 84 x 100 nF at the LEDs behind the "
        "jumpers. USB 2.0 sizes the host bulk for a device of <= 10 uF so that its VBUS droops < 330 mV for the other "
        "devices on it; the USB-IF inrush test allows 50 uC in the first 100 us.\n")
    rows = []
    for c2, rf, populated in [("ref", 0, False), (None, 0.5, False)] + [(c, r, True) for c in (100e-6, 22e-6, 10e-6, 0.0) for r in (0.5, 1.17)]:
        body = MODELS + f"""
VH hsrc 0 5.0
RHS hsrc hs1 0.1
LHS hs1 hport 5u
CH hport 0 120u IC=5.0
SATT hport cab sw 0 SWA
VSW sw 0 PULSE(0 1 10u 10n 10n 1 2)
.model SWA SW(RON=0.01 ROFF=1e9 VT=0.5 VH=0.1)
VI cab cab2 0
RCAB cab2 cl 0.25
LCAB cl vbus 2u
DPICO vbus vsys DSCH
CPICO vsys 0 10u
RPICO vsys 0 {5.0 / 0.03:.1f}
""" if c2 != "ref" else MODELS + f"""
VH hsrc 0 5.0
RHS hsrc hs1 0.1
LHS hs1 hport 5u
CH hport 0 120u IC=5.0
SATT hport cab sw 0 SWA
VSW sw 0 PULSE(0 1 10u 10n 10n 1 2)
.model SWA SW(RON=0.01 ROFF=1e9 VT=0.5 VH=0.1)
VI cab cab2 0
RCAB cab2 cl 0.25
LCAB cl vbus 2u
CREF vbus 0 10u
RREF vbus 0 44
"""
        if populated:
            body += f"RF vbus rail {rf}\nCD rail 0 0.1u\n"
            if c2:
                body += f"C2 rail c2e {c2}\nRESR c2e 0 0.3\n"
            body += f"RFFC rail halves {FFC['LEN'][1] * FFC['R_PER_M'] / 2 + r5:.4f}\nCLED halves 0 8.4u\n"
        r = spice("E1_inrush", body.replace("CH hport 0 120u IC=5.0", "CH hport 0 120u IC=5.0").replace(
            ".model SWA", ".ic v(hport)=5.0 v(hs1)=5.0\n.model SWA"), ["v(hport)", "v(vbus)", "i(vi)"], tran="20n 400u uic")
        t, vh, ii = r["t"], r["v(hport)"], r["i(vi)"]
        m = t > 10e-6
        droop = 5.0 - float(vh[m].min())
        ipk = float(np.abs(ii[m]).max())
        w = (t >= 10e-6) & (t <= 110e-6)
        q100 = float(np.trapezoid(np.abs(ii[w]), t[w]))
        rows.append((populated, c2, rf, droop, ipk, q100))
    rep("| device | C2 | fuse R | host VBUS droop | peak inrush | charge in 100 us |")
    rep("|---|---|---|---|---|---|")
    for populated, c2, rf, droop, ipk, q in rows:
        dev = "USB limit (10 uF + 44 ohm)" if c2 == "ref" else ("Pico, RGB empty" if not populated else "Pico + RGB")
        rep(f"| {dev} | {'-' if not populated else ('none' if not c2 else f'{c2 * 1e6:.0f} uF')} | "
            f"{rf if populated else '-'} | {droop * 1e3:.0f} mV | {ipk:.1f} A | {q * 1e6:.0f} uC |")
    by = {(p, c, r_): (d, q) for p, c, r_, d, _, q in rows}
    ref = by[(False, "ref", 0)][0]
    e = by[(False, None, 0.5)][0]
    rep(f"\nAbsolute droop depends on the host model; compare against the USB spec-limit device in the same model ({ref * 1e3:.0f} mV).")
    verdict(e <= ref * 1.1, f"RGB empty: the board adds nothing to the Pico's own hot-plug load ({e * 1e3:.0f} mV vs {ref * 1e3:.0f} mV)")
    d10, d100, d0 = by[(True, 10e-6, 0.5)][0], by[(True, 100e-6, 0.5)][0], by[(True, 0.0, 0.5)][0]
    verdict(d10 <= ref * 1.1, f"RGB fitted, C2 = 10 uF: {d10 / ref:.1f}x the spec-limit droop ({d10 * 1e3:.0f} mV). Most of it is "
            f"the halves' 84 x 100 nF (no C2: {d0 / ref:.1f}x); 100 uF would make it {d100 / ref:.1f}x. Typical of RGB "
            f"keyboards; fewer LED decoupling caps on the halves (one per 2-4 LEDs) or a switched LED rail would fix it",
            warn_only=True)

    # E2: DC drop to the far LED and brightness cap
    rep("\n**E2 LED rail at load.** Device VBUS = 4.75 V host minimum - 0.25 ohm cable x total current; then the "
        "polyfuse (R1max 1.17 ohm after a trip, 0.5 ohm new), routed +5V_LED copper, jumper (2 x 5V and 3 x GND "
        f"conductors in parallel, {FFC['LEN'][1] * 1e3:.0f} mm, {FFC['R_PER_M']:.0f} ohm/m), half board rail+return 0.15 ohm (assumed for rev 2 halves).\n")
    rep("| LED current | fuse R | far LED VDD | data high at far LED (HCT VOH) | VIH (0.7 VDD) |")
    rep("|---|---|---|---|---|")
    worst_vdd = 9
    for i_led, rf in itertools.product((0.1, 0.3, 0.45), (0.5, 1.17)):
        i_tot = i_led + 0.06                                  # Pico + OLED + pointing device
        vbus = 4.75 - 0.25 * i_tot - rv * i_tot
        v_ctrl = vbus - rf * i_led - r5 * i_led
        r_ffc = FFC["LEN"][1] * FFC["R_PER_M"] / 2 + FFC["LEN"][1] * FFC["R_PER_M"] / 3
        v_far = v_ctrl - i_led * (r_ffc + 0.15)
        voh = v_ctrl - 6e-3 * 110                             # HCT at 6 mA worst
        rep(f"| {i_led * 1e3:.0f} mA | {rf} | {v_far:.2f} V | {voh:.2f} V | {0.7 * v_far:.2f} V |")
        worst_vdd = min(worst_vdd, v_far)
    verdict(worst_vdd >= 3.7, f"far LED VDD >= 3.7 V (SK6812 MINI-E / WS2812B-2020 minimum) at 450 mA: {worst_vdd:.2f} V")
    # brightness cap
    i_white, i_q, n_led = 36e-3, 0.7e-3, 84
    budget = 0.45 - n_led * i_q
    cap = int(255 * budget / (n_led * i_white))
    rep(f"\nBrightness cap: {n_led} LEDs x {i_white * 1e3:.0f} mA full white + {i_q * 1e3:.1f} mA idle each; the polyfuse holds "
        f"0.5 A and USB gives 0.5 A in total. Keeping the LEDs under 450 mA -> **RGB_MATRIX_MAXIMUM_BRIGHTNESS {cap}** "
        f"(of 255) for full white; colours/effects average lower.")
    return rows, cap


# ------------------------------------------------------------------ F: matrix
def sim_matrix(facts):
    rep("\n## F. Matrix scan (QMK COL2ROW: rows driven low one at a time, columns read with pull-ups)\n")
    segs, length, res, _ = facts
    rows_n = [f"GP{g}" for g in range(0, 6)]
    cols_n = [f"GP{g}" for g in list(range(6, 13)) + list(range(16, 23))]
    Lr = max(length.get(n, 0) for n in rows_n) * 1e-3
    Lc = max(length.get(n, 0) for n in cols_n) * 1e-3
    rep(f"Longest routed row {Lr * 1e3:.0f} mm, column {Lc * 1e3:.0f} mm on the controller. Rows are shared by both "
        f"halves (two jumpers); columns go to one half.\n")

    def caps(lf, lh_row, lh_col, cpm, cpp):
        c_row = RP["CIN"] + Lr * 1e3 * cpp + 2 * (lf * cpm + lh_row * 1e3 * cpp)
        c_col = RP["CIN"] + Lc * 1e3 * cpp + lf * cpm + lh_col * 1e3 * cpp
        return c_row, c_col

    # F1 low level + timing
    rep("**F1 key read and recovery.** One key pressed (1N4148), row driven by GPIO 50/170 ohm, pull-ups 50/80k, "
        f"jumper {LEN_TXT}, half row trace 120/250 mm, column 80/200 mm, cable C 30/60 pF/m, PCB 0.05/0.1 pF/mm.\n")
    worst = dict(vlow=0, t_sel=0, t_rec=0)
    corners = 0
    for rdrv, rpu, lf, (lhr, lhc), cpm, cpp in itertools.product(RP["R_DRV"], RP["RPU"], FFC["LEN"], [(0.12, 0.08), (0.25, 0.20)],
                                                                FFC["C_PER_M"], PCBZ["C_PER_MM"]):
        corners += 1
        c_row, c_col = caps(lf, lhr, lhc, cpm, cpp)
        body = MODELS + f"""
VIO vio 0 3.3
* row: GPIO output low during the strobe, input + pull-up after (QMK unselect = input high)
VR rdrv 0 PULSE(3.3 0 1u 3n 3n 5u 100u)
SR rdrv rowd rctl 0 SWR
VRC rctl 0 PULSE(0 1 0.999u 1n 1n 5.002u 100u)
.model SWR SW(RON={rdrv} ROFF=1e12 VT=0.5 VH=0.05)
RPR vio row {rpu}
CR row 0 {c_row}
RRW rowd row 1m
* pressed key: column -> diode -> row (anode at the column)
D1 col row D1N4148
RPC vio col {rpu}
CC col 0 {c_col}
"""
        r = spice("F1_scan", body, ["v(col)", "v(row)"], tran="2n 40u")
        t, vc = r["t"], r["v(col)"]
        on = (t > 3e-6) & (t < 5.9e-6)
        vlow = float(vc[on].max())
        dn = [c[0] for c in crossings(t, vc, RP["VIL"]) if c[1] < 0]
        up = [c[0] for c in crossings(t, vc, RP["VIH"]) if c[1] > 0 and c[0] > 6e-6]
        t_sel = (dn[0] - 1e-6) if dn else float("inf")
        t_rec = (up[0] - 6.0e-6) if up else float("inf")
        if vlow > worst["vlow"]:
            worst["vlow"] = vlow
        if t_sel > worst["t_sel"]:
            worst["t_sel"] = t_sel
        if t_rec > worst["t_rec"]:
            worst["t_rec"] = t_rec
            worst["rec_res"] = r
            worst["rec_c"] = (c_row, c_col, rpu)
    rep(f"{corners} corners.")
    verdict(worst["vlow"] < RP["VIL"] - 0.2, f"pressed key reads low: worst column level {worst['vlow']:.2f} V "
            f"(VIL {RP['VIL']} V, >= 0.2 V margin)")
    verdict(worst["t_sel"] < QMK["SELECT"], f"column falls below VIL {worst['t_sel'] * 1e9:.0f} ns after the row is selected "
            f"(QMK samples ~{QMK['SELECT'] * 1e9:.0f} ns later)")
    verdict(worst["t_rec"] < QMK["IO_DELAY"] * 0.5, f"column back above VIH {worst['t_rec'] * 1e6:.1f} us after unselect "
            f"(QMK waits MATRIX_IO_DELAY = {QMK['IO_DELAY'] * 1e6:.0f} us after a row with a key down; 2x margin required)")
    plot_wave(worst["rec_res"], ["v(row)", "v(col)"], "F1_scan_worst.png", "Matrix: slowest recovery corner",
              hlines=[(RP["VIH"], "VIH"), (RP["VIL"], "VIL")])

    # F2 crosstalk
    rep("\n**F2 crosstalk.** Idle columns are high-impedance inputs (pull-up only), and so are the rows that are not "
        "being strobed (QMK's default unselect = input with pull-up). A fast edge next to either couples in. "
        "A column fails if it drops below VIH; an idle row fails if it drops so far that a pressed key on it "
        "would drag its column below VIH (row + 0.4 V diode drop < VIH). Aggressor edges 3 ns (GPIO), "
        "5 ns (buffer / LED output). Victims at their lowest capacitance (shortest cable and half traces) "
        "and the stiffest 80k pull-up.\n")
    pairs = coupled_runs(segs)
    # the RGB data nets (compose/controller/rev2.py), each by what drives it:
    #   RGB_BUF, RGB_HOP_BUF   a 74HCT125 output, before its 330 ohm
    #   RGB_L_IN, RGB_R_IN     the same, after the 330 ohm
    #   RGB_L_RET              the left half's last LED output, back through its jumper
    #   RGB_HOP_IN             that, after the 220 ohm (left out here: the edge is the LED's 5 ns either way)
    rgb_kind = {"RGB_BUF": "led", "RGB_HOP_BUF": "led", "RGB_L_IN": "rgb", "RGB_R_IN": "rgb",
                "RGB_L_RET": "led", "RGB_HOP_IN": "led"}
    agg_nets = set(rows_n) | set(rgb_kind) | {"GP13", "GP14", "GP15", "GP26", "GP27", "GP28"}
    vic_nets = set(cols_n) | set(rows_n) | {"GP14", "GP15"}
    stale = sorted(n for n in agg_nets | vic_nets if n not in length)
    verdict(not stale, "every net named in the crosstalk sweep has tracks on the routed board"
            + (f": not found {stale} (renamed in compose/controller/rev2.py?)" if stale else ""))
    c_col_min = RP["CIN"] + Lc * 1e3 * PCBZ["C_PER_MM"][0] + FFC["LEN"][0] * FFC["C_PER_M"][0] + 0.08e3 * PCBZ["C_PER_MM"][0]
    c_row_min = RP["CIN"] + Lr * 1e3 * PCBZ["C_PER_MM"][0] + 2 * (FFC["LEN"][0] * FFC["C_PER_M"][0] + 0.12e3 * PCBZ["C_PER_MM"][0])
    cases = []
    # jumper neighbours from the slot table: COL6 (11) | ROW0 (12) and ROW5 (17) | RGB data back (18);
    # the data to the half (3) sits between 5 V and GND
    for lf in FFC["LEN"]:
        cm = lf * FFC["CM_PER_M"][1]
        cvc = RP["CIN"] + Lc * 1e3 * PCBZ["C_PER_MM"][0] + lf * FFC["C_PER_M"][0] + 0.08e3 * PCBZ["C_PER_MM"][0]
        cvr = RP["CIN"] + Lr * 1e3 * PCBZ["C_PER_MM"][0] + 2 * (lf * FFC["C_PER_M"][0] + 0.12e3 * PCBZ["C_PER_MM"][0])
        cases.append((f"jumper {lf * 1e3:.0f} mm: ROW0 (12) -> COL6 (11)", "gpio", "col", cm, cvc))
        cases.append((f"jumper {lf * 1e3:.0f} mm: LED data back (18) -> idle ROW5 (17)", "led", "row", cm, cvr))
    for (a, b), (L, gap) in pairs.items():
        for agg, vic in ((a, b), (b, a)):
            if agg in agg_nets and vic in vic_nets and agg != vic and not (agg in rows_n and vic in rows_n):
                cm = L * PCBZ["CM_PER_MM_AT"](gap)
                kind = rgb_kind.get(agg, "gpio")
                vk = "row" if vic in rows_n else "col"
                cases.append((f"board {agg} -> {vic} ({L:.1f} mm @ {gap:.2f} mm)", kind, vk, cm,
                              c_row_min if vk == "row" else c_col_min))
    worst = {"col": (9, None), "row": (9, None)}
    rep("| aggressor -> victim | Cm | victim C | dip | level at QMK's sample | min level | limit |")
    rep("|---|---|---|---|---|---|---|")
    rows_out = []
    for name, kind, vk, cm, c_vic in cases:
        swing, tr, rdrv = {"rgb": (5.25, 5e-9, 30 + 330), "led": (5.25, 5e-9, 30), "gpio": (3.3, 3e-9, 50)}[kind]
        body = f"""
VIO vio 0 3.3
VA a0 0 PULSE({swing} 0 1u {tr} {tr} 2u 10u)
RA a0 agg {rdrv}
CA agg 0 10p
CM agg vic {cm}
RPU vio vic {RP['RPU'][1]}
CV vic 0 {c_vic}
DCL vic vio DCLAMP
DCG 0 vic DCLAMP
""" + MODELS
        r = spice("F2_xtalk", body, ["v(vic)"], tran="0.5n 4u")
        t, v = r["t"], r["v(vic)"]
        vmin = float(v[(t > 0.9e-6) & (t < 3e-6)].min())
        vs = float(np.interp(1e-6 + QMK["SELECT"], t, v))
        limit = RP["VIH"] if vk == "col" else RP["VIH"] - 0.4
        margin = vmin - limit
        rows_out.append((margin, name, cm, c_vic, vmin, vs, limit))
        if margin < worst[vk][0]:
            worst[vk] = (margin, name, vmin, limit)
    for margin, name, cm, c_vic, vmin, vs, limit in sorted(rows_out)[:14]:
        rep(f"| {name} | {cm * 1e12:.2f} pF | {c_vic * 1e12:.1f} pF | {3.3 - vmin:.2f} V | {vs:.2f} V | {vmin:.2f} V | {limit:.1f} V |")
    rep(f"\n{len(cases)} aggressor/victim pairs simulated (board pairs from the routed copper: parallel within 14 deg, "
        f"edge gap <= 0.6 mm); the 14 tightest shown.")
    for vk, lab in (("col", "idle column"), ("row", "idle row")):
        m, name, vmin, limit = worst[vk]
        if name:
            verdict(m > 0, f"worst crosstalk into an {lab}: {name}, minimum {vmin:.2f} V vs {limit:.1f} V limit - no false key")
    return worst


# ------------------------------------------------------------------ plotting
def plot_wave(res, vecs, fname, title, hlines=()):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=120)
    for v in vecs:
        ax.plot(res["t"] * 1e6, res[v], label=v, lw=1.1)
    for y, lab in hlines:
        ax.axhline(y, color="0.5", ls="--", lw=0.8)
        ax.text(res["t"][-1] * 1e6, y, " " + lab, va="center", fontsize=8, color="0.3")
    ax.set_xlabel("time (us)")
    ax.set_ylabel("V")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(SIM, fname))
    plt.close(fig)


def main():
    facts = board_facts()
    rep("# Compose controller rev 2 - circuit simulation (ngspice)\n")
    rep("Models: RP2040 (VIH 2.0 / VIL 0.8 V, pull-ups 50-80k, 4 mA drive <= 170 ohm, abs max 3.8 V), "
        "74HCT125 (VIH 2.0 V, VOH 3.84 V at -6 mA), WS2812B/SK6812 (VIH 0.7 VDD, VIL 0.3 VDD, T0H 250-550, T1H 650-950 ns), "
        "1N4148 (SPICE model), MF-RHT050 (0.5 A hold, 0.5-1.17 ohm), QMK defaults (WS2812 350/900/1250 ns, "
        "MATRIX_IO_DELAY 30 us). Flex jumper, 1.0 mm pitch: Z0 100-180 ohm, 4.8 ns/m, 3 ohm/m, 30-60 pF/m, 10-30 pF/m "
        f"mutual, {LEN_TXT}.")
    sim_rgb_first(facts)
    sim_rgb_hop(facts)
    sim_i2c()
    sim_ps2()
    _, cap = sim_power(facts)
    sim_matrix(facts)
    rep("\n## Summary\n")
    rep(f"{len(FAILS)} failures, {len(WARNS)} warnings.")
    for f in FAILS:
        rep(f"- FAIL: {f}")
    for w in WARNS:
        rep(f"- WARN: {w}")
    open(os.path.join(SIM, "report.md"), "w").write("\n".join(REPORT) + "\n")
    json.dump(dict(fails=FAILS, warns=WARNS, brightness_cap=cap), open(os.path.join(SIM, "summary.json"), "w"), indent=1)
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
