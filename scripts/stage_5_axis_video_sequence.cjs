'use strict';
// Visual-review only: no timing, no envelope verdict, no change to the fixed statistics set.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {localContinuity,detectBaseline}=require('./stage_5_rail_axis_experiment.cjs');
const [rawDir,output,...indices]=process.argv.slice(2);
if(!rawDir||!output||!indices.length)throw new Error('Usage: node scripts/stage_5_axis_video_sequence.cjs <raw-dir> <output.json> <indices...>');
const frames=indices.map(value=>{
  const index=Number(value);if(!Number.isInteger(index)||index<0)throw new Error(`invalid index ${value}`);
  const file=path.join(rawDir,`frame_${String(index).padStart(5,'0')}.xyzf`),bytes=fs.readFileSync(file);
  const raw=new Float32Array(bytes.buffer,bytes.byteOffset,bytes.length/4);
  if(raw.length%3)throw new Error(`not xyzf: ${file}`);
  const baseline=detectBaseline(raw),candidate=localContinuity(raw);
  return {index,file:path.relative(process.cwd(),file).replaceAll('\\','/'),point_count:raw.length/3,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),baseline:{status:baseline.status,reason:baseline.reason,rail_pairs:baseline.rail_pairs},candidate:{status:candidate.status,reason:candidate.reason,rail_pairs:candidate.rail_pairs}};
});
fs.writeFileSync(output,JSON.stringify({format:'stage_5_visual_sequence_v1',scope:'VISUAL_REVIEW_ONLY_NOT_STATISTICAL_OR_RUNTIME',coordinate_basis:'SOURCE_XYZ_UNCHANGED',frames},null,2));
console.log(JSON.stringify({output,frames:frames.map(f=>({index:f.index,baseline:f.baseline.status,candidate:f.candidate.status,baseline_pairs:f.baseline.rail_pairs.length,candidate_pairs:f.candidate.rail_pairs.length}))},null,2));
