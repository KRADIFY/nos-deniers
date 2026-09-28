'use strict';
// Read-only browser test: compare the actual visible amounts with the live API.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const norm=s=>s.replace(/[\s\u2002\u202f\u00a0]+/g,' ').trim();
const format=(n,unit=1,exact=false)=>new Intl.NumberFormat('fr-FR',{minimumFractionDigits:exact?2:unit===1?0:1,maximumFractionDigits:exact?2:unit===1?0:1,useGrouping:true}).format(n/(exact?1:unit));
(async()=>{
 const out=path.resolve(process.argv[2]||'reports/crash-test-display-20260924');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const result={at:new Date().toISOString(),scenarios:[],visibleAmounts:0,missingLabels:0,chartAmounts:0,summaryAmounts:0,errors:[]};
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1050}});page.on('pageerror',e=>result.errors.push(e.message));
  for(const q of ['start=2017&end=2026&measure=CP','start=2017&end=2026&measure=AE&scope=TA','start=2020&end=2025&measure=CP&scope=TA/174','start=2021&end=2025&measure=AE&topic=maprimerenov','start=2021&end=2024&measure=CP&scope=TA&topic=maprimerenov&topic_mode=without&exclude=%5B%22TA%2F345%22%5D','start=2017&end=2025&measure=CP&budget=CAS&constant=1&base=2025','start=2017&end=2026&measure=AE&budget=BA','start=2017&end=2025&measure=CP&budget=CCF']){
   await page.goto('http://127.0.0.1:8552/?'+q);
   const r=await page.request.get('http://127.0.0.1:8552/api/explorer?'+q);assert.equal(r.status(),200);const data=await r.json();
   await page.waitForFunction(()=>document.querySelector('#loading').hidden&&!document.querySelector('#export').disabled);
   const expected=new Map(),scope=new URLSearchParams(q).get('scope')||'';
   for(const [id,series] of [[scope,data.totals],...data.rows.map(r=>[r.id,r.series])])for(const r of series)for(const s of Object.keys(data.stages))expected.set([id,r.year,s].join('|'),r[s]);
   for(const unit of [1,1000000,1000000000]){
    await page.locator('#unit').selectOption(String(unit));
    await page.locator('[data-mode="series"]').click();
    for(const stage of Object.keys(data.stages)){
     await page.locator('#stage').selectOption(stage);
     const cells=await page.locator('#credits-table button[data-cell-scope][data-stage]').evaluateAll(nodes=>nodes.map(n=>({key:[n.dataset.cellScope,n.dataset.year,n.dataset.stage].join('|'),text:n.innerText,aria:n.getAttribute('aria-label')})));
     assert(cells.length>0);
     for(const cell of cells){
      const c=expected.get(cell.key);assert(c,'Unexpected displayed cell '+cell.key);
      if(c.value==null){assert(!/[0-9]/.test(cell.text),'Unavailable figure rendered as number '+cell.key);result.missingLabels++;}
      else{const wanted=(c.approximate?'≈ ':'')+format(c.value,unit)+(c.status==='partial'?'*':'');assert.equal(norm(cell.text),norm(wanted),q+' '+cell.key);assert(norm(cell.aria).includes(norm(format(c.value,1,true))),'Exact accessible amount mismatch '+cell.key);result.visibleAmounts++;}
     }
    }
    const titles=await page.locator('#chart rect title').allTextContents();
    const expectedTitles=data.totals.flatMap(r=>['PLF','LFI','EXEC'].filter(s=>r[s].value!=null).map(s=>`${r.year} · ${data.stages[s]} : ${format(r[s].value,1,true)} €${r[s].status==='partial'?' (partiel)':''}`));
    assert.deepEqual(titles.map(norm),expectedTitles.map(norm));result.chartAmounts+=titles.length;
    const summaries=await page.locator('#summary .metric strong').allTextContents();
    const latest=data.totals.at(-1),last=['PLF','LFI','EXEC'].map(s=>latest[s]);
    const complete=data.totals.every(r=>['ok','excluded'].includes(r.EXEC.status));
    const eligible=data.totals.filter(r=>['ok','excluded'].includes(r.EXEC.status));
    last.push({value:complete?eligible.reduce((a,r)=>a+Math.round(r.EXEC.value*100),0)/100:null,approximate:eligible.some(r=>r.EXEC.approximate)});
    const label=unit===1?'€':unit===1000000?'M€':'Md€';
    assert.equal(summaries.length,4);
    last.forEach((c,i)=>assert.equal(norm(summaries[i]),norm((c.approximate?'≈ ':'')+(c.value==null?'—':format(c.value,unit))+(c.status==='partial'?'*':'')+' '+label),q+' summary '+i));result.summaryAmounts+=4;
   }
   result.scenarios.push(q);console.log('Verified displayed figures: '+q);
  }
  assert.deepEqual(result.errors,[]);result.success=true;
  await page.screenshot({path:path.join(out,'display-tested.png')});
 }catch(e){result.success=false;result.failure={message:e.message,stack:e.stack};throw e;}
 finally{await browser.close();await fs.writeFile(path.join(out,'display-report.json'),JSON.stringify(result,null,2));}
 console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exitCode=1;});
