'use strict';
// Real exclusion event handlers and load lifecycle, with deferred fetches.
// A small DOM models attributes; it does not claim browser hit-testing coverage.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const file = path.resolve(__dirname, '../public/assets/explorer.js');
const source = fs.readFileSync(file, 'utf8');
assert.equal((source.match(/^init\(\);\s*$/gm) || []).length, 1);
const elements = new Map(), listeners = new Map(), requests = [];
let visibleButtons=[],focused=null;
function node(dataset = {}) {
  const attrs = new Map();
  return {dataset, innerHTML: '', textContent: '', value: '', hidden: false, disabled: false,
    setAttribute(key, value) { attrs.set(key, String(value)); },
    getAttribute(key) { return attrs.get(key) ?? null; },
    removeAttribute(key) { attrs.delete(key); },
    addEventListener(type, callback) { (this.handlers ??= {})[type]=callback; }, focus() {focused=this;}, classList: {toggle() {}}};
}
function element(id) { if (!elements.has(id)) elements.set(id, node()); return elements.get(id); }
const context = vm.createContext({
  URL, URLSearchParams, AbortController, Intl, Date, console, setTimeout, clearTimeout,
  fetch: (url, options) => new Promise((resolve, reject) => requests.push({
    url: new URL(url, 'http://test.invalid'), options, reject,
    respond(body, ok = true) { resolve({ok, json: async () => body}); }
  })),
  document: {getElementById: element, querySelectorAll: selector => selector.includes('[data-exclude]')?visibleButtons:[],
    addEventListener(type, callback) {if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(callback);}},
  window: {addEventListener() {}}, history: {replaceState() {}}, location: {search: ''},
  localStorage: {getItem: () => '[]', setItem() {}}
});
vm.runInContext(source.replace(/^init\(\);\s*$/m, ''), context, {filename: file});
const run = code => vm.runInContext(code, context);
const flush = () => new Promise(resolve => setImmediate(resolve));

run("load=()=>{globalThis.loaded=JSON.parse(JSON.stringify(state));}; renderChart=()=>{}; data=null;");
const baseline={start:2018,end:2025,budget:'BG',measure:'AE',scope:'TA/174',exclude:['TA/345'],constant:true,base:2020,topic:'maprimerenov',topic_mode:'only',denominator:'OUVERT'};
for(const origin of ['credits','movements','documents','coverage']){
 context.initial=baseline;run('state={...initial,exclude:[...initial.exclude]};view='+JSON.stringify(origin));
 element('topic').value='';element('row-search').value='ancien filtre';element('topic').handlers.change();
 const actual=JSON.parse(run('JSON.stringify(state)'));
 assert.equal(run('view'),'credits');assert.equal(run('currentPilot()'),'');assert.equal(actual.scope,'');assert.deepEqual(actual.exclude,[]);assert.equal(actual.topic_mode,'only');assert.equal(element('row-search').value,'');
 for(const k of ['start','end','budget','measure','constant','base','denominator'])assert.equal(actual[k],baseline[k]);
 assert.equal(element('page-title').textContent,'Évolution des crédits de l’État.');assert.equal(context.loaded.topic,'');
}
run("view='documents'; state={...defaults,budget:'CAS',scope:'ZA',exclude:['ZA/811']};");element('topic').value='maprimerenov';element('topic').handlers.change();
assert.equal(run('view'),'credits');assert.equal(run('currentPilot()'),'maprimerenov');assert.equal(context.loaded.budget,'BG');assert.equal(context.loaded.scope,'');
run("view='credits';state={...defaults,topic:'maprimerenov',scope:'TA',exclude:['TA/345']};");element('topic_mode').value='without';element('topic_mode').handlers.change();
assert.equal(context.loaded.scope,'TA');assert.deepEqual(Array.from(context.loaded.exclude),['TA/345']);assert.equal(context.loaded.topic_mode,'without');
console.log('6 parcours Grand dossier réussis ; paramètres de comparaison conservés.');
