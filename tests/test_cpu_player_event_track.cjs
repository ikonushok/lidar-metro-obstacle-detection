'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

class Element {
  constructor() {
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.className = '';
    this.hidden = false;
    this.classList = {toggle() {}};
  }

  appendChild(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; }
  querySelectorAll() { return this.children.filter(child => child.dataset.objectId); }
  setAttribute(name, value) { this[name] = value; }
  getAttribute(name) { return this[name]; }
}

test('timeline preloads only user windows and adds C++ signals when viewed', () => {
  const source = fs.readFileSync(path.join(__dirname, '..', 'web',
    'stage_4_cpu_player_events.js'), 'utf8');
  const elements = new Map();
  for (const id of ['event-review', 'event-track', 'event-track-legend', 'cpp-summary',
    'noise-min-points', 'noise-radius', 'noise-max-axis-span', 'noise-max-axis-distance',
    'temporal-required-frames', 'train-moving', 'temporal-near-zone-m',
    'temporal-match-axis-m', 'status']) elements.set(id, new Element());
  const objects = Array.from({length: 10}, (_, index) => ({
    object_id: `obj${String(index + 1).padStart(2, '0')}`,
    description_ru: `Объект ${index + 1}`,
    review_status: 'user_visible',
    working_role: index === 6 ? 'negative_review' : 'positive',
    frames_inclusive: index === 0 ? [135, 228] : index === 6 ? [617, 633] : null,
  }));
  let navigatedTo = null;
  const context = {
    document: {
      getElementById(id) { return elements.get(id); },
      createElement() { return new Element(); },
    },
    MutationObserver: class { observe() {} },
    manifest: {dataset_id: 'cloud_with_fake_obj', frames: Array(1510).fill(null),
      review_objects: objects, review_alarm_frames: [204], review_early_frames: [137]},
    current: 139,
    result: {noise_filter_mode: 'baseline_v3', status: 'UNKNOWN',
      intrusion_candidate_present: false},
    earlyRunPresent: () => true,
    showNow(index) { navigatedTo = index; },
  };
  vm.runInNewContext(source, context);
  context.updateEventReview();

  const markers = () => elements.get('event-track').children;
  assert.equal(elements.get('event-review').querySelectorAll().length, 10);
  assert.equal(markers().filter(item => item.className === 'user-window').length, 2);
  assert.equal(markers().filter(item => item.className === 'early-detection').length, 1);
  assert.equal(markers().filter(item => item.className === 'confirmed-detection').length, 0);
  assert.ok(markers().some(item => item.title.includes('кадр 139')));
  assert.ok(!markers().some(item => item.title.includes('кадр 137')));
  assert.equal(elements.get('event-track-legend').hidden, false);
  assert.ok(Number.parseFloat(markers()[0].style.width) > 0);
  elements.get('event-review').children.find(item => item.dataset.objectId === 'obj07').onclick();
  assert.equal(navigatedTo, 617);

  context.current = 204;
  context.result = {noise_filter_mode: 'baseline_v3', status: 'OBSERVED_CORE_INTRUSION_CANDIDATE',
    intrusion_candidate_present: true};
  context.updateEventReview();
  assert.equal(markers().filter(item => item.className === 'confirmed-detection').length, 1);
  assert.equal(markers().filter(item => item.className === 'early-detection').length, 1);
});
