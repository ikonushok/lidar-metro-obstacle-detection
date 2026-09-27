'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

class Vector3 {
  constructor(x = 0, y = 0, z = 0) {
    this.x = x;
    this.y = y;
    this.z = z;
  }

  add(other) {
    this.x += other.x;
    this.y += other.y;
    this.z += other.z;
    return this;
  }

  clone() {
    return new Vector3(this.x, this.y, this.z);
  }

  sub(other) {
    this.x -= other.x;
    this.y -= other.y;
    this.z -= other.z;
    return this;
  }

  multiplyScalar(value) {
    this.x *= value;
    this.y *= value;
    this.z *= value;
    return this;
  }

  addScaledVector(other, value) {
    this.x += other.x * value;
    this.y += other.y * value;
    this.z += other.z * value;
    return this;
  }

  length() {
    return Math.hypot(this.x, this.y, this.z);
  }

  normalize() {
    const length = this.length();
    this.x /= length;
    this.y /= length;
    this.z /= length;
    return this;
  }

  toArray() {
    return [this.x, this.y, this.z];
  }
}

function loadProductionBounds() {
  const viewerPath = path.join(__dirname, '..', 'web', 'stage_4_cpu_player.js');
  const source = fs.readFileSync(viewerPath, 'utf8');
  const start = source.indexOf('function validWireframe(');
  const end = source.indexOf('function rails(){', start);
  assert.notEqual(start, -1, 'production wireframe validation must exist');
  assert.notEqual(end, -1, 'production rails() function must follow bounds()');
  return source.slice(start, end);
}

function renderProductionBounds(result, checked = {}) {
  const lines = [];
  const context = {
    THREE: {Vector3},
    $(id) {
      return {checked: Boolean(checked[id])};
    },
    result,
    overlay: {},
    addLine(_group, points, color) {
      lines.push({points, color});
    },
  };
  vm.runInNewContext(`${loadProductionBounds()}\nbounds();`, context);
  return lines;
}

function validateProductionGeometry(result) {
  vm.runInNewContext(`${loadProductionBounds()}\nvalidateEnvelopeGeometry(result);`, {result});
}

function segmentWireframe(bounds) {
  const [left, right, bottom, top] = bounds;
  const a = [0, 0, 0];
  const b = [0.5, -2, 0];
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const length = Math.hypot(dx, dy);
  const tangent = [dx / length, dy / length];
  const normal = [dy / length, -dx / length];
  const point = (station, lateral, height) => [
    a[0] + tangent[0] * station + normal[0] * lateral,
    a[1] + tangent[1] * station + normal[1] * lateral,
    height,
  ];
  const corners = [
    point(0, left, bottom), point(0, left, top),
    point(0, right, bottom), point(0, right, top),
    point(length, left, bottom), point(length, left, top),
    point(length, right, bottom), point(length, right, top),
  ];
  const edges = [
    [0, 1], [1, 3], [3, 2], [2, 0],
    [4, 5], [5, 7], [7, 6], [6, 4],
    [0, 4], [1, 5], [2, 6], [3, 7],
  ];
  return edges.map(([start, end]) => [corners[start], corners[end]]);
}

test('viewer uses the same segment-normal direction as C++ core membership', () => {
  const coreBounds = [-1, 1, 0, 2];
  const result = {
    core_bounds_source_axis: coreBounds,
    core_envelope_wireframe_source_xyz: segmentWireframe(coreBounds),
    expanded_envelope_wireframe_source_xyz: [],
    rail_pairs_source_xyz: [
      {left_xyz: [-1, 0, 0], right_xyz: [1, 0, 0]},
      {left_xyz: [-0.5, -2, 0], right_xyz: [1.5, -2, 0]},
    ],
  };

  const lines = renderProductionBounds(result, {'core-envelope-layer': true});
  assert.equal(lines.length, 12, 'one displayed segment prism should have twelve edges');

  const firstTopEdge = lines[1].points;
  const displayedLateral = [
    firstTopEdge[1][0] - firstTopEdge[0][0],
    firstTopEdge[1][1] - firstTopEdge[0][1],
  ];

  const firstCenter = [0, 0];
  const secondCenter = [0.5, -2];
  const tangent = [secondCenter[0] - firstCenter[0], secondCenter[1] - firstCenter[1]];
  const tangentLength = Math.hypot(...tangent);
  const cppSegmentNormal = [tangent[1] / tangentLength, -tangent[0] / tangentLength];
  const cross = displayedLateral[0] * cppSegmentNormal[1]
    - displayedLateral[1] * cppSegmentNormal[0];

  assert.ok(
    Math.abs(cross) < 1e-9,
    'white core cross-section must be parallel to the normal used by AnalyzeCurveEnvelope',
  );
});

test('viewer rejects supported-axis results without exact C++ wireframes', () => {
  assert.throws(
    () => validateProductionGeometry({curve_axis_status: 'CURVE_AXIS_SUPPORTED'}),
    /некорректную геометрию габарита/,
  );
  assert.doesNotThrow(() => validateProductionGeometry({
    curve_axis_status: 'MISSING_CURVE_AXIS',
    core_envelope_wireframe_source_xyz: [],
    expanded_envelope_wireframe_source_xyz: [],
  }));
});

test('viewer can toggle core and expanded envelope boundaries independently', () => {
  const core = segmentWireframe([-1, 1, 0, 2]);
  const expanded = segmentWireframe([-1.5, 1.5, -0.5, 2.5]);
  const result = {
    core_envelope_wireframe_source_xyz: core,
    expanded_envelope_wireframe_source_xyz: expanded,
  };

  assert.deepEqual(
    renderProductionBounds(result, {'core-envelope-layer': true, 'margin-envelope-layer': false}).map(line => line.color),
    Array(core.length).fill(0xf6f6f6),
    'core envelope checkbox must control only the white core boundary',
  );
  assert.deepEqual(
    renderProductionBounds(result, {'core-envelope-layer': false, 'margin-envelope-layer': true}).map(line => line.color),
    Array(expanded.length).fill(0xffc34d),
    'expanded envelope checkbox must control only the +0.5 m warning boundary',
  );
});
