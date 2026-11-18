"""
The MX switch as a KiCad footprint: the reversible footprint both generations' half boards place, built from
the measurements in params.py. Its geometry without KiCad (the plate's hole, the socket's body, the holes it
drills) is switch.py.
"""
import math
import pcbnew
from compose import params as PR
from compose.pcb.switch import mirror_fp
from compose.pcb.toolbox import add_pad, silk_poly, courtyard, _layers


def switch_fp(board, variant, ref, net_col, net_anode):
    """Reversible MX footprint: every pin also at its mirror image (same net),
    so the switch fits from either face. Built at the origin, orientation 0."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("kb2", f"MX_Reversible_{'Hotswap' if variant == 'hotswap' else 'PCB'}"))
    fp.SetReference(ref)
    fp.SetValue("MX")
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    p1, p2 = PR.MX_PIN1, PR.MX_PIN2
    m1, m2 = mirror_fp(p1), mirror_fp(p2)
    add_pad(fp, "", "npth", "circle", (0, 0), (PR.MX_CENTER_D,) * 2, (PR.MX_CENTER_D,) * 2)
    for sx in (-1, 1):
        add_pad(fp, "", "npth", "circle", (sx * PR.MX_PEG_X, 0), (PR.MX_PEG_D,) * 2, (PR.MX_PEG_D,) * 2)
    if variant == "solder":
        for pos in (p1, m1):
            add_pad(fp, "1", "pth", "circle", pos, (PR.MX_PTH_PAD,) * 2, (PR.MX_PTH_DRILL,) * 2, net=net_anode)
        for pos in (p2, m2):
            add_pad(fp, "2", "pth", "circle", pos, (PR.MX_PTH_PAD,) * 2, (PR.MX_PTH_DRILL,) * 2, net=net_col)
    else:
        d = PR.HS_HOLE_D
        for a, c in ((p1, m2), (p2, m1)):                    # each pin merges with a mirrored one into a slot
            mid = ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2)
            ln = math.dist(a, c)
            ang = -math.degrees(math.atan2(c[1] - a[1], c[0] - a[0]))
            add_pad(fp, "", "npth", "oval", mid, (ln + d, d), (ln + d, d), angle=ang)
        bl = _layers(pcbnew.B_Cu, pcbnew.B_Mask, pcbnew.B_Paste)
        fl = _layers(pcbnew.F_Cu, pcbnew.F_Mask, pcbnew.F_Paste)
        (c2, s2), (c1, s1) = PR.HS_PAD2, PR.HS_PAD1
        # left-half orientation: socket on B; right-half (flipped) orientation: socket on F, mirrored
        add_pad(fp, "2", "smd", "rect", c2, s2, layers=bl, net=net_col)
        add_pad(fp, "1", "smd", "rect", c1, s1, layers=bl, net=net_anode)
        add_pad(fp, "2", "smd", "rect", mirror_fp(c2), s2, layers=fl, net=net_col)
        add_pad(fp, "1", "smd", "rect", mirror_fp(c1), s1, layers=fl, net=net_anode)
    if variant == "solder":
        for lay in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            silk_poly(fp, [(-7, -7), (7, -7), (7, 7), (-7, 7)], lay, 0.1)
    courtyard(fp, -7.5, -7.5, 7.5, 7.5, pcbnew.F_CrtYd)
    return fp
