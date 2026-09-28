const fs=require('node:fs');const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});const p=await b.newPage({viewport:{width:1440,height:1080}});const errors=[];p.on('pageerror',e=>errors.push(e.message));
await p.goto('http://127.0.0.1:8553/');await p.waitForFunction(()=>document.getElementById('state').textContent!=='Chargement…');
await p.screenshot({path:'resultats/auditeur-accueil.png',fullPage:true});
await p.getByRole('link',{name:'Comprendre la vérification'}).click();await p.getByRole('heading',{name:'Ce que vérifie le moteur indépendant'}).waitFor();
await p.setViewportSize({width:390,height:844});await p.goto('http://127.0.0.1:8553/');await p.screenshot({path:'resultats/auditeur-mobile.png',fullPage:true});
if(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth))errors.push('Débordement horizontal mobile');
await p.getByRole('button',{name:'Lancer la vérification'}).click();await p.getByRole('heading',{name:'Vérification en cours'}).waitFor({timeout:15000});
const state=await(await p.request.get('http://127.0.0.1:8553/api/status')).json();console.log(JSON.stringify({errors,state}));await b.close();if(errors.length)process.exitCode=2;})();
