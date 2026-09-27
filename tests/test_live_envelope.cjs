'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const G=require('../web/stage_2_review_layers.js'),createChecker=require('../web/stage_3_live_envelope.js'),C=createChecker(G);
const config=require('../web/stage_3_live_envelope_config.json'),Z=G.zones;
const reference={lateral_extent_m:{min:-1.4,max:1.4},vertical_extent_above_rail_m:{min:0,max:3.7}};
const margins={left:.5,right:.5,top:.5,bottom:.5};
const axis=G.railAxis([[-1.4,2,-2],[.2,2,-2],[2.6,-14,-1.2],[4.2,-14,-1.2]]);
const envelope=G.createEnvelope(axis,reference,margins),identity={index:0,header_timestamp_ns:'test-0',source_frame:'test'};
const point=(s,l,h)=>G.world(axis,s,l,h);
const analyze=points=>C.analyze(new Float64Array(points.flat()),envelope,config,identity);
test('all train faces and corners match the rendered translated/yawed/graded envelope',()=>{
  const points=[];
  for(const s of [0,axis.length/2,axis.length])for(const l of [-1.4,0,1.4])for(const h of [0,1,3.7])points.push(point(s,l,h));
  const r=analyze(points);assert.equal(r.counts.core,points.length);
  G.rings(envelope.axis,envelope.core).flat().forEach(p=>assert.equal(G.classify(envelope,p),Z.CORE));
  const nearOutside=analyze([point(5,1.4+1e-4,1),point(5,0,-1e-4)]);
  assert.equal(nearOutside.counts.core,0);assert.equal(nearOutside.counts.margin,2);
});
test('margin faces, outside reference and unknown ends remain distinct; crop uses identical boundaries',()=>{
  const samples=[[5,-1.9,1],[5,1.9,1],[5,0,-.5],[5,0,4.2],[5,2.0,1],[-.01,0,1],[axis.length+.01,0,1],[5,0,.01]];
  const raw=new Float64Array(samples.map(v=>point(...v)).flat()),r=C.analyze(raw,envelope,config,identity);
  assert.deepEqual([...r.labels],[Z.MARGIN,Z.MARGIN,Z.MARGIN,Z.MARGIN,Z.OUTSIDE_REFERENCE,Z.UNKNOWN,Z.UNKNOWN,Z.CORE]);
  assert.equal(r.status,'OBSERVED_CORE_INTRUSION_CANDIDATE');assert.equal(r.intrusion_candidate_present,true);assert.equal(r.margin_return_present,true);
  const cropped=G.crop(raw,axis,envelope.expanded);assert.equal(cropped.length/3,7);
  assert.equal(r.system_status,'UNKNOWN');assert.equal(r.safety_decision_permitted,false);
});
test('a singleton low intrusion is immediate despite the minimum cluster size; nearest is a return, not a box center',()=>{
  const p=point(4,0,.005),r=analyze([p,point(8,0,1),point(5,1.6,1)]);
  assert.equal(r.status,'OBSERVED_CORE_INTRUSION_CANDIDATE');assert.equal(r.intrusion_candidate_present,true);assert.equal(r.margin_return_present,true);assert.equal(r.counts.core,2);
  assert.equal(r.clusters.length,0);assert.equal(r.ungrouped_candidate_points,3);
  assert.deepEqual(r.nearest_core.point,p);assert.equal(r.nearest_core.distance_from_source_origin_m,Math.hypot(...p));
});
test('grouping is zone-local, preserves small returns and never controls candidate status',()=>{
  const points=[];for(let i=0;i<5;i++)points.push(point(5+i*.002,1.39,.1));
  for(let i=0;i<5;i++)points.push(point(5+i*.002,1.41,.1));
  points.push(point(12,0,.005));
  const r=analyze(points);assert.equal(r.clusters.length,2);
  assert.deepEqual(r.clusters.map(c=>c.zone).sort(),['CORE','MARGIN']);assert.equal(r.ungrouped_candidate_points,1);
  const budget=C.analyze(new Float64Array(points.flat()),envelope,{...config,max_voxels:1},identity);
  assert.equal(budget.grouping_status,'LIMIT_EXCEEDED_POINTS_RETAINED');
  assert.equal(budget.counts.core,r.counts.core);assert.equal(budget.status,r.status);assert.equal(budget.ungrouped_candidate_points,points.length);
});
test('no intersection, no geometry, malformed data/config or frame identity never produce CLEAR',()=>{
  const raw=new Float32Array(point(5,3,1));
  const none=C.analyze(raw,envelope,config,identity);assert.equal(none.status,'UNKNOWN');assert.equal(none.geometric_candidate_present,false);assert.equal(none.intrusion_candidate_present,false);assert.equal(none.margin_return_present,false);
  const missingCurve=C.analyze(raw,null,config,identity,'MISSING_CURVE_AXIS');assert.equal(missingCurve.reason,'MISSING_CURVE_AXIS');
  for(const [data,geometry,c,id] of [[raw,null,config,identity],[raw,{},config,identity],[raw,envelope,null,identity],
    [new Float32Array([NaN,0,0]),envelope,config,identity],[new Float32Array([1,2]),envelope,config,identity],
    [raw,envelope,config,{}],[raw,envelope,{...config,voxel_size_m:0},identity]]){
    const r=C.analyze(data,geometry,c,id);assert.equal(r.status,'UNKNOWN');assert.equal(r.geometric_candidate_present,null);assert.equal(r.intrusion_candidate_present,null);assert.equal(r.margin_return_present,null);
    assert.equal(r.nearest_core,null);assert.equal(r.clusters.length,0);
  }
  assert.throws(()=>G.createEnvelope({...axis,tx:NaN},reference,margins));
  assert.throws(()=>G.createEnvelope(axis,reference,{...margins,left:-.1}));
  assert.throws(()=>G.createEnvelope(axis,{...reference,vertical_extent_above_rail_m:{min:0,max:0}},margins));
});
test('changing the same axis/margins changes membership and drawn geometry, without mutating raw or prior snapshot',()=>{
  const raw=new Float32Array(point(6,1.7,1)),before=Buffer.from(raw.buffer).toString('hex');
  const small=G.createEnvelope(axis,reference,{...margins,right:.1});
  const wide=G.createEnvelope(axis,reference,{...margins,right:.5});
  assert.equal(C.analyze(raw,small,config,identity).labels[0],Z.OUTSIDE_REFERENCE);
  assert.equal(C.analyze(raw,wide,config,identity).labels[0],Z.MARGIN);
  assert.notDeepEqual(G.rings(axis,small.expanded),G.rings(axis,wide.expanded));
  const shifted=G.railAxis([[-1.4,2,-2],[.2,2,-2],[2.6,-14,-1.2],[4.2,-14,-1.2]].map(p=>[p[0]+6,p[1],p[2]]));
  assert.notEqual(G.classify(G.createEnvelope(shifted,reference,margins),point(6,0,1)),Z.CORE);
  assert.equal(Buffer.from(raw.buffer).toString('hex'),before);assert.throws(()=>{wide.core.left=99;});
  const summary=C.summary(C.analyze(raw,wide,config,identity));assert.equal('labels' in summary,false);
  assert.equal(summary.header_timestamp_ns,identity.header_timestamp_ns);assert.equal(summary.envelope.expanded.right,1.9);
});
test('curve axis follows only its paired support and preserves low returns without a straight fallback',()=>{
  const pairs=[
    {source_s_m:4,left_xyz:[-1,-4,0],right_xyz:[1,-4,0]},
    {source_s_m:6,left_xyz:[-1.1,-6,0],right_xyz:[.9,-6,0]},
    {source_s_m:8,left_xyz:[-1.5,-8,0],right_xyz:[.5,-8,0]}
  ];
  const curve=G.curveRailAxis(pairs),curveEnvelope=G.createEnvelope(curve,reference,margins);
  assert.equal(curve.kind,'CURVE_RAIL_AXIS_SOURCE_XYZ');assert.equal(curve.segments.length,2);
  const low=G.world(curve,.5,0,.005),middle=G.world(curve,curve.length-.5,0,1),last=curve.segments.at(-1);
  const after=G.world(last,last.length+.01,0,1),r=C.analyze(new Float64Array([...low,...middle,...after]),curveEnvelope,config,identity);
  assert.deepEqual([...r.labels],[Z.CORE,Z.CORE,Z.UNKNOWN]);assert.equal(r.status,'OBSERVED_CORE_INTRUSION_CANDIDATE');assert.equal(r.intrusion_candidate_present,true);
  assert.deepEqual(r.nearest_core.point,low);assert.ok(r.nearest_core.station_from_segment_start_m>=0);
  assert.equal(curveEnvelope.coordinate_basis,'CURRENT_CURVE_AXIS_FROM_SOURCE_XYZ');
  assert.equal(r.curve_axis_status,'CURVE_AXIS_SUPPORTED');assert.equal(r.straight_fallback_used,false);
  assert.deepEqual(r.curve_axis_diagnostics.rail_pair_count,pairs.length);
  assert.throws(()=>G.curveRailAxis(pairs.slice(0,1)));assert.throws(()=>G.curveRailAxis([{...pairs[0]},{...pairs[0]}]));
});
test('collinear curve pairs match the existing straight envelope at core, margin, outside and unsupported points',()=>{
  const rails=[[-1,-4,0],[1,-4,0],[-1,-8,0],[1,-8,0]],straight=G.createEnvelope(G.railAxis(rails),reference,margins);
  const curve=G.createEnvelope(G.curveRailAxis([
    {source_s_m:4,left_xyz:rails[0],right_xyz:rails[1]},
    {source_s_m:6,left_xyz:[-1,-6,0],right_xyz:[1,-6,0]},
    {source_s_m:8,left_xyz:rails[2],right_xyz:rails[3]}
  ]),reference,margins);
  for(const sample of [[2,0,1],[2,1.7,1],[2,2,1],[-.01,0,1],[4.01,0,1]]){
    const point=G.world(straight.axis,...sample);assert.equal(G.classify(curve,point),G.classify(straight,point),JSON.stringify(sample));
  }
});
test('viewer checks full raw, exports matching evidence, refreshes geometry and clears stale results',async()=>{
  const THREE=require('../artefacts/stage_2/player_doubleT_obstacle/vendor/three.min.js');
  const els=new Map(),el=id=>{if(!els.has(id))els.set(id,{value:'',checked:false,disabled:false,textContent:'',replaceChildren(){},appendChild(){}});return els.get(id);};
  el('axis-mode').value='auto';for(const id of ['axis-layer','train-layer','live-layer'])el(id).checked=true;
  for(const s of ['left','right','top','bottom'])el('margin-'+s).value='.5';
  const scene=new THREE.Scene(),raw=new Float32Array([...point(5,0,.01),...point(5,1.7,1),...point(5,3,1),...point(axis.length+1,0,1)]);
  let displayed=raw;
  let exportedBlob=null,downloadName=null;
  const document={getElementById:el,createElement:()=>({width:0,height:0,getContext:()=>({fillRect(){},fillText(){}}),textContent:'',
    click(){downloadName=this.download;}})};
  const stubRails=[[-1.4,2,-2],[.2,2,-2],[2.6,-14,-1.2],[4.2,-14,-1.2]];
  const stubAuto={detect:()=>({rails:stubRails,rail_pairs:[{source_s_m:2,left_xyz:stubRails[0],right_xyz:stubRails[1]},{source_s_m:14,left_xyz:stubRails[2],right_xyz:stubRails[3]}],support:[],diagnostics:{forwardRange:[0,20],supportedStations:8,rms:0}})};
  const ctx=vm.createContext({THREE,document,AutoRails:stubAuto,createLiveEnvelopeChecker:createChecker,Float32Array,console,Blob,
    URL:{createObjectURL:blob=>{exportedBlob=blob;return 'blob:test';},revokeObjectURL(){}},setTimeout:callback=>callback()});
  vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../web/stage_2_review_layers.js'),'utf8'),ctx);
  const ui=ctx.createReviewLayers({scene,canvas:{style:{},addEventListener(){}},pause(){},cloud:()=>({}),display:p=>displayed=p,colors(){}});
  const meta={dataset:'synthetic',frames:[identity],visualization_overlay:{source_axis_assumption:{longitudinal_axis:'y',longitudinal_sign:-1,lateral_axis:'x',vertical_axis:'z',source_units:'m'},reference_cross_section:reference}};
  ui.setFrame(identity,raw,meta,{},config);assert.match(el('live-status').textContent,/ПРЕДУПРЕЖДЕНИЕ: 1 наблюдаемых возвратов внутри/);
  el('export-live').onclick();const exported=JSON.parse(await exportedBlob.text());
  assert.equal(downloadName,'live_envelope_frame_0.json');assert.equal(exported.counts.core,1);
  assert.equal(exported.header_timestamp_ns,identity.header_timestamp_ns);assert.equal(exported.frame_index,0);
  assert.equal(exported.envelope.expanded.right,1.9);assert.equal(exported.safety_decision_permitted,false);
  assert.equal('labels' in exported,false);assert.equal(exported.geometry_source.mode,'auto');
  const status=el('live-status').textContent;el('crop-layer').checked=true;el('crop-layer').onchange();
  assert.ok(displayed.length<raw.length);assert.equal(el('live-status').textContent,status);
  el('margin-right').value='.1';el('margin-right').onchange();assert.match(el('live-status').textContent,/в отступах 0/);
  el('export-live').onclick();const changed=JSON.parse(await exportedBlob.text());
  assert.equal(changed.counts.margin,0);assert.equal(changed.envelope.expanded.right,1.5);
  ui.unload();assert.match(el('live-status').textContent,/UNKNOWN/);assert.equal(el('export-live').disabled,true);
  assert.equal(scene.children[0].children.length,0);
  ui.setFrame({...identity,index:1,header_timestamp_ns:'next'},new Float32Array(point(5,3,1)),meta,{},config);
  assert.match(el('live-status').textContent,/не «путь свободен»/);assert.equal(el('crop-layer').checked,true);
  ui.setFrame({...identity,index:2,header_timestamp_ns:'objects-off'},new Float32Array(point(5,0,1)),{...meta,object_candidates_enabled:false},{},config);
  assert.equal(el('object-layer').disabled,true);assert.equal(el('object-layer').checked,false);
  assert.match(el('object-status').textContent,/только пересечения текущего габарита/);
  el('raw-only').onclick();assert.equal(displayed.length,3);assert.equal(scene.children[0].children.length,0);
  assert.match(el('live-status').textContent,/UNKNOWN/);
});
