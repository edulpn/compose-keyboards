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


# ---- routed boards: the router's job, result and log beside each
SEG_B = '(segment (start 0 0) (end 9 9) (width 0.25) (layer "F.Cu") (net 2) (tstamp {i}))'
ROUTED = board(NETS, fp(), SEG, SEG_B, VIA, ZONE)
SES = '(session "b" (routes (network_out (net A (wire (path F.Cu 2500 1 1 5 1)) (via "V" 5 1)) (net "B" (wire (path F.Cu 2500 0 0 9 9))))))'
LOG = """compose: Freerouting 2.5.0 -mp 40 --router.optimizer.max_passes=5
2026-11-18 15:16:04.758 INFO   Freerouting v2.5.0 (build-date: 2026-10-05)
2026-11-18 15:16:11.872 INFO   [J] Auto-routing pass #1 on board 'aa01' was completed in 4.47 seconds with score 779.27 (24 unrouted and 116 violations), using 3.69 CPU seconds
2026-11-18 15:16:13.869 INFO   [J] Auto-routing pass #2 on board 'aa02' was completed in 1.95 seconds with score 988.42 (0 unrouted and 116 violations), using 5.62 CPU seconds
2026-11-18 15:16:16.383 INFO   [J] Optimization stage started on board 'aa03'. Baseline router score: 988.42, optimizer score: 548.95
2026-11-18 15:16:27.766 INFO   [J] Optimizer pass #1 on board 'bb01' was completed in 11.25 seconds with the score of 546.96 (0 unrouted and 116 violations).
2026-11-18 15:16:54.319 INFO   [J] Optimizer pass #2 on board 'bb02' was completed in 26.41 seconds with the score of 553.46 (0 unrouted and 116 violations).
"""
A_MOVED = ROUTED.replace("(end 5 1)", "(end 5 1.2)")                       # net A's track ends elsewhere
SES_A = SES.replace("1 1 5 1))", "1 1 5 1.2))")                             # ... because the router's result says so
LOG_OPT = LOG.replace("'bb02'", "'bb99'").replace("553.46", "552.68")       # the optimizer's second pass ended elsewhere
# (what the second run is: board, job, result, log; the verdict; a word its lines must have)
RUNS = [
    ("the same board, job and log", (ROUTED, "job", SES, LOG), "same", "handed the same job"),
    ("the optimizer ended elsewhere and net A's tracks with it", (A_MOVED, "job", SES_A, LOG_OPT), "routing", "optimizer pass 2"),
    ("the same, but the track that differs is on a net the router left alone",
     (ROUTED.replace("(end 9 9)", "(end 9 8)"), "job", SES_A, LOG_OPT), "differs", "tracks differ on B"),
    ("the same, and a part moved too", (A_MOVED.replace("(at 10 20)", "(at 10 20.5)"), "job", SES_A, LOG_OPT), "differs", "more than its tracks"),
    ("the router ended on the same board, the board made from it differs", (A_MOVED, "job", SES, LOG), "differs", "made after it"),
    ("the router routed another way", (A_MOVED, "job", SES_A, LOG.replace("'aa02'", "'aa77'")), "differs", "from auto-routing pass 2"),
    ("another job", (A_MOVED, "job 2", SES_A, LOG_OPT), "differs", "not handed the same job"),
    ("the same job, the router called another way", (A_MOVED, "job", SES_A, LOG_OPT.replace("max_passes=5", "max_passes=3")), "differs", "called another way"),
    ("a log from before the call was written down", (A_MOVED, "job", SES_A, LOG_OPT.split("\n", 1)[1]), "differs", "cannot be told"),
    ("a log with no passes in it", (A_MOVED, "job", SES_A, LOG_OPT.split("\n")[0] + "\n"), "differs", "does not show its passes"),
    ("the same board from another job", (ROUTED, "job 2", SES, LOG), "same", "not handed the same job"),
]


def write(folder, pcb, dsn, ses, log):
    os.makedirs(folder, exist_ok=True)
    for ext, text in ((".kicad_pcb", pcb), (".dsn", dsn), (".ses", ses), ("_freerouting.log", log)):
        open(os.path.join(folder, "b" + ext), "w").write(text)
    return os.path.join(folder, "b.kicad_pcb")


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
        was = write(os.path.join(d, "was"), ROUTED, "job", SES, LOG)
        for n, (name, run, want, word) in enumerate(RUNS):
            verdict, heads, lines = sameboard.judge(was, write(os.path.join(d, f"now{n}"), *run), "b")
            ok = verdict == want and word in " ".join(heads + lines)
            bad += not ok
            print(("ok   " if ok else "FAIL ") + f"{name}: {verdict}" + ("" if ok else f" {heads + lines}"))
        # a board with no router files beside it (the jumper): compared as before, no word about a job
        verdict, heads, lines = sameboard.judge(a, was, "b")
        ok = verdict == "differs" and len(heads) == 1
        bad += not ok
        print(("ok   " if ok else "FAIL ") + f"no router files beside one of them: {verdict}")
    n = len(CASES) + len(RUNS) + 1
    print(f"{n - bad}/{n} verdicts as expected")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
