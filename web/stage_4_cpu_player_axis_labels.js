'use strict';
const renderWithoutAxisLabels=render;
function axisLabel(text,position,options={}){const canvas=document.createElement('canvas');canvas.width=options.width||160;canvas.height=options.height||40;const context=canvas.getContext('2d');context.font=options.font||'24px sans-serif';context.fillStyle=options.color||'#ffd34f';if(options.shadow){context.shadowColor='#000';context.shadowBlur=6;context.shadowOffsetY=2}context.fillText(text,2,options.baseline||28);const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(canvas),depthTest:false}));sprite.scale.set(options.scaleX||1.4,options.scaleY||.35,1);sprite.position.fromArray(position);overlay.add(sprite)}
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
function obstacleDistanceLabel(pairs){
  const split=effectiveCoreSplit();
  const distance=split.reportableCount>0?split.nearestDisplayDistance:NaN;
  if(!Number.isFinite(distance))return;
  const pair=pairClosestToDistance(pairs,distance);
  if(!pair)return;
  axisLabel(`Препятствие ${distance.toFixed(1)} м`,sideAxisLabelPosition(pair,1.35,1.05),{
    width:320,height:56,font:'bold 28px sans-serif',baseline:38,scaleX:2.8,scaleY:.5,shadow:true,
  });
}
function endDistancePair(pairs){
  const observedEnd=Number(result?.observed_support_end_source_s_m);
  if(Number.isFinite(observedEnd))return pairClosestToDistance(pairs,observedEnd);
  return pairs.at(-1);
}
function axisDistanceLabels(pairs){
  const labelled=new Set(),stride=Math.max(1,Math.ceil(pairs.length/8));
  for(let i=0;i<pairs.length;i+=stride){
    const pair=pairs[i];
    labelled.add(pair);
    axisLabel(`${pair.source_s_m.toFixed(1)} м`,sideAxisLabelPosition(pair));
  }
  const endPair=endDistancePair(pairs);
  if(endPair&&!labelled.has(endPair))axisLabel(`${endPair.source_s_m.toFixed(1)} м`,sideAxisLabelPosition(endPair,1.0,.7));
}
render=function(){renderWithoutAxisLabels();const pairs=result?.rail_pairs_source_xyz||[];if(!pairs.length)return;obstacleDistanceLabel(pairs);if(!$('axis-layer').checked)return;axisDistanceLabels(pairs)};
