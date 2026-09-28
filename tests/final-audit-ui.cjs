const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
 const out=path.resolve(__dirname,'../reports/audit-final-20260920');
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage({baseURL:'http://127.0.0.1:8552',viewport:{width:1440,height:1050}});
  const errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
  const load=async q=>{await page.goto('/?'+q);await page.waitForFunction(()=>document.querySelector('#loading').hidden&&!document.querySelector('#export').disabled);};
  const get=async route=>{const r=await page.request.get(route);assert.equal(r.status(),200,route);return r.json();};
  await load('start=2020&end=2022&topic=maprimerenov&measure=CP');
  let d=await get('/api/explorer?start=2020&end=2022&topic=maprimerenov&measure=CP');
  assert.equal(d.totals[0].EXEC.value,455000000);assert.equal(d.totals[1].LFI.value,1655000000);assert.equal(d.totals[2].PLF.value,1955500000);
  const button=page.locator('#credits-table button[data-year="2021"][data-stage="LFI"][data-cell-scope=""]');
  await button.click();await page.locator('#source-content .source-card').first().waitFor();
  const link=page.locator('#source-content a[href="/api/download/2ee68df9e243bf45b79d#page=32"]');assert(await link.count()>=1);
  assert.equal((await page.request.head(await link.first().getAttribute('href'))).status(),200);await page.locator('#close-source').click();checks.push('historical-MPR-and-source-page');
  await page.screenshot({path:path.join(out,'mpr-final-desktop.png')});
  await page.locator('#unit').selectOption('1');assert(/1[\s\u202f\u00a0]655[\s\u202f\u00a0]000[\s\u202f\u00a0]000/.test(await button.innerText()));checks.push('french-thousands-separator');
  const q='start=2021&end=2021&topic=maprimerenov&measure=CP';
  const nominal=await get('/api/selection?'+q);const real=await get('/api/selection?'+q+'&constant=1&base=2025');
  assert(nominal.sources.length>0);assert(nominal.selection_id!==real.selection_id);assert.equal(real.totals[0].LFI.nominal,1655000000);assert(real.totals[0].LFI.value>1655000000);checks.push('inflation-and-selection-provenance');
  for(const [route,file,magic] of [['/api/export.xlsx?','audit-selection.xlsx','504b'],['/api/export?','audit-selection.csv','efbbbf']]){
   const r=await page.request.get(route+q);assert.equal(r.status(),200);const b=await r.body();assert(b.toString('hex').startsWith(magic));await fs.writeFile(path.join(out,file),b);
  }checks.push('CSV-and-XLSX-download');
  await load('start=2024&end=2024&scope=TA&measure=CP');
  const preset=page.locator('[data-ecology-preset="selected"]');
  await preset.click();await page.waitForFunction(()=>document.querySelector('#loading').hidden);
  assert.equal(await page.locator('#exclude-count').innerText(),'3');
  for(const selector of ['#exclusions [data-exclude="TA/345"]','#exclusions [data-exclude="TA/235"]','#exclusions [data-toggle-topic]']){
   const sw=page.locator(selector);assert.equal(await sw.getAttribute('aria-checked'),'false');
   await sw.click();await page.waitForFunction(()=>document.querySelector('#loading').hidden);
   assert.equal(await sw.getAttribute('aria-checked'),'true');
  }
  assert.equal(await page.locator('#exclude-count').innerText(),'0');checks.push('three-independent-instant-switches');
  await load('start=2017&end=2026&scope=TA&measure=CP');
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  const widths=await page.locator('#chart rect').evaluateAll(nodes=>nodes.map(x=>Number(x.getAttribute('width'))));assert(widths.every(x=>x>=0));
  await page.screenshot({path:path.join(out,'ecologie-final-mobile.png')});checks.push('mobile-and-ten-year-chart');
  await page.locator('[data-view="coverage"]').click();assert(!(await page.locator('#quality-notes').innerText()).includes('PLF 2026 et l’exécution 2026 restent à intégrer'));checks.push('coverage-updated');
  for(const route of ['/api/explorer?start=9999','/api/explorer?scope=..%2F..%2Fsecrets','/api/provenance?year=2024&stage=INVALID','/api/download/does-not-exist','/.env']){
   const r=await page.request.get(route);assert([400,404].includes(r.status()),route+' '+r.status());
  }checks.push('invalid-parameters-and-paths');
  const response=await page.request.get('/');assert(response.headers()['content-security-policy'].includes("frame-ancestors 'none'"));assert.equal(response.headers()['x-content-type-options'],'nosniff');checks.push('browser-security-headers');
  assert.deepEqual(errors,[]);await fs.writeFile(path.join(out,'ui-final.json'),JSON.stringify({success:true,checks,errors},null,2));console.log(checks.length+' parcours finaux réussis.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
