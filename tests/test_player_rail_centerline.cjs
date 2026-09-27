const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../web/stage_2_player.html'), 'utf8');

function functionBody(name, nextName) {
  const start = html.indexOf(`    function ${name}(`);
  const end = html.indexOf(`    function ${nextName}(`, start);
  assert.ok(start >= 0 && end > start, `extract production ${name} function`);
  return html.slice(start, end);
}

test('straight rail centreline, grid and both train sweeps use one reference path', () => {
  // Regression input: the floor-support polyline drifts laterally even though
  // the manually reviewed tunnel/rail direction is straight along -Y.
  // The test deliberately checks the browser production functions: an
  // estimated floor path must not become the reference rail centreline used
  // to draw the green axis, grid or train clearance sweeps.
  assert.match(html,
    /function straightRailCenterline\(overlay\)[\s\S]*track_centerline_lateral_m[\s\S]*rail_head_vertical_m/,
    'the visual contract must expose its straight, reference-only rail centreline');

  const centrelineStart = html.indexOf('    function straightRailCenterline(');
  const centrelineEnd = html.indexOf('    function buildTrackGrid(', centrelineStart);
  const context = vm.createContext({Number});
  vm.runInContext(html.slice(centrelineStart, centrelineEnd), context);
  const centreline = JSON.parse(JSON.stringify(context.straightRailCenterline({
    placement_in_source_coordinates: {
      forward_start_m: 0, forward_end_m: 200,
      track_centerline_lateral_m: 0, rail_head_vertical_m: 0,
    },
  })));
  assert.deepEqual(centreline.nodes, [
    {depth_m: 0, x_m: 0, y_m: 0, z_m: 0},
    {depth_m: 200, x_m: 0, y_m: -200, z_m: 0},
  ]);

  const greenAxis = functionBody('renderAutoGradePath', 'renderReferenceProfile');
  const trainSweep = functionBody('renderReferenceProfile', 'renderFloorGrid');
  const grid = functionBody('renderFloorGrid', 'clearCandidateAuditBoxes');

  for (const [name, source] of [['green axis', greenAxis], ['train sweep', trainSweep], ['grid', grid]]) {
    assert.match(source, /straightRailCenterline\(manifest\.visualization_overlay\)/,
      `${name} must use the same configured rail centreline`);
  }

  assert.doesNotMatch(greenAxis, /ACTIVE_ASSUMED_AUTO_TRACK/,
    'the green rail axis must not visualise floor-support drift as a rail');
  assert.doesNotMatch(trainSweep, /ACTIVE_ASSUMED_AUTO_TRACK/,
    'the train sweep must not bend with floor-support drift');
  assert.doesNotMatch(grid, /ACTIVE_ASSUMED_AUTO_TRACK/,
    'the grid must not bend with floor-support drift');
});
