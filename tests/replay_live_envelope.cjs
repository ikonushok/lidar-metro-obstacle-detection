'use strict';
// Development-only replay and source-anchor check. Does not estimate recall/precision.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const G=require('../web/stage_2_review_layers.js'),A=require('../web/stage_2_auto_rails.js');
const C=require('../web/stage_3_live_envelope.js')(G);
const autoConfig=require('../web/stage_2_auto_rails_config.json'),config=require('../web/stage_3_live_envelope_config.json');
const annotations=require('../config/obstacle_annotations_development.json');
const root=path.resolve(__dirname,'..'),dir=path.join(root,'artefacts/stage_2/player_doubleT_obstacle');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'manifest.json')));
assert.equal(manifest.frames[0].header_timestamp_ns,annotations.first_header_timestamp_ns,'wrong source recording');
const indices=process.argv.includes('--all')?manifest.frames.map((_,i)=>i):[0,55,100,160,200];
const rows=[],anchors=[],times=[],margins={left:.5,right:.5,top:.5,bottom:.5};
const namedZone=n=>Object.keys(G.zones).find(k=>G.zones[k]===n);
for(const index of indices){
  const frame=manifest.frames[index],b=fs.readFileSync(path.join(dir,frame.file)),before=Buffer.from(b);
  const raw=new Float32Array(b.buffer,b.byteOffset,b.length/4),start=performance.now(),auto=A.detect(raw,autoConfig);
  const axis=auto.rail_pairs?.length>=2?G.curveRailAxis(auto.rail_pairs):null,
    envelope=G.createEnvelope(axis,manifest.visualization_overlay.reference_cross_section,margins);
  const result=C.analyze(raw,envelope,config,frame);times.push(performance.now()-start);
  assert.ok(before.equals(b),`mutated frame ${index}`);assert.equal(result.system_status,'UNKNOWN');assert.equal(result.safety_decision_permitted,false);
  const c=result.counts;assert.equal(c.core+c.margin+c.outside_reference+c.unknown,c.total);
  for(const name of ['core','margin'])if(result['nearest_'+name]){
    const p=result['nearest_'+name],i=p.source_index;assert.deepEqual(p.point,[raw[i*3],raw[i*3+1],raw[i*3+2]]);
  }
  rows.push({frame:index,header_timestamp_ns:frame.header_timestamp_ns,axis_range:auto.diagnostics?.forwardRange,
    status:result.status,counts:c,groups:result.clusters.length,grouping_status:result.grouping_status,
    nearest_core:result.nearest_core,nearest_margin:result.nearest_margin});
  for(const annotation of annotations.point_annotations.filter(a=>a.frame_index===index)){
    assert.equal(frame.header_timestamp_ns,annotation.header_timestamp_ns);assert.equal(frame.source_frame,annotation.source_frame);
    const p=['x','y','z'].map(k=>annotation.anchor_source_coordinates[k]),matched=[];
    for(let i=0;i<raw.length;i+=3)if(Math.hypot(raw[i]-p[0],raw[i+1]-p[1],raw[i+2]-p[2])<1e-6)matched.push(i/3);
    assert.ok(matched.length,'annotation is not a source return');
    const zone=G.classify(envelope,p);assert.ok(matched.every(i=>result.labels[i]===zone));
    // These two known anchors are outside this version's measured rail segment, not safe negatives.
    assert.equal(zone,G.zones.UNKNOWN);
    anchors.push({event:annotation.event_id,frame:index,header_timestamp_ns:frame.header_timestamp_ns,source_frame:frame.source_frame,
      source_match_count:matched.length,anchor:p,axis_range:auto.diagnostics?.forwardRange,zone:namedZone(zone),
      local:envelope?G.local(envelope.axis,p):null,independent_ground_truth:false,reason:'OUTSIDE_SUPPORTED_AXIS_INTERVAL'});
  }
}
times.sort((a,b)=>a-b);
const output={scope:'DEVELOPMENT_SINGLE_EXPORT_NO_INDEPENDENT_GROUND_TRUTH',config,autoConfig,margins,
  frame_count:indices.length,source_buffers_changed:0,frames_with_core_candidates:rows.filter(r=>r.counts.core>0).length,
  grouping_limited_frames:rows.filter(r=>r.grouping_status!=='COMPLETE').length,
  coverage_definition:'fraction of source returns in the longitudinal supported segment, not spatial visibility or recall',
  evaluated_return_fraction_minmax:[Math.min(...rows.map(r=>1-r.counts.unknown/r.counts.total)),Math.max(...rows.map(r=>1-r.counts.unknown/r.counts.total))],
  local_node_auto_plus_check_ms:{median:times[Math.floor(times.length*.5)],p95:times[Math.floor(times.length*.95)],max:times.at(-1)},
  anchors,frames:rows};
const outputDir=path.join(root,'artefacts/stage_3/live_envelope');fs.mkdirSync(outputDir,{recursive:true});
const file=path.join(outputDir,process.argv.includes('--all')?'development_full_replay.json':'development_sample.json');
fs.writeFileSync(file,JSON.stringify(output,null,2));
console.log(JSON.stringify({...output,frames:rows.filter(r=>[0,55,100,160,200].includes(r.frame)),artifact:file},null,2));
