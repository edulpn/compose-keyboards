// node shoot.js <base-url> <outdir> '<json list of [name, query-string]>'
const {chromium} = require('playwright');
const [base, outdir, viewsJson] = process.argv.slice(2);
const views = JSON.parse(viewsJson);
(async () => {
  const b = await chromium.launch({executablePath: process.env.CHROMIUM || undefined,
                                   args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader']});
  const p = await b.newPage({viewport: {width: 1600, height: 1000}});
  p.on('pageerror', e => console.log('ERR', e.message));
  for (const [n, q] of views) {
    await p.goto(base + '/view.html?' + q);
    await p.waitForFunction('window.done', {timeout: 300000});
    await p.screenshot({path: outdir + '/' + n + '.png'});
    console.log('shot', n);
  }
  await b.close();
})();
