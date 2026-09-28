const {chromium}=require('playwright');
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await b.newPage({viewport:{width:1440,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root='http://127.0.0.1:8553',run='20260928-142500-016300';
 await page.goto(root+'/reports/'+run+'/rapport.html');if(await page.locator('tbody tr').count()!==163)errors.push('Rapport incomplet');
 await page.screenshot({path:'resultats/verification-163-zeros.png'});
 await page.goto(root+'/zeros?run='+run);await page.locator('#rows tr').first().waitFor();
 await page.locator('#search').fill('2018 869 CP');await page.waitForTimeout(700);
 if(!(await page.locator('#rows').innerText()).includes('0 + 0 = 0'))errors.push('Preuve de calcul absente');
 if(!(await page.locator('#rows').innerText()).includes('PDF · page 6'))errors.push('Repère PDF absent');
 await page.screenshot({path:'resultats/verification-163-preuve.png'});
 await page.setViewportSize({width:390,height:844});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))errors.push('Débordement mobile');
 console.log(JSON.stringify({reportRows:163,calculatedProofVisible:!errors.length,errors}));await b.close();if(errors.length)process.exitCode=2;
})().catch(e=>{console.error(e);process.exit(1)});
