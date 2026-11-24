// node html2png.js <page.html> <out.png> <width> <height>   (needs playwright; the page's images load from its folder)
const {chromium} = require('playwright');
const path = require('path');
const [inp, out, w, h] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch({executablePath: process.env.CHROMIUM || undefined});
  const p = await b.newPage({viewport: {width: +w, height: +h}});
  await p.goto('file://' + path.resolve(inp));
  await p.waitForFunction(() => [...document.images].every(i => i.complete && i.naturalWidth > 0), null, {timeout: 120000});
  await p.waitForTimeout(300);
  await p.screenshot({path: out});
  await b.close();
})();
