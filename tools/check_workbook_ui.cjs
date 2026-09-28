const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const results=[];
 for(const width of [1440,1024,390]){
  await page.setViewportSize({width,height:950});await page.goto('http://127.0.0.1:8552/');
  await page.waitForSelector('.summary .metric');
  for(const selector of ['[data-view="credits"]','[data-pilot="ecologie"]','[data-pilot="maprimerenov"]','[data-view="movements"]','[data-view="documents"]','[data-view="coverage"]']){
   await page.locator('.nav '+selector).click();
   const link=page.getByRole('link',{name:'Contrôle indépendant des montants'});
   if(!await link.isVisible())throw Error('Audit button hidden');
   const b=await link.boundingBox();if(b.x<0||b.x+b.width>width+1)throw Error('Audit button overflows');
   if(await link.getAttribute('href')!=='https://auditnosdeniers.lexmachine.net/')throw Error('Wrong destination');
  }
  await page.screenshot({path:`reports/integration-classeurs-20260928/ui-${width}.png`});
  results.push({width,all_views_audit_link:true});
 }
 await page.setViewportSize({width:1440,height:950});
 await page.goto('http://127.0.0.1:8552/?start=2017&end=2017&budget=BA&scope=XC&measure=CP');
 const proof=page.locator('button.amount[data-cell-scope="XC/612"][data-stage="EXEC"]').first();await proof.waitFor();await proof.click();
 await page.waitForSelector('#source-dialog[open]');
 await page.waitForFunction(()=>document.querySelector('#source-content').innerText.includes('hors')); 
 const text=await page.locator('#source-content').innerText();
 if(!text.includes('572'))throw Error('Expected programme proof missing');
 if(!text.includes('hors'))throw Error('Budget annexe scope explanation missing');
 await page.screenshot({path:'reports/integration-classeurs-20260928/ui-proof.png'});
 if(errors.length)throw Error(errors.join('\n'));
 fs.writeFileSync('reports/integration-classeurs-20260928/browser.json',JSON.stringify({passed:true,results,provenance_checked:true,errors},null,2));
 console.log(JSON.stringify({passed:true,results}));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
