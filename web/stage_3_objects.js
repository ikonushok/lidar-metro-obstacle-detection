/* Supplemental above-floor proposals. No annotations, no accumulated frames, no safety decision. */
'use strict';
const ObjectCandidates = (() => {
  function detect(raw,c,identity) {
    const result={format:'lidar-object-candidates-v1',frame_index:identity?.index,
      header_timestamp_ns:identity?.header_timestamp_ns,source_frame:identity?.source_frame,
      status:'UNKNOWN',system_status:'UNKNOWN',safety_decision_permitted:false,
      objects:[],reason:'INVALID_INPUT',floor:null,counts:{input:raw.length/3,selected:0,small:0,oversized:0},config:c?{...c}:null};
    if(raw.length%3||!raw.every(Number.isFinite)||!Number.isInteger(identity?.index)||identity.index<0||
      typeof identity?.header_timestamp_ns!=='string'||!identity.header_timestamp_ns||typeof identity?.source_frame!=='string'||!identity.source_frame)return result;
    const keys=['forward_min','forward_max','search_half_width','floor_half_width','floor_forward_max','floor_bin',
      'floor_quantile','floor_min_points','floor_min_bins','max_grade','max_residual','min_height','max_height',
      'voxel','min_points','max_horizontal_extent','max_voxels'];
    if(!c||keys.some(k=>!Number.isFinite(c[k]))||c.forward_min<0||c.forward_max<=c.forward_min||
      c.search_half_width<=0||c.floor_half_width<=0||c.floor_forward_max<=0||c.floor_bin<=0||c.voxel<=0||
      c.floor_quantile<=0||c.floor_quantile>=1||c.floor_min_bins<2||c.max_grade<=0||c.max_residual<=0||
      c.min_height<0||c.max_height<=c.min_height||c.max_horizontal_extent<=0||
      ['floor_min_bins','floor_min_points','min_points','max_voxels'].some(k=>!Number.isInteger(c[k])||c[k]<1)||
      c.max_voxels>200000||Math.ceil(c.floor_forward_max/c.floor_bin)>1000){result.reason='INVALID_CONFIG';return result;}
    const bins=Array.from({length:Math.ceil(c.floor_forward_max/c.floor_bin)},()=>[]);
    for(let i=0;i<raw.length;i+=3){const s=-raw[i+1];if(s>=0&&s<c.floor_forward_max&&Math.abs(raw[i])<=c.floor_half_width)
      bins[Math.floor(s/c.floor_bin)].push(raw[i+2]);}
    const samples=[];
    bins.forEach((z,i)=>{if(z.length<c.floor_min_points)return;z.sort((a,b)=>a-b);
      const f=(z.length-1)*c.floor_quantile,j=Math.floor(f),q=z[j]+(z[Math.ceil(f)]-z[j])*(f-j);
      samples.push([(i*c.floor_bin+Math.min((i+1)*c.floor_bin,c.floor_forward_max))/2,q]);});
    if(samples.length<c.floor_min_bins){result.reason='INSUFFICIENT_FLOOR_SUPPORT';return result;}
    const ms=samples.reduce((v,p)=>v+p[0],0)/samples.length,mz=samples.reduce((v,p)=>v+p[1],0)/samples.length;
    const den=samples.reduce((v,p)=>v+(p[0]-ms)**2,0);
    const grade=samples.reduce((v,p)=>v+(p[0]-ms)*(p[1]-mz),0)/den,intercept=mz-grade*ms;
    const residual=Math.max(...samples.map(p=>Math.abs(p[1]-intercept-grade*p[0])));
    result.floor={grade,intercept,residual,samples,kind:'ASSUMED_LINEAR_FLOOR_NOT_RAIL_PATH'};
    if(Math.abs(grade)>c.max_grade||residual>c.max_residual){result.reason='FLOOR_FIT_REJECTED';return result;}
    const cells=new Map();
    for(let i=0;i<raw.length;i+=3){const x=raw[i],s=-raw[i+1],h=raw[i+2]-intercept-grade*s;
      if(s<c.forward_min||s>c.forward_max||Math.abs(x)>c.search_half_width||h<c.min_height||h>c.max_height)continue;
      result.counts.selected++;
      const xyz=[x,raw[i+1],raw[i+2]].map(v=>Math.floor(v/c.voxel)),key=xyz.join(',');
      if(!cells.has(key)){
        if(cells.size>=c.max_voxels){result.reason='VOXEL_BUDGET_EXCEEDED';return result;}
        cells.set(key,{xyz,indices:[],visited:false});
      }cells.get(key).indices.push(i/3);
    }
    for(const first of cells.values()){
      if(first.visited)continue;
      const queue=[first],indices=[];first.visited=true;
      for(let j=0;j<queue.length;j++){const cell=queue[j];for(const i of cell.indices)indices.push(i);
        for(let x=-1;x<=1;x++)for(let y=-1;y<=1;y++)for(let z=-1;z<=1;z++){
          const next=cells.get([cell.xyz[0]+x,cell.xyz[1]+y,cell.xyz[2]+z].join(','));
          if(next&&!next.visited){next.visited=true;queue.push(next);}
        }
      }
      if(indices.length<c.min_points){result.counts.small+=indices.length;continue;}
      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];let nearest=null;
      for(const i of indices){const p=[raw[i*3],raw[i*3+1],raw[i*3+2]],distance=Math.hypot(...p);
        for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],p[j]);hi[j]=Math.max(hi[j],p[j]);}
        if(!nearest||distance<nearest.distance_m)nearest={source_index:i,point:p,distance_m:distance};
      }
      if(Math.max(hi[0]-lo[0],hi[1]-lo[1])>c.max_horizontal_extent){result.counts.oversized+=indices.length;continue;}
      result.objects.push({id:result.objects.length,source_indices:indices,point_count:indices.length,
        bounds_source_coordinates:Object.fromEntries(['x','y','z'].map((k,j)=>[k,{min:lo[j],max:hi[j]}])),nearest,
        possibly_roi_clipped:lo[0]<=-c.search_half_width+c.voxel||hi[0]>=c.search_half_width-c.voxel||
          -hi[1]<=c.forward_min+c.voxel||-lo[1]>=c.forward_max-c.voxel,
        kind:'ABOVE_FLOOR_OBJECT_CANDIDATE',envelope_membership:'UNKNOWN_UNTIL_CURRENT_ENVELOPE_CHECK'});
    }
    result.objects.sort((a,b)=>a.nearest.distance_m-b.nearest.distance_m);
    result.objects.forEach((v,i)=>v.id=i);
    result.status=result.objects.length?'OBJECT_CANDIDATES':'UNKNOWN';
    result.reason=result.objects.length?'SUPPLEMENTAL_PROPOSALS_NOT_PERSON_CLASSIFICATION':'NO_PROPOSALS_NOT_CLEAR';
    return result;
  }
  function summary(r){return {...r,objects:r.objects.map(({source_indices,...o})=>o)};}
  return {detect,summary};
})();
if(typeof module!=='undefined')module.exports=ObjectCandidates;
