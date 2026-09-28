const fs=require('node:fs');const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});const p=await b.newPage({viewport:{width:1440,height:1000}});const errors=[];p.on('pageerror',e=>errors.push(e.message));const run='20260928-135814-e77928';
await p.goto('http://127.0.0.1:8553/zeros?run='+run);await p.locator('#rows tr').first().waitFor();
await p.locator('#status').selectOption('source_zero');await p.locator('#search').fill('2024 CP');await p.waitForTimeout(700);await p.screenshot({path:'resultats/auditeur-zeros.png',fullPage:false});
const count=await p.locator('#rows tr').count();if(!count)errors.push('Recherche des zéros sans résultat');
await p.locator('#search').fill('');await p.locator('#kind').selectOption('cases');await p.waitForTimeout(700);await p.locator('#rows tr').first().waitFor();
await p.setViewportSize({width:390,height:844});if(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth))errors.push('Débordement global du tableau mobile');await p.screenshot({path:'resultats/auditeur-zeros-mobile.png',fullPage:false});
console.log(JSON.stringify({errors,filteredRows:count}));await b.close();if(errors.length)process.exitCode=2;})();
