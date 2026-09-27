/* Frame-local visual hypothesis, never a safety decision. No source mutation. */
'use strict';
const AutoRails = (() => {
  // Explicit development configuration is required; no guessed geometry on a missing config.
  const keys=('forwardMin forwardMax stationLength lateralMin lateralMax cellWidth minCellPoints '+
    'floorQuantile cellFloorQuantile floorBandBelow floorBandAbove headQuantile headBand flankMin flankMax minFlankCells '+
    'minProminence maxProminence peakSeparation pairMin pairMax maxCrossHeight minStations minSpan maxGap '+
    'minCoverage maxSlope lateralTolerance heightTolerance maxRms ambiguityRatio maxPairsPerStation maxSeedPairs').split(' ');
  const quantile=(a,q)=>{if(!a.length)return NaN;const b=a.slice().sort((x,y)=>x-y);return b[Math.floor((b.length-1)*q)];};
  const fit=(rows,key)=>{const n=rows.length,meanS=rows.reduce((a,r)=>a+r.s,0)/n,
    meanV=rows.reduce((a,r)=>a+r[key],0)/n;
    const den=rows.reduce((a,r)=>a+(r.s-meanS)**2,0);
    const slope=den?rows.reduce((a,r)=>a+(r.s-meanS)*(r[key]-meanV),0)/den:0;
    return {slope,intercept:meanV-slope*meanS};};
  const value=(line,s)=>line.intercept+line.slope*s;
  function stationPeaks(points,s,c) {
    const cells=Array.from({length:Math.ceil((c.lateralMax-c.lateralMin)/c.cellWidth)},()=>[]);
    for(const p of points)cells[Math.floor((p[0]-c.lateralMin)/c.cellWidth)].push(p);
    // Equal lateral-cell weight prevents dense side-wall returns from setting floor height.
    const floor=quantile(cells.filter(a=>a.length>=c.minCellPoints).map(a=>quantile(a.map(p=>p[2]),c.cellFloorQuantile)),c.floorQuantile);
    for(let i=0;i<cells.length;i++)cells[i]=cells[i].filter(p=>p[2]>=floor-c.floorBandBelow&&p[2]<=floor+c.floorBandAbove);
    const heights=cells.map(a=>a.length>=c.minCellPoints?quantile(a.map(p=>p[2]),c.headQuantile):NaN);
    const peaks=[];
    for(let i=0;i<cells.length;i++){
      if(!Number.isFinite(heights[i]))continue;
      const flank=[[],[]];
      for(let j=Math.ceil(c.flankMin/c.cellWidth);j<=Math.floor(c.flankMax/c.cellWidth);j++)
        for(let side=0;side<2;side++){const h=heights[i+(side?j:-j)];if(Number.isFinite(h))flank[side].push(h);}
      if(flank.some(a=>a.length<c.minFlankCells))continue;
      // Both sides must drop: a step, trench edge or wall is not a rail head.
      const prominence=Math.min(...flank.map(a=>heights[i]-quantile(a,.5)));
      if(prominence<c.minProminence||prominence>c.maxProminence)continue;
      const nearHead=cells[i].filter(p=>p[2]>=heights[i]-c.headBand);
      const x=quantile(nearHead.map(p=>p[0]),.5);
      const observed=nearHead.reduce((a,p)=>Math.abs(p[0]-x)+Math.abs(p[1]-s)*.01<
        Math.abs(a[0]-x)+Math.abs(a[1]-s)*.01?p:a);
      peaks.push({s,x,z:heights[i],prominence,point:[observed[0],-observed[1],observed[2]]});
    }
    peaks.sort((a,b)=>b.prominence-a.prominence);
    const selected=[];for(const p of peaks)if(selected.every(q=>Math.abs(p.x-q.x)>c.peakSeparation))selected.push(p);
    return selected.sort((a,b)=>a.x-b.x);
  }
  function detect(positions,options) {
    const c={...options};
    const unknown=(reason,diagnostics={})=>({status:'UNKNOWN',reason,rails:[],rail_pairs:[],support:[],diagnostics,
      safety_decision_permitted:false});
    if(Object.keys(c).some(k=>!keys.includes(k))||keys.some(k=>!Number.isFinite(c[k]))||
      c.forwardMax<=c.forwardMin||c.lateralMax<=c.lateralMin||c.stationLength<=0||c.cellWidth<=0||
      c.pairMin<=0||c.pairMax<c.pairMin||c.minStations<3||c.minSpan<=0||
      c.minCoverage<=0||c.minCoverage>1||c.ambiguityRatio<=0||c.ambiguityRatio>1||
      ['floorQuantile','cellFloorQuantile','headQuantile'].some(k=>c[k]<0||c[k]>1)||
      ['minStations','minCellPoints','minFlankCells','maxPairsPerStation','maxSeedPairs'].some(k=>!Number.isInteger(c[k])||c[k]<1)||
      ['maxGap','maxSlope','lateralTolerance','heightTolerance','maxRms','flankMin','headBand',
        'minProminence','peakSeparation','floorBandAbove','floorBandBelow','maxCrossHeight'].some(k=>c[k]<=0)||
      c.flankMax<c.flankMin||c.maxProminence<c.minProminence||
      Math.ceil((c.forwardMax-c.forwardMin)/c.stationLength)>500||
      Math.ceil((c.lateralMax-c.lateralMin)/c.cellWidth)>2000)
      return unknown('INVALID_SEARCH_PARAMETERS');
    if(positions.length%3)return unknown('INVALID_XYZ');
    const stations=Array.from({length:Math.ceil((c.forwardMax-c.forwardMin)/c.stationLength)},()=>[]);
    for(let i=0;i<positions.length;i+=3){
      const x=positions[i],s=-positions[i+1],z=positions[i+2];
      if(!Number.isFinite(x)||!Number.isFinite(s)||!Number.isFinite(z))return unknown('NONFINITE_XYZ');
      if(s>=c.forwardMin&&s<c.forwardMax&&x>=c.lateralMin&&x<c.lateralMax)
        stations[Math.floor((s-c.forwardMin)/c.stationLength)].push([x,s,z]);
    }
    const bins=stations.map((points,i)=>{
      const s=c.forwardMin+(i+.5)*c.stationLength,peaks=stationPeaks(points,s,c),pairs=[];
      for(let a=0;a<peaks.length;a++)for(let b=a+1;b<peaks.length;b++){
        const l=peaks[a],r=peaks[b],width=r.x-l.x;
        if(width>=c.pairMin&&width<=c.pairMax&&Math.abs(r.z-l.z)<=c.maxCrossHeight)
          pairs.push({s,l:l.x,r:r.x,lz:l.z,rz:r.z,lPoint:l.point,rPoint:r.point,prominence:Math.min(l.prominence,r.prominence)});
      }return {s,peaks,pairs};
    });
    const diagnostics={stationCount:bins.length,pairStations:bins.filter(b=>b.pairs.length).length,
      peakCounts:bins.map(b=>b.peaks.length)};
    if(diagnostics.pairStations<c.minStations)return unknown('INSUFFICIENT_PAIRED_RAIL_SUPPORT',diagnostics);
    let seeds=0;for(let i=0;i<bins.length;i++)for(let j=i+1;j<bins.length;j++)
      if(bins[j].s-bins[i].s>=c.minSpan)seeds+=bins[i].pairs.length*bins[j].pairs.length;
    if(bins.some(b=>b.pairs.length>c.maxPairsPerStation)||seeds>c.maxSeedPairs)
      return unknown('SEARCH_BUDGET_EXCEEDED',diagnostics);
    const model=rows=>Object.fromEntries(['l','r','lz','rz'].map(k=>[k,fit(rows,k)]));
    const error=(p,m)=>Math.max(Math.abs(p.l-value(m.l,p.s))/c.lateralTolerance,
      Math.abs(p.r-value(m.r,p.s))/c.lateralTolerance,Math.abs(p.lz-value(m.lz,p.s))/c.heightTolerance,
      Math.abs(p.rz-value(m.rz,p.s))/c.heightTolerance);
    const gather=m=>bins.map(b=>b.pairs.map(p=>({p,e:error(p,m)})).filter(o=>o.e<=1).sort((a,b)=>a.e-b.e)[0]?.p).filter(Boolean);
    const candidates=[];
    // Global deterministic pair consensus, not cumulative steering from one layer to the next.
    for(let i=0;i<bins.length;i++)for(let j=i+1;j<bins.length;j++){
      if(bins[j].s-bins[i].s<c.minSpan)continue;
      for(const a of bins[i].pairs)for(const b of bins[j].pairs){
        let m=model([a,b]);if(Object.values(m).some(l=>Math.abs(l.slope)>c.maxSlope))continue;
        let rows=gather(m);if(rows.length<c.minStations)continue;
        m=model(rows);rows=gather(m);if(rows.length<c.minStations)continue;
        // Keep only contiguous supported runs; never bridge long missing evidence.
        const runs=[[]];for(const r of rows){const run=runs[runs.length-1];
          if(run.length&&r.s-run[run.length-1].s>c.maxGap)runs.push([]);runs[runs.length-1].push(r);}
        for(const run of runs){
          const span=run.length?run[run.length-1].s-run[0].s:0;
          if(run.length<c.minStations||span<c.minSpan||run.length/(span/c.stationLength+1)<c.minCoverage)continue;
          m=model(run);const centerSlope=(m.l.slope+m.r.slope)/2;
          // Independently fitted rails must be parallel within the residual budget over this span.
          if(Math.abs(m.l.slope-m.r.slope)*span>c.lateralTolerance||Object.values(m).some(l=>Math.abs(l.slope)>c.maxSlope))continue;
          const rms=Math.sqrt(run.reduce((sum,p)=>sum+['l','r','lz','rz'].reduce((a,k)=>a+(p[k]-value(m[k],p.s))**2,0),0)/(run.length*4));
          if(rms>c.maxRms||run.some(p=>error(p,m)>1))continue;
          if([run[0].s,run[run.length-1].s].some(s=>{
            const width=(value(m.r,s)-value(m.l,s))/Math.hypot(1,centerSlope);
            return width<c.pairMin||width>c.pairMax||Math.abs(value(m.rz,s)-value(m.lz,s))>c.maxCrossHeight;
          }))continue;
          candidates.push({m,rows:run,rms,score:run.length,span});
        }
      }
    }
    candidates.sort((a,b)=>b.score-a.score||a.rms-b.rms);
    if(!candidates.length)return unknown('NO_STRAIGHT_CONSISTENT_PAIR',diagnostics);
    const best=candidates[0],start=best.rows[0].s,end=best.rows[best.rows.length-1].s;
    if(candidates.some(v=>v.score>=best.score*c.ambiguityRatio&&
      Math.max(Math.abs(value(v.m.l,start)-value(best.m.l,start)),Math.abs(value(v.m.r,start)-value(best.m.r,start)),
        Math.abs(value(v.m.l,end)-value(best.m.l,end)),Math.abs(value(v.m.r,end)-value(best.m.r,end)))>c.pairMin/2))
      return unknown('AMBIGUOUS_RAIL_PAIRS',diagnostics);
    const rails=[start,end].flatMap(s=>[[value(best.m.l,s),-s,value(best.m.lz,s)],
      [value(best.m.r,s),-s,value(best.m.rz,s)]]);
    const rail_pairs=best.rows.map(p=>({source_s_m:p.s,left_xyz:[...p.lPoint],right_xyz:[...p.rPoint]}));
    return {status:'AUTO_HYPOTHESIS',reason:'PAIRED_RAISED_LINEAR_RIDGES',rails,rail_pairs,
      support:best.rows.flatMap(p=>[p.lPoint,p.rPoint]),
      diagnostics:{...diagnostics,supportedStations:best.rows.length,forwardRange:[start,end],rms:best.rms},
      safety_decision_permitted:false};
  }
  return {detect};
})();
if(typeof module!=='undefined')module.exports=AutoRails;
