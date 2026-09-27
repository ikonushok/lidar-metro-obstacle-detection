'use strict';
// Emits the JS reference labels for byte-for-byte C++ core parity checks.
const fs = require('node:fs');
const path = require('node:path');
const Geometry = require('../web/stage_2_review_layers.js');
const AutoRails = require('../web/stage_2_auto_rails.js');
const createChecker = require('../web/stage_3_live_envelope.js');
const autoConfig = require('../web/stage_2_auto_rails_config.json');
const liveConfig = require('../web/stage_3_live_envelope_config.json');

const [xyzfPath, outputPath] = process.argv.slice(2);
if (!xyzfPath || !outputPath) throw new Error('usage: export_curve_envelope_labels.cjs FRAME.xyzf OUTPUT.bin');
const source = fs.readFileSync(path.resolve(xyzfPath));
if (source.byteLength % 12) throw new Error('xyzf must contain float32 XYZ triplets');
const before = Buffer.from(source);
const raw = new Float32Array(source.buffer, source.byteOffset, source.byteLength / 4);
const auto = AutoRails.detect(raw, autoConfig);
if (!before.equals(source)) throw new Error('AutoRails mutated source XYZ');
if (auto.rail_pairs.length < 2) throw new Error(`curve axis unavailable: ${auto.reason || auto.status}`);
const manifest = JSON.parse(fs.readFileSync(path.resolve('artefacts/stage_2/player_doubleT_obstacle/manifest.json')));
const axis = Geometry.curveRailAxis(auto.rail_pairs);
const envelope = Geometry.createEnvelope(axis, manifest.visualization_overlay.reference_cross_section,
                                         {left: .5, right: .5, top: .5, bottom: .5});
const checker = createChecker(Geometry);
const result = checker.analyze(raw, envelope, liveConfig,
  {index: 0, header_timestamp_ns: 'cpp-parity', source_frame: 'hesai_lidar'}, 'CURVE_AXIS_SUPPORTED');
fs.writeFileSync(path.resolve(outputPath), Buffer.from(result.labels));
console.log(JSON.stringify({points: raw.length / 3, core: result.counts.core, margin: result.counts.margin,
  outside_reference: result.counts.outside_reference, unknown: result.counts.unknown, source_mutations: 0}));
