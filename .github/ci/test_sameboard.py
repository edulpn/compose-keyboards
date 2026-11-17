"""Checks sameboard.py on small boards: python3 .github/ci/test_sameboard.py (exit 1 on a wrong verdict)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import sameboard  # noqa: E402

PAD1 = '(pad "1" smd rect (at 0 1) (size 1 2) (layers "F.Cu") (net 1 "A") (tstamp {i}))'
PAD2 = '(pad "2" smd rect (at 0 -1) (size 1 2) (layers "F.Cu") (net 2 "B") (tstamp {i}))'
FP = '(footprint "lib:part" (layer "F.Cu") (tstamp {i}) (at 10 20) (fp_text reference "D1" (at 0 0) (layer "F.SilkS") (tstamp {i})) {pads})'
SEG = '(segment (start 1 1) (end 5 1) (width 0.25) (layer "F.Cu") (net 1) (tstamp {i}))'
VIA = '(via (at 5 1) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1) (tstamp {i}))'
ZONE = '(zone (net 0) (net_name "") (layer "F.Cu") (tstamp {i}) (polygon (pts (xy 0 0) (xy 9 0) (xy 9 9))))'
NETS = '(net 0 "") (net 1 "A") (net 2 "B")'


def board(*parts, ids="a"):
    return "(kicad_pcb (version 20221018) " + " ".join(p.replace("{i}", f"{ids}{n}") for n, p in enumerate(parts)) + ")"


def fp(pads=PAD1 + " " + PAD2, **kw):
    out = FP.replace("{pads}", pads)
    for k, v in kw.items():
        out = out.replace(k, v)
    return out


BASE = board(NETS, fp(), SEG, VIA, ZONE)
# (what the second board is, the same board?)
CASES = [
    ("the same file", BASE, True),
    ("new ids on everything", board(NETS, fp(), SEG, VIA, ZONE, ids="b"), True),
    ("the items saved in another order", board(ZONE, VIA, NETS, SEG, fp(), ids="c"), True),
    ("a part's pads saved in another order", board(NETS, fp(PAD2 + " " + PAD1), SEG, VIA, ZONE, ids="d"), True),
    ("other spacing and line breaks", BASE.replace(") (", ")\n   ("), True),
    ("a track's end moved", board(NETS, fp(), SEG.replace("(end 5 1)", "(end 5 1.1)"), VIA, ZONE), False),
    ("a track on the other face", board(NETS, fp(), SEG.replace("F.Cu", "B.Cu"), VIA, ZONE), False),
    ("a track on another net", board(NETS, fp(), SEG.replace("(net 1)", "(net 2)"), VIA, ZONE), False),
    ("a track twice", board(NETS, fp(), SEG, SEG, VIA, ZONE), False),
    ("no via", board(NETS, fp(), SEG, ZONE), False),
    ("a part moved", board(NETS, fp(**{"(at 10 20)": "(at 10 20.5)"}), SEG, VIA, ZONE), False),
    ("a pad of a part on another net", board(NETS, fp(PAD1 + " " + PAD2.replace('(net 2 "B")', '(net 1 "A")')), SEG, VIA, ZONE), False),
    ("a part's reference changed", board(NETS, fp(**{'"D1"': '"D2"'}), SEG, VIA, ZONE), False),
    ("a zone's corners in another order", board(NETS, fp(), SEG, VIA, ZONE.replace("(xy 9 0) (xy 9 9)", "(xy 9 9) (xy 9 0)")), False),
    ("a net renamed", board(NETS.replace('"B"', '"C"'), fp(), SEG, VIA, ZONE), False),
]


def main():
    bad = 0
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "a.kicad_pcb")
        open(a, "w").write(BASE)
        for name, text, want in CASES:
            b = os.path.join(d, "b.kicad_pcb")
            open(b, "w").write(text)
            got, lines = sameboard.compare(a, b)
            ok = got == want and (got or lines)
            bad += not ok
            print(("ok   " if ok else "FAIL ") + f"{name}: {'the same' if got else 'differs'}")
    print(f"{len(CASES) - bad}/{len(CASES)} verdicts as expected")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
