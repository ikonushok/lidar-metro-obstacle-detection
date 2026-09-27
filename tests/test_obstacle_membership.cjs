const test=require('node:test'),assert=require('node:assert/strict');
const G=require('../web/stage_2_review_layers.js');
const axis=G.railAxis([[-.8,-4,0],[.8,-4,0],[-.8,-44,0],[.8,-44,0]]);
const reference={lateral_extent_m:{min:-1.4,max:1.4},vertical_extent_above_rail_m:{min:0,max:3.7}};
const envelope=G.createEnvelope(axis,reference,{left:.5,right:.5,bottom:.5,top:.5});
test('semantic-free intersections use actual hit distance; outside closer point does not replace it',()=>{
  const raw=new Float32Array([3,-5,1,0,-20,.01,1.7,-10,1]),before=raw.slice();
  const r=G.assessComponent(raw,[0,1,2],envelope);
  assert.equal(r.status,'CORE_INTERSECTION');assert.equal(r.nearest.core.source_index,1);
  assert.equal(r.nearest.margin.source_index,2);assert.deepEqual(raw,before);
  assert.equal(r.safety_decision_permitted,false);
});
test('unknown ends explain missing coverage; positive low intersection survives incomplete group',()=>{
  const raw=new Float32Array([0,-3,1,0,-56,1,0,-10,.001]);
  const r=G.assessComponent(raw,[0,1,2],envelope,true);
  assert.equal(r.status,'CORE_INTERSECTION');assert.equal(r.complete_observed_component,false);
  assert.deepEqual(r.reason_codes,['BEFORE_SUPPORTED_PATH','AFTER_SUPPORTED_PATH','SEARCH_ROI_MAY_CLIP_OBJECT']);
  assert.equal(G.assessComponent(raw,[0,1],envelope).status,'UNKNOWN');
});
test('outside observed points never certify clipped object or missing geometry as clear',()=>{
  const raw=new Float32Array([3,-10,1]);
  assert.equal(G.assessComponent(raw,[0],envelope).status,'OBSERVED_RETURNS_OUTSIDE');
  assert.equal(G.assessComponent(raw,[0],envelope,true).status,'UNKNOWN');
  assert.equal(G.assessComponent(raw,[0],null).status,'UNKNOWN');
  for(const indices of [[],[0,0],[-1],[1],[.5]])assert.equal(G.assessComponent(raw,indices,envelope).status,'UNKNOWN');
  assert.equal(G.assessComponent(new Float32Array([NaN,0,0]),[0],envelope).status,'UNKNOWN');
});
