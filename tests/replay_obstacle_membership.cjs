// Development coverage audit; no annotations are passed to geometry or detector.
const fs=require('node:fs'),assert=require('node:assert/strict');
const A=require('../web/stage_2_auto_rails.js'),G=require('../web/stage_2_review_layers.js'),D=require('../web/stage_3_objects.js');
const railConfig=require('../web/stage_2_auto_rails_config.json'),objectConfig=require('../web/stage_3_objects_config.json');
const dir='artefacts/stage_2/player_doubleT_obstacle/',manifest=JSON.parse(fs.readFileSync(dir+'manifest.json'));
const annotations=require('../config/obstacle_annotations_development.json');
const reference=manifest.visualization_overlay.reference_cross_section;
assert.ok(reference,'explicit player reference profile required');
const margins={left:.5,right:.5,top:.5,bottom:.5};
const frames=[],controls=[],experiments=[];
for(const f of manifest.frames){
  const bytes=fs.readFileSync(dir+f.file),before=Buffer.from(bytes),raw=new Float32Array(bytes.buffer,bytes.byteOffset,bytes.length/4);
  const rails=A.detect(raw,railConfig),envelope=rails.rails.length?G.createEnvelope(G.railAxis(rails.rails),reference,margins):null;
  const result=D.detect(raw,objectConfig,f),objects=result.objects.map(o=>({id:o.id,point_count:o.point_count,
    assessment:G.assessComponent(raw,o.source_indices,envelope,o.possibly_roi_clipped)}));
  frames.push({index:f.index,header_timestamp_ns:f.header_timestamp_ns,source_frame:f.source_frame,rail_status:rails.status,
    supported_range:rails.diagnostics.forwardRange,objects});
  for(const mark of annotations.point_annotations.filter(e=>e.frame_index===f.index)){
    assert.equal(mark.header_timestamp_ns,f.header_timestamp_ns);assert.equal(mark.source_frame,f.source_frame);
    const matches=[];for(let i=0;i<raw.length;i+=3)if(['x','y','z'].every((k,j)=>raw[i+j]===mark.anchor_source_coordinates[k]))matches.push(i/3);
    const groups=result.objects.filter(o=>matches.some(i=>o.source_indices.includes(i)));
    controls.push({event_id:mark.event_id,index:f.index,supported_range:rails.diagnostics.forwardRange,
      groups:groups.map(o=>({id:o.id,nearest:o.nearest,assessment:objects.find(v=>v.id===o.id).assessment}))});
    for(const stationLength of [2,4,6,8]){
      const candidate=A.detect(raw,{...railConfig,forwardMin:0,stationLength});
      experiments.push({frame:f.index,stationLength,forwardMin:0,status:candidate.status,reason:candidate.reason,range:candidate.diagnostics.forwardRange});
    }
  }
  assert.ok(bytes.equals(before));
}
const counts={};for(const f of frames)for(const o of f.objects)counts[o.assessment.status]=(counts[o.assessment.status]||0)+1;
const summary={frame_count:frames.length,component_observations_by_status:counts,controls,source_buffers_changed:0,
  event_recall:null,fp_per_min:null,safety_decision_permitted:false};
const out='artefacts/stage_3/obstacle_membership';fs.mkdirSync(out,{recursive:true});
fs.writeFileSync(out+'/coverage.json',JSON.stringify({scope:'DEVELOPMENT_NOT_INDEPENDENT_TEST',railConfig,objectConfig,reference,margins,summary,experiments,frames},null,2));
console.log(JSON.stringify(summary,null,2));
