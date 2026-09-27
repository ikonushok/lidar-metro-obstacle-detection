// Playback regressions: real viewer code, controlled frame I/O, no browser/GPU required.
// Does not establish WebGL frame rate or reproduce CSS layout changes.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const THREE = require(path.join(root, 'artefacts/stage_2/player_doubleT_obstacle/vendor/three.min.js'));
const createChecker = require('../web/stage_3_live_envelope.js');
const liveConfig = require('../web/stage_3_live_envelope_config.json');
const reviewSource = fs.readFileSync(path.join(root, 'web/stage_2_review_layers.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'web/stage_2_raw_player.html'), 'utf8');

test('sidebar legend explains candidate colors and sensor distance', () => {
  assert.match(html, /Легенда/);
  assert.match(html, /Точки внутри габарита/);
  assert.match(html, /прямая от датчика до ближайшего возврата/);
  assert.match(html, /не класс объекта/);
});

function elements() {
  const all = new Map();
  return id => {
    if (!all.has(id)) all.set(id, {
      value: '', checked: false, disabled: false, textContent: '', style: {},
      clientWidth: 1280, clientHeight: 720,
      appendChild() {}, replaceChildren() {}, addEventListener() {},
    });
    return all.get(id);
  };
}
const identity = index => ({index, header_timestamp_ns: 'test-' + index, source_frame: 'synthetic'});
const rails = center => [[center - .76, -4, -2], [center + .76, -4, -2],
  [center - .76, -24, -2], [center + .76, -24, -2]];

test('crop preference survives frame changes; crop uses the new axis, never the previous one', () => {
  const el = elements();
  el('axis-mode').value = 'auto';
  for (const side of ['left', 'right', 'top', 'bottom']) el('margin-' + side).value = '.5';
  let center = 0, available = true, pairsAvailable = true, displayed;
  const context = vm.createContext({THREE, Float32Array, console,
    createLiveEnvelopeChecker: createChecker,
    document: {getElementById: el, createElement: () => ({textContent: ''})},
    AutoRails: {detect: () => ({rails: available ? rails(center) : [], rail_pairs: available && pairsAvailable ? [{source_s_m:4,left_xyz:rails(center)[0],right_xyz:rails(center)[1]},{source_s_m:24,left_xyz:rails(center)[2],right_xyz:rails(center)[3]}] : [], support: [],
      reason: 'INSUFFICIENT_PAIRED_RAIL_SUPPORT',
      diagnostics: {forwardRange: [4, 24], supportedStations: 11, rms: 0}})},
  });
  vm.runInContext(reviewSource, context);
  const ui = context.createReviewLayers({scene: new THREE.Scene(), canvas: el('canvas'),
    pause() {}, cloud: () => ({}), display: value => {displayed = value;}, colors() {}});
  const meta = {dataset: 'synthetic', frames: [identity(0)], visualization_overlay: {
    source_axis_assumption: {longitudinal_axis: 'y', longitudinal_sign: -1,
      lateral_axis: 'x', vertical_axis: 'z', source_units: 'm'},
    reference_cross_section: {lateral_extent_m: {min: -1.4, max: 1.4},
      vertical_extent_above_rail_m: {min: 0, max: 3.7}},
  }};
  const raw = new Float32Array([0, -10, -1, 8, -10, -1, 0, -30, -1]);
  const before = Buffer.from(raw.buffer).toString('hex');
  ui.setFrame(identity(0), raw, meta, {}, liveConfig);
  el('crop-layer').checked = true;
  el('crop-layer').onchange();
  assert.deepEqual([...displayed], [0, -10, -1, 0, -30, -1], 'fixture must initially crop');
  center = 8;
  ui.unload();
  ui.setFrame(identity(1), raw, meta, {}, liveConfig);
  assert.equal(el('crop-layer').checked, true, 'changing frame must not reset the user crop preference');
  assert.deepEqual([...displayed], [8, -10, -1, 0, -30, -1], 'crop must use new-frame rails');
  pairsAvailable = false;
  ui.unload();
  ui.setFrame(identity(2), raw, meta, {}, liveConfig);
  assert.equal(el('crop-layer').checked, true, 'unavailable geometry must not erase the preference');
  assert.equal(el('crop-layer').disabled, true);
  assert.deepEqual([...displayed], [...raw], 'legacy straight rails without pairs must not become an auto fallback');
  assert.match(el('live-status').textContent, /UNKNOWN/);
  assert.equal(Buffer.from(raw.buffer).toString('hex'), before);
});

async function makePlayer() {
  const el = elements(), timers = new Map(), scenes = [], reviewFrames = [], notices = [];
  let timerId = 0, resolveNext, nextRequested = false;
  const nextResponse = new Promise(resolve => {resolveNext = resolve;});
  const values = [new Float32Array([0, -10, -1]), new Float32Array([1, -20, -2])];
  const frames = values.map((p, index) => ({...identity(index), file: 'frame-' + index,
    displayed_points: p.length / 3, bag_offset_seconds: index * .1, zero_xyz_returns: 0}));
  const manifest = {dataset: 'synthetic', geometry_enabled: true, geometry_notice: 'Экспериментальная геометрия: геометрические кандидаты.', format: 'lidar-mosmetro3d.xyzf', format_version: 1,
    point_encoding: {decimation: 'NONE', bytes_per_point: 12}, frames};
  el('play').disabled = true;
  el('view').value = 'forward';
  el('speed').value = '1';
  const response = data => ({ok: true, json: async () => data});
  const context = vm.createContext({console, Float32Array, AbortController, devicePixelRatio: 1,
    document: {getElementById: el, createElement: () => ({className: '', textContent: ''})},
    THREE: {...THREE,
      Scene: class extends THREE.Scene {constructor() {super(); scenes.push(this);}},
      WebGLRenderer: class {constructor() {this.domElement = el('canvas');}
        setPixelRatio() {} setSize() {} render() {}},
      OrbitControls: class {constructor() {this.target = new THREE.Vector3();} update() {}},
    },
    ResizeObserver: class {constructor(fn) {this.fn = fn;} observe() {this.fn();}},
    requestAnimationFrame() {},
    setTimeout(fn) {const id = ++timerId; timers.set(id, fn); return id;},
    clearTimeout(id) {timers.delete(id);},
    createReviewLayers: () => ({unload() {}, setFrame(frame) {reviewFrames.push(frame.index);}}),
    fetch: async url => {
      if (url === 'manifest.json') return response(manifest);
      if (url.endsWith('.json')) return response({});
      if (url === 'frame-0') return {ok: true, arrayBuffer: async () => values[0].buffer};
      if (url === 'frame-1') {nextRequested = true; return nextResponse;}
      throw new Error('Unexpected fixture fetch: ' + url);
    },
  });
  el('status').before = note => {notices.push(note);};
  vm.runInContext(html.split('<script>')[1].split('</script>')[0], context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(el('error').textContent, '', 'fixture must load the initial frame');
  assert.equal(notices.length, 1);
  assert.match(notices[0].textContent, /геометрические кандидаты/);
  assert.equal(el('play').disabled, false);
  assert.equal(scenes[0].getObjectByName('raw-frame').geometry.attributes.position.array.buffer, values[0].buffer);
  return {el, scene: scenes[0], reviewFrames, values, notices,
    start() {
      el('play').onclick();
      const entry = timers.entries().next().value;
      assert.ok(entry, 'play must schedule the next frame');
      timers.delete(entry[0]);
      const task = entry[1]();
      assert.equal(nextRequested, true, 'the test must reach pending frame I/O');
      return task;
    },
    finish() {resolveNext({ok: true, arrayBuffer: async () => values[1].buffer});},
  };
}

test('playback retains the displayed cloud while the next frame response is pending', async () => {
  const player = await makePlayer();
  const original = player.scene.getObjectByName('raw-frame');
  let disposed = false;
  original.geometry.addEventListener('dispose', () => {disposed = true;});
  const pending = player.start();
  try {
    assert.equal(player.scene.getObjectByName('raw-frame') === original, true,
      'pending frame I/O must not expose an empty scene');
    assert.equal(disposed, false, 'displayed cloud is still needed while waiting');
    assert.equal(Number(player.el('frame-output').value), 0, 'old cloud retains its own identity');
  } finally {
    player.finish();
    await pending;
  }
});

test('playback harness reaches next-frame commit with exactly one source cloud and matching identity', async () => {
  const player = await makePlayer();
  const pending = player.start();
  player.finish();
  await pending;
  assert.equal(player.scene.children.filter(o => o.name === 'raw-frame').length, 1);
  assert.equal(player.scene.getObjectByName('raw-frame').geometry.attributes.position.array.buffer, player.values[1].buffer);
  assert.equal(Number(player.el('frame-output').value), 1);
  assert.deepEqual(player.reviewFrames, [0, 1]);
  assert.equal(player.el('error').textContent, '');
});
