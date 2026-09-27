const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('web/stage_2_player.html', 'utf8');
const start = html.indexOf('    function floorCoordinates(');
const end = html.indexOf('    function clusterSettings()', start);
assert.ok(start >= 0 && end > start, 'player must use local floor coordinates');
const context = vm.createContext({Float32Array, Math, Number});
vm.runInContext(html.slice(start, end), context);
const result = {path_profile: {status:'ACTIVE_ASSUMED_AUTO_TRACK', nodes:[
  {depth_m:5,x_m:0,y_m:-5,z_m:-2},
  {depth_m:15,x_m:1,y_m:-15,z_m:-3},
  {depth_m:25,x_m:2,y_m:-25,z_m:-2}
]}};
const bounds = {x:{min:-1.4,max:1.4},z:{min:0,max:3.7}};
const margins = {left:0.5,right:0.5,top:0.5,bottom:0.5};
const points = new Float32Array([1,-15,-3.4, 1,-15,-3.8, 2,-25,-2.4]);
assert.equal(context.croppedPositions(points,bounds,margins,result).length, 6);
assert.equal(context.croppedPositions(points,bounds,{...margins,bottom:1.3},result).length,9);
assert.ok(Math.abs(context.floorCoordinates(1,-15,-3,result).z) < 1e-9);
assert.equal(context.floorCoordinates(0,-100,0,result), null, 'no invented extrapolation');
console.log('Floor-relative crop: descent, ascent, lateral turn, bottom margin and missing support PASS');
