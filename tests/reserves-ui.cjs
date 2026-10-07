const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
 const out=path.resolve(__dirname,'../reports/reserves-et-consignes-20260909/ui');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage({baseURL:'http://127.0.0.1:8552',viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const ready=()=>page.waitForFunction(()=>document.querySelector('#loading').hidden&&!document.querySelector('#export').disabled);
  await page.goto('/?start=2024&end=2024&measure=CP&budget=BG&scope=TA%2F174');await ready();
  await page.locator('#unit').selectOption('1');
  await page.locator('[data-view="movements"]').click();await page.locator('#reserves-table tbody tr').waitFor();
  const table=(await page.locator('#reserves-table').innerText()).replace(/\s+/g,' ');
  assert(table.includes('298 406 398'));assert(table.includes('-1 444 830 817'));assert(table.includes('257 091 666'));
  assert(table.includes('Données non disponibles'));assert(table.includes('437'));
  const source=page.locator('#reserves-table a').first();assert((await source.getAttribute('href')).endsWith('#page=437'));
  const sourceReply=await page.request.head(await source.getAttribute('href'));assert.equal(sourceReply.status(),200);assert(sourceReply.headers()['content-type'].startsWith('application/pdf'));
  const exported=await page.request.get(await page.locator('#reserves-export').getAttribute('href'));assert.equal(exported.status(),200);
  const json=await exported.json();assert(json.selection_id);assert.equal(json.items[0].cells.initial.value,298406398);
  await fs.writeFile(path.join(out,'reserves-selection.json'),JSON.stringify(json,null,2));
  await page.screenshot({path:path.join(out,'reserves-2024.png'),fullPage:true});
  await page.locator('#constant').check();await ready();await page.waitForFunction(()=>!document.querySelector('#reserves-coverage').textContent.includes('Lecture'));
  const corrected=await (await page.request.get('/api/reserves?'+new URL(page.url()).searchParams)).json();assert.notEqual(corrected.items[0].cells.initial.value,298406398);
  await page.goto('/?start=2017&end=2026&measure=AE&budget=BG&scope=TA%2F174');await ready();await page.locator('[data-view="movements"]').click();await page.waitForFunction(()=>document.querySelectorAll('#reserves-table tbody tr').length===9);
  assert((await page.locator('#reserves-missing').innerText()).includes('2026'));
  await page.setViewportSize({width:390,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await page.screenshot({path:path.join(out,'reserves-mobile.png'),fullPage:true});
  await page.goto('/?start=2024&end=2024&measure=CP&budget=BG&scope=TA%2F174&topic=maprimerenov&topic_mode=without');await ready();await page.locator('[data-view="movements"]').click();await page.locator('#reserves-table tbody tr').waitFor();
  const amounts=await page.locator('#reserves-table tbody tr td').allTextContents();assert(amounts.slice(0,5).every(x=>x==='Données non disponibles · Pourquoi ?'));
  assert((await page.locator('#reserves-missing').innerText()).includes('MaPrimeRénov’'));
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(out,'reserves-result.json'),JSON.stringify({passed:true,errors,checks:['source_pdf_opens','exact_cp_display','grouped_numbers','null_not_zero','json_export','inflation','nine_years','2026_missing','mobile','mpr_subtraction_unavailable']}));
  console.log('Reserves UI passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
