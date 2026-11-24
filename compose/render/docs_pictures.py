"""
Rev 2 doc pictures:  python3 -m compose docs-pictures OUTDIR    (needs node + playwright; run gasket-render first)

Writes the pictures the docs show into OUTDIR/docs-pictures/, under the paths they have in the repository: copy
that folder over the repository's root to update them. They come from gasket-render's views (OUTDIR/png) and from
board previews of the routed boards' Gerbers (board_preview.js; the half boards in OUTDIR, the controller in
CTRL_OUT, default out/controller):

  docs/images/controller_rev2_top.png, _bottom.png       the controller's faces
  docs/images/controller_rev2_parts_underside.png        render r2_17_controller_bottom
  layouts/<layout>/images/rev2_hero.png                  render r2_01_hero
  layouts/<layout>/images/rev2_gasket.png                render r2_06_gasket_exploded
  layouts/<layout>/images/rev2_boards_in_case.png        render r2_14_boards_plates_off
  layouts/<layout>/images/rev2_assembly_underside.png    render r2_11_assembly_underside
  layouts/<layout>/images/rev2_half_boards.png           the four half boards' bottom faces, two by two
  layouts/<layout>/images/rev2_half_hotswap_rgb_bottom.png
  layouts/<layout>/images/rev2_half_rgb_closeup.png      one key of the hotswap RGB board's bottom face, 40 x 30 mm
                                                         round the LED nearest the middle that has a capacitor
"""
from compose import must
import os
import re
import sys
import shutil
import subprocess
from compose import outputs
from compose import params as PR
from compose.render import gasket as R

OUT = sys.argv[1] if len(sys.argv) > 1 else "out_r2t"
DOCS = os.path.join(OUT, "docs-pictures")
WORK = os.path.join(OUT, "docs-pictures-work")
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
CTRL = os.path.join(outputs.controller(), "pcb")
HALF = os.path.join(OUT, "pcb")
LAYOUT_IMAGES = os.path.join("layouts", PR.LAYOUT, "images")

RENDERS = {                       # doc picture: gasket-render view
    os.path.join("docs", "images", "controller_rev2_parts_underside.png"): "r2_17_controller_bottom",
    os.path.join(LAYOUT_IMAGES, "rev2_hero.png"): "r2_01_hero",
    os.path.join(LAYOUT_IMAGES, "rev2_gasket.png"): "r2_06_gasket_exploded",
    os.path.join(LAYOUT_IMAGES, "rev2_boards_in_case.png"): "r2_14_boards_plates_off",
    os.path.join(LAYOUT_IMAGES, "rev2_assembly_underside.png"): "r2_11_assembly_underside",
}
HALVES = (("hotswap · plain", "half_rev2_hotswap"), ("solder · plain", "half_rev2_solder"),
          ("hotswap · RGB", "half_rev2_hotswap_rgb"), ("solder · RGB", "half_rev2_solder_rgb"))
CLOSEUP_MM = (40.0, 30.0)         # the close-up's window on the board, 840 x 630 px


def node(script, *args):
    subprocess.run(["node", os.path.join(WEB, script)] + [str(a) for a in args], check=True, env=R._node_env())


def preview(gerbers, name):
    """Top and bottom SVGs of a board from its Gerbers: WORK/<name>_top.svg, _bottom.svg."""
    must(os.path.isdir(gerbers), f"no Gerbers at {gerbers}: build the board first")
    pre = os.path.join(WORK, name)
    node("board_preview.js", gerbers, pre)
    return pre + "_top.svg", pre + "_bottom.svg"


def dest(rel):
    p = os.path.join(DOCS, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def closeup_svg(svg, board):
    """The board's bottom-face SVG with its viewBox narrowed to one key: centred on the bottom-face LED nearest a
    bottom-face capacitor, taking the capacitor nearest the middle of the board."""
    import pcbnew
    b = pcbnew.LoadBoard(board)
    mm = pcbnew.ToMM
    at = lambda fp: (mm(fp.GetPosition().x), mm(fp.GetPosition().y))
    back = [fp for fp in b.GetFootprints() if fp.GetLayer() == pcbnew.B_Cu]
    caps = [fp for fp in back if re.fullmatch(r"C\d+B", fp.GetReference())]
    leds = [fp for fp in back if len(fp.Pads()) == 4 and not re.match(r"(C|D|J|H|SW)\d", fp.GetReference())]
    must(caps and leds, f"{board}: no capacitor and LED on the bottom face to centre the close-up on")
    bb = b.GetBoardEdgesBoundingBox()
    mid = (mm(bb.GetCenter().x), mm(bb.GetCenter().y))
    d2 = lambda p, q: (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
    cap = min(caps, key=lambda fp: d2(at(fp), mid))
    led = min(leds, key=lambda fp: d2(at(fp), at(cap)))
    _, _, to_svg = R._svg_map(svg)
    u, v = to_svg(*at(led))
    w, h = CLOSEUP_MM[0] * 1000.0, CLOSEUP_MM[1] * 1000.0
    full = open(svg).read()
    out = os.path.join(WORK, "closeup.svg")
    open(out, "w").write(re.sub(r'viewBox="[^"]+"', f'viewBox="{u - w / 2:.1f} {v - h / 2:.1f} {w:.1f} {h:.1f}"',
                                full, count=1))
    print(f"  close-up round {led.GetReference()} (its capacitor {cap.GetReference()})", flush=True)
    return out


def page(html, out, width, height):
    path = os.path.join(WORK, os.path.basename(out) + ".html")
    open(path, "w").write(html)
    node("html2png.js", path, os.path.abspath(out), width, height)


def main():
    shutil.rmtree(DOCS, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    png = os.path.join(OUT, "png")
    for rel, view in RENDERS.items():
        src = os.path.join(png, view + ".png")
        must(os.path.isfile(src), f"no {src}: run gasket-render first")
        shutil.copy(src, dest(rel))
    top, bottom = preview(os.path.join(CTRL, "controller_rev2_gerbers"), "controller_rev2")
    node("svg2png.js", top, dest(os.path.join("docs", "images", "controller_rev2_top.png")), 1400)
    node("svg2png.js", bottom, dest(os.path.join("docs", "images", "controller_rev2_bottom.png")), 1400)
    bottoms = {name: preview(os.path.join(HALF, name + "_gerbers"), name)[1] for _, name in HALVES}
    node("svg2png.js", bottoms["half_rev2_hotswap_rgb"],
         dest(os.path.join(LAYOUT_IMAGES, "rev2_half_hotswap_rgb_bottom.png")), 1400)
    cells = "".join(
        f'<div class="cell"><h2>{title}<span>{name}</span></h2><img src="{os.path.basename(bottoms[name])}"></div>'
        for title, name in HALVES)
    page(f"""<html><head><style>
      body {{ margin: 0; background: #232428; font-family: 'DejaVu Sans', sans-serif; }}
      .grid {{ display: grid; grid-template-columns: 800px 800px; }}
      .cell {{ height: 632px; display: flex; flex-direction: column; background: #26282c; box-sizing: border-box;
               padding: 0 10px 10px; border: 1px solid #232428; }}
      h2 {{ color: #f2f2f2; font-size: 26px; margin: 22px 14px 14px; }}
      h2 span {{ color: #9a9ca2; font-size: 20px; font-weight: normal; margin-left: 16px; }}
      img {{ flex: 1; min-height: 0; object-fit: contain; }}
    </style></head><body><div class="grid">{cells}</div></body></html>""",
         dest(os.path.join(LAYOUT_IMAGES, "rev2_half_boards.png")), 1600, 1264)
    svg = closeup_svg(bottoms["half_rev2_hotswap_rgb"], os.path.join(HALF, "half_rev2_hotswap_rgb.kicad_pcb"))
    page(f"""<html><body style="margin:0;background:#26282c">
      <img src="{os.path.basename(svg)}" style="display:block;width:840px;height:630px"></body></html>""",
         dest(os.path.join(LAYOUT_IMAGES, "rev2_half_rgb_closeup.png")), 840, 630)
    for root, _, files in sorted(os.walk(DOCS)):
        for f in sorted(files):
            print("  " + os.path.relpath(os.path.join(root, f), DOCS), flush=True)


if __name__ == "__main__":
    main()
