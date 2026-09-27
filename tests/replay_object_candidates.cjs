// Development-only descriptive replay. Annotations are read only by this evaluator.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const D=require('../web/stage_3_objects.js'),config=require('../web/stage_3_objects_config.json');
const dir='artefacts/stage_2/player_doubleT_obstacle/',m=JSON.parse(fs.readFileSync(dir+'manifest.json'));
const annotations=require('../config/obstacle_annotations_development.json'),all=process.argv.includes('--all');
const indices=all?m.frames.map(f=>f.index):[0,55,100,160,200],frames=[],times=[];
for(const index of indices){const f=m.frames[index],b=fs.readFileSync(dir+f.file),before=Buffer.from(b);
  const raw=new Float32Array(b.buffer,b.byteOffset,b.length/4),t=performance.now(),r=D.detect(raw,config,f);times.push(performance.now()-t);
  assert.ok(b.equals(before));const anchorChecks=[];
  for(const e of annotations.point_annotations.filter(a=>a.frame_index===index)){
    assert.equal(e.header_timestamp_ns,f.header_timestamp_ns);assert.equal(e.source_frame,f.source_frame);
    const matches=[];for(let i=0;i<raw.length;i+=3)if(['x','y','z'].every((k,j)=>raw[i+j]===e.anchor_source_coordinates[k]))matches.push(i/3);
    const objects=r.objects.filter(o=>matches.some(i=>o.source_indices.includes(i)));
    anchorChecks.push({event:e.event_id,source_matches:matches.length,matched_ids:objects.map(o=>o.id),
      nearest_m:objects.map(o=>o.nearest.distance_m),criterion:'EXACT_SOURCE_INDEX_IN_COMPONENT_NOT_EVENT_RECALL'});
  }
  frames.push({...D.summary(r),processing_ms:times[times.length-1],anchor_checks:anchorChecks});
}
times.sort((a,b)=>a-b);
const report={scope:'single development run; other candidates unreviewed, NOT FP count',config,frames,
  summary:{frames:frames.length,source_buffers_changed:0,objects_min:Math.min(...frames.map(f=>f.objects.length)),
    objects_max:Math.max(...frames.map(f=>f.objects.length)),processing_ms_p95:times[Math.floor(times.length*.95)],
    anchor_checks:frames.flatMap(f=>f.anchor_checks),event_recall:null,fp_per_min:null}};
const out='artefacts/stage_3/object_candidates';fs.mkdirSync(out,{recursive:true});
fs.writeFileSync(path.join(out,all?'full_replay.json':'sample_replay.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify(report.summary,null,2));
