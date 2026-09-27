const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root,'web/stage_2_raw_player.html'),'utf8');
new vm.Script(html.split('<script>')[1].split('</script>')[0]);
const THREE = require(path.join(root,'artefacts/stage_2/player_doubleT_obstacle/vendor/three.min.js'));
const context=vm.createContext({THREE,Float32Array,Number,Error});
vm.runInContext(html.slice(html.indexOf('  function decodeRawFrame'),html.indexOf('  (() =>')),context);

test('all XYZ survive unchanged including off-axis, low and distant points',()=>{
  const values=new Float32Array([7,-100,-4,-5,-30,2,0,8,-1,2,-300,5]);
  const decoded=context.decodeRawFrame(values.buffer,4);
  assert.equal(decoded.buffer,values.buffer);
  assert.deepEqual([...decoded],[...values]);
  assert.throws(()=>context.decodeRawFrame(values.buffer,3),/manifest/);
  assert.throws(()=>context.decodeRawFrame(new Float32Array([NaN,0,1]).buffer,1),/NaN/);
});

test('frame replacement retains exactly one identity-transformed cloud and disposes old geometry',()=>{
  const scene=new THREE.Scene(),material=new THREE.PointsMaterial();
  const a=new Float32Array([2,-10,-2,3,-20,4]);
  const first=context.replaceRawCloud(scene,null,a,material);
  let disposed=false;first.geometry.addEventListener('dispose',()=>disposed=true);
  const b=new Float32Array([1,-200,6]);
  const second=context.replaceRawCloud(scene,first,b,material);
  assert.equal(scene.children.length,1);assert.equal(scene.children[0],second);
  assert.equal(second.geometry.attributes.position.array,b);
  assert.ok(disposed);second.updateMatrix();
  assert.deepEqual(second.matrix.elements,new THREE.Matrix4().elements);
});

test('first, middle and last real export buffers retain all coordinates',()=>{
  const dir=path.join(root,'artefacts/stage_2/player_doubleT_obstacle');
  const manifest=JSON.parse(fs.readFileSync(path.join(dir,'manifest.json')));
  for(const i of [0,100,200]){
    const frame=manifest.frames[i],file=fs.readFileSync(path.join(dir,frame.file));
    const buffer=file.buffer.slice(file.byteOffset,file.byteOffset+file.byteLength);
    const positions=context.decodeRawFrame(buffer,frame.displayed_points);
    const scene=new THREE.Scene();
    const cloud=context.replaceRawCloud(scene,null,positions,new THREE.PointsMaterial());
    assert.equal(cloud.geometry.attributes.position.count,frame.displayed_points);
    assert.ok(Buffer.from(cloud.geometry.attributes.position.array.buffer).equals(file));
    console.log(`frame ${i}: ${positions.length/3} points, byte-identical GPU input`);
  }
});
