const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const D=require('../web/stage_3_objects.js'),c=require('../web/stage_3_objects_config.json');
const identity={index:0,header_timestamp_ns:'test',source_frame:'test'};
function fixture(x=0,s=20){const p=[];for(let k=0;k<6;k++)for(let j=0;j<220;j++)p.push((j%20)/10-.95,-(k*10+1+Math.floor(j/20)*.5),-2);
  for(let j=0;j<20;j++)p.push(x+(j%2)*.03,-s-Math.floor(j/2)*.015,-1+(j%3)*.04);
  p.push(0,-12,-1.99);return new Float32Array(p);}
test('objects follow input coordinates, keep raw and do not require annotation/frame number',()=>{
  for(const [x,s] of [[0,20],[-.8,55],[1.2,3]]){const p=fixture(x,s),b=Buffer.from(p.buffer).toString('hex'),r=D.detect(p,c,identity);
    assert.equal(r.objects.length,1);assert.equal(r.objects[0].point_count,20);
    assert.equal(r.objects[0].nearest.point[0],p[r.objects[0].nearest.source_index*3]);
    assert.equal(Buffer.from(p.buffer).toString('hex'),b);assert.equal(r.safety_decision_permitted,false);
    assert.deepEqual(D.detect(p,c,{...identity,index:99}).objects,r.objects);
    assert.equal(p[p.length-1],Math.fround(-1.99),'low return retained in raw');}
});
test('missing support, invalid input/config, and empty detection never claim CLEAR',()=>{
  for(const [p,config,id] of [[new Float32Array(),c,identity],[new Float32Array([NaN,0,1]),c,identity],
    [fixture(),null,identity],[fixture(),{...c,voxel:0},identity],[fixture(),c,{}]]){
    const r=D.detect(p,config,id);assert.equal(r.status,'UNKNOWN');assert.equal(r.objects.length,0);}
  const r=D.detect(fixture(),{...c,max_voxels:1},identity);assert.equal(r.status,'UNKNOWN');
});
test('real user anchors belong to actual component indices, not merely bounding boxes',()=>{
  const dir='artefacts/stage_2/player_doubleT_obstacle/',m=JSON.parse(fs.readFileSync(dir+'manifest.json'));
  const annotations=require('../config/obstacle_annotations_development.json');
  for(const e of annotations.point_annotations){const f=m.frames[e.frame_index];assert.equal(f.header_timestamp_ns,e.header_timestamp_ns);
    const b=fs.readFileSync(dir+f.file),p=new Float32Array(b.buffer,b.byteOffset,b.length/4),r=D.detect(p,c,f),matches=[];
    for(let i=0;i<p.length;i+=3)if(['x','y','z'].every((k,j)=>p[i+j]===e.anchor_source_coordinates[k]))matches.push(i/3);
    assert.ok(matches.length);const objects=r.objects.filter(o=>matches.some(i=>o.source_indices.includes(i)));
    assert.equal(objects.length,1);assert.ok(objects[0].point_count>=5);
    assert.ok(r.objects.length>1,'must report other candidates, not select by annotation');
    console.log(JSON.stringify({event:e.event_id,count:r.objects.length,matched:D.summary({...r,objects}).objects}));
  }
});
