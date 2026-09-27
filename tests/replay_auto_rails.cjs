// Development regression, not accuracy evaluation against labelled rails.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const A=require('../web/stage_2_auto_rails.js'),config=require('../web/stage_2_auto_rails_config.json');
const dir=path.resolve(__dirname,'../artefacts/stage_2/player_doubleT_obstacle');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'manifest.json')));
const times=[],unknown=[],ranges=[],centers=[],rms=[];
for(const frame of manifest.frames){
  const b=fs.readFileSync(path.join(dir,frame.file)),before=Buffer.from(b);
  const raw=new Float32Array(b.buffer,b.byteOffset,b.length/4),start=performance.now();
  const r=A.detect(raw,config);times.push(performance.now()-start);
  assert.ok(b.equals(before),`source mutation in frame ${frame.index}`);
  assert.equal(r.safety_decision_permitted,false);
  if(r.status!=='AUTO_HYPOTHESIS'){unknown.push([frame.index,r.reason]);continue;}
  ranges.push(r.diagnostics.forwardRange);rms.push(r.diagnostics.rms);
  const a=r.rails[0].map((v,j)=>(v+r.rails[1][j])/2),z=r.rails[2].map((v,j)=>(v+r.rails[3][j])/2);
  centers.push(a[0]+(z[0]-a[0])*((-20-a[1])/(z[1]-a[1])));
}
times.sort((a,b)=>a-b);
const minmax=a=>a.length?[Math.min(...a),Math.max(...a)]:null;
console.log(JSON.stringify({scope:'single development export, no rail ground truth',frames:manifest.frames.length,
  hypotheses:ranges.length,unknown,source_buffers_changed:0,start_minmax:minmax(ranges.map(r=>r[0])),
  end_minmax:minmax(ranges.map(r=>r[1])),rms_max:rms.length?Math.max(...rms):null,
  center_x_at_y_minus20_minmax:minmax(centers),ms_median:times[Math.floor(times.length*.5)],
  ms_p95:times[Math.floor(times.length*.95)],ms_max:times[times.length-1]},null,2));
