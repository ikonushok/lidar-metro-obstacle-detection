/* Every observed core return is an immediate intrusion candidate in the exact
   envelope used by the renderer. No source mutation or CLEAR state. */
'use strict';
function createLiveEnvelopeChecker(G) {
  const Z=G.zones;
  const validConfig=c=>c&&Number.isFinite(c.voxel_size_m)&&c.voxel_size_m>=.05&&c.voxel_size_m<=2&&
    Number.isInteger(c.min_cluster_points)&&c.min_cluster_points>=1&&c.min_cluster_points<=10000&&
    Number.isInteger(c.max_voxels)&&c.max_voxels>=1&&c.max_voxels<=200000;
  function analyze(raw,envelope,config,identity,curveAxisStatus=null) {
    const configSnapshot=config?Object.freeze({...config}):null;
    const total=raw.length/3,frame={frame_index:identity?.index,header_timestamp_ns:identity?.header_timestamp_ns,source_frame:identity?.source_frame};
    const empty=reason=>({format:'lidar-live-envelope-v1',...frame,status:'UNKNOWN',system_status:'UNKNOWN',reason,
      curve_axis_status:curveAxisStatus,
      straight_fallback_used:false,curve_axis_diagnostics:null,
      safety_decision_permitted:false,geometric_candidate_present:null,intrusion_candidate_present:null,
      margin_return_present:null,envelope,config:configSnapshot,
      counts:{total,core:0,margin:0,outside_reference:0,unknown:total},nearest_core:null,nearest_margin:null,
      labels:new Uint8Array(Math.floor(total)),clusters:[],grouping_status:'UNAVAILABLE',ungrouped_candidate_points:0});
    if(!Number.isInteger(total)||!raw.every(Number.isFinite))return empty('INVALID_XYZ');
    if(!Number.isInteger(frame.frame_index)||frame.frame_index<0||typeof frame.header_timestamp_ns!=='string'||
      !frame.header_timestamp_ns.length||typeof frame.source_frame!=='string'||!frame.source_frame.length)
      return empty('MISSING_FRAME_IDENTITY');
    if(!envelope)return empty(curveAxisStatus==='MISSING_CURVE_AXIS'?'MISSING_CURVE_AXIS':'MISSING_CURRENT_ENVELOPE');
    if(!G.isEnvelope(envelope))return empty('INVALID_CURRENT_ENVELOPE');
    if(!validConfig(config))return empty('INVALID_CANDIDATE_CONFIG');
    const result=empty('NO_RETURNS_INTERSECT_REFERENCE_NOT_CLEAR');
    result.curve_axis_status=envelope.axis.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ'?'CURVE_AXIS_SUPPORTED':curveAxisStatus;
    if(envelope.axis.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ')result.curve_axis_diagnostics={rail_pair_count:envelope.axis.rail_pairs.length,
      segment_count:envelope.axis.segments.length,supported_path_length_m:envelope.axis.length,supported_path_length_3d_m:envelope.axis.length3};
    result.geometric_candidate_present=false;result.intrusion_candidate_present=false;result.margin_return_present=false;result.counts.unknown=0;
    const cells=new Map(),counters=['unknown','core','margin','outside_reference'];let budgetExceeded=false;
    for(let i=0;i<total;i++){
      const p=[raw[i*3],raw[i*3+1],raw[i*3+2]],v=G.local(envelope.axis,p),zone=G.classifyLocal(envelope,v);
      result.labels[i]=zone;result.counts[counters[zone]]++;
      if(zone!==Z.CORE&&zone!==Z.MARGIN)continue;
      result.geometric_candidate_present=true;
      if(zone===Z.CORE)result.intrusion_candidate_present=true;
      else result.margin_return_present=true;
      const key=zone===Z.CORE?'nearest_core':'nearest_margin',distance=Math.hypot(...p);
      if(!result[key]||distance<result[key].distance_from_source_origin_m)result[key]={source_index:i,point:p,
        distance_from_source_origin_m:distance,station_from_segment_start_m:Number.isFinite(v.path_s_3_m)?v.path_s_3_m:
          Math.max(0,Math.min(envelope.axis.length,v.s))*Math.hypot(1,envelope.axis.dz/envelope.axis.length),
        lateral_m:v.l,height_above_axis_m:v.h,units:'m_ASSUMED'};
      if(budgetExceeded)continue;
      // Partition by zone: margin infrastructure cannot connect two core components.
      const xyz=p.map(a=>Math.floor(a/config.voxel_size_m)),voxelKey=[zone,...xyz].join(',');
      if(!cells.has(voxelKey)){
        if(cells.size>=config.max_voxels){budgetExceeded=true;cells.clear();continue;}
        cells.set(voxelKey,{xyz,zone,indices:[],visited:false});
      }cells.get(voxelKey).indices.push(i);
    }
    if(result.geometric_candidate_present){result.status=result.counts.core?'OBSERVED_CORE_INTRUSION_CANDIDATE':'OBSERVED_MARGIN_RETURN';
      result.reason=result.counts.core?'ANY_OBSERVED_RETURN_INSIDE_SUPPORTED_CORE_IS_INTRUSION_CANDIDATE':'OBSERVED_RETURN_IN_CLEARANCE_MARGIN';}
    result.grouping_status=budgetExceeded?'LIMIT_EXCEEDED_POINTS_RETAINED':'COMPLETE';
    if(budgetExceeded){result.ungrouped_candidate_points=result.counts.core+result.counts.margin;return result;}
    for(const cell of cells.values()){
      if(cell.visited)continue;
      const queue=[cell],indices=[];cell.visited=true;
      for(let j=0;j<queue.length;j++){
        const current=queue[j];for(const i of current.indices)indices.push(i);
        for(let x=-1;x<=1;x++)for(let y=-1;y<=1;y++)for(let z=-1;z<=1;z++){
          const next=cells.get([current.zone,current.xyz[0]+x,current.xyz[1]+y,current.xyz[2]+z].join(','));
          if(next&&!next.visited){next.visited=true;queue.push(next);}
        }
      }
      if(indices.length<config.min_cluster_points){result.ungrouped_candidate_points+=indices.length;continue;}
      const bounds={x:{min:Infinity,max:-Infinity},y:{min:Infinity,max:-Infinity},z:{min:Infinity,max:-Infinity}};
      let nearest=null;
      for(const i of indices){const p=[raw[i*3],raw[i*3+1],raw[i*3+2]],distance=Math.hypot(...p);
        for(let j=0;j<3;j++){const b=bounds['xyz'[j]];b.min=Math.min(b.min,p[j]);b.max=Math.max(b.max,p[j]);}
        if(!nearest||distance<nearest.distance_from_source_origin_m)nearest={source_index:i,point:p,distance_from_source_origin_m:distance};
      }
      result.clusters.push({zone:cell.zone===Z.CORE?'CORE':'MARGIN',point_count:indices.length,bounds_source_coordinates:bounds,nearest});
    }
    result.clusters.sort((a,b)=>a.nearest.distance_from_source_origin_m-b.nearest.distance_from_source_origin_m);
    return result;
  }
  function summary(result){const {labels,...rest}=result;return rest;}
  function selectPoints(raw,labels,zone){
    let count=0;for(const label of labels)if(label===zone)count++;
    const points=new Float32Array(count*3);let j=0;
    for(let i=0;i<labels.length;i++)if(labels[i]===zone){points[j++]=raw[i*3];points[j++]=raw[i*3+1];points[j++]=raw[i*3+2];}
    return points;
  }
  return {analyze,summary,selectPoints};
}
if(typeof module!=='undefined')module.exports=createLiveEnvelopeChecker;
