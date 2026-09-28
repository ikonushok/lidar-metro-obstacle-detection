'use strict';
const renderWithoutAxisLabels=render;
function axisLabel(text,position,options={}){const canvas=document.createElement('canvas');canvas.width=options.width||160;canvas.height=options.height||40;const context=canvas.getContext('2d');if(options.background){context.fillStyle='rgba(7,16,28,0.88)';context.fillRect(0,0,canvas.width,canvas.height)}context.font=options.font||'24px sans-serif';context.fillStyle=options.color||'#ffd34f';if(options.shadow){context.shadowColor='#000';context.shadowBlur=6;context.shadowOffsetY=2}context.fillText(text,2,options.baseline||28);const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(canvas),depthTest:false}));sprite.scale.set(options.scaleX||1.4,options.scaleY||.35,1);sprite.position.fromArray(position);overlay.add(sprite)}
function sideAxisLabelPosition(pair,extraOffset=.75,extraHeight=.45){
  const center=pair.left_xyz.map((value,index)=>(value+pair.right_xyz[index])*.5);
  const side=[pair.right_xyz[0]-center[0],pair.right_xyz[1]-center[1],0];
  const length=Math.hypot(side[0],side[1])||1;
  const bounds=result?.core_bounds_source_axis||[];
  const halfWidth=Math.max(Math.abs(Number(bounds[0])||0),Math.abs(Number(bounds[1])||0),length);
  const offset=halfWidth+extraOffset;
  return[center[0]+side[0]/length*offset,center[1]+side[1]/length*offset,center[2]+extraHeight];
}
function pairClosestToDistance(pairs,distance){
  let best=null,bestDelta=Infinity;
  for(const pair of pairs){const delta=Math.abs(Number(pair.source_s_m)-distance);if(delta<bestDelta){best=pair;bestDelta=delta}}
  return best;
}
function obstacleDistanceLabel(){
  const split=effectiveCoreSplit();
  const distance=split.reportableCount>0?split.nearestDisplayDistance:NaN;
  if(!Number.isFinite(distance))return;
  const point=split.backendMode==='baseline_v3'?result?.nearest_reportable_intrusion_xyz:
    split.nearestIndex>=0?Array.from(xyz.slice(split.nearestIndex*3,split.nearestIndex*3+3)):null;
  if(!Array.isArray(point)||point.length!==3||!point.every(Number.isFinite))return;
  const labelPosition=[point[0],point[1],point[2]+.65];
  addLine(overlay,[point,labelPosition],0xff5365);
  axisLabel(`${distance.toFixed(1)} м`,labelPosition,{
    width:160,height:52,font:'bold 26px sans-serif',baseline:36,scaleX:1.2,scaleY:.4,background:true,color:'#ff5365',
  });
}
function endDistancePair(pairs){
  const observedEnd=Number(result?.observed_support_end_source_s_m);
  if(Number.isFinite(observedEnd))return pairClosestToDistance(pairs,observedEnd);
  return pairs.at(-1);
}
function axisDistanceLabels(pairs){
  const labelled=new Set(),stride=Math.max(1,Math.ceil(pairs.length/8));
  const envelopeEndPair=pairs.at(-1);
  for(let i=0;i<pairs.length;i+=stride){
    const pair=pairs[i];
    if(pair===envelopeEndPair)continue;
    labelled.add(pair);
    axisLabel(`${pair.source_s_m.toFixed(1)} м`,sideAxisLabelPosition(pair));
  }
  const endPair=endDistancePair(pairs);
  if(endPair&&endPair!==envelopeEndPair&&!labelled.has(endPair))axisLabel(`${endPair.source_s_m.toFixed(1)} м`,sideAxisLabelPosition(endPair,1.0,.7));
}
function envelopeEndDescription(pairs){
  const end=Number(pairs.at(-1)?.source_s_m);
  if(!pairs.length||!Number.isFinite(end))return '';
  const observed=result?.observed_support_end_source_s_m;
  const extension=Number.isFinite(observed)&&end>observed+.05?`\nПродление после ${observed.toFixed(1)} м`:'';
  return `Конец габарита: ${end.toFixed(1)} м по оси${extension}`;
}
render=function(){
  renderWithoutAxisLabels();
  obstacleDistanceLabel();
  const pairs=result?.rail_pairs_source_xyz||[];
  let endBadge=$('envelope-end-banner');
  if(!endBadge){
    endBadge=document.createElement('div');
    endBadge.id='envelope-end-banner';
    $('scene').appendChild(endBadge);
  }
  endBadge.textContent=$('core-envelope-layer').checked&&result?.core_envelope_wireframe_source_xyz?.length?
    envelopeEndDescription(pairs):'';
  endBadge.hidden=!endBadge.textContent;
  if(!$('axis-layer').checked||!pairs.length)return;
  axisDistanceLabels(pairs);
};
