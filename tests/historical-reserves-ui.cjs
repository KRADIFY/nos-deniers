const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
 const out=path.resolve(__dirname,'../reports/reserves-ecologie-2017-2022-20260910/ui');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage({baseURL:'http://127.0.0.1:8552',viewport:{width:1440,height:1050}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const go=async(q,n)=>{await page.goto('/?'+q);await page.waitForFunction(()=>document.querySelector('#loading').hidden&&!document.querySelector('#export').disabled);await page.locator('#unit').selectOption('1');await page.locator('[data-view="movements"]').click();await page.waitForFunction(n=>document.querySelectorAll('#reserves-table tbody tr').length===n,n);};
  const row=p=>page.locator('#reserves-table tbody tr').filter({has:page.locator('th small',{hasText:p+' ·'})});
  const txt=async p=>(await row(p).innerText()).replace(/\s+/g,' ');
  await go('start=2017&end=2017&scope=TA&measure=CP&budget=BG',8);
  assert((await txt('203')).includes('238 383 395'));
  assert((await txt('203')).includes('155 926 310'));
  assert((await txt('203')).includes('titre 2'));
  assert((await row('203').locator('a').first().getAttribute('href')).endsWith('#page=62'));
  assert((await row('203').locator('a').nth(1).getAttribute('href')).endsWith('#page=63'));
  await go('start=2018&end=2018&scope=TA&measure=CP&budget=BG',8);
  assert((await txt('205')).includes('2 081 616'));
  await go('start=2019&end=2019&scope=TA&measure=CP&budget=BG',8);
  assert((await txt('217')).includes('13 829 480'));
  assert((await txt('217')).includes('1 €'));
  assert.equal(await row('217').locator('.missing-label').count(),1);
  await go('start=2020&end=2020&scope=TA&measure=CP&budget=BG',9);
  assert.equal(await row('355').locator('.missing-label').count(),5);
  assert((await txt('113')).includes('explicitement exclu'));
  await go('start=2022&end=2022&scope=TA&measure=CP&budget=BG',9);
  assert((await txt('203')).includes('59 477 730'));
  const download=await(await page.request.get(await page.locator('#reserves-export').getAttribute('href'))).json();
  assert.equal(download.items.find(r=>r.program==='203').cells.cancellations.nominal_cents,-5947773000);
  await page.screenshot({path:path.join(out,'historique-2022.png'),fullPage:true});
  await go('start=2017&end=2025&scope=TA&measure=CP&budget=BG',80);
  const all=await(await page.request.get(await page.locator('#reserves-export').getAttribute('href'))).json();
  assert.equal(all.integrated_table_count,76);
  assert((await page.locator('#reserves-coverage').innerText()).includes('8 programmes par an de 2017 à 2022'));
  await fs.writeFile(path.join(out,'export-2017-2025.json'),JSON.stringify(all,null,2));
  const links=await page.locator('#reserves-table a').evaluateAll(xs=>[...new Set(xs.map(x=>x.href.split('#')[0]))]);
  assert.equal(links.length,9);
  for(const url of links){const response=await page.request.head(url);assert.equal(response.status(),200);assert(response.headers()['content-type'].startsWith('application/pdf'));}
  await page.setViewportSize({width:390,height:900});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await page.locator('#reserves-heading').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'mobile-historique.png')});
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(out,'validation.json'),JSON.stringify({passed:true,errors,checks:['76_tables_2017_2025','missing_programme_355','signs_and_thousands','2019_source_discrepancy','2018_year_end_note','2020_cp_not_annual_zero','9_source_pdfs','exact_json_export','mobile']},null,2));
  console.log('Historical reserves UI passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});