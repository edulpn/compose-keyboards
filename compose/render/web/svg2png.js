// node svg2png.js <in.svg> <out.png> [width]   (needs playwright)
const {chromium} = require('playwright');
const [inp, out, w] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch({executablePath: process.env.CHROMIUM || undefined});
  const p = await b.newPage({viewport: {width: +(w || 1400), height: 1000}, deviceScaleFactor: 1});
  const svg = require('fs').readFileSync(inp, 'utf8');
  await p.setContent(`<html><body style="margin:0;background:#26282c;display:flex;justify-content:center;align-items:center;height:100vh">
     <div style="width:92%;height:92%;display:flex;justify-content:center;align-items:center">${svg}</div>
     <style>svg{max-width:100%;max-height:100%;width:auto;height:100%}</style></body></html>`);
  await p.waitForTimeout(300);
  await p.screenshot({path: out});
  await b.close();
})();
