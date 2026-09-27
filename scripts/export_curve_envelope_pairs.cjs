'use strict';
// Exports the already accepted AutoRails pairs as plain CSV for C++ parity checks.
// It never changes source XYZ, profile, margin or AutoRails configuration.
const fs = require('node:fs');
const path = require('node:path');
const AutoRails = require('../web/stage_2_auto_rails.js');
const config = require('../web/stage_2_auto_rails_config.json');

const [xyzfPath, outputPath] = process.argv.slice(2);
if (!xyzfPath || !outputPath) {
  throw new Error('usage: export_curve_envelope_pairs.cjs FRAME.xyzf OUTPUT.csv');
}
const source = fs.readFileSync(path.resolve(xyzfPath));
if (source.byteLength % 12) throw new Error('xyzf must contain float32 XYZ triplets');
const before = Buffer.from(source);
const raw = new Float32Array(source.buffer, source.byteOffset, source.byteLength / 4);
const result = AutoRails.detect(raw, config);
if (!before.equals(source)) throw new Error('AutoRails mutated source XYZ');
if (!result.rail_pairs || result.rail_pairs.length < 2) {
  throw new Error(`curve axis unavailable: ${result.reason || result.status}`);
}
const csv = result.rail_pairs.map(pair => [pair.source_s_m, ...pair.left_xyz, ...pair.right_xyz].join(',')).join('\n') + '\n';
fs.writeFileSync(path.resolve(outputPath), csv, 'utf8');
console.log(JSON.stringify({status: result.status, rail_pairs: result.rail_pairs.length, source_mutations: 0}));
