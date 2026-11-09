// node svg2tex.js <in.svg> <out.png> <px_per_unit>   (needs playwright)
// Rasterises a board preview SVG to exactly its viewBox, transparent outside the board: a texture whose pixel
// (0, 0) is the viewBox's top-left corner and whose size is viewBox * px_per_unit (viewBox units: um).
const fs = require('fs');
const {chromium} = require('playwright');
const [inp, out, ppu] = process.argv.slice(2);
(async () => {
  let svg = fs.readFileSync(inp, 'utf8');
  const vb = svg.match(/viewBox="([^"]+)"/)[1].split(/\s+/).map(Number);
  const w = Math.round(vb[2] * +ppu), h = Math.round(vb[3] * +ppu);
  svg = svg.replace(/(<svg[^>]*?)\swidth="[^"]*"/, `$1 width="${w}"`).replace(/(<svg[^>]*?)\sheight="[^"]*"/, `$1 height="${h}"`);
  const b = await chromium.launch({executablePath: process.env.CHROMIUM || undefined});
  const p = await b.newPage({viewport: {width: w, height: h}});
  await p.setContent(`<html><body style="margin:0;background:transparent">${svg}</body></html>`);
  await p.waitForTimeout(300);
  await p.screenshot({path: out, omitBackground: true, clip: {x: 0, y: 0, width: w, height: h}});
  await b.close();
  console.log(JSON.stringify({w, h, viewBox: vb}));
})();
