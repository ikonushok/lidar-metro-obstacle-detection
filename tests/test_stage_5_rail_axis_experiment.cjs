'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),child=require('node:child_process');
test('stage 5 experiment is isolated and records fixed paired comparison',()=>{
  const source=fs.readFileSync(path.resolve(__dirname,'../scripts/stage_5_rail_axis_experiment.cjs'),'utf8');
  assert.match(source,/no global straight regression/);assert.match(source,/no extrapolation/);assert.match(source,/source mutation/);
  assert.doesNotMatch(source,/writeFileSync\(.*web\//);assert.equal(child.spawnSync(process.execPath,['--check',path.resolve(__dirname,'../scripts/stage_5_rail_axis_experiment.cjs')]).status,0);
});
