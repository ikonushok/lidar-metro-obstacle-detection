const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');

// Frozen development evidence: stage_3_results.jsonl, frames 159--162.
// These are per-frame floor hypotheses, NOT registered track ground truth.
const samples = [
  [159, [0.2953374683856964,-0.28946438431739807,0.5121718049049377,1.6339447498321533,2.1713316440582275,2.6544408798217773,3.6810076236724854,3.892071008682251], [-1.6836159229278564,-1.9026585817337036,-2.267642879486084,-2.6182209491729735,-2.8488965034484863,-2.961629629135132,-3.100727152824402,-3.2033355712890623]],
  [160, [0.30000895261764526,-0.31259170174598694,0.494159460067749,1.5865097045898438,2.1462044715881348,1.8040647506713867], [-1.6822342634201048,-1.9033933281898499,-2.2677664756774902,-2.6180428981781008,-2.850578546524048,-2.926284980773926]],
  [161, [0.30361461639404297,-0.28946438431739807,0.4927714765071869,1.5802394151687622,2.1061363220214844,2.6092939376831055,3.7564642429351807,3.6111817359924316], [-1.685004711151123,-1.902825951576233,-2.2653167247772217,-2.6174824237823486,-2.8390982151031494,-2.9644866228103637,-3.08200945854187,-3.3262871742248534]],
  [162, [0.3074434995651245,-0.29842349886894226,0.5106798410415649,1.5865097045898438,2.145606279373169,2.616055965423584,3.698848009109497,3.491482734680176], [-1.6866188049316406,-1.9043262004852295,-2.2689884662628175,-2.616800308227539,-2.850941467285156,-2.9589638710021973,-3.117615747451782,-3.3518667221069336]],
].map(([frame, xs, zs]) => ({frame, nodes: xs.map((x_m, i) => ({
  depth_m: 5 + 10*i, x_m, y_m: -(5 + 10*i), z_m: zs[i],
}))}));

const html = fs.readFileSync(path.join(__dirname, '../web/stage_2_player.html'), 'utf8');
const start = html.indexOf('    function extendedPathNodes(');
const end = html.indexOf('    function buildTrackGrid(', start);
assert.ok(start >= 0 && end > start, 'extract actual player function, not a duplicate');
const context = vm.createContext({fullPositions: new Float32Array([0, -200, 0])});
vm.runInContext(html.slice(start, end), context);
const rendered = samples.map(sample => context.extendedPathNodes(sample));

test('production path extension preserves measured support and reaches 200 m', () => {
  samples.forEach((sample, i) => {
    assert.equal(rendered[i].at(-1).depth_m, 200);
    sample.nodes.forEach(node => {
      const actual = rendered[i].find(n => n.depth_m === node.depth_m);
      assert.equal(actual.x_m, node.x_m);
      assert.equal(actual.z_m, node.z_m);
    });
  });
});

test('unsupported continuation must not amplify jumps as a precise envelope', t => {
  // Proposed visualization regression contract for this reported sequence only.
  // Not a universal bound on physical motion, a safety threshold, or proof of alignment.
  const failures = [];
  for (let i = 1; i < samples.length; i++) {
    const previous = samples[i-1], current = samples[i];
    const shared = Math.min(previous.nodes.length, current.nodes.length);
    const supportJump = Math.max(...current.nodes.slice(0, shared).map((n,j) =>
      Math.abs(n.x_m - previous.nodes[j].x_m)));
    const farJump = Math.abs(rendered[i].at(-1).x_m - rendered[i-1].at(-1).x_m);
    const evidence = `${previous.frame}->${current.frame}: support jump=${supportJump.toFixed(6)} m, 200 m jump=${farJump.toFixed(6)} m, amplification=${(farJump/supportJump).toFixed(2)}x`;
    t.diagnostic(evidence);
    if (farJump > supportJump + 1e-6 &&
        rendered[i].at(-1).envelopeEligible !== false &&
        rendered[i-1].at(-1).envelopeEligible !== false) failures.push(evidence);
  }
  assert.equal(failures.length, 0, failures.join('\n'));
});

test('all four long unsupported tails are explicitly unknown and excluded from envelope', () => {
  rendered.forEach(nodes => {
    assert.equal(nodes.at(-1).envelopeEligible, false);
    assert.equal(nodes.at(-1).continuationStatus, 'UNKNOWN');
  });
  assert.match(html, /extendedPathNodes\(path\)\.filter\(node => node\.envelopeEligible !== false\)/);
});

test('straight multi-support continuation works, sparse support is not trusted', () => {
  const straight = {nodes:[0,50,100,150].map(depth_m => ({depth_m,
    x_m:depth_m*0.02,y_m:-depth_m,z_m:-2-depth_m*0.01}))};
  const tail = context.extendedPathNodes(straight).at(-1);
  assert.equal(tail.x_m,4);
  assert.equal(tail.z_m,-4);
  assert.equal(tail.envelopeEligible,true);
  assert.equal(context.extendedPathNodes({nodes:straight.nodes.slice(0,2)}).at(-1).envelopeEligible,false);
});
