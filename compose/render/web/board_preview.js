// node board_preview.js <gerber_dir> <out_prefix>
// Realistic top/bottom SVGs from the fab Gerbers: black mask, white silk, HASL (silver) copper.
const fs = require('fs');
const path = require('path');
const pcbStackup = require('pcb-stackup');
const [dir, outPrefix] = process.argv.slice(2);
const files = fs.readdirSync(dir).filter(f => /\.(gtl|gbl|gts|gbs|gto|gbo|gtp|gbp|gm1|drl)$/i.test(f) && !/drl_map/.test(f));
const layers = files.map(f => ({ filename: f, gerber: fs.createReadStream(path.join(dir, f)) }));
const color = {
  fr4: '#3a3324', cu: '#b8b8b0', cf: '#d9d9d2', sm: 'rgba(14, 16, 16, 0.93)', ss: '#f4f4f0', sp: 'rgba(0,0,0,0)', out: '#000'
};
pcbStackup(layers, { color, outlineGapFill: 0.05 }).then(s => {
  fs.writeFileSync(outPrefix + '_top.svg', s.top.svg);
  fs.writeFileSync(outPrefix + '_bottom.svg', s.bottom.svg);
  console.log('preview', outPrefix);
}).catch(e => { console.error(e); process.exit(1); });
