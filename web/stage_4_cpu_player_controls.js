'use strict';
const refreshCpuViewerLayers=()=>{componentFilterCache=null;if(current>=0){replaceCloud();render();showStatus()}};
for(const name of ['rails-layer','axis-layer','core-envelope-layer','margin-envelope-layer','core-layer','noise-layer','margin-layer','core-only','train-moving'])$(name).onchange=refreshCpuViewerLayers;
for(const name of ['noise-min-points','noise-radius','noise-max-axis-span','noise-max-axis-distance','temporal-required-frames','temporal-near-zone-m','temporal-match-axis-m']){
  $(name).oninput=refreshCpuViewerLayers;
  $(name).onchange=refreshCpuViewerLayers;
}
$('raw-only').onclick=()=>{for(const name of ['rails-layer','axis-layer','core-envelope-layer','margin-envelope-layer','core-layer','noise-layer','margin-layer','core-only'])$(name).checked=false;refreshCpuViewerLayers()};
