const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const G=require('../web/stage_2_review_layers.js');
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-5,`${a} != ${b}`);
const nearPoint=(a,b)=>a.forEach((v,i)=>near(v,b[i]));
const rails=[[4,8,-3],[6,8,-3],[16,-8,-1],[18,-8,-1]];
test('manual rail midpoints preserve translation, yaw and grade',()=>{
  const axis=G.railAxis(rails);nearPoint(axis.a,[5,8,-3]);nearPoint(axis.b,[17,-8,-1]);
  near(axis.length,20);nearPoint(G.world(axis,0,0,0),axis.a);nearPoint(G.world(axis,20,0,0),axis.b);
  const p=G.world(axis,7,.6,.1),v=G.local(axis,p);near(v.s,7);near(v.l,.6);near(v.h,.1);
});
test('every train cross-section stays centered on the same manual axis',()=>{
  const axis=G.railAxis(rails),rings=G.rings(axis,{left:-1.4,right:1.4,bottom:0,top:3.7});
  rings.forEach((r,i)=>{
    nearPoint(r[0].map((v,j)=>(v+r[1][j])/2),G.world(axis,axis.length*i/20,0,0));
    nearPoint(r[2].map((v,j)=>(v+r[3][j])/2),G.world(axis,axis.length*i/20,0,3.7));
  });
});
test('crop keeps low and boundary points, retains unknown beyond both ends, never edits raw',()=>{
  const axis=G.railAxis(rails),bounds={left:-1.4,right:1.4,bottom:0,top:3.7};
  const samples=[[10,0,.01],[10,1.4,0],[10,2,1],[-1,9,9],[21,9,9]].map(v=>G.world(axis,...v));
  const raw=new Float32Array(samples.flat()),before=Buffer.from(raw.buffer).toString('hex');
  const cropped=G.crop(raw,axis,bounds);
  assert.equal(cropped.length,12);
  assert.equal(Buffer.from(raw.buffer).toString('hex'),before);
  assert.equal(G.crop(raw,null,bounds),raw);
});
test('left/right margins agree with looking near to far with Z up',()=>{
  const axis=G.railAxis([[-1,0,0],[1,0,0],[-1,-20,0],[1,-20,0]]);
  nearPoint(G.world(axis,10,1,0),[-1,-10,0]);
  const b=G.profileBounds({lateral_extent_m:{min:-1.4,max:1.4},vertical_extent_above_rail_m:{min:0,max:3.7}},
    {left:.7,right:.2,top:.3,bottom:.1});
  near(b.left,-2.1);near(b.right,1.6);near(b.bottom,-.1);near(b.top,4);
});
test('incomplete, duplicate and vertical-only stations cannot create an axis',()=>{
  assert.throws(()=>G.railAxis([]));assert.throws(()=>G.railAxis([[0,0,0],[0,0,0],[0,-1,0],[1,-1,0]]));
  assert.throws(()=>G.railAxis([[-1,0,0],[1,0,0],[-1,0,2],[1,0,2]]));
});
test('manual review restores rails only for the exact source frame',()=>{
  const manifest={dataset:'doubleT_obstacle',frames:[{header_timestamp_ns:'first'}]},frame={index:0,header_timestamp_ns:'frame-0',source_frame:'lidar_livox'};
  const payload={format:'lidar-manual-review-v1',dataset:'doubleT_obstacle',first_header_timestamp_ns:'first',
    coordinate_basis:'SOURCE_XYZ_UNCHANGED',units:'m_ASSUMED',safety_decision_permitted:false,
    rail_model:'PAIR_MIDPOINT_SEGMENT_SOURCE_Z_UP_NO_EXTRAPOLATION',records:[{frame_index:frame.index,header_timestamp_ns:frame.header_timestamp_ns,source_frame:frame.source_frame,rails}]};
  const restored=G.manualRailsFromReview(payload,manifest,frame);
  assert.deepEqual(restored,rails);assert.notEqual(restored[0],rails[0]);
  assert.throws(()=>G.manualRailsFromReview({...payload,dataset:'other'},manifest,frame),/другому датасету/);
  assert.throws(()=>G.manualRailsFromReview({...payload,records:[{...payload.records[0],header_timestamp_ns:'other'}]},manifest,frame),/текущему кадру/);
  assert.throws(()=>G.manualRailsFromReview({...payload,safety_decision_permitted:true},manifest,frame),/Неподдерживаемый/);
});
test('object-candidate layer leaves the point-cloud view free of distance sprites',()=>{
  const source=fs.readFileSync(path.join(__dirname,'..','web','stage_2_review_layers.js'),'utf8');
  const start=source.indexOf('for(const o of objects){');
  const end=source.indexOf("$('object-info').textContent=descriptions.join",start);
  assert.ok(start>=0&&end>start,'test must inspect the reachable object-candidate render loop');
  assert.doesNotMatch(source.slice(start,end),/distanceLabel\(/,
    'object-candidate boxes must not add screen-covering distance labels to the scene');
});
test('distance labels are transparent numerals without a background plaque',()=>{
  const source=fs.readFileSync(path.join(__dirname,'..','web','stage_2_review_layers.js'),'utf8');
  const start=source.indexOf('function distanceLabel('),end=source.indexOf('function volume(',start);
  assert.ok(start>=0&&end>start);
  const label=source.slice(start,end);
  assert.doesNotMatch(label,/fillRect\(/);assert.match(label,/transparent:true/);
  assert.doesNotMatch(source.slice(end,end+700),/toFixed\(1\)\+' м\*'/);
});
