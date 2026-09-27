'use strict';
// Reuse the existing frame-local rails/envelope algorithms on a bounded export.
// Results are development hypotheses, never motion estimates or ground truth.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const G=require('../web/stage_2_review_layers.js'),A=require('../web/stage_2_auto_rails.js');
const C=require('../web/stage_3_live_envelope.js')(G);
const autoConfig=require('../web/stage_2_auto_rails_config.json');
const liveConfig=require('../web/stage_3_live_envelope_config.json');
const directory=path.resolve(process.argv[2]||'artefacts/stage_3/new_data_transfer/baseline_1050_1150');
const outputDirectory=path.resolve(process.argv[3]||directory);
const source=fs.readFileSync(path.join(directory,'frames.jsonl'),'utf8');
const records=source.trim().split('\n').map(line=>JSON.parse(line));
const inputSummary=JSON.parse(fs.readFileSync(path.join(directory,'summary.json')));
assert.equal(records.length,inputSummary.frame_count,'incomplete offline export');
const originalManifest=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../artefacts/stage_2/player_doubleT_obstacle/manifest.json')));
const reference=originalManifest.visualization_overlay.reference_cross_section;
// Unchanged UI development margins; distinct from Python warning-layer offsets.
const margins={left:.5,right:.5,top:.5,bottom:.5};
const rows=[],times=[];
for(const record of records){
  assert.equal(record.input.frame,'hesai_lidar');
  const b=fs.readFileSync(path.join(directory,`frame_${String(record.index).padStart(5,'0')}.xyzf`));
  assert.equal(b.length,record.input.nonzero_finite*12);
  const before=Buffer.from(b),raw=new Float32Array(b.buffer,b.byteOffset,b.length/4);
  // Epoch nanoseconds must come from a JSON string, never a rounded JS number.
  const stamp=record.header_timestamp_ns||record.result?.header_timestamp_ns;
  assert.equal(typeof stamp,'string','lossless source header timestamp required');
  const identity={index:record.index,source_frame:record.input.frame,header_timestamp_ns:stamp};
  const started=performance.now(),auto=A.detect(raw,autoConfig);
  const axis=auto.rail_pairs?.length>=2?G.curveRailAxis(auto.rail_pairs):null;
  const envelope=G.createEnvelope(axis,reference,margins);
  const curveAxisStatus=axis?.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ'?'CURVE_AXIS_SUPPORTED':'MISSING_CURVE_AXIS';
  const result=C.analyze(raw,envelope,liveConfig,identity,curveAxisStatus),elapsed=performance.now()-started;
  assert.ok(before.equals(b),'source XYZ mutation');
  assert.equal(result.system_status,'UNKNOWN');assert.equal(result.safety_decision_permitted,false);
  const counts=result.counts;
  assert.equal(counts.core+counts.margin+counts.outside_reference+counts.unknown,counts.total);
  for(const kind of ['core','margin']){
    const nearest=result['nearest_'+kind];
    if(nearest)assert.deepEqual(nearest.point,Array.from(raw.slice(nearest.source_index*3,nearest.source_index*3+3)));
  }
  times.push(elapsed);
  rows.push({index:record.index,bag_offset_seconds:record.bag_offset_seconds,header_timestamp_ns:identity.header_timestamp_ns,
    auto,live:C.summary(result),processing_ms:elapsed});
}
const countBy=fn=>rows.reduce((a,r)=>{const k=fn(r);a[k]=(a[k]||0)+1;return a;},{});
const range=values=>values.length?[Math.min(...values),Math.max(...values)]:null;
const ranges=rows.map(r=>r.auto.diagnostics?.forwardRange).filter(Boolean);
times.sort((a,b)=>a-b);
const summary={scope:'DEVELOPMENT_WINDOW_AUTO_RAILS_AND_LOCAL_ENVELOPE_NOT_QUALITY_OR_ODOMETRY',
  frame_count:rows.length,first_index:records[0].index,last_index:records.at(-1).index,
  input_jsonl_sha256:crypto.createHash('sha256').update(source).digest('hex'),
  source_mutations:0,system_status:'UNKNOWN',safety_decision_permitted:false,
  auto_status_counts:countBy(r=>r.auto.status),live_status_counts:countBy(r=>r.live.status),
  grouping_status_counts:countBy(r=>r.live.grouping_status),
  supported_forward_start_minmax:range(ranges.map(r=>r[0])),supported_forward_end_minmax:range(ranges.map(r=>r[1])),
  evaluated_return_fraction_minmax:range(rows.map(r=>1-r.live.counts.unknown/r.live.counts.total)),
  local_node_auto_plus_check_ms:{median:times[Math.floor(times.length*.5)],p95:times[Math.floor(times.length*.95)],max:times.at(-1)},
  quality_metrics:null,quality_reason:'NO_EVENT_OR_INFRASTRUCTURE_GROUND_TRUTH',
  reference_source:'existing first-dataset player manifest; dimensions retained as unverified hypothesis',
  reference,margins,autoConfig,liveConfig};
fs.mkdirSync(outputDirectory,{recursive:true});
fs.writeFileSync(path.join(outputDirectory,'visual_replay.json'),JSON.stringify({summary,frames:rows},null,2));
console.log(JSON.stringify(summary,null,2));
