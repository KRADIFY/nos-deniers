'use strict';
// Render the current browser code with isolated DOM/fetch responses.
// No browser, server, network, financial recalculation or source-data mutation.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const crypto=require('node:crypto');
const sourcePath=path.resolve(__dirname,'../public/assets/explorer.js');
const source=fs.readFileSync(sourcePath,'utf8');
assert.equal((source.match(/^init\(\);\s*$/gm)||[]).length,1);
const elements=new Map(),requests=[];
function element(id){
 if(!elements.has(id)){
  const attrs=new Map();
  elements.set(id,{innerHTML:'',textContent:'',value:id==='unit'?'1':'',hidden:false,
   selectedOptions:[{textContent:'Budget général'}],
   addEventListener(){},classList:{toggle(){}},
   insertAdjacentHTML(position,html){assert.equal(position,'beforeend');this.innerHTML+=html;},
   setAttribute(k,v){attrs.set(k,String(v));},removeAttribute(k){attrs.delete(k);},
   getAttribute(k){return attrs.get(k)??null;},
   get href(){return attrs.get('href')||'';},set href(v){attrs.set('href',String(v));}
  });
 }
 return elements.get(id);
}
const context=vm.createContext({URL,URLSearchParams,AbortController,Intl,Date,console,setTimeout,clearTimeout,
 fetch:url=>new Promise(resolve=>requests.push({url,respond:body=>resolve({ok:true,json:async()=>body})})),
 document:{getElementById:element,querySelectorAll:()=>[],addEventListener(){}},
 window:{addEventListener(){}},history:{replaceState(){}},location:{search:''},
 localStorage:{getItem:()=>'[]',setItem(){}}
});
vm.runInContext(source.replace(/^init\(\);\s*$/m,''),context,{filename:sourcePath});
const run=code=>vm.runInContext(code,context);
const baseItem={kind:'TOTAL',year:2018,date:'2018-12-31',date_precision:'annual',date_kind:'annual',
 kind_label:'Total annuel net ouvertures et annulations',program:'109',program_label:'Aide au logement',
 title_label:'Autres titres',value:1500,measure:'CP',reason:'',field:'Net annuel publié',
 citation:{url:'/api/download/fixture#page=10',label:'RAP 2018, p. 10'}};
const witnesses=[];
async function movement(overrides,expectedDate,expectedKind){
 const item={...baseItem,...overrides},before=JSON.stringify(item);
 const pending=context.loadRapMovements();
 const request=requests.shift();assert.ok(request.url.startsWith('/api/rap-movements?'));
 request.respond({coverage:'Couverture provenant du service',items:[item],years_without_integrated_rows:[],reconciliations:[]});
 await pending;
 const html=element('rap-movements-table').innerHTML;
 assert.ok(html.includes(expectedDate+'<br><small>'+expectedKind+'</small>'),html);
 if(item.date_precision==='annual'||item.date_kind==='annual'){
  assert.ok(!html.includes('31/12/'),'A placeholder end-of-year date must not be displayed');
  assert.ok(!html.includes('Signature indiquée'),'An annual summary has no known signing date');
 }
 assert.equal(JSON.stringify(item),before,'Rendering must not mutate source data');
 assert.ok(html.includes('+1\u2002500'),'Published amount must retain its formatting and value');
 assert.ok(html.includes('/api/download/fixture#page=10'),'Citation must remain unchanged');
 witnesses.push({input_date:item.date,date_precision:item.date_precision,date_kind:item.date_kind,date:expectedDate,label:expectedKind});
}
async function main(){
 await movement({},'Exercice 2018','Total annuel ; date non connue');
 await movement({kind:'TRANSFERT'},'Exercice 2018','Date non publiée ; exercice indiqué');
 await movement({date_kind:'signature'},'Exercice 2018','Total annuel ; date non connue');
 await movement({date_precision:'day'},'Exercice 2018','Total annuel ; date non connue');
 await movement({year:2024,date:'2024-12-31',date_precision:'day',date_kind:'signature'},'31/12/2024','Signature indiquée dans le RAP');
 await movement({year:2024,date:'2024-03-01',date_precision:'month',date_kind:'month'},'mars 2024','Mois indiqué dans le RAP');
 const coverage=[];
 for(const [version,available] of [['old-local-release',false],['future-restored-release',true]]){
  context.fixture={coverage:[],stages:{},documents:12,meta:{application_version:version,source_count:20,imported_source_count:3,inflation_source:'ipc',issues:[]}};
  context.searchFixture={available,documents:12,passages:99,state:available?'ready':'unavailable',message:available?'':'Service temporairement indisponible'};
  run('bootstrap=fixture;documentSearchStatus=searchFixture;renderCoverage()');
  const note=element('quality-notes').textContent;
  assert.ok(!note.includes('la recherche documentaire fonctionne'));
  assert.ok(note.includes('La disponibilité de la recherche'));
  assert.ok(note.includes('Rapports et documents'));
  assert.ok(note.includes('mouvements RAP 2017–2022'));
  assert.ok(note.includes('couverture reste partielle'));
  assert.ok(note.includes('supérieurs à 10 €'));
  assert.ok(!note.includes('421'),'No hard-coded count of certified historical registries');
  coverage.push(note);
  run("docMode='hybrid';documents=[];renderDocumentMatches()");
  if(available)assert.equal(element('doc-count').textContent,'Texte intégral prêt');
  else assert.ok(element('documents').innerHTML.includes('Recherche documentaire indisponible'));
 }
 assert.equal(coverage[0],coverage[1],'Conditional coverage notice must not depend on a release string');
 assert.equal(requests.length,0);
 console.log(JSON.stringify({passed:true,source_sha256:crypto.createHash('sha256').update(source).digest('hex'),browser_used:false,network_used:false,dates:witnesses,quality_note:coverage[0],search_states_verified:['unavailable','available']},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
