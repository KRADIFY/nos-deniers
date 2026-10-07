const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
 const out=path.resolve(__dirname,'../reports/rap-limits-20260920');
 const baseURL='http://127.0.0.1:8552';
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const context=await browser.newContext({baseURL,viewport:{width:1440,height:1050},permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const load=async query=>{
   await page.goto('/?'+query);await page.waitForFunction(()=>document.querySelector('#loading').hidden&&!document.querySelector('#export').disabled);
   await page.locator('[data-view="movements"]').click();
   await page.waitForFunction(()=>document.querySelector('#rap-movements-export').hasAttribute('href')&&!document.querySelector('#reserves-coverage').textContent.includes('Lecture'));
  };
  await load('start=2024&end=2024&scope=TA&measure=CP&topic=maprimerenov&topic_mode=without');
  const rows=page.locator('#rap-movements-table tbody tr');
  const p203=rows.filter({hasText:'203 ·'}),p174=rows.filter({hasText:'174 ·'});
  assert(await p203.count());assert.equal(await p203.locator('[data-rap-explanation]').count(),0);
  assert(await p174.locator('[data-rap-explanation]').count());
  await p174.locator('[data-rap-explanation]').first().click();await page.locator('.quality-explanation').waitFor();
  assert((await page.locator('.quality-explanation').innerText()).includes('MaPrimeRénov’'));
  await page.locator('.quality-requests summary').click();
  const request=await page.locator('#quality-request').inputValue();assert(request.includes('TA/174')&&request.includes('2024')&&request.includes('CP'));
  await page.locator('[data-copy-quality]').click();assert.equal((await page.evaluate(()=>navigator.clipboard.readText())).replace(/\r\n/g,'\n'),request);
  await page.locator('#close-source').click();
  const exported=await (await page.request.get(await page.locator('#rap-movements-export').getAttribute('href'))).json();
  assert(exported.items.some(r=>r.program==='203'&&r.value!==null));
  assert(exported.items.filter(r=>r.program==='174').every(r=>r.value===null));
  const reserve=page.locator('#reserves-table tbody tr').filter({hasText:'174 ·'});
  await reserve.locator('[data-rap-explanation]').first().click();assert((await page.locator('#source-content').innerText()).includes('MaPrimeRénov’'));await page.locator('#close-source').click();
  await load('start=2025&end=2025&scope=AD%2F384&measure=CP');
  const exempt=page.locator('#reserves-table tbody tr');assert.equal(await exempt.locator('button').count(),5);
  assert((await exempt.innerText()).includes('Sans objet'));
  await exempt.locator('button').first().click();
  assert((await page.locator('#source-content').innerText()).includes('aucune mesure de mise en réserve'));
  await page.locator('.quality-explanation details summary').click();
  const link=page.locator('#source-content a[href$="#page=146"]');assert.equal(await link.count(),1);
  assert.equal((await page.request.head(await link.getAttribute('href'))).status(),200);
  await page.screenshot({path:path.join(out,'exemption-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  assert.equal(await page.locator('#source-dialog').evaluate(e=>e.scrollWidth>e.clientWidth+2),false);
  await page.screenshot({path:path.join(out,'exemption-mobile.png')});
  await page.locator('#close-source').click();
  await load('start=2023&end=2023&scope=AD%2F370&measure=AE');
  await page.locator('#rap-movements-gaps summary').click();await page.locator('#rap-movements-gaps button').click();
  assert((await page.locator('#source-content').innerText()).includes('aucune ouverture de crédit'));
  assert(await page.locator('#source-content a[href$="#page=159"]').count());await page.locator('#close-source').click();
  await load('start=2023&end=2023&scope=TA%2F217&measure=CP');
  const source=page.locator('#reserves-table tbody tr button').filter({hasText:'ⓘ'}).last();
  await source.click();assert((await page.locator('#source-content').innerText()).includes('1 €'));
  await page.locator('#close-source').click();
  await load('start=2026&end=2026&scope=TA&measure=CP');
  await page.locator('#reserves-missing button').click();assert((await page.locator('#source-content').innerText()).includes('exercice est en cours'));
  await page.locator('#close-source').click();
  await load('start=2024&end=2024&scope=TA&measure=CP&topic=maprimerenov&topic_mode=only');
  const only=await (await page.request.get('/api/rap-movements?'+new URL(page.url()).searchParams)).json();
  assert.deepEqual([...new Set(only.items.map(r=>r.program))],['174']);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(out,'ui-checks.json'),JSON.stringify({success:true,baseURL,errors,checks:[
   'unrelated-programme-kept','MPR-unallocated-click','request-context','copy-request','export-null-vs-number',
   'reserve-click','documented-exemption','source-PDF','mobile-fit','programme-gap-click','printed-discrepancy-click','2026-explanation','MPR-only-filter']},null,2));
  console.log('13 contrôles navigateur réussis ; aucune erreur JavaScript.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
