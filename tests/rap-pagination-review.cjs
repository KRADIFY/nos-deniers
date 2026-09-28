'use strict';
// Exercise the actual browser functions and delegated click handler in a small
// DOM/fetch harness. No browser, server, financial recalculation or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');

const root = path.resolve(__dirname, '..');
const sourcePath = path.join(root, 'public/assets/explorer.js');
const source = fs.readFileSync(sourcePath, 'utf8');
assert.equal((source.match(/^init\(\);\s*$/gm) || []).length, 1);
const elements = new Map();
const listeners = new Map();
function element(id) {
  if (!elements.has(id)) {
    const attrs = new Map(); let htmlContent = "";
    elements.set(id, {
      get innerHTML(){return htmlContent;}, set innerHTML(value){htmlContent=String(value);if(id==='rap-movements-table'){const m=htmlContent.match(/<tbody[^>]*>([\s\S]*)<\/tbody>/);element('rap-movements-body').innerHTML=m?m[1]:'';}}, textContent: '', value: id === 'unit' ? '1' : '',
      hidden: false, disabled: false, checked: false,
      addEventListener() {}, focus() {},
      insertAdjacentHTML(position, html) { assert.equal(position, 'beforeend'); this.innerHTML += html; },
      setAttribute(key, value) { attrs.set(key, String(value)); },
      removeAttribute(key) { attrs.delete(key); },
      getAttribute(key) { return attrs.get(key) ?? null; },
      get href() { return attrs.get('href') || ''; },
      set href(value) { attrs.set('href', String(value)); },
      classList: {toggle() {}}
    });
  }
  return elements.get(id);
}
const requests = [];
function fetchMock(url, options) {
  return new Promise((resolve, reject) => requests.push({
    url: new URL(url, 'http://test.invalid'), options, reject,
    respond(body, ok = true) { resolve({ok, json: async () => body}); }
  }));
}
const context = vm.createContext({
  URL, URLSearchParams, AbortController, Intl, Date, console,
  fetch: fetchMock,
  document: {
    getElementById: element,
    querySelectorAll: () => [],
    addEventListener(type, callback) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(callback);
    }
  },
  window: {addEventListener() {}},
  history: {replaceState() {}},
  location: {search: ''},
  localStorage: {getItem: () => '[]', setItem() {}},
  setTimeout, clearTimeout
});
// Suppress only automatic bootstrap. All tested functions and listeners are
// evaluated from the current application file, not copied into the test.
vm.runInContext(source.replace(/^init\(\);\s*$/m, ''), context, {filename: sourcePath});
const run = code => vm.runInContext(code, context);
const state = () => JSON.parse(run('JSON.stringify(state)'));
const nextRequest = endpoint => {
  const request = requests.shift();
  assert.ok(request, 'Expected an HTTP request');
  assert.equal(request.url.pathname, endpoint);
  return request;
};
const flush = () => new Promise(resolve => setImmediate(resolve));
function inactive() {
  assert.equal(element('rap-movements-table').innerHTML, '');
  assert.equal(element('rap-movements-notes').textContent, '');
  assert.equal(element('rap-movements-export').getAttribute('href'), null);
  assert.equal(element('rap-movements-export').getAttribute('aria-disabled'), 'true');
}
function rap(label, measure = 'CP') {
  return {coverage: label, years_without_integrated_rows: [], items: [{
    date: '2025-02-05', date_precision: 'day', date_kind: 'signature',
    kind_label: label, program: '174', program_label: 'Énergie, climat et après-mines',
    value: 302578, measure, reason: '', field: 'Autres titres : ouvertures',
    citation: {url: '/api/download/06557292eccf98885e32#page=403', label: 'RAP 2025, p. 403'}
  }]};
}
function click(dataset) {
  const button = {dataset};
  for (const callback of listeners.get('click') || []) {
    callback({target: {closest: selector => selector === 'button' ? button : null}});
  }
}

async function main(){
 run("state={...defaults,start:2023,end:2025,scope:'',measure:'AE',exclude:[]}");
 const scenarios=[];
 function page(offset,length,count=1003){
  const base=rap('base','AE');return {...base,selection_id:'VERSION-A',count,displayed_count:offset+length,has_more:offset+length<count,next_offset:offset+length<count?offset+length:null,items:Array.from({length},(_,i)=>({...base.items[0],kind_label:'ROW_'+(offset+i)+'_END'}))};
 }
 let pending=context.loadRapMovements();let req=nextRequest('/api/rap-movements');
 assert.equal(req.url.searchParams.get('view'),'summary');assert.equal(req.url.searchParams.get('limit'),'500');assert.equal(req.url.searchParams.get('offset'),'0');req.respond(page(0,500));await pending;
 assert.equal((element('rap-movements-body').innerHTML.match(/<tr>/g)||[]).length,500);assert.equal(element('rap-movements-more').hidden,false);
 pending=context.loadRapMovements(true);req=nextRequest('/api/rap-movements');assert.equal(req.url.searchParams.get('offset'),'500');req.respond({error:'Temporary page failure'},false);await pending;
 assert.equal((element('rap-movements-body').innerHTML.match(/<tr>/g)||[]).length,500);assert.equal(element('rap-movements-more').disabled,false);
 scenarios.push('A failed subsequent page keeps already rendered rows and allows retry');
 pending=context.loadRapMovements(true);req=nextRequest('/api/rap-movements');assert.equal(req.url.searchParams.get('offset'),'500');req.respond(page(500,500));await pending;
 pending=context.loadRapMovements(true);req=nextRequest('/api/rap-movements');assert.equal(req.url.searchParams.get('offset'),'1000');req.respond(page(1000,3));await pending;
 const rendered=[...element('rap-movements-body').innerHTML.matchAll(/ROW_(\d+)_END/g)].map(m=>Number(m[1]));assert.deepEqual(rendered,Array.from({length:1003},(_,i)=>i));assert.equal(element('rap-movements-more').hidden,true);
 const download=new URL(element('rap-movements-export').href,'http://test.invalid');for(const name of ['view','offset','limit'])assert.equal(download.searchParams.has(name),false);assert.equal(download.searchParams.get('download'),'1');assert.equal(download.searchParams.get('measure'),'AE');
 scenarios.push('500, 500 and 3 displayed rows form the exact result sequence; export omits every page parameter');
 pending=context.loadRapMovements();req=nextRequest('/api/rap-movements');req.respond(page(0,500));await pending;
 const stale=context.loadRapMovements(true);const staleReq=nextRequest('/api/rap-movements');
 run("state={...state,scope:'AD/365',measure:'CP'}");pending=context.loadRapMovements();req=nextRequest('/api/rap-movements');req.respond(page(0,1,1));await pending;const currentHTML=element('rap-movements-body').innerHTML;
 staleReq.respond(page(500,500));await stale;assert.equal(element('rap-movements-body').innerHTML,currentHTML);assert.equal(element('rap-movements-more').hidden,true);
 scenarios.push('A pending old subsequent page cannot append after a new selection');
 pending=context.loadRapMovements();req=nextRequest('/api/rap-movements');const oldPage=page(0,500);oldPage.items=oldPage.items.map(r=>({...r,kind_label:'OLDVER_'+r.kind_label}));req.respond(oldPage);await pending;
 pending=context.loadRapMovements(true);req=nextRequest('/api/rap-movements');const changed=page(500,500);changed.selection_id='VERSION-B';changed.items=changed.items.map(r=>({...r,kind_label:'NEWVER_'+r.kind_label}));req.respond(changed);await flush();
 const restart=nextRequest('/api/rap-movements');assert.equal(restart.url.searchParams.get('offset'),'0');const replacement=page(0,2,2);replacement.selection_id='VERSION-B';replacement.items=replacement.items.map(r=>({...r,kind_label:'NEWVER_'+r.kind_label}));restart.respond(replacement);await pending;
 assert.ok(!element('rap-movements-body').innerHTML.includes('OLDVER_'));assert.ok(element('rap-movements-body').innerHTML.includes('NEWVER_'));assert.equal((element('rap-movements-body').innerHTML.match(/<tr>/g)||[]).length,2);assert.match(element('rap-movements-coverage').textContent,/sources ont changé/);
 scenarios.push('A changed server selection fingerprint restarts the first page and never mixes source versions');
 const external=context.sourceExplanation({title:'Proof',summary:'',references:[{url:'https://www.budget.gouv.fr/documentation/file-download/28577',page:2,label:'Circular'}]});
 assert.match(external,/href="https:\/\/www\.budget\.gouv\.fr\/documentation\/file-download\/28577#page=2"/);assert.match(external,/PDF p\. 2/);
 const html=context.sourceExplanation({title:'Proof',summary:'',references:[{url:'https://www.assemblee-nationale.fr/report.html#note-76',locator:'note 76',label:'Report'}]});assert.ok(!html.includes('#page='));assert.ok(!html.includes('PDF p.'));assert.match(html,/note 76/);assert.match(html,/href="https:\/\/www\.assemblee-nationale\.fr\/report\.html#note-76"/);
 const unsafe=context.sourceExplanation({title:'Proof',summary:'',references:[{url:'javascript:alert(1)',label:'Unsafe'}]});assert.ok(!unsafe.includes('href='));
 scenarios.push('External PDF references reach the cited page; HTML locators and unsafe URLs remain distinct');
 pending=context.loadRapMovements();req=nextRequest('/api/rap-movements');
 const partial=rap('Mouvement BA vérifié','AE');partial.items[0]={...partial.items[0],year:2019,program:'613',annual_reconciliation_status:'annual_reference_unavailable',annual_reconciliation_note:'Rapprochement annuel indisponible'};partial.reconciliations=[{year:2019,program:'613',measure:'AE',status:'annual_reference_unavailable',canonical_cents:null,difference_cents:null,note:'Rapprochement annuel indisponible'}];req.respond(partial);await pending;
 assert.match(element('rap-movements-body').innerHTML,/<small>AE<br>Tableau détaillé vérifié ; rapprochement annuel indisponible\.<\/small>/);assert.match(element('rap-movements-body').innerHTML,/302/);assert.match(element('rap-movements-notes').textContent,/2019 · P613 · AE : Rapprochement annuel indisponible/);
 scenarios.push('A published partial movement retains its amount with an adjacent annual-reconciliation warning');
 pending=context.loadRapMovements();req=nextRequest('/api/rap-movements');const undated=rap('Report FDC sans date','AE');undated.items[0]={...undated.items[0],year:2018,date:'2018',date_precision:'annual',date_kind:'annual',kind:'REPORT_FDC'};req.respond(undated);await pending;
 assert.match(element('rap-movements-body').innerHTML,/Date non publiée ; exercice indiqué/);assert.ok(!element('rap-movements-body').innerHTML.includes('Total annuel ; date non connue'));
 scenarios.push('An undated source row is described as undated and is never labelled an annual total');
 console.log(JSON.stringify({passed:true,scenarios,source_sha256:crypto.createHash('sha256').update(source).digest('hex'),network_used:false},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
