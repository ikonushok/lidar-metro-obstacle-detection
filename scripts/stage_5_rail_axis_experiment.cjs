'use strict';
/*
 * Isolated Stage 5 comparison.  It neither imports nor changes runtime code.
 * Baseline is AutoRails' global straight consensus.  Candidate keeps exactly
 * the same station/ridge eligibility but selects one locally continuous chain
 * of paired ridges; it never extrapolates beyond observed pair stations.
 */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const AutoRails=require('../web/stage_2_auto_rails.js');
const G=require('../web/stage_2_review_layers.js');
const checker=require('../web/stage_3_live_envelope.js')(G);
const c=require('../web/stage_2_auto_rails_config.json');
const liveConfig=require('../web/stage_3_live_envelope_config.json');
const playerManifest=require('../artefacts/stage_2/player_doubleT_obstacle/manifest.json');
const manualRails=require('../artefacts/stage_3/manual_rail_reviews/rail_anchors_frame_168.json');

const root=path.resolve(__dirname,'..');
let out=null,repetitions=5;
if(require.main===module){
  out=path.resolve(process.argv[2]||path.join(root,'artefacts/stage_5/rail_axis_open_method'));
  if(fs.existsSync(out)) throw new Error(`output already exists: ${out}`);
  repetitions=Number(process.argv[3]||5);
  if(!Number.isInteger(repetitions)||repetitions<1||repetitions>20)throw new Error('repetitions must be an integer in [1,20]');
}
const quantile=(a,q)=>{if(!a.length)return NaN;const b=a.slice().sort((x,y)=>x-y);return b[Math.floor((b.length-1)*q)];};
const finite=p=>p.every(Number.isFinite);

function pairBins(raw){
  const stationCount=Math.ceil((c.forwardMax-c.forwardMin)/c.stationLength);
  const bins=Array.from({length:stationCount},(_,i)=>({s:c.forwardMin+(i+.5)*c.stationLength,points:[]}));
  for(let i=0;i<raw.length;i+=3){
    const x=raw[i],s=-raw[i+1],z=raw[i+2]; if(!Number.isFinite(x+s+z))throw new Error('NONFINITE_XYZ');
    if(s>=c.forwardMin&&s<c.forwardMax&&x>=c.lateralMin&&x<c.lateralMax)bins[Math.floor((s-c.forwardMin)/c.stationLength)].points.push([x,s,z]);
  }
  return bins.map(bin=>{
    const n=Math.ceil((c.lateralMax-c.lateralMin)/c.cellWidth),cells=Array.from({length:n},()=>[]);
    for(const p of bin.points)cells[Math.floor((p[0]-c.lateralMin)/c.cellWidth)].push(p);
    const floor=quantile(cells.filter(a=>a.length>=c.minCellPoints).map(a=>quantile(a.map(p=>p[2]),c.cellFloorQuantile)),c.floorQuantile);
    const filtered=cells.map(a=>a.filter(p=>p[2]>=floor-c.floorBandBelow&&p[2]<=floor+c.floorBandAbove));
    const heights=filtered.map(a=>a.length>=c.minCellPoints?quantile(a.map(p=>p[2]),c.headQuantile):NaN),peaks=[];
    for(let i=0;i<n;i++){
      if(!Number.isFinite(heights[i]))continue; const flank=[[],[]];
      for(let j=Math.ceil(c.flankMin/c.cellWidth);j<=Math.floor(c.flankMax/c.cellWidth);j++)for(let side=0;side<2;side++){
        const h=heights[i+(side?j:-j)];if(Number.isFinite(h))flank[side].push(h);
      }
      if(flank.some(a=>a.length<c.minFlankCells))continue;
      const prominence=Math.min(...flank.map(a=>heights[i]-quantile(a,.5)));
      if(prominence<c.minProminence||prominence>c.maxProminence)continue;
      const heads=filtered[i].filter(p=>p[2]>=heights[i]-c.headBand),x=quantile(heads.map(p=>p[0]),.5);
      const point=heads.reduce((a,p)=>Math.abs(p[0]-x)+Math.abs(p[1]-bin.s)*.01<Math.abs(a[0]-x)+Math.abs(a[1]-bin.s)*.01?p:a);
      peaks.push({x,z:heights[i],point,prominence});
    }
    peaks.sort((a,b)=>b.prominence-a.prominence);const chosen=[];
    for(const peak of peaks)if(chosen.every(prior=>Math.abs(peak.x-prior.x)>c.peakSeparation))chosen.push(peak);
    chosen.sort((a,b)=>a.x-b.x);const pairs=[];
    for(let a=0;a<chosen.length;a++)for(let b=a+1;b<chosen.length;b++){
      const left=chosen[a],right=chosen[b],width=right.x-left.x;
      if(width>=c.pairMin&&width<=c.pairMax&&Math.abs(right.z-left.z)<=c.maxCrossHeight)
        pairs.push({s:bin.s,l:left.x,r:right.x,lz:left.z,rz:right.z,left_xyz:[left.point[0],-left.point[1],left.point[2]],right_xyz:[right.point[0],-right.point[1],right.point[2]]});
    }
    return {s:bin.s,pairs};
  });
}

function localContinuity(raw){
  const bins=pairBins(raw),nodes=[];
  for(const bin of bins)for(const pair of bin.pairs)nodes.push({...pair,score:1,cost:0,previous:null});
  for(let i=0;i<nodes.length;i++)for(let j=0;j<i;j++){
    const a=nodes[j],b=nodes[i],gap=b.s-a.s;if(gap<=0||gap>c.maxGap)continue;
    const perM=Math.max(...['l','r','lz','rz'].map(k=>Math.abs(b[k]-a[k])/gap));
    if(perM>c.maxSlope)continue;
    const edge=perM/c.maxSlope+(gap-c.stationLength)/c.stationLength;
    if(a.score+1>b.score||(a.score+1===b.score&&a.cost+edge<b.cost)){b.score=a.score+1;b.cost=a.cost+edge;b.previous=a;}
  }
  const ends=nodes.filter(n=>n.score>=c.minStations).sort((a,b)=>b.score-a.score||a.cost-b.cost);
  if(!ends.length)return {status:'UNKNOWN',reason:nodes.length?'INSUFFICIENT_LOCALLY_CONTINUOUS_PAIR_SUPPORT':'INSUFFICIENT_PAIRED_RAIL_SUPPORT',rail_pairs:[],diagnostics:{pairStations:bins.filter(b=>b.pairs.length).length}};
  const best=ends[0],chain=[];for(let n=best;n;n=n.previous)chain.push(n);chain.reverse();
  const span=chain.at(-1).s-chain[0].s,coverage=chain.length/(span/c.stationLength+1);
  if(span<c.minSpan||coverage<c.minCoverage)return {status:'UNKNOWN',reason:'INSUFFICIENT_CONTIGUOUS_COVERAGE',rail_pairs:[],diagnostics:{pairStations:bins.filter(b=>b.pairs.length).length}};
  const runner=ends.find(n=>n!==best&&n.score>=best.score*c.ambiguityRatio&&Math.abs((n.l+n.r-best.l-best.r)/2)>c.pairMin/2);
  if(runner)return {status:'UNKNOWN',reason:'AMBIGUOUS_LOCAL_CONTINUITY_PATH',rail_pairs:[],diagnostics:{pairStations:bins.filter(b=>b.pairs.length).length}};
  return {status:'AUTO_HYPOTHESIS',reason:'PAIRED_RAISED_LOCAL_CONTINUITY_PATH',rail_pairs:chain.map(p=>({source_s_m:p.s,left_xyz:p.left_xyz,right_xyz:p.right_xyz})),diagnostics:{pairStations:bins.filter(b=>b.pairs.length).length,supportedStations:chain.length,forwardRange:[chain[0].s,chain.at(-1).s],localCost:best.cost}};
}

function axisErrors(pairs){
  if(!pairs.length)return null;const anchors=[[manualRails.rails[0],manualRails.rails[1]],[manualRails.rails[2],manualRails.rails[3]]];
  const rows=[];
  for(const pair of anchors){
    const mid=pair[0].map((v,i)=>(v+pair[1][i])/2),s=-mid[1];
    const hit=pairs.reduce((best,p)=>Math.abs(p.source_s_m-s)<Math.abs(best.source_s_m-s)?p:best,pairs[0]);
    const estimate=hit.left_xyz.map((v,i)=>(v+hit.right_xyz[i])/2);
    const supported=s>=pairs[0].source_s_m&&s<=pairs.at(-1).source_s_m;
    rows.push({anchor_s_m:s,matched_station_s_m:hit.source_s_m,support_status:supported?'SUPPORTED_NEAREST_STATION':'OUTSIDE_SUPPORTED_PATH',lateral_error_x_m:supported?estimate[0]-mid[0]:null,vertical_error_z_m:supported?estimate[2]-mid[2]:null,station_offset_m:hit.source_s_m-s});
  }
  const supported=rows.filter(r=>r.support_status==='SUPPORTED_NEAREST_STATION');
  return {anchors:rows,max_abs_lateral_m:supported.length?Math.max(...supported.map(r=>Math.abs(r.lateral_error_x_m))):null,max_abs_vertical_m:supported.length?Math.max(...supported.map(r=>Math.abs(r.vertical_error_z_m))):null};
}

const newRows=fs.readFileSync(path.join(root,'artefacts/stage_5/raw_new_data/frames.jsonl'),'utf8').trim().split('\n').map(JSON.parse).sort((a,b)=>a.index-b.index);
const cases=[...newRows.map(r=>({id:`new_data_${r.index}`,index:r.index,dataset:'new_data',kind:({0:'straight',5500:'curve',1150:'sparse_far_support',10000:'baseline_axis_loss_unresolved_geometry',1054:'baseline_axis_loss_unresolved_geometry'})[r.index]||'other',file:path.join(root,'artefacts/stage_5/raw_new_data',`frame_${String(r.index).padStart(5,'0')}.xyzf`),source_frame:r.input.frame,stamp:r.header_timestamp_ns,manual_axis_anchors:false})),
  {id:'doubleT_0168_manual_axis',index:168,dataset:'doubleT_obstacle',kind:'manual_axis_anchor',file:path.join(root,'artefacts/stage_2/player_doubleT_obstacle/frames/frame_0168.xyzf'),source_frame:'lidar_livox',stamp:manualRails.header_timestamp_ns,manual_axis_anchors:true},
  {id:'doubleT_0055_obstacle_anchor',index:55,dataset:'doubleT_obstacle',kind:'obstacle_anchor',file:path.join(root,'artefacts/stage_2/player_doubleT_obstacle/frames/frame_0055.xyzf'),source_frame:'lidar_livox',stamp:playerManifest.frames[55].header_timestamp_ns,manual_axis_anchors:false,annotations:[{event_id:'OBS-002',point:[-1.3050981760025024,-56.34038162231445,-1.1873599290847778]}]},
  {id:'doubleT_0160_obstacle_and_infrastructure',index:160,dataset:'doubleT_obstacle',kind:'obstacle_and_infrastructure',file:path.join(root,'artefacts/stage_2/player_doubleT_obstacle/frames/frame_0160.xyzf'),source_frame:'lidar_livox',stamp:playerManifest.frames[160].header_timestamp_ns,manual_axis_anchors:false,annotations:[{event_id:'OBS-003',point:[1.791092872619629,-3.4157321453094482,-0.5219449400901794]}]}];

function annotatedMembership(raw,live,annotations=[]){
  if(!live)return annotations.map(a=>({event_id:a.event_id,status:'UNKNOWN_NO_AXIS'}));
  const names=['UNKNOWN','CORE','MARGIN','OUTSIDE_REFERENCE'];
  return annotations.map(a=>{let hit=-1;for(let i=0;i<raw.length;i+=3)if(Math.hypot(raw[i]-a.point[0],raw[i+1]-a.point[1],raw[i+2]-a.point[2])<1e-6){hit=i/3;break;}
    return {event_id:a.event_id,source_return_found:hit>=0,status:hit>=0?names[live.labels[hit]]:'MISSING_SOURCE_RETURN'};});
}

function runMethod(name,raw,identity,manual,annotations){
  const start=process.hrtime.bigint();const result=name==='baseline'?AutoRails.detect(raw,c):localContinuity(raw);
  let live=null,axis=null;if(result.rail_pairs.length>=2){axis=G.curveRailAxis(result.rail_pairs);const envelope=G.createEnvelope(axis,playerManifest.visualization_overlay.reference_cross_section,{left:.5,right:.5,top:.5,bottom:.5});live=checker.analyze(raw,envelope,liveConfig,identity,'CURVE_AXIS_SUPPORTED');}
  const elapsed=Number(process.hrtime.bigint()-start)/1e6;
  return {status:result.status,reason:result.reason,rail_pairs:result.rail_pairs.length,rail_pairs_source_xyz:result.rail_pairs,supported_length_m:axis?.length3??0,diagnostics:result.diagnostics,axis_error_manual_anchor:manual?axisErrors(result.rail_pairs):null,intersection:live?{status:live.status,counts:live.counts,ungrouped_candidate_points:live.ungrouped_candidate_points,core_observed:live.geometric_candidate_present,unknown_fraction:live.counts.unknown/live.counts.total,annotated_points:annotatedMembership(raw,live,annotations)}: {status:'UNKNOWN',counts:{total:raw.length/3,unknown:raw.length/3},unknown_fraction:1,annotated_points:annotatedMembership(raw,null,annotations)},compute_ms:elapsed};
}
function repeatedMethod(name,raw,identity,manual,annotations){
  const runs=Array.from({length:repetitions},()=>runMethod(name,raw,identity,manual,annotations));
  const canonical=JSON.stringify({...runs[0],compute_ms:0});
  assert.ok(runs.every(run=>JSON.stringify({...run,compute_ms:0})===canonical),'non-deterministic geometry result');
  const samples=runs.map(run=>run.compute_ms).sort((a,b)=>a-b),middle=Math.floor(samples.length/2);
  return {...runs[0],compute_ms:{samples,median:samples[middle],p95:samples[Math.floor((samples.length-1)*.95)],max:samples.at(-1)}};
}
module.exports={localContinuity,detectBaseline:(raw)=>AutoRails.detect(raw,c),autoRailsConfig:c};

if(require.main===module){
const records=[];
for(const item of cases){
  const bytes=fs.readFileSync(item.file),hash=crypto.createHash('sha256').update(bytes).digest('hex'),raw=new Float32Array(bytes.buffer,bytes.byteOffset,bytes.length/4);assert.equal(raw.length%3,0);assert.ok(finite([raw[0],raw[1],raw[2]]));
  const identity={index:item.index,source_frame:item.source_frame,header_timestamp_ns:item.stamp};const baseline=repeatedMethod('baseline',raw,identity,item.manual_axis_anchors,item.annotations),candidate=repeatedMethod('candidate',raw,identity,item.manual_axis_anchors,item.annotations);
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),hash,'source mutation');
  for(const result of [baseline,candidate])assert.ok(result.intersection.unknown_fraction>=0&&result.intersection.unknown_fraction<=1);
  records.push({...item,file:path.relative(root,item.file).replaceAll('\\','/'),point_count:raw.length/3,sha256:hash,baseline,candidate,source_mutations:0});
}
// Separately labelled synthetic check: a single low return is appended only in memory
// inside a supported segment. It verifies preservation through the common checker,
// not the observability of a real obstacle.
{
  const source=path.join(root,'artefacts/stage_2/player_doubleT_obstacle/frames/frame_0168.xyzf'),bytes=fs.readFileSync(source),raw=new Float32Array(bytes.buffer,bytes.byteOffset,bytes.length/4);
  const base=AutoRails.detect(raw,c),alternative=localContinuity(raw);assert.deepEqual(alternative.rail_pairs,base.rail_pairs,'synthetic comparison requires identical supported axis');
  const axis=G.curveRailAxis(base.rail_pairs),point=G.world(axis,Math.min(5,axis.length/2),0,.10),augmented=new Float32Array(raw.length+3);augmented.set(raw);augmented.set(point,raw.length);
  const item={id:'synthetic_low_singleton_inside_supported',index:168,dataset:'synthetic',kind:'low_single_return_inside_supported_axis',synthetic:true,file:'IN_MEMORY_APPEND_ONLY',source_frame:'lidar_livox',stamp:manualRails.header_timestamp_ns,annotations:[{event_id:'SYNTHETIC_LOW_SINGLETON',point}]};
  const identity={index:item.index,source_frame:item.source_frame,header_timestamp_ns:item.stamp},baseline=repeatedMethod('baseline',augmented,identity,false,item.annotations),candidate=repeatedMethod('candidate',augmented,identity,false,item.annotations);
  assert.equal(baseline.intersection.annotated_points[0].status,'CORE');assert.equal(candidate.intersection.annotated_points[0].status,'CORE');
  records.push({...item,point_count:augmented.length/3,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),baseline,candidate,source_mutations:0});
}
const summary={format:'stage_5_rail_axis_method_comparison_v1',scope:'SINGLE_FRAME_OFFLINE_DEVELOPMENT_NOT_CALIBRATION_OR_RUNTIME',candidate:'local dynamic-programming continuity path over the same per-station paired ridge eligibility; no global straight regression, no extrapolation, no multi-frame accumulation',baseline:'existing AutoRails global linear consensus plus unchanged CurveRailAxis/envelope checker',configs:{autoRails:c,liveEnvelope:liveConfig,reference:playerManifest.visualization_overlay.reference_cross_section,margins:{left:.5,right:.5,top:.5,bottom:.5}},hardware:{platform:process.platform,arch:process.arch,node:process.version,cpus:require('node:os').cpus()[0]?.model||'unknown'},timing_repetitions:repetitions,measurement_boundary:'process monotonic time: pair extraction/axis/envelope membership only; excludes file I/O, PointCloud2 decode, ROS2, publish, queue and viewer',quality_metrics:null,quality_reason:'No calibrated rail ground truth or complete obstacle/infrastructure labels. Manual rail anchors are source-return-verified development checks only; no precision/recall/FP computed.',records};
fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'comparison.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify({output:out,cases:records.map(r=>({id:r.id,baseline:r.baseline.status,candidate:r.candidate.status,baseline_m:r.baseline.supported_length_m,candidate_m:r.candidate.supported_length_m}))},null,2));
}
