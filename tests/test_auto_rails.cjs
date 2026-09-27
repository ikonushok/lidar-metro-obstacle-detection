const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const test=require('node:test'),assert=require('node:assert/strict');
const A=require('../web/stage_2_auto_rails.js'),G=require('../web/stage_2_review_layers.js');
const config=require('../web/stage_2_auto_rails_config.json');
function fixture({center=.6,yaw=.025,grade=-.018,rails=[-.8,.8],curve=0,gap=false,obstacle=false}={}){
  const data=[];
  for(let s=3.1;s<53;s+=.27)for(let l=-3;l<=3;l+=.025){
    const ridge=(!gap||s<12||s>45)&&rails.some(r=>Math.abs(l-r)<.05);
    const x=center+yaw*s+curve*(s-28)**2+l,z=-2+grade*s+.015*l+(ridge?.17:0);
    data.push(x,-s,z+.001*Math.sin(s*17+l*11));
  }
  if(obstacle)data.push(center+yaw*20,-20,-2+grade*20+.02);
  return new Float32Array(data);
}
test('automatic pair fits translated/yawed/sloped rails and preserves every raw byte',()=>{
  const raw=fixture({obstacle:true}),before=Buffer.from(raw.buffer).toString('hex'),r=A.detect(raw,config);
  assert.equal(r.status,'AUTO_HYPOTHESIS');assert.equal(r.safety_decision_permitted,false);
  assert.equal(r.rail_pairs.length,r.diagnostics.supportedStations);
  assert.deepEqual(r.support,r.rail_pairs.flatMap(pair=>[pair.left_xyz,pair.right_xyz]));
  assert.ok(r.rail_pairs.every((pair,index)=>Number.isFinite(pair.source_s_m)&&(!index||pair.source_s_m>r.rail_pairs[index-1].source_s_m)));
  const axis=G.railAxis(r.rails);
  for(const p of [axis.a,axis.b]){
    assert.ok(Math.abs(p[0]-(.6+.025*-p[1]))<.04);
    assert.ok(Math.abs(p[2]-(-2-.018*-p[1]+.17))<.025);
  }
  assert.equal(Buffer.from(raw.buffer).toString('hex'),before);
  const source=new Set();for(let i=0;i<raw.length;i+=3)source.add([raw[i],raw[i+1],raw[i+2]].join(','));
  assert.ok(r.support.every(p=>source.has(p.join(','))),'all displayed support markers are real source points');
  G.rings(axis,{left:-1.4,right:1.4,bottom:0,top:3.7}).forEach((ring,i)=>{
    const midpoint=ring[0].map((v,j)=>(v+ring[1][j])/2),expected=G.world(axis,axis.length*i/20,0,0);
    midpoint.forEach((v,j)=>assert.ok(Math.abs(v-expected[j])<1e-9));
  });
});
test('plane, single rail, disconnected short runs and strong curve never invent a fallback',()=>{
  for(const options of [{rails:[]},{rails:[-.8]},{gap:true},{curve:.03}]){
    const r=A.detect(fixture(options),config);assert.equal(r.status,'UNKNOWN',JSON.stringify(options));assert.deepEqual(r.rails,[]);assert.deepEqual(r.rail_pairs,[]);
  }
});
test('two competing pairs are explicitly ambiguous',()=>{
  const r=A.detect(fixture({center:0,rails:[-1.6,0,1.6]}),config);
  assert.equal(r.status,'UNKNOWN');assert.equal(r.reason,'AMBIGUOUS_RAIL_PAIRS');
});
test('empty, invalid XYZ and missing/invalid configuration fail closed',()=>{
  assert.equal(A.detect(fixture(),{...config,maxSeedPairs:1}).reason,'SEARCH_BUDGET_EXCEEDED');
  assert.equal(A.detect(new Float32Array(),config).status,'UNKNOWN');
  for(const values of [[NaN,0,0],[0,Infinity,0],[0,0]])assert.equal(A.detect(new Float32Array(values),config).status,'UNKNOWN');
  for(const c of [undefined,{}, {...config,cellWidth:0},{...config,minCoverage:2},{...config,heightTolerance:0}])
    assert.equal(A.detect(fixture(),c).reason,'INVALID_SEARCH_PARAMETERS');
});
test('real development frames 0/100/200: bounded pair hypothesis, immutable buffers (not rail ground truth)',()=>{
  const dir=path.resolve(__dirname,'../artefacts/stage_2/player_doubleT_obstacle');
  const m=JSON.parse(fs.readFileSync(path.join(dir,'manifest.json')));
  for(const i of [0,100,200]){
    const b=fs.readFileSync(path.join(dir,m.frames[i].file)),before=Buffer.from(b);
    const p=new Float32Array(b.buffer,b.byteOffset,b.length/4),start=performance.now(),r=A.detect(p,config);
    assert.equal(r.status,'AUTO_HYPOTHESIS');assert.ok(b.equals(before));
    assert.ok(r.diagnostics.forwardRange[1]<=config.forwardMax);assert.ok(r.diagnostics.rms<=config.maxRms);
    console.log(JSON.stringify({frame:i,rails:r.rails,diagnostics:r.diagnostics,elapsed_ms:performance.now()-start}));
  }
});
test('review lifecycle: auto defaults, UNKNOWN clears geometry, raw-only persists and manual does not borrow auto',()=>{
  const THREE=require('../artefacts/stage_2/player_doubleT_obstacle/vendor/three.min.js');
  const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,{value:'',checked:false,disabled:false,
    textContent:'',replaceChildren(){},appendChild(){}});return elements.get(id);};
  element('axis-mode').value='auto';for(const id of ['axis-layer','rail-grid','train-layer'])element(id).checked=true;
  for(const side of ['left','right','top','bottom'])element('margin-'+side).value='.5';
  const document={getElementById:element,createElement:tag=>tag==='canvas'?{width:0,height:0,
    getContext:()=>({fillRect(){},fillText(){}})}:{textContent:''}};
  const scene=new THREE.Scene(),raw=fixture();let displayed=raw;
  const host={scene,canvas:{style:{},addEventListener(){}},pause(){},cloud:()=>({}),display:p=>displayed=p,colors(){}};
  const context=vm.createContext({THREE,document,AutoRails:A,console,Float32Array});
  vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../web/stage_2_review_layers.js'),'utf8'),context);
  const ui=context.createReviewLayers(host);
  const meta={visualization_overlay:{source_axis_assumption:{longitudinal_axis:'y',longitudinal_sign:-1,lateral_axis:'x',vertical_axis:'z',source_units:'m'},
    reference_cross_section:{lateral_extent_m:{min:-1.4,max:1.4},vertical_extent_above_rail_m:{min:0,max:3.7}}}};
  const frame=index=>({index,source_frame:'test',header_timestamp_ns:String(index)});
  ui.setFrame(frame(0),raw,meta,config);
  assert.match(element('axis-info').textContent,/Автоматическая гипотеза/);assert.equal(element('train-layer').disabled,false);
  assert.ok(scene.children[0].children.length>0);assert.equal(displayed,raw);
  ui.unload();assert.equal(scene.children[0].children.length,0);
  const empty=fixture({rails:[]});ui.setFrame(frame(1),empty,meta,config);
  assert.match(element('auto-status').textContent,/UNKNOWN/);assert.equal(element('train-layer').disabled,true);
  assert.equal(scene.children[0].children.length,0);assert.equal(displayed,empty);
  ui.setFrame(frame(2),raw,meta,config);assert.match(element('axis-info').textContent,/Автоматическая гипотеза/);
  element('raw-only').onclick();ui.setFrame(frame(3),raw,meta,config);
  assert.equal(element('axis-mode').value,'off');assert.equal(scene.children[0].children.length,0);assert.equal(displayed,raw);
  element('axis-mode').value='manual';element('axis-mode').onchange();
  assert.match(element('auto-status').textContent,/UNKNOWN/);assert.equal(scene.children[0].children.length,0);
  element('axis-mode').value='auto';element('axis-mode').onchange();assert.ok(scene.children[0].children.length>0);
  ui.setFrame(frame(4),raw,{visualization_overlay:{}},config);
  assert.match(element('auto-status').textContent,/UNKNOWN/);assert.equal(scene.children[0].children.length,0);
  ui.setFrame(frame(5),raw,meta,null);assert.match(element('auto-status').textContent,/UNKNOWN/);
  assert.equal(scene.children[0].children.length,0);
});
