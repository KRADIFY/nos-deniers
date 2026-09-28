'use strict';
// Independent observer: does not evaluate or import the site's JavaScript.
const fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const out={errors:[],visible_cells:0,scenarios:0,units:[1,1000000,1000000000]};
const norm=s=>String(s).replace(/[\s\u00a0\u202f]+/g,' ').trim();
const fmt=(n,u,exact=false)=>new Intl.NumberFormat('fr-FR',{minimumFractionDigits:exact?2:u===1?0:1,maximumFractionDigits:exact?2:u===1?0:1,useGrouping:true}).format(n/(exact?1:u));
const query=p=>new URLSearchParams(Object.entries(p).map(([k,v])=>[k,Array.isArray(v)?JSON.stringify(v):typeof v==='boolean'?String(+v):String(v)])).toString();
function equal(cell,expected,actual){if(norm(expected)!==norm(actual))out.errors.push({cell,expected,actual});}
(async()=>{
 let browser;
 try{
  const executable=process.env.AUDIT_CHROME||['C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(fs.existsSync);
  browser=await chromium.launch({headless:true,...(executable?{executablePath:executable}:{})});
  const page=await browser.newPage({viewport:{width:1500,height:1000}});
  page.on('pageerror',e=>out.errors.push({cell:'erreur JavaScript du site',actual:e.message}));
  for(const p of config.scenarios){
   try{
    const q=query(p);await page.goto(config.url+'/?'+q,{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForFunction(()=>document.querySelector('#loading')?.hidden&&!document.querySelector('#export')?.disabled,{},{timeout:60000});
    const response=await page.request.get(config.url+'/api/explorer?'+q);if(response.status()!==200)throw Error('API '+response.status());
    const data=await response.json();const expected=new Map();
    for(const [id,series] of [[p.scope,data.totals],...data.rows.map(r=>[r.id,r.series])])for(const annual of series)for(const stage of Object.keys(data.stages))expected.set([id,annual.year,stage].join('|'),annual[stage]);
    for(const unit of out.units){
     await page.locator('#unit').selectOption(String(unit));await page.locator('[data-mode="series"]').click();
     for(const stage of Object.keys(data.stages)){
      await page.locator('#stage').selectOption(stage);
      const snapshot=await page.locator('#credits-table').evaluate(table=>({headers:[...table.querySelectorAll('thead th')].map(t=>t.innerText.trim()),rows:[...table.querySelectorAll('tbody tr')].map(tr=>({label:tr.querySelector('th')?.innerText,cells:[...tr.querySelectorAll('button[data-cell-scope][data-stage]')].map(n=>({scope:n.dataset.cellScope,year:+n.dataset.year,stage:n.dataset.stage,text:[...n.childNodes].filter(c=>c.nodeType===3).map(c=>c.textContent).join(''),all:n.innerText,aria:n.getAttribute('aria-label'),column:n.closest('td')?.cellIndex}))}))}));
      let observed=0;
      for(const row of snapshot.rows){
       const rowScopes=new Set(row.cells.map(c=>c.scope));if(rowScopes.size>1)out.errors.push({cell:'plusieurs postes sur une ligne',actual:[...rowScopes]});
       for(const c of row.cells){
        observed++;const key=[c.scope,c.year,c.stage].join('|'),wanted=expected.get(key);
        if(!wanted){out.errors.push({cell:key,expected:'case connue',actual:'case inconnue'});continue;}
        equal(key+' étape sélectionnée',stage,c.stage);
        if(c.column>0){const columnYear=data.years[c.column-1];equal(key+' colonne année',columnYear,c.year);}
        if(wanted.value==null){if(/[0-9]/.test(c.all))out.errors.push({cell:key,expected:'absence sans zéro inventé',actual:c.all});}
        else{
         equal(key+' texte unité '+unit,(wanted.approximate?'≈ ':'')+fmt(wanted.value,unit)+(wanted.status==='partial'?'*':''),c.text);
         if(!norm(c.aria).includes(norm(fmt(wanted.value,1,true))))out.errors.push({cell:key+' montant exact accessible',expected:fmt(wanted.value,1,true),actual:c.aria});
        }
        out.visible_cells++;
       }
      }
      const expectedCount=(data.rows.length+1)*data.years.length;
      if(observed!==expectedCount)out.errors.push({cell:'nombre de cases visibles '+q+' '+stage,expected:expectedCount,actual:observed});
     }
    }
    out.scenarios++;console.log('Affichage contrôlé : '+p.budget+' '+p.measure+' '+p.scope+' '+p.topic);
   }catch(e){out.errors.push({cell:'parcours navigateur',actual:e.message,scenario:p});out.incomplete=true;}
  }
  await page.screenshot({path:path.join(config.output,'controle-affichage.png'),fullPage:false});
 }catch(e){out.errors.push({cell:'navigateur',actual:e.message});out.incomplete=true;}
 finally{if(browser)await browser.close();out.passed=!out.errors.length&&!out.incomplete;fs.writeFileSync(path.join(config.output,'browser.json'),JSON.stringify(out,null,2));}
 process.exitCode=out.passed?0:2;
})();
