'use strict';
const fs = require('node:fs');
const path = require('node:path');
const AutoRails = require('../web/stage_2_auto_rails.js');
const config = require('../web/stage_2_auto_rails_config.json');

const [xyzfPath, cppPairsPath] = process.argv.slice(2);
if (!xyzfPath || !cppPairsPath) throw new Error('usage: compare_auto_rail_pairs.cjs FRAME.xyzf CPP_PAIRS.csv');
const bytes = fs.readFileSync(path.resolve(xyzfPath));
const raw = new Float32Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 4);
const js = AutoRails.detect(raw, config).rail_pairs;
const cpp = fs.readFileSync(path.resolve(cppPairsPath), 'utf8').trim().split('\n').filter(Boolean)
  .map(line => line.split(',').map(Number));
if (js.length !== cpp.length) throw new Error(`pair count JS=${js.length} C++=${cpp.length}`);
for (let index = 0; index < js.length; index++) {
  const expected = [js[index].source_s_m, ...js[index].left_xyz, ...js[index].right_xyz];
  for (let coordinate = 0; coordinate < expected.length; coordinate++) {
    if (expected[coordinate] !== cpp[index][coordinate]) {
      throw new Error(`pair ${index}, coordinate ${coordinate}: JS=${expected[coordinate]} C++=${cpp[index][coordinate]}`);
    }
  }
}
console.log(JSON.stringify({rail_pairs: js.length, exact_numeric_match: true}));
