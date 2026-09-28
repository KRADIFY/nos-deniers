const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
 const out=path.resolve(__dirname,'../reports/finalisation-20260919/ui');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({baseURL:'http://127.0.0.1:8552',viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('/?start=2020&end=2025&scope=TA&measure=CP&budget=BG');
  await page.locator('#loading').waitFor({state:'hidden'});
  await page.locator('[data-view="documents"]').click();await page.locator('.document').first().waitFor();
  await page.locator('[data-doc-mode="hybrid"]').click();
  await page.locator('#documents[aria-busy="false"]').waitFor({timeout:30000});
  await page.locator('#doc-year').selectOption('2020');
  await page.locator('#documents[aria-busy="false"]').waitFor({timeout:30000});
  await page.locator('#doc-search').fill('MaPrimeRénov crédits AE CP LFI consommation');
  await page.locator('#doc-submit').click();
  await page.locator('.document-match').first().waitFor({timeout:90000});
  const text=await page.locator('.document-match').first().innerText();
  assert(/prime|mpr/i.test(text));
  const pageLinks=await page.locator('.document-match a[href*="#page="]').count();assert(pageLinks>0);
  await page.locator('.document-match').first().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'recherche-semantique.png')});
  await page.locator('[data-passage]').first().click();await page.locator('#source-content .document-excerpt').waitFor();
  assert((await page.locator('#source-content').innerText()).includes('Empreinte du passage'));
  assert.equal(await page.locator('#source-dialog .eyebrow').innerText(),'PASSAGE DU DOCUMENT SOURCE');
  await page.screenshot({path:path.join(out,'passage-source.png')});await page.locator('#close-source').click();
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await page.screenshot({path:path.join(out,'recherche-mobile.png')});
  assert.deepEqual(errors,[]);await fs.writeFile(path.join(out,'result.json'),JSON.stringify({passed:true,errors,pageLinks,firstResult:text},null,2));
  console.log('Semantic UI passed: real results, source pages, full passage, mobile');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});