/* Frame-local auto/manual review layers. Source positions are never transformed. */
'use strict';
const ReviewGeometry = (() => {
  const tolerance=1e-6;
  const zones=Object.freeze({UNKNOWN:0,CORE:1,MARGIN:2,OUTSIDE_REFERENCE:3});
  const envelopes=new WeakSet();
  const midpoint = (a,b) => a.map((v,i)=>(v+b[i])/2);
  function railAxis(points) {
    if(points.length!==4 || points.some(p=>p.length!==3 || !p.every(Number.isFinite)))
      throw new Error('Нужны четыре точки: два рельса в ближнем и дальнем сечении.');
    if([0,2].some(i=>Math.hypot(...points[i].map((v,j)=>v-points[i+1][j]))<1e-6))
      throw new Error('В паре выбрана одна и та же точка.');
    const a=midpoint(points[0],points[1]), b=midpoint(points[2],points[3]);
    const dx=b[0]-a[0],dy=b[1]-a[1],dz=b[2]-a[2],length=Math.hypot(dx,dy);
    if(length<1e-6) throw new Error('Ближнее и дальнее сечения должны различаться.');
    // Positive lateral direction is right when looking a -> b with Z up.
    return {a,b,length,dz,tx:dx/length,ty:dy/length,nx:dy/length,ny:-dx/length,
      length3:Math.hypot(length,dz)};
  }
  function curveRailAxis(pairs) {
    if(!Array.isArray(pairs)||pairs.length<2)throw new Error('Для кривой оси нужны минимум две пары рельсов.');
    const normalized=pairs.map((pair,index)=>{
      if(!pair||!Number.isFinite(pair.source_s_m)||!Array.isArray(pair.left_xyz)||!Array.isArray(pair.right_xyz)||
        pair.left_xyz.length!==3||pair.right_xyz.length!==3||!pair.left_xyz.every(Number.isFinite)||!pair.right_xyz.every(Number.isFinite))
        throw new Error('Некорректная пара рельсов кривой оси.');
      if(index&&pair.source_s_m<=pairs[index-1].source_s_m)throw new Error('Пары рельсов должны быть строго упорядочены.');
      if(Math.hypot(...pair.left_xyz.map((v,i)=>v-pair.right_xyz[i]))<tolerance)throw new Error('В паре выбрана одна и та же точка.');
      return {source_s_m:pair.source_s_m,left_xyz:[...pair.left_xyz],right_xyz:[...pair.right_xyz],center:midpoint(pair.left_xyz,pair.right_xyz)};
    });
    let path=0,path3=0;
    const segments=normalized.slice(0,-1).map((pair,index)=>{
      const next=normalized[index+1],a=pair.center,b=next.center,dx=b[0]-a[0],dy=b[1]-a[1],dz=b[2]-a[2],length=Math.hypot(dx,dy);
      if(length<tolerance)throw new Error('Соседние сечения кривой оси должны различаться.');
      const tx=dx/length,ty=dy/length,side=[pair.left_xyz[0]-pair.right_xyz[0],pair.left_xyz[1]-pair.right_xyz[1]];
      let nx=ty,ny=-tx;
      if(nx*side[0]+ny*side[1]<0){nx=-nx;ny=-ny;}
      const segment={a,b,length,dz,tx,ty,nx,ny,length3:Math.hypot(length,dz),path_start_m:path,path_start_3_m:path3};
      path+=length;path3+=segment.length3;return segment;
    });
    return {kind:'CURVE_RAIL_AXIS_SOURCE_XYZ',a:[...normalized[0].center],b:[...normalized.at(-1).center],length:path,
      dz:normalized.at(-1).center[2]-normalized[0].center[2],tx:segments[0].tx,ty:segments[0].ty,nx:segments[0].nx,ny:segments[0].ny,
      length3:path3,rail_pairs:normalized.map(({source_s_m,left_xyz,right_xyz})=>({source_s_m,left_xyz,right_xyz})),segments};
  }
  function manualRailsFromReview(payload,manifest,frame) {
    if(!payload||payload.format!=='lidar-manual-review-v1'||payload.coordinate_basis!=='SOURCE_XYZ_UNCHANGED'||
      payload.units!=='m_ASSUMED'||payload.rail_model!=='PAIR_MIDPOINT_SEGMENT_SOURCE_Z_UP_NO_EXTRAPOLATION'||
      payload.safety_decision_permitted!==false)
      throw new Error('Неподдерживаемый формат ручной разметки.');
    if(!manifest||!frame||payload.dataset!==manifest.dataset||
      payload.first_header_timestamp_ns!==manifest.frames?.[0]?.header_timestamp_ns)
      throw new Error('Разметка относится к другому датасету.');
    if(!Array.isArray(payload.records))throw new Error('В разметке нет записей кадров.');
    const matches=payload.records.filter(r=>r&&r.frame_index===frame.index&&
      r.header_timestamp_ns===frame.header_timestamp_ns&&r.source_frame===frame.source_frame);
    if(matches.length!==1)throw new Error('Разметка не относится к текущему кадру.');
    const rails=matches[0].rails;
    railAxis(rails);
    return rails.map(point=>[...point]);
  }
  function world(axis,s,l,h) {
    if(axis?.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ'){
      const segment=axis.segments.find(item=>s<=item.path_start_m+item.length+tolerance)||axis.segments.at(-1);
      return world(segment,Math.max(0,Math.min(segment.length,s-segment.path_start_m)),l,h);
    }
    return [axis.a[0]+axis.tx*s+axis.nx*l,axis.a[1]+axis.ty*s+axis.ny*l,axis.a[2]+axis.dz*s/axis.length+h];
  }
  function local(axis,p) {
    if(axis?.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ')return {curve:true,candidates:axis.segments.map((segment,segment_index)=>{
      const value=local(segment,p);return {...value,segment_index,segment_length:segment.length,path_s_m:segment.path_start_m+value.s,
        path_s_3_m:segment.path_start_3_m+value.s*segment.length3/segment.length};
    })};
    const dx=p[0]-axis.a[0],dy=p[1]-axis.a[1],s=dx*axis.tx+dy*axis.ty;
    return {s,l:dx*axis.nx+dy*axis.ny,h:p[2]-axis.a[2]-axis.dz*s/axis.length};
  }
  function profileBounds(reference,margins) {
    const x=reference.lateral_extent_m,z=reference.vertical_extent_above_rail_m;
    return {left:x.min-margins.left,right:x.max+margins.right,
      bottom:z.min-margins.bottom,top:z.max+margins.top};
  }
  function createEnvelope(axis,reference,margins) {
    if(!axis||!reference)return null;
    const vectors=[axis.a,axis.b],curve=axis.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ';
    if(vectors.some(p=>!Array.isArray(p)||p.length!==3||!p.every(Number.isFinite))||
      !['length','dz','tx','ty','nx','ny','length3'].every(k=>Number.isFinite(axis[k]))||axis.length<=0)
      throw new Error('Некорректная ось габарита.');
    if(curve){
      if(!Array.isArray(axis.segments)||!axis.segments.length||!Array.isArray(axis.rail_pairs)||axis.rail_pairs.length!==axis.segments.length+1||
        axis.segments.some(item=>!['a','b','length','dz','tx','ty','nx','ny','length3','path_start_m','path_start_3_m'].every(k=>
          (Array.isArray(item[k])&&item[k].length===3&&item[k].every(Number.isFinite))||Number.isFinite(item[k]))||item.length<=0))
        throw new Error('Некорректная кривая ось габарита.');
    }else{
      const dx=axis.b[0]-axis.a[0],dy=axis.b[1]-axis.a[1],dz=axis.b[2]-axis.a[2],len=Math.hypot(dx,dy);
      if(Math.abs(len-axis.length)>tolerance||Math.abs(dz-axis.dz)>tolerance||Math.abs(Math.hypot(len,dz)-axis.length3)>tolerance||
        Math.abs(axis.tx-dx/len)>tolerance||Math.abs(axis.ty-dy/len)>tolerance||
        Math.abs(axis.nx-dy/len)>tolerance||Math.abs(axis.ny+dx/len)>tolerance)
        throw new Error('Оси локального габарита не согласованы.');
    }
    if(!margins||!['left','right','top','bottom'].every(k=>Number.isFinite(margins[k])&&margins[k]>=0&&margins[k]<=10))
      throw new Error('Некорректные отступы габарита.');
    const core=profileBounds(reference,{left:0,right:0,top:0,bottom:0}),expanded=profileBounds(reference,margins);
    if(!Object.values(core).every(Number.isFinite)||core.left>=core.right||core.bottom>=core.top)
      throw new Error('Некорректный профиль габарита.');
    const frozenAxis=curve?Object.freeze({
      ...axis,
      a:Object.freeze([...axis.a]),
      b:Object.freeze([...axis.b]),
      rail_pairs:Object.freeze(axis.rail_pairs.map(pair=>Object.freeze({
        source_s_m:pair.source_s_m,left_xyz:Object.freeze([...pair.left_xyz]),right_xyz:Object.freeze([...pair.right_xyz])
      }))),
      segments:Object.freeze(axis.segments.map(segment=>Object.freeze({
        ...segment,a:Object.freeze([...segment.a]),b:Object.freeze([...segment.b])
      })))
    }):Object.freeze({...axis,a:Object.freeze([...axis.a]),b:Object.freeze([...axis.b])});
    const envelope=Object.freeze({axis:frozenAxis,
      core:Object.freeze(core),expanded:Object.freeze(expanded),tolerance,
      coordinate_basis:curve?'CURRENT_CURVE_AXIS_FROM_SOURCE_XYZ':'CURRENT_AXIS_FROM_SOURCE_XYZ',units:'m_ASSUMED',safety_decision_permitted:false});
    envelopes.add(envelope);return envelope;
  }
  const inSegment=(axis,s)=>Number.isFinite(s)&&s>=-tolerance&&s<=axis.length+tolerance;
  const inBounds=(bounds,v)=>Number.isFinite(v.l)&&Number.isFinite(v.h)&&
    v.l>=bounds.left-tolerance&&v.l<=bounds.right+tolerance&&v.h>=bounds.bottom-tolerance&&v.h<=bounds.top+tolerance;
  function classifyLocal(envelope,v){
    if(!envelopes.has(envelope))return zones.UNKNOWN;
    if(v?.curve){
      const candidates=v.candidates.filter(item=>inSegment({length:item.segment_length},item.s));
      const classified=candidates.map(item=>({item,zone:inBounds(envelope.core,item)?zones.CORE:inBounds(envelope.expanded,item)?zones.MARGIN:zones.OUTSIDE_REFERENCE}));
      const winner=classified.find(item=>item.zone===zones.CORE)||classified.find(item=>item.zone===zones.MARGIN)||classified[0];
      if(!winner)return zones.UNKNOWN;
      v.selected=winner.item;v.s=winner.item.s;v.l=winner.item.l;v.h=winner.item.h;v.path_s_m=winner.item.path_s_m;v.path_s_3_m=winner.item.path_s_3_m;
      return winner.zone;
    }
    if(!inSegment(envelope.axis,v.s)||!Number.isFinite(v.l)||!Number.isFinite(v.h))return zones.UNKNOWN;
    if(inBounds(envelope.core,v))return zones.CORE;
    return inBounds(envelope.expanded,v)?zones.MARGIN:zones.OUTSIDE_REFERENCE;
  }
  function classify(envelope,p){
    if(!envelopes.has(envelope)||p.length!==3||!p.every(Number.isFinite))return zones.UNKNOWN;
    return classifyLocal(envelope,local(envelope.axis,p));
  }
  // Observed returns only: never infer that an incomplete object or scene is clear.
  function assessComponent(positions,indices,envelope,clipped=false){
    const counts={unknown:0,core:0,margin:0,outside:0},names=['unknown','core','margin','outside'];
    const nearest={core:null,margin:null},reasons=new Set();
    const invalid=()=>({status:'UNKNOWN',reason_codes:['INVALID_COMPONENT'],counts:null,nearest:null,safety_decision_permitted:false});
    if(!positions||positions.length%3||!Array.isArray(indices)||!indices.length||new Set(indices).size!==indices.length)return invalid();
    for(const i of indices){
      if(!Number.isInteger(i)||i<0||i>=positions.length/3)return invalid();
      const p=[positions[3*i],positions[3*i+1],positions[3*i+2]];
      if(!p.every(Number.isFinite))return invalid();
      const zone=classify(envelope,p),name=names[zone];counts[name]++;
      if(zone===zones.CORE||zone===zones.MARGIN){
        const distance=Math.hypot(...p);
        if(!nearest[name]||distance<nearest[name].distance_m)nearest[name]={source_index:i,point:p,distance_m:distance};
      }
      if(zone===zones.UNKNOWN){
        if(!envelopes.has(envelope))reasons.add('NO_CURRENT_ENVELOPE');
        else {const value=local(envelope.axis,p);reasons.add(value.curve?'OUTSIDE_SUPPORTED_CURVE_PATH':value.s<0?'BEFORE_SUPPORTED_PATH':'AFTER_SUPPORTED_PATH');}
      }
    }
    if(clipped)reasons.add('SEARCH_ROI_MAY_CLIP_OBJECT');
    const status=counts.core?'CORE_INTERSECTION':counts.margin?'MARGIN_INTERSECTION':
      counts.unknown||clipped?'UNKNOWN':'OBSERVED_RETURNS_OUTSIDE';
    return {status,counts,nearest,reason_codes:[...reasons],complete_observed_component:!counts.unknown&&!clipped,
      safety_decision_permitted:false,scope:'OBSERVED_COMPONENT_REFERENCE_GEOMETRY_NOT_SCENE_CLEARANCE'};
  }
  function rings(axis,bounds,sections=20) {
    return Array.from({length:sections+1},(_,i)=>[
      [bounds.left,bounds.bottom],[bounds.right,bounds.bottom],
      [bounds.right,bounds.top],[bounds.left,bounds.top]
    ].map(([l,h])=>world(axis,axis.length*i/sections,l,h)));
  }
  function crop(positions,axis,bounds) {
    if(!axis) return positions;
    const result=new Float32Array(positions.length);let count=0;
    for(let i=0;i<positions.length;i+=3) {
      const p=[positions[i],positions[i+1],positions[i+2]],v=local(axis,p);
      // Same boundaries as live membership; retain the unobserved range as UNKNOWN.
      const supported=v.curve?v.candidates.filter(item=>inSegment({length:item.segment_length},item.s)):inSegment(axis,v.s);
      if((Array.isArray(supported)?!supported.length:!supported) || (Array.isArray(supported)?supported.some(item=>inBounds(bounds,item)):inBounds(bounds,v))) {
        result[count++]=p[0];result[count++]=p[1];result[count++]=p[2];
      }
    }
    return result.slice(0,count);
  }
  return {railAxis,curveRailAxis,manualRailsFromReview,world,local,profileBounds,createEnvelope,isEnvelope:value=>envelopes.has(value),classify,classifyLocal,assessComponent,zones,tolerance,rings,crop};
})();
if(typeof module!=='undefined') module.exports=ReviewGeometry;

function createReviewLayers(host) {
  const $=id=>document.getElementById(id),G=ReviewGeometry;
  const layer=new THREE.Group();layer.name='review-layers';host.scene.add(layer);
  const records=new Map();let frame=null,manifest=null,raw=null,mode=null,picks=[],axis=null;
  let down=null,autoConfig=null,autoResult=null,liveConfig=null,liveResult=null,liveKey=null,liveCore=null,liveMargin=null;
  const checker=typeof createLiveEnvelopeChecker==='function'?createLiveEnvelopeChecker(G):null;
  let objectConfig=null,objectResult=null;
  const toggles=['marks-layer','axis-layer','rail-grid','train-layer','margin-layer','crop-layer','live-layer','object-layer'];
  if(typeof window!=='undefined')window.addEventListener('beforeunload',event=>{
    if([...records.values()].some(r=>r.rails.length||r.marks.length||r.measurements.length)){
      event.preventDefault();event.returnValue='';
    }
  });
  const geometryToggles=['axis-layer','rail-grid','train-layer','margin-layer','crop-layer'];
  const selectionSteps={rails:['ближний рельс 1','ближний рельс 2 (то же сечение)',
    'дальний рельс 1','дальний рельс 2 (то же сечение)'],measure:['первую точку','вторую точку'],point:['точку объекта']};
  function key(){return frame && `${frame.index}:${frame.header_timestamp_ns}:${frame.source_frame}`;}
  function record(){if(!records.has(key()))records.set(key(),{frame_index:frame.index,
    header_timestamp_ns:frame.header_timestamp_ns,source_frame:frame.source_frame,rails:[],marks:[],measurements:[]});return records.get(key());}
  function clearLayer(){while(layer.children.length){const child=layer.children[0];layer.remove(child);
    child.traverse(o=>{if(o.geometry)o.geometry.dispose();if(o.material){if(o.material.map)o.material.map.dispose();o.material.dispose();}});}}
  function message(text){$('review-message').textContent=text;}
  function cancel(){mode=null;picks=[];$('cancel-pick').disabled=true;host.canvas.style.cursor='';}
  function margins(){const values={};for(const side of ['left','right','top','bottom']){
    values[side]=Number($('margin-'+side).value);if(!Number.isFinite(values[side])||values[side]<0||values[side]>10)
      throw new Error('Отступы должны быть от 0 до 10.');}return values;}
  function line(points,color,segments=false){const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(points.flat(),3));
    const material=new THREE.LineBasicMaterial({color});
    const object=segments?new THREE.LineSegments(geometry,material):new THREE.Line(geometry,material);
    layer.add(object);return object;}
  function markers(points,color,size=8){if(!points.length)return;
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(points.flat(),3));
    layer.add(new THREE.Points(geometry,new THREE.PointsMaterial({color,size,sizeAttenuation:false,depthTest:false})));}
  function livePoints(positions,color){if(!positions?.length)return;
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
    const object=new THREE.Points(geometry,new THREE.PointsMaterial({color,size:2,sizeAttenuation:false,depthTest:true,depthWrite:false}));
    object.renderOrder=5;layer.add(object);}
  function checkLive(envelope,rails){
    if(!checker){$('live-status').textContent='UNKNOWN: модуль пересечений недоступен';$('export-live').disabled=true;return;}
    const nextKey=JSON.stringify([key(),$('axis-mode').value,rails,envelope,liveConfig]);
    if(nextKey!==liveKey){
      const curveAxisStatus=$('axis-mode').value==='auto'?(axis?.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ'?'CURVE_AXIS_SUPPORTED':'MISSING_CURVE_AXIS'):null;
      liveResult=checker.analyze(raw,envelope,liveConfig,frame,curveAxisStatus);liveKey=nextKey;
      liveResult.geometry_source={mode:$('axis-mode').value,rails,rail_pairs:$('axis-mode').value==='auto'?autoResult?.rail_pairs||[]:[],
        auto_diagnostics:$('axis-mode').value==='auto'?autoResult?.diagnostics:null};
      liveCore=checker.selectPoints(raw,liveResult.labels,G.zones.CORE);
      liveMargin=checker.selectPoints(raw,liveResult.labels,G.zones.MARGIN);
    }
    const r=liveResult,c=r.counts,nearest=r.nearest_core;
    if(r.geometric_candidate_present===null)$('live-status').textContent='UNKNOWN: вторжения не определены ('+r.reason+')';
    else if(r.intrusion_candidate_present)$('live-status').textContent=`ПРЕДУПРЕЖДЕНИЕ: ${c.core} наблюдаемых возвратов внутри текущего габарита — помеха-кандидат`+
      (nearest?`; ближайшая ${nearest.distance_from_source_origin_m.toFixed(2)} м* от датчика`:'')+
      ` · в отступах ${c.margin} · вне участка UNKNOWN: ${c.unknown}.`;
    else if(r.margin_return_present)$('live-status').textContent=`ВНИМАНИЕ: ${c.margin} наблюдаемых возвратов в отступах габарита; core-вторжений нет. Вне участка UNKNOWN: ${c.unknown}.`;
    else $('live-status').textContent=`Внутри текущего габарита наблюдаемых возвратов нет; вне участка UNKNOWN: ${c.unknown}. Это не «путь свободен».`;
    $('live-details').textContent=r.geometric_candidate_present===null?'Нет результата текущей геометрии.':
      `Групп ≥${liveConfig.min_cluster_points} точек: ${r.clusters.length}; вне рамок малых групп: ${r.ungrouped_candidate_points} точек (учтены). `+
      `Каждый возврат внутри core — немедленный помеха-кандидат, независимо от размера группы. Проверены ${c.core+c.margin+c.outside_reference} / ${c.total} возвратов в продольном участке. `+
      `Группировка: ${r.grouping_status}. Решение о свободности пути не формируется. Расчёт всегда по полному исходному кадру.`+
      (r.nearest_margin?` Ближайшая в отступах: ${r.nearest_margin.distance_from_source_origin_m.toFixed(2)} м* от датчика.`:'');
    $('export-live').disabled=false;
    if($('live-layer').checked){livePoints(liveCore,0xff3f58);livePoints(liveMargin,0xffc34d);}
  }
  function distanceLabel(point,text){const canvas=document.createElement('canvas');canvas.width=160;canvas.height=48;
    const context=canvas.getContext('2d');context.fillStyle='#c7e1ef';context.font='28px sans-serif';context.textAlign='center';context.fillText(text,80,33);
    const object=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(canvas),depthTest:false,transparent:true}));
    object.position.set(...point);object.scale.set(3,.75,1);layer.add(object);}
  function volume(bounds,color){const rings=G.rings(axis,bounds),points=[];
    rings.forEach((ring,i)=>ring.forEach((p,j)=>{points.push(p,ring[(j+1)%4]);if(i)points.push(rings[i-1][j],p);}));line(points,color,true);}
  function box(bounds,color){if(!bounds)return;
    const dims=['x','y','z'].map(k=>[Number(bounds[k]?.min),Number(bounds[k]?.max)]);
    if(dims.flat().some(v=>!Number.isFinite(v))||dims.some(([a,b])=>b<a))return;
    const geometry=new THREE.BoxGeometry(...dims.map(([a,b])=>Math.max(b-a,.02)));
    const edges=new THREE.EdgesGeometry(geometry);geometry.dispose();
    const object=new THREE.LineSegments(edges,new THREE.LineBasicMaterial({color}));
    object.position.set(...dims.map(([a,b])=>(a+b)/2));layer.add(object);}
  function render(){
    clearLayer();if(!frame||!raw)return;
    const saved=record(),reference=manifest.visualization_overlay?.reference_cross_section;
    const axisMode=$('axis-mode').value;
    if(axisMode==='auto'&&!autoResult){
      const a=manifest.visualization_overlay?.source_axis_assumption;
      if(a?.longitudinal_axis!=='y'||a.longitudinal_sign!==-1||a.lateral_axis!=='x'||a.vertical_axis!=='z'||a.source_units!=='m')
        autoResult={status:'UNKNOWN',reason:'UNSUPPORTED_SOURCE_AXIS_ASSUMPTION',rails:[]};
      else autoResult=AutoRails.detect(raw,autoConfig);
    }
    const rails=axisMode==='auto'?(autoResult?.rails||[]):axisMode==='manual'?saved.rails:[];
    const railPairs=axisMode==='auto'?(autoResult?.rail_pairs||[]):[];
    axis=axisMode==='auto'?(railPairs.length>=2?G.curveRailAxis(railPairs):null):rails.length===4?G.railAxis(rails):null;
    geometryToggles.forEach(id=>{$(id).disabled=!axis||(!reference&&['train-layer','margin-layer','crop-layer'].includes(id));});
    const envelope=G.createEnvelope(axis,reference,margins());
    if(envelope)axis=envelope.axis;
    const bounds=envelope?.expanded||null;
    const displayed=$('crop-layer').checked&&bounds?G.crop(raw,axis,bounds):raw;
    host.display(displayed);
    host.colors(null);
    if($('marks-layer').checked){for(const mark of saved.marks)markers([mark.point],0xffffff);
      for(const m of saved.measurements){line(m.points,0xffd34d);markers(m.points,0xffd34d);}}
    markers(picks,0xffffff);
    if(axis){
      if($('axis-layer').checked){const centerline=line(axis.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ'?
        axis.rail_pairs.map(pair=>pair.left_xyz.map((value,index)=>(value+pair.right_xyz[index])/2)):[axis.a,axis.b],0x3dff6f);
        centerline.material.depthTest=false;centerline.material.depthWrite=false;centerline.renderOrder=20;
        markers(axisMode==='auto'?autoResult.support:rails,axisMode==='auto'?0xffb74d:0x3dff6f,axisMode==='auto'?4:8);
        if(axis.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ'){
          const pairLines=axis.rail_pairs.flatMap(pair=>[pair.left_xyz,pair.right_xyz]);line(pairLines,0xffb74d,true);
        }else line([rails[0],rails[2],rails[1],rails[3]],0xffb74d,true);}
      if($('rail-grid').checked){const points=[];const half=bounds?Math.max(Math.abs(bounds.left),Math.abs(bounds.right)):2;
        for(let i=0;i<=10;i++){const s=axis.length*i/10;points.push(G.world(axis,s,-half,0),G.world(axis,s,half,0));
          distanceLabel(G.world(axis,s,half+2,0),(axis.length3*i/10).toFixed(1));}
        for(const l of [-half,0,half])points.push(G.world(axis,0,l,0),G.world(axis,axis.length,l,0));line(points,0x496782,true);}
      if(envelope&&$('train-layer').checked)volume(envelope.core,0x987fff);
      if(envelope&&$('margin-layer').checked)volume(envelope.expanded,0xe8ceff);
    }
    checkLive(envelope,rails);
    const objectCandidatesEnabled=manifest.object_candidates_enabled!==false;
    $('object-layer').disabled=!objectCandidatesEnabled;
    if(!objectCandidatesEnabled){
      $('object-layer').checked=false;$('object-status').textContent='Объектные кандидаты по всему участку отключены: показаны только пересечения текущего габарита.';$('object-info').textContent='';
    }else if(typeof ObjectCandidates!=='undefined'&&manifest.geometry_enabled!==false){
      if(!objectResult)objectResult=ObjectCandidates.detect(raw,objectConfig,frame);
      const objects=objectResult.objects;
      $('object-status').textContent=`Объектных кандидатов: ${objects.length}. `+
        (objects.length?`Ближайший ${objects[0].nearest.distance_m.toFixed(2)} м* от датчика. Не все кандидаты — помехи.`:`UNKNOWN: ${objectResult.reason}`);
      const descriptions=[];
      for(const o of objects){
        const assessment=G.assessComponent(raw,o.source_indices,envelope,o.possibly_roi_clipped);
        o.envelope_assessment=assessment;o.current_envelope_counts=assessment.counts;
        const labels={CORE_INTERSECTION:'ПЕРЕСЕЧЕНИЕ ГАБАРИТА',MARGIN_INTERSECTION:'В ОТСТУПАХ',UNKNOWN:'НЕИЗВЕСТНО',OBSERVED_RETURNS_OUTSIDE:'Наблюдаемые точки вне габарита'};
        const reasons={NO_CURRENT_ENVELOPE:'нет текущего габарита',BEFORE_SUPPORTED_PATH:'до первой опоры пути',AFTER_SUPPORTED_PATH:'за последней опорой пути',SEARCH_ROI_MAY_CLIP_OBJECT:'возможна обрезка поисковой полосой',INVALID_COMPONENT:'невалидная группа'};
        const hit=assessment.nearest?.core||assessment.nearest?.margin;
        descriptions.push(`#${o.id+1}: ${labels[assessment.status]}; группа ${o.nearest.distance_m.toFixed(2)} м*, ${o.point_count} точек`+
          (hit?`; ${assessment.nearest.core?'в габарите':'в отступах'} ${hit.distance_m.toFixed(2)} м*`:'')+
          (assessment.reason_codes.length?' · '+assessment.reason_codes.map(r=>reasons[r]||r).join('; '):''));
        const color=assessment.status==='CORE_INTERSECTION'?0xff3f58:assessment.status==='MARGIN_INTERSECTION'?0xffc34d:0x40ffcf;
        if($('object-layer').checked)box(o.bounds_source_coordinates,color);
      }
      $('object-info').textContent=descriptions.join('\n');
    }else{$('object-status').textContent=manifest.geometry_enabled===false?'UNKNOWN: для этой записи оси и габарит ещё не проверены; поиск отключён':'UNKNOWN: модуль объектных кандидатов недоступен';$('object-info').textContent='';}
    const widths=axis?(axis.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ'?[axis.rail_pairs[0],axis.rail_pairs.at(-1)].map(pair=>
      Math.hypot(...pair.left_xyz.map((value,index)=>value-pair.right_xyz[index])).toFixed(3)):[0,2].map(i=>
      Math.hypot(...rails[i].map((v,j)=>v-rails[i+1][j])).toFixed(3))):[];
    const reasons={INVALID_SEARCH_PARAMETERS:'нет корректной конфигурации поиска',UNSUPPORTED_SOURCE_AXIS_ASSUMPTION:'неподдержанные допущения осей/единиц',
      INSUFFICIENT_PAIRED_RAIL_SUPPORT:'недостаточно опор двух рельсов',NO_STRAIGHT_CONSISTENT_PAIR:'пара не проходит проверку прямизны/покрытия',
      AMBIGUOUS_RAIL_PAIRS:'найдено несколько сопоставимых пар',SEARCH_BUDGET_EXCEEDED:'слишком много геометрических кандидатов',
      NONFINITE_XYZ:'некорректные координаты',INVALID_XYZ:'некорректный XYZ'};
    $('auto-status').textContent=axisMode==='off'?'Разметка выключена':axisMode==='manual'?
      (axis?'Ручная ось · только текущий кадр':'Ручная ось не задана · UNKNOWN'):
      axis?'':
        `UNKNOWN: ${reasons[autoResult?.reason]||autoResult?.reason||'ось не найдена'}`;
    $('axis-info').textContent=axis?`${axisMode==='auto'?'Автоматическая гипотеза':'Ручная ось'} только кадра ${frame.index}: ${axis.length3.toFixed(3)} м* ${axis.kind==='CURVE_RAIL_AXIS_SOURCE_XYZ'?'по поддержанной ломаной':'между сечениями'}. Расстояния между точками пар: ${widths.join(' / ')} м*. Метки 0–${axis.length3.toFixed(1)} от ближнего сечения, не от датчика. Уровень — среднее двух головок рельсов. Проверяйте промежуточный участок.`+
      (axisMode==='auto'?` Опорных сечений: ${autoResult.diagnostics.supportedStations}; RMS модели: ${autoResult.diagnostics.rms.toFixed(3)} м* (не физическая точность).`:''):
      'Ось не задана для этого кадра; габарит не показан. Ручная разметка доступна как отдельный режим.';
    $('layer-info').textContent=`Показано ${displayed.length/3} / ${raw.length/3} точек.`+
      ($('crop-layer').checked&&axis?' Вне размеченного интервала точки сохранены.':'');
    const list=$('annotations');list.replaceChildren();
    const add=text=>{const item=document.createElement('li');item.textContent=text;list.appendChild(item);};
    const zoneNames=['UNKNOWN — вне поддержанного участка или нет геометрии','внутри reference-габарита','в отступах','вне reference-габарита на поддержанном участке'];
    for(const mark of saved.marks)add(`${mark.label}: XYZ ${mark.point.map(v=>v.toFixed(3)).join(', ')}; от датчика ${Math.hypot(...mark.point).toFixed(3)} м*; ${zoneNames[G.classify(envelope,mark.point)]}`);
    for(const m of saved.measurements){const delta=m.points[1].map((v,i)=>v-m.points[0][i]);add(`Расстояние ${Math.hypot(...delta).toFixed(3)} м*; ΔXYZ ${delta.map(v=>v.toFixed(3)).join(', ')}`);}
    $('export-review').disabled=![...records.values()].some(r=>r.rails.length||r.marks.length||r.measurements.length);
  }
  function safeRender(){try{render();}catch(e){clearLayer();
    objectResult=null;$('object-status').textContent='UNKNOWN: текущий объектный расчёт недоступен';$('object-info').textContent='';
    axis=null;$('auto-status').textContent='UNKNOWN: ошибка геометрии';
    liveResult=null;liveKey=null;liveCore=null;liveMargin=null;$('live-status').textContent='UNKNOWN: текущий расчёт недоступен';$('export-live').disabled=true;
    if(raw&&host.cloud()){host.display(raw);host.colors(null);}
    $('crop-layer').checked=false;
    $('layer-info').textContent='Ошибка параметров: показано полное исходное облако.';message(e.message);}}
  function begin(next){if(!frame)return;host.pause();cancel();mode=next;
    $('cancel-pick').disabled=false;host.canvas.style.cursor='crosshair';message('Щёлкните '+selectionSteps[mode][0]+'.');safeRender();}
  $('pick-point').onclick=()=>begin('point');$('pick-measure').onclick=()=>begin('measure');$('pick-rails').onclick=()=>begin('rails');
  $('import-review').onclick=()=>$('import-review-file').click();
  $('import-review-file').onchange=async event=>{
    const file=event.target.files?.[0];event.target.value='';if(!file||!frame||!manifest)return;
    host.pause();
    try{
      const rails=G.manualRailsFromReview(JSON.parse(await file.text()),manifest,frame),saved=record();
      saved.rails=rails;$('axis-mode').value='manual';
      for(const id of ['axis-layer','rail-grid','train-layer'])$(id).checked=true;
      message(`Импортированы 4 опоры рельсов для кадра ${frame.index}. Габарит показан только между ними.`);safeRender();
    }catch(error){message(error.message);safeRender();}
  };
  $('cancel-pick').onclick=()=>{cancel();message('Выбор отменён.');safeRender();};
  $('clear-frame').onclick=()=>{if(frame){records.delete(key());cancel();geometryToggles.forEach(id=>$(id).checked=false);message('Ручные отметки текущего кадра удалены.');safeRender();}};
  $('raw-only').onclick=()=>{toggles.forEach(id=>$(id).checked=false);$('axis-mode').value='off';cancel();safeRender();message('Все дополнительные слои выключены. Ручные отметки сохранены.');};
  $('axis-mode').onchange=()=>{host.pause();cancel();
    geometryToggles.forEach(id=>$(id).checked=$('axis-mode').value!=='off'&&['axis-layer','rail-grid','train-layer'].includes(id));safeRender();};
  host.canvas.addEventListener('pointerdown',event=>{down={x:event.clientX,y:event.clientY};});
  host.canvas.addEventListener('pointerup',event=>{
    if(!mode||!frame||!down||Math.hypot(event.clientX-down.x,event.clientY-down.y)>5)return;
    const cloud=host.cloud();if(!cloud)return;
    const rect=host.canvas.getBoundingClientRect(),p=new THREE.Vector3();host.camera.updateMatrixWorld();
    const data=cloud.geometry.attributes.position.array;
    let selected=null,best=7,depth=Infinity;
    for(let i=0;i<data.length;i+=3){p.set(data[i],data[i+1],data[i+2]).project(host.camera);
      if(p.z<-1||p.z>1)continue;
      const distance=Math.hypot(rect.left+(p.x+1)*rect.width/2-event.clientX,rect.top+(1-p.y)*rect.height/2-event.clientY);
      if(distance<best-.05 || (Math.abs(distance-best)<=.05&&p.z<depth)){
        best=distance;depth=p.z;selected=[data[i],data[i+1],data[i+2]];}}
    if(!selected){message('Рядом с курсором нет точки. Приблизьте нужное место.');return;}
    picks.push(selected);
    if(picks.length<selectionSteps[mode].length){message('Щёлкните '+selectionSteps[mode][picks.length]+'.');safeRender();return;}
    try{
      const saved=record();
      if(mode==='rails'){G.railAxis(picks);saved.rails=picks.slice();$('axis-mode').value='manual';
        for(const id of ['axis-layer','rail-grid','train-layer'])$(id).checked=true;}
      if(mode==='measure')saved.measurements.push({points:picks.slice()});
      if(mode==='point')saved.marks.push({label:$('mark-label').value.trim()||'Объект',point:picks[0]});
      if(mode!=='rails')$('marks-layer').checked=true;
      cancel();message('Сохранено для текущего кадра. Проверьте положение выбранных точек с другого ракурса.');safeRender();
    }catch(e){cancel();message(e.message);safeRender();}
  });
  toggles.forEach(id=>$(id).onchange=()=>{host.pause();safeRender();});
  for(const id of ['margin-left','margin-right','margin-top','margin-bottom'])$(id).onchange=()=>{host.pause();safeRender();};
  $('export-review').onclick=()=>{
    const payload={format:'lidar-manual-review-v1',dataset:manifest.dataset,
      first_header_timestamp_ns:manifest.frames[0].header_timestamp_ns,
      coordinate_basis:'SOURCE_XYZ_UNCHANGED',units:'m_ASSUMED',safety_decision_permitted:false,
      rail_model:'PAIR_MIDPOINT_SEGMENT_SOURCE_Z_UP_NO_EXTRAPOLATION',
      records:[...records.values()].filter(r=>r.rails.length||r.marks.length||r.measurements.length)};
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='lidar_manual_review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  $('export-live').onclick=()=>{
    if(!liveResult||!frame||!checker)return;
    const payload={...checker.summary(liveResult),dataset:manifest.dataset,first_header_timestamp_ns:manifest.frames[0].header_timestamp_ns,
      object_candidates:objectResult&&typeof ObjectCandidates!=='undefined'?ObjectCandidates.summary(objectResult):null,
      reviewed_points:record().marks.map(mark=>({...mark,zone:Object.keys(G.zones).find(k=>G.zones[k]===G.classify(liveResult.envelope,mark.point)),
        annotation_source:'USER_PICKED_POINT_NOT_INDEPENDENT_GROUND_TRUTH'})),
      point_encoding:'SOURCE_XYZ_UNCHANGED',note:'GEOMETRIC_CANDIDATES_ONLY_NOT_SAFETY_DECISION'};
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=`live_envelope_frame_${frame.index}.json`;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  return {
    unload(){frame=null;raw=null;axis=null;autoResult=null;objectResult=null;cancel();clearLayer();geometryToggles.forEach(id=>$(id).disabled=true);
      $('object-status').textContent='UNKNOWN: загрузка кадра';$('object-info').textContent='';
      liveKey=null;liveResult=null;liveCore=null;liveMargin=null;$('live-status').textContent='UNKNOWN: загрузка кадра';$('live-details').textContent='';$('export-live').disabled=true;
      $('auto-status').textContent='Загрузка кадра · габарит не определён';$('axis-info').textContent='Нет геометрии текущего кадра.';},
    setFrame(next,data,meta,config,candidateConfig,objectsConfig){frame=next;raw=data;manifest=meta;autoConfig=config;autoResult=null;liveConfig=candidateConfig;liveKey=null;objectConfig=objectsConfig;objectResult=null;cancel();
      // Keep the user's preference; render applies it only to this frame's valid envelope.
      message('');safeRender();}
  };
}
