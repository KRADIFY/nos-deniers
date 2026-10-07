const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
 const out=path.resolve(__dirname,'../reports/fdc-prevus-2023-20260910/ui');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  const page=await browser.newPage({baseURL:'http://127.0.0.1:8552',viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const ready=()=>page.waitForFunction(()=>document.querySelector('#loading').hidden&&!document.querySelector('#export').disabled);
  const query='start=2023&end=2023&scope=TA&measure=CP&budget=BG';
  await page.goto('/?'+query);await ready();await page.locator('#unit').selectOption('1');await page.locator('[data-view="movements"]').click();
  const button=page.locator('#movements-table [data-stage="FDC_PREVU"]');
  assert((await button.innerText()).replace(/\s+/g,' ').includes('2 778 942 926'));
  assert((await page.locator('#movements-table [data-stage="FDC"]').innerText()).replace(/\s+/g,' ').includes('3 632 480 161'));
  await button.click();await page.waitForFunction(()=>document.querySelector('#source-content').textContent.includes('PAP2023'));
  assert((await page.locator('#source-content').innerText()).includes('prevision_fdc_adp_2023_cp'));
  await page.keyboard.press('Escape');await page.locator('#movements-table').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'previsions-et-rattachements.png')});
  const detail=await(await page.request.get('/api/explorer?'+query+'&exclude=%5B%22TA%2F203%22%5D')).json();
  assert.equal(detail.totals[0].FDC_PREVU.nominal_cents,3483409700);
  const action=await(await page.request.get('/api/explorer?start=2023&end=2023&scope=TA%2F203%2F41')).json();assert.equal(action.totals[0].FDC_PREVU.value,null);
  const source=await(await page.request.get('/api/provenance?'+query+'&year=2023&stage=FDC_PREVU&cell_scope=TA')).json();
  assert(source.rows.every(r=>r.source==='21342e83b18e59c74d21'&&r.stage==='FDC_PREVU'&&r.year===2023));assert.equal(source.sources.length,1);
  const excel=await page.request.get('/api/export.xlsx?'+query);assert.equal(excel.status(),200);await fs.writeFile(path.join(out,'ecologie-2023.xlsx'),await excel.body());
  const real=await(await page.request.get('/api/explorer?'+query+'&constant=1&base=2017')).json();assert(real.totals[0].FDC_PREVU.value<2778942926);assert.equal(real.totals[0].FDC_PREVU.nominal_cents,277894292600);
  await page.goto('/?start=2023&end=2023&scope=TA%2F174');await ready();await page.locator('[data-view="movements"]').click();
  assert.equal((await page.locator('#movements-table [data-stage="FDC_PREVU"]').innerText()).trim().replace(',','.'),'0.0');
  assert.deepEqual(errors,[]);await fs.writeFile(path.join(out,'validation.json'),JSON.stringify({passed:true,errors,checks:['forecast_vs_attached','exact_cp','source_provenance','programme_exclusion','action_unavailable','xlsx_export','inflation','published_zero']},null,2));
  console.log('FdC forecasts UI passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});