const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
 const out=path.resolve(__dirname,'../reports/reserves-et-consignes-20260909/ui');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage({baseURL:'http://127.0.0.1:8552',viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const ready=()=>page.waitForFunction(()=>document.querySelector('#loading').hidden&&!document.querySelector('#export').disabled);
  const action=async(fn)=>{const loaded=page.waitForResponse(r=>r.url().includes('/api/explorer?')&&r.status()===200);await fn();await loaded;await ready();};
  const query=()=>new URL(page.url()).searchParams;
  const active=async(pilot)=>{assert.equal(await page.locator('.nav [aria-current="page"]').count(),1);assert.equal(await page.locator('.nav [aria-current="page"]').getAttribute('data-pilot'),pilot);};
  await page.goto('/?start=2021&end=2024&measure=AE&budget=BG&scope=TA&exclude=%5B%22TA%2F345%22%5D&constant=1&base=2017');await ready();
  await page.locator('#unit').selectOption('1000000000');await page.locator('[data-mode="ratios"]').click();
  await action(()=>page.locator('[data-pilot="maprimerenov"]').click());await active('maprimerenov');
  assert.equal(query().get('topic'),'maprimerenov');assert.equal(query().get('scope'),'');assert.equal(query().get('exclude'),'[]');
  for(const [key,value] of Object.entries({start:'2021',end:'2024',measure:'AE',constant:'1',base:'2017'}))assert.equal(query().get(key),value);
  assert.equal(await page.locator('#unit').inputValue(),'1000000000');assert.equal(await page.locator('[data-mode="ratios"]').getAttribute('class'),'active');
  assert((await page.locator('#credits-table').innerText()).includes('Consommé'));
  await page.screenshot({path:path.join(out,'maprimerenov.png'),fullPage:true});
  await action(()=>page.locator('[data-pilot="ecologie"]').click());await active('ecologie');
  assert.equal(query().get('scope'),'TA');assert.equal(query().get('topic'),'');assert.equal(query().get('measure'),'AE');assert.equal(query().get('constant'),'1');
  await page.reload();await ready();await active('ecologie');
  await page.locator('[data-view="movements"]').click();assert.equal(await page.locator('.nav [aria-current="page"]').getAttribute('data-view'),'movements');
  await page.locator('[data-view="credits"]').click();await active('ecologie');
  await page.screenshot({path:path.join(out,'ecologie.png'),fullPage:true});
  await action(()=>page.locator('[data-pilot="maprimerenov"]').click());
  await action(()=>page.locator('[data-topic-example="ecology"]').click());await active('ecologie');
  assert.equal(query().get('topic_mode'),'without');assert.equal(query().get('scope'),'TA');
  const without=await (await page.request.get('/api/explorer?'+query())).json();
  assert.equal(without.parameters.topic_mode,'without');assert(without.totals.length);
  for(const width of [850,390]){
   await page.setViewportSize({width,height:900});await page.waitForTimeout(200);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Page overflow at '+width);
   await action(()=>page.locator('[data-pilot="ecologie"]').click());await active('ecologie');
  }
  await page.screenshot({path:path.join(out,'ecologie-mobile.png'),fullPage:true});
  await action(()=>page.locator('#reset').click());assert.equal(await page.locator('.nav [aria-current="page"]').getAttribute('data-view'),'credits');
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify({passed:true,errors,checks:['two_direct_dossiers','exclusive_active_tab','preserved_analysis_filters','clear_previous_exclusions','reload','movement_view','ecology_without_mpr','mobile_overflow','reset']},null,2));
  console.log('Pilot dossiers UI passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
