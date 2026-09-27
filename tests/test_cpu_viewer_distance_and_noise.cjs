'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function loadShowStatusSource() {
  const source = fs.readFileSync(
    path.join(__dirname, '..', 'web', 'stage_4_cpu_player.js'),
    'utf8',
  );
  const start = source.indexOf('function finiteNumber(');
  const end = source.indexOf('async function show(', start);
  const modelTemporalStart = source.indexOf('function backendModelTemporalComponents(');
  assert.notEqual(start, -1, 'production noise filter helpers must exist');
  assert.ok(end > start, 'showStatus() must be followed by show()');
  assert.notEqual(modelTemporalStart, -1, 'production model temporal override must exist');
  return source.slice(start, end) + '\n' + source.slice(modelTemporalStart);
}

function runShowStatus(result, extra = {}) {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) {
      const defaults = {
        'noise-min-points': '22',
        'noise-radius': '0.25',
        'noise-max-axis-span': '1.0',
        'noise-max-axis-distance': '1.20',
        'temporal-required-frames': '2',
        'temporal-near-zone-m': '6',
        'temporal-match-axis-m': '2',
      };
      elements.set(id, {
        className: '',
        textContent: '',
        value: defaults[id] || '',
        checked: id === 'train-moving',
      });
    }
    return elements.get(id);
  };
  const context = {
    $: element,
    Number,
    id: () => 'test-frame',
    manifest: {dataset: 'doubleT_obstacle', frames: Array.from({length: 47}, () => ({}))},
    current: 46,
    result,
    xyz: extra.xyz,
    cache: extra.cache || new Map(),
    componentFilterCache: null,
    controlObstacles: [],
  };
  if (extra.minPoints) element('noise-min-points').value = String(extra.minPoints);
  if (extra.radius) element('noise-radius').value = String(extra.radius);
  if (extra.maxAxisSpan) element('noise-max-axis-span').value = String(extra.maxAxisSpan);
  if (extra.maxAxisDistance) element('noise-max-axis-distance').value = String(extra.maxAxisDistance);
  if (extra.requiredFrames) element('temporal-required-frames').value = String(extra.requiredFrames);
  if (extra.nearZoneM !== undefined) element('temporal-near-zone-m').value = String(extra.nearZoneM);
  if (extra.moving !== undefined) element('train-moving').checked = extra.moving;
  if (extra.matchAxisM) element('temporal-match-axis-m').value = String(extra.matchAxisM);
  vm.runInNewContext(`${loadShowStatusSource()}\nshowStatus();`, context);
  return {status: element('status'), banner: element('obstacle-distance-banner')};
}

test('viewer shows the nearest obstacle distance as a top-left scene banner', () => {
  const {banner, status} = runShowStatus({
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    intrusion_candidate_present: true,
    reportable_intrusion_candidate_present: true,
    core_count: 12,
    reportable_core_count: 12,
    reportable_core_source_indices: [0],
    nearest_reportable_intrusion_source_index: 0,
    nearest_reportable_intrusion_distance_from_source_origin_m: 27.0,
    nearest_intrusion_distance_from_source_origin_m: 27.0,
    rail_pair_count: 8,
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297000000000',
  });

  assert.equal(
    banner.textContent,
    'Препятствие на 27.0 м',
    'distance must be visible in the left-top overlay, not only in the bottom status line',
  );
  assert.match(status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
});

test('viewer does not warn for core returns that backend marks as ignored right-side noise', () => {
  const {status, banner} = runShowStatus({
    status: 'NO_REPORTABLE_INTRUSION_NOISE_IGNORED',
    intrusion_candidate_present: true,
    reportable_intrusion_candidate_present: false,
    core_count: 31,
    reportable_core_count: 0,
    ignored_noise_source_indices: [101, 102, 103, 104],
    nearest_intrusion_distance_from_source_origin_m: 27.0,
    rail_pair_count: 8,
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297100000000',
  });

  assert.doesNotMatch(
    status.textContent,
    /ПРЕДУПРЕЖДЕНИЕ/,
    'noise-only red/core returns must not be counted as an obstacle warning',
  );
  assert.equal(banner.textContent, '', 'noise-only frames must not show an obstacle-distance banner');
});

test('viewer threshold changes reportable core components without backend rerun', () => {
  const result = {
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    core_count: 4,
    core_source_indices: [0, 1, 2, 3],
    margin_count: 0,
    rail_pair_count: 8,
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297200000000',
    noise_filter_config: {min_reportable_core_points: 5, connectivity_radius_m: 0.35},
  };
  const xyz = new Float32Array([
    0.00, -3.80, 0.01,
    0.05, -3.81, 0.02,
    0.10, -3.79, 0.03,
    0.15, -3.80, 0.04,
  ]);

  assert.doesNotMatch(runShowStatus(result, {xyz, minPoints: 5, requiredFrames: 1}).status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
  assert.match(runShowStatus(result, {xyz, minPoints: 4, requiredFrames: 1}).status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
});

test('viewer uses active backend model split instead of old JS thresholds', () => {
  const result = {
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    noise_filter_mode: 'baseline_v3_assist_score',
    core_count: 4,
    core_source_indices: [0, 1, 2, 3],
    reportable_core_count: 4,
    reportable_core_source_indices: [0, 1, 2, 3],
    ignored_noise_source_indices: [],
    nearest_reportable_intrusion_source_index: 0,
    nearest_reportable_intrusion_distance_from_source_origin_m: 12.0,
    margin_count: 0,
    rail_pair_count: 8,
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297250000000',
    noise_filter_config: {min_reportable_core_points: 22, connectivity_radius_m: 0.25},
  };
  const xyz = new Float32Array([
    0.00, -12.00, 0.01,
    0.05, -12.01, 0.02,
    0.10, -11.99, 0.03,
    0.15, -12.00, 0.04,
  ]);

  const {status, banner} = runShowStatus(result, {xyz, minPoints: 22, requiredFrames: 1});

  assert.match(status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
  assert.equal(banner.textContent, 'Препятствие на 12.0 м');
});

test('viewer temporal filter suppresses one-frame backend model candidates', () => {
  const result = {
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    noise_filter_mode: 'baseline_v3_assist_score',
    core_count: 3,
    core_source_indices: [0, 1, 2],
    reportable_core_count: 3,
    reportable_core_source_indices: [0, 1, 2],
    ignored_noise_source_indices: [],
    nearest_reportable_intrusion_source_index: 0,
    nearest_reportable_intrusion_distance_from_source_origin_m: 20.0,
    margin_count: 0,
    rail_pair_count: 3,
    rail_pairs_source_xyz: [
      {source_s_m: 18, left_xyz: [-0.75, -18, 0], right_xyz: [0.75, -18, 0]},
      {source_s_m: 20, left_xyz: [-0.75, -20, 0], right_xyz: [0.75, -20, 0]},
      {source_s_m: 22, left_xyz: [-0.75, -22, 0], right_xyz: [0.75, -22, 0]},
    ],
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297260000000',
    noise_filter_config: {min_reportable_core_points: 22, connectivity_radius_m: 0.25},
  };
  const xyz = new Float32Array([
    0.00, -20.00, 0.80,
    0.04, -20.02, 0.90,
    -0.03, -19.98, 1.00,
  ]);

  const {status, banner} = runShowStatus(result, {xyz, requiredFrames: 2});

  assert.doesNotMatch(
    status.textContent,
    /ПРЕДУПРЕЖДЕНИЕ/,
    'a backend model candidate seen in only one frame must remain unconfirmed',
  );
  assert.equal(banner.textContent, '', 'one-frame model candidates must not show an obstacle banner');
});

test('viewer temporal filter keeps backend model candidates confirmed by a neighbor frame', () => {
  const result = {
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    noise_filter_mode: 'baseline_v3_assist_score',
    core_count: 3,
    core_source_indices: [0, 1, 2],
    reportable_core_count: 3,
    reportable_core_source_indices: [0, 1, 2],
    ignored_noise_source_indices: [],
    nearest_reportable_intrusion_source_index: 0,
    nearest_reportable_intrusion_distance_from_source_origin_m: 20.0,
    margin_count: 0,
    rail_pair_count: 3,
    rail_pairs_source_xyz: [
      {source_s_m: 18, left_xyz: [-0.75, -18, 0], right_xyz: [0.75, -18, 0]},
      {source_s_m: 20, left_xyz: [-0.75, -20, 0], right_xyz: [0.75, -20, 0]},
      {source_s_m: 22, left_xyz: [-0.75, -22, 0], right_xyz: [0.75, -22, 0]},
    ],
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297270000000',
    noise_filter_config: {min_reportable_core_points: 22, connectivity_radius_m: 0.25},
  };
  const xyz = new Float32Array([
    0.00, -20.00, 0.80,
    0.04, -20.02, 0.90,
    -0.03, -19.98, 1.00,
  ]);
  const cache = new Map([
    [45, {
      frame: {header_timestamp_ns: '946687297260000000'},
      result: {...result, header_timestamp_ns: '946687297260000000'},
      xyz,
    }],
  ]);

  const {status, banner} = runShowStatus(result, {xyz, cache, requiredFrames: 2});

  assert.match(status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
  assert.equal(banner.textContent, 'Препятствие на 20.0 м');
});

test('viewer compactness controls keep centered obstacle and suppress elongated side noise', () => {
  const result = {
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    core_count: 20,
    core_source_indices: Array.from({length: 20}, (_, index) => index),
    margin_count: 0,
    rail_pair_count: 4,
    rail_pairs_source_xyz: [
      {source_s_m: 0, left_xyz: [-0.75, 0, 0], right_xyz: [0.75, 0, 0]},
      {source_s_m: 4, left_xyz: [-0.75, -4, 0], right_xyz: [0.75, -4, 0]},
      {source_s_m: 8, left_xyz: [-0.75, -8, 0], right_xyz: [0.75, -8, 0]},
      {source_s_m: 12, left_xyz: [-0.75, -12, 0], right_xyz: [0.75, -12, 0]},
    ],
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297300000000',
  };
  const xyz = new Float32Array([
    0.80, -0.00, 0.00,
    0.80, -0.10, 0.00,
    0.80, -0.20, 0.00,
    0.80, -0.30, 0.00,
    0.80, -0.40, 0.00,
    0.80, -0.50, 0.00,
    0.80, -0.60, 0.00,
    0.80, -0.70, 0.00,
    0.80, -0.80, 0.00,
    0.80, -0.90, 0.00,
    0.20, -5.00, 0.00,
    0.20, -5.04, 0.00,
    0.20, -5.08, 0.00,
    0.20, -5.12, 0.00,
    0.20, -5.16, 0.00,
    0.20, -5.20, 0.00,
    0.20, -5.24, 0.00,
    0.20, -5.28, 0.00,
    0.20, -5.32, 0.00,
    0.20, -5.36, 0.00,
  ]);

  const {status, banner} = runShowStatus(result, {
    xyz,
    minPoints: 10,
    radius: 0.12,
    requiredFrames: 1,
    nearZoneM: 0,
    maxAxisSpan: 1.0,
    maxAxisDistance: 0.70,
  });

  assert.match(status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
  assert.match(status.textContent, /10 возвратов препятствия/);
  assert.equal(banner.textContent, 'Препятствие на 5.0 м');
});

test('viewer temporal confirmation suppresses a one-frame obstacle-sized core component', () => {
  const result = {
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    core_count: 25,
    core_source_indices: Array.from({length: 25}, (_, index) => index),
    margin_count: 0,
    rail_pair_count: 3,
    rail_pairs_source_xyz: [
      {source_s_m: 0, left_xyz: [-0.75, 0, 0], right_xyz: [0.75, 0, 0]},
      {source_s_m: 20, left_xyz: [-0.75, -20, 0], right_xyz: [0.75, -20, 0]},
      {source_s_m: 40, left_xyz: [-0.75, -40, 0], right_xyz: [0.75, -40, 0]},
    ],
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297400000000',
  };
  const coordinates = [];
  for (let index = 0; index < 25; index++) coordinates.push(0.20, -25 - index * 0.01, 0);
  const xyz = new Float32Array(coordinates);

  const {status, banner} = runShowStatus(result, {
    xyz,
    minPoints: 22,
    radius: 0.25,
    requiredFrames: 2,
    nearZoneM: 6,
    maxAxisSpan: 1.0,
    maxAxisDistance: 1.20,
  });

  assert.doesNotMatch(status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
  assert.equal(banner.textContent, '');
});

test('viewer temporal confirmation keeps a matching obstacle in neighboring frames', () => {
  const result = {
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    core_count: 25,
    core_source_indices: Array.from({length: 25}, (_, index) => index),
    margin_count: 0,
    rail_pair_count: 3,
    rail_pairs_source_xyz: [
      {source_s_m: 0, left_xyz: [-0.75, 0, 0], right_xyz: [0.75, 0, 0]},
      {source_s_m: 20, left_xyz: [-0.75, -20, 0], right_xyz: [0.75, -20, 0]},
      {source_s_m: 40, left_xyz: [-0.75, -40, 0], right_xyz: [0.75, -40, 0]},
    ],
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297400000000',
  };
  const coordinates = [];
  for (let index = 0; index < 25; index++) coordinates.push(0.20, -25 - index * 0.01, 0);
  const xyz = new Float32Array(coordinates);
  const cache = new Map([
    [45, {result, xyz, frame: {header_timestamp_ns: '946687297300000000'}}],
  ]);

  const {status, banner} = runShowStatus(result, {
    xyz,
    cache,
    minPoints: 22,
    radius: 0.25,
    requiredFrames: 2,
    nearZoneM: 6,
    maxAxisSpan: 1.0,
    maxAxisDistance: 1.20,
  });

  assert.match(status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
  assert.match(status.textContent, /25 возвратов препятствия/);
  assert.equal(banner.textContent, 'Препятствие на 25.0 м');
});

test('viewer temporal confirmation survives unstable axis-s for the same XYZ component', () => {
  const result = {
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    core_count: 25,
    core_source_indices: Array.from({length: 25}, (_, index) => index),
    margin_count: 0,
    rail_pair_count: 3,
    rail_pairs_source_xyz: [
      {source_s_m: 0, left_xyz: [-0.75, 0, 0], right_xyz: [0.75, 0, 0]},
      {source_s_m: 20, left_xyz: [-0.75, -20, 0], right_xyz: [0.75, -20, 0]},
      {source_s_m: 40, left_xyz: [-0.75, -40, 0], right_xyz: [0.75, -40, 0]},
    ],
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297400000000',
  };
  const shiftedAxisResult = {
    ...result,
    header_timestamp_ns: '946687297300000000',
    rail_pairs_source_xyz: [
      {source_s_m: 6, left_xyz: [-0.75, 0, 0], right_xyz: [0.75, 0, 0]},
      {source_s_m: 26, left_xyz: [-0.75, -20, 0], right_xyz: [0.75, -20, 0]},
      {source_s_m: 46, left_xyz: [-0.75, -40, 0], right_xyz: [0.75, -40, 0]},
    ],
  };
  const coordinates = [];
  for (let index = 0; index < 25; index++) coordinates.push(0.20, -25 - index * 0.01, 0);
  const xyz = new Float32Array(coordinates);
  const cache = new Map([
    [45, {result: shiftedAxisResult, xyz, frame: {header_timestamp_ns: '946687297300000000'}}],
  ]);

  const {status, banner} = runShowStatus(result, {
    xyz,
    cache,
    minPoints: 22,
    radius: 0.25,
    requiredFrames: 2,
    nearZoneM: 6,
    matchAxisM: 2,
    maxAxisSpan: 1.0,
    maxAxisDistance: 1.20,
  });

  assert.match(status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
  assert.equal(banner.textContent, 'Препятствие на 25.0 м');
});

test('viewer suppresses near-zone components while train is moving', () => {
  const result = {
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    core_count: 25,
    core_source_indices: Array.from({length: 25}, (_, index) => index),
    margin_count: 0,
    rail_pair_count: 2,
    rail_pairs_source_xyz: [
      {source_s_m: 0, left_xyz: [-0.75, 0, 0], right_xyz: [0.75, 0, 0]},
      {source_s_m: 20, left_xyz: [-0.75, -20, 0], right_xyz: [0.75, -20, 0]},
    ],
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297500000000',
  };
  const coordinates = [];
  for (let index = 0; index < 25; index++) coordinates.push(0.95, -4 - index * 0.01, 0);
  const xyz = new Float32Array(coordinates);

  const {status, banner} = runShowStatus(result, {
    xyz,
    minPoints: 22,
    radius: 0.25,
    requiredFrames: 2,
    moving: true,
    nearZoneM: 6,
    maxAxisSpan: 1.0,
    maxAxisDistance: 1.20,
  });

  assert.doesNotMatch(status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
  assert.equal(banner.textContent, '');
});

test('viewer allows near-zone components to warn immediately while train is stopped', () => {
  const result = {
    status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    core_count: 25,
    core_source_indices: Array.from({length: 25}, (_, index) => index),
    margin_count: 0,
    rail_pair_count: 2,
    rail_pairs_source_xyz: [
      {source_s_m: 0, left_xyz: [-0.75, 0, 0], right_xyz: [0.75, 0, 0]},
      {source_s_m: 20, left_xyz: [-0.75, -20, 0], right_xyz: [0.75, -20, 0]},
    ],
    compute_backend_used: 'cpu',
    source_frame: 'lidar_livox',
    header_timestamp_ns: '946687297500000000',
  };
  const coordinates = [];
  for (let index = 0; index < 25; index++) coordinates.push(0.95, -4 - index * 0.01, 0);
  const xyz = new Float32Array(coordinates);

  const {status, banner} = runShowStatus(result, {
    xyz,
    minPoints: 22,
    radius: 0.25,
    requiredFrames: 2,
    moving: false,
    nearZoneM: 6,
    maxAxisSpan: 1.0,
    maxAxisDistance: 1.20,
  });

  assert.match(status.textContent, /ПРЕДУПРЕЖДЕНИЕ/);
  assert.equal(banner.textContent, 'Препятствие на 4.0 м');
});

test('viewer exposes a noise layer toggle and uses ignored noise indices', () => {
  const html = fs.readFileSync(
    path.join(__dirname, '..', 'web', 'stage_4_cpu_viewer.html'),
    'utf8',
  );
  const player = fs.readFileSync(
    path.join(__dirname, '..', 'web', 'stage_4_cpu_player.js'),
    'utf8',
  );
  const controls = fs.readFileSync(
    path.join(__dirname, '..', 'web', 'stage_4_cpu_player_controls.js'),
    'utf8',
  );

  assert.match(html, /id="noise-layer"/, 'sidebar must expose the noise checkbox');
  assert.match(html, />Шум</, 'noise layer label must be visible to the operator');
  assert.match(player, /ignored_noise_source_indices/, 'viewer must consume backend noise indices');
  assert.match(player, /noise-layer/, 'main player must wire the noise layer');
  assert.match(controls, /noise-layer/, 'controls helper must preserve the noise layer toggle');
  assert.match(html, /id="noise-min-points"/, 'viewer must expose component-size threshold');
  assert.match(html, /id="noise-radius"/, 'viewer must expose connectivity radius');
  assert.match(html, /id="noise-max-axis-span"/, 'viewer must expose axis-span compactness');
  assert.match(html, /id="noise-max-axis-distance"/, 'viewer must expose axis-distance compactness');
  assert.match(html, /id="temporal-required-frames"/, 'viewer must expose temporal confirmation');
  assert.match(html, /id="train-moving"/, 'viewer must expose moving train mode');
  assert.match(html, /id="temporal-near-zone-m"/, 'viewer must expose near-zone threshold');
  assert.match(html, /id="temporal-match-axis-m"/, 'viewer must expose temporal matching tolerance');
  assert.match(player, /function effectiveCoreSplit/, 'viewer must recompute components for experiments');
  assert.match(player, /function componentAxisStats/, 'viewer must classify component compactness against the C++ axis');
  assert.match(player, /function temporalMatch/, 'viewer must match components across neighboring frames');
  assert.match(controls, /noise-min-points/, 'controls helper must wire threshold edits');
  assert.match(controls, /noise-radius/, 'controls helper must wire connectivity edits');
  assert.match(controls, /noise-max-axis-span/, 'controls helper must wire axis-span edits');
  assert.match(controls, /noise-max-axis-distance/, 'controls helper must wire axis-distance edits');
  assert.match(controls, /temporal-required-frames/, 'controls helper must wire temporal confirmation edits');
  assert.match(controls, /train-moving/, 'controls helper must wire moving train mode');
  assert.match(controls, /temporal-near-zone-m/, 'controls helper must wire near-zone edits');
  assert.match(controls, /temporal-match-axis-m/, 'controls helper must wire temporal matching edits');
});
