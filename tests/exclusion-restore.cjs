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
    addEventListener() {}, focus() {focused=this;}, classList: {toggle() {}}};
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
const initial = {start: 2017, end: 2025, measure: 'CP', budget: 'BG', scope: 'TA', exclude: ['TA/345', 'TA/235'], topic: 'maprimerenov', topic_mode: 'without', constant: true, base: 2020, denominator: 'LFI'};
const labels = {'TA/345': 'Service public de l’énergie', 'TA/235': 'Sûreté nucléaire et radioprotection'};
const state = () => JSON.parse(run('JSON.stringify(state)'));
function fixture(parameters) {
  return {parameters:structuredClone(parameters), exclusions: parameters.exclude.map(id => ({id, label: labels[id]})),
    totals: [{year: 2025, EXEC: {value: 1234567.89, nominal_cents: 123456789, status: 'ok'}}]};
}
function reset() {
  assert.equal(requests.length, 0);
  run('finishRestores();state=' + JSON.stringify(initial) + ';data=' + JSON.stringify(fixture(initial)) + ';render=function(){renderExclusions()}');
  context.renderExclusions();
  element('error').hidden = true;
  visibleButtons=[];focused=null;
}
function button(id,kind) {
  const b = node({[kind||(id === 'maprimerenov'?'restoreTopic':'restore')]:id});
  b.setAttribute('aria-checked', 'false');
  return b;
}
function click(b) {
  for (const callback of listeners.get('click') || []) callback({target: {closest: selector => selector === 'button' ? b : null}});
}
function take() {const r = requests.shift(); assert.ok(r); assert.equal(r.url.pathname, '/api/explorer'); return r;}
function pending(b) {assert.equal(b.getAttribute('aria-checked'), 'true'); assert.equal(b.getAttribute('aria-busy'), 'true');}
function retryable(b) {assert.equal(b.getAttribute('aria-checked'), 'false'); assert.equal(b.getAttribute('aria-busy'), null); assert.equal(b.disabled, false);}
function parameters(r) {
  const p=Object.fromEntries(r.url.searchParams);return {...p,start:Number(p.start),end:Number(p.end),base:Number(p.base),constant:p.constant==='1',exclude:JSON.parse(p.exclude)};
}
async function main() {
  const scenarios = [];
  for (const id of ['TA/345', 'TA/235', 'maprimerenov']) {
    reset();
    const b = button(id,id==='maprimerenov'?'toggleTopic':'exclude');visibleButtons=[b];click(b); pending(b);
    const r = take();
    click(b); assert.equal(requests.length, 0); pending(b);
    const p = parameters(r);
    if (id === 'maprimerenov') {assert.equal(p.topic, ''); assert.deepEqual(p.exclude, initial.exclude);}
    else {assert.ok(!p.exclude.includes(id)); assert.equal(p.topic, 'maprimerenov');}
    for (const key of ['start', 'end', 'measure', 'budget', 'scope', 'base', 'denominator']) assert.equal(r.url.searchParams.get(key), String(initial[key]), key);
    assert.equal(r.url.searchParams.get('constant'), '1');
    r.respond(fixture(p)); await flush();
    assert.equal(b.getAttribute('aria-busy'), null);
    assert.equal(Number(element('exclude-count').textContent), 2);
    const attr = id === 'maprimerenov' ? 'data-toggle-topic' : 'data-exclude';
    assert.match(element('exclusions').innerHTML, new RegExp('aria-checked="true"[^>]*'+attr + '="' + id + '"'));
    assert.equal((element('exclusions').innerHTML.match(/class="exclude-chip"/g)||[]).length,3);
    assert.deepEqual(state(), p);
    assert.equal(element('error').hidden, true);
    assert.equal(focused,b);
    click(b);assert.equal(b.getAttribute('aria-checked'),'false');assert.equal(b.getAttribute('aria-busy'),'true');
    const excludeAgain=take();assert.deepEqual(parameters(excludeAgain),{...initial,exclude:id==='maprimerenov'?initial.exclude:[...p.exclude,id]});excludeAgain.respond(fixture(parameters(excludeAgain)));await flush();
    assert.equal(Number(element('exclude-count').textContent),3);
    assert.equal((element('exclusions').innerHTML.match(/class="exclude-chip"/g)||[]).length,3);
    click(b);pending(b);const includeAgain=take();assert.deepEqual(parameters(includeAgain),p);includeAgain.respond(fixture(p));await flush();
    assert.equal(Number(element('exclude-count').textContent),2);
    assert.equal((element('exclusions').innerHTML.match(/class="exclude-chip"/g)||[]).length,3);
  }
  scenarios.push('All three persistent Ecology controls toggle off/on/off/on independently by click, show immediate busy feedback, ignore a second pending click, retain focus and remain visible with the exact exclusion count');

  for(const id of ['TA','TA/174','TA/174/02','TA/345/17/17.03']){
    reset();
    const base={...initial,scope:id.includes('/')?id.slice(0,id.lastIndexOf('/')):'',topic:'',topic_mode:'only',exclude:['AA/105']};
    run('state='+JSON.stringify(base)+';data='+JSON.stringify({...fixture(base),stages:{EXEC:'Consommé'}}));
    const row={id,label:'Poste témoin',code:id.split('/').at(-1),series:[{year:2025,EXEC:{nominal:100}}]};
    const generated=context.categorySwitch(row,false);
    assert.match(generated,/aria-checked="true"/);assert.ok(generated.includes('data-exclude="'+id+'"'));
    const b=button(id,'exclude');b.setAttribute('aria-checked','true');visibleButtons=[b];
    click(b);assert.equal(b.getAttribute('aria-checked'),'false');assert.equal(b.getAttribute('aria-busy'),'true');
    const off=take();assert.deepEqual(parameters(off).exclude,['AA/105',id]);
    off.respond(fixture(parameters(off)));await flush();assert.equal(focused,b);
    click(b);pending(b);const on=take();assert.deepEqual(parameters(on),base);
    on.respond(fixture(base));await flush();assert.equal(focused,b);assert.equal(b.getAttribute('aria-checked'),'true');
  }
  scenarios.push('The same table switch excludes then reincludes each mission, programme, action and sub-action; other filters and exclusions remain unchanged and focus returns to that control');

  reset();
  const excludeTarget='TA/174';const exclusionButton=button(excludeTarget,'exclude');exclusionButton.setAttribute('aria-checked','true');
  click(exclusionButton);const excludeFailure=take();assert.equal(exclusionButton.getAttribute('aria-checked'),'false');
  excludeFailure.respond({error:'Failed exclusion'},false);await flush();
  assert.equal(exclusionButton.getAttribute('aria-checked'),'true');assert.equal(exclusionButton.getAttribute('aria-busy'),null);
  assert.ok(state().exclude.includes(excludeTarget));
  click(exclusionButton);const excludeRetry=take();assert.equal(excludeRetry.url.search,excludeFailure.url.search);
  assert.equal(parameters(excludeRetry).exclude.filter(x=>x===excludeTarget).length,1);
  excludeRetry.respond(fixture(parameters(excludeRetry)));await flush();
  scenarios.push('Failed exclusion returns to the prior included position and retries the same desired filter without accidentally toggling or duplicating it');

  reset();
  const first = button('TA/345'), second = button('TA/235');
  click(first); const old = take(); pending(first);
  click(second); const latest = take(); pending(first); pending(second);
  assert.equal(old.options.signal.aborted, true);
  old.reject(Object.assign(new Error('Aborted'), {name: 'AbortError'})); await flush();
  pending(first); pending(second);
  assert.equal(element('error').hidden, true);
  latest.respond(fixture(parameters(latest))); await flush();
  assert.equal(Number(element('exclude-count').textContent), 1);
  assert.deepEqual(state().exclude, []);
  assert.equal(first.getAttribute('aria-busy'), null);
  assert.equal(second.getAttribute('aria-busy'), null);
  scenarios.push('Different restore switches remain clickable while a request is pending; aborting the superseded request does not clear either pending switch');

  reset();
  const failed = button('maprimerenov'); click(failed); const failure = take();
  failure.respond({error: 'Temporary network error'}, false); await flush();
  retryable(failed);
  assert.equal(run('data'), null);
  assert.equal(state().topic, '');
  assert.deepEqual(state().exclude, initial.exclude);
  assert.equal(element('error').textContent, 'Temporary network error');
  click(failed); pending(failed); const retry = take();
  assert.equal(retry.url.search, failure.url.search);
  retry.respond(fixture(parameters(retry))); await flush();
  assert.equal(Number(element('exclude-count').textContent), 2);
  assert.equal(element('error').hidden, true);
  assert.doesNotMatch(element('exclusions').innerHTML, /data-restore-topic/);
  scenarios.push('A current failure resets the pending switch for retry, preserves the mutated filters and can recover even while data is null');

  reset();
  const a = button('TA/345'), b = button('TA/235');
  click(a); const lateError = take(); click(b); const newer = take();
  lateError.respond({error: 'STALE ERROR'}, false); await flush();
  pending(a); pending(b); assert.equal(element('error').hidden, true); assert.notEqual(run('data'), null);
  newer.respond({error: 'CURRENT ERROR'}, false); await flush();
  retryable(a); retryable(b); assert.deepEqual(state().exclude, []);
  click(a); const afterError = take(); pending(a);
  afterError.respond(fixture(parameters(afterError))); await flush();
  assert.equal(Number(element('exclude-count').textContent), 1);
  assert.equal(element('error').hidden, true);
  scenarios.push('A stale non-abort error cannot reset pending UI or erase current data; failure of the current request resets all pending switches and permits retry');

  reset();
  const earlier = button('TA/345'), final = button('maprimerenov');
  click(earlier); const staleSuccess = take(); click(final); const finalRequest = take();
  finalRequest.respond(fixture(parameters(finalRequest))); await flush();
  const accepted = JSON.stringify(state());
  const acceptedMarkup = element('exclusions').innerHTML;
  staleSuccess.respond(fixture(parameters(staleSuccess))); await flush();
  assert.equal(JSON.stringify(state()), accepted);
  assert.equal(element('exclusions').innerHTML, acceptedMarkup);
  assert.equal(Number(element('exclude-count').textContent), 1);
  assert.equal(element('error').hidden, true);
  scenarios.push('A late success from a superseded request cannot restore an old selection or repaint the refreshed exclusion list');
  assert.equal(requests.length, 0);
  assert.equal(run('pendingRestores.size'), 0);
  console.log(JSON.stringify({passed: true, source_sha256: crypto.createHash('sha256').update(source).digest('hex'), browser_used: false, network_used: false, scenarios}, null, 2));
}
main().catch(error => {console.error(error); process.exitCode = 1;});
