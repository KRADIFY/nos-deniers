const {chromium}=require('C:/Users/Jean-Christophe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const results=[];
try { for (const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]) {
 const page=await browser.newPage({viewport:{width,height}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8552/',{waitUntil:'networkidle'});await page.locator('#sources tr').first().waitFor();
 const rows=await page.locator('#sources tr').count();if(rows!==26)throw Error('Nombre de sources incorrect: '+rows);
 await page.getByRole('button',{name:'Actualiser l’affichage'}).click();await page.waitForLoadState('networkidle');
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);if(overflow||errors.length)throw Error(JSON.stringify({overflow,errors}));
 await page.screenshot({path:'reports/ui-'+name+'.png',fullPage:true});results.push({name,width,rows,overflow,errors});await page.close();
 }
 const page=await browser.newPage();const paths={};for(const p of ['/healthz','/readyz','/api/status','/run/secrets/piste_config.py','/evidence/pap2026.bin','/../compose.yaml','/connections.sqlite3']){const r=await page.request.get('http://127.0.0.1:8552'+p);paths[p]=r.status()}
 if(paths['/healthz']!==200||paths['/api/status']!==200||Object.entries(paths).some(([p,s])=>!['/healthz','/readyz','/api/status'].includes(p)&&s!==404))throw Error('Contrat HTTP incorrect');
 fs.writeFileSync('reports/UI-VERIFICATION.json',JSON.stringify({checked_at:new Date().toISOString(),viewports:results,http:paths},null,2));console.log(JSON.stringify({viewports:results,http:paths}));
}finally{await browser.close()}})().catch(e=>{console.error(e.message);process.exitCode=1});
