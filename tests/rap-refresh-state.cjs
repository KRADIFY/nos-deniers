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
    const attrs = new Map();
    elements.set(id, {
      innerHTML: '', textContent: '', value: id === 'unit' ? '1' : '',
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

async function main() {
  const scenarios = [];
  run("state={...defaults,scope:'TA/174',exclude:[]}");
  element('rap-movements-table').innerHTML = 'Previously rendered RAP';
  element('rap-movements-export').href = '/api/rap-movements?measure=CP&download=1';
  const oldRap = context.loadRapMovements();
  const delayed = nextRequest('/api/rap-movements');
  inactive();
  run("state={...state,start:2025,end:2025,measure:'AE',constant:true,base:2017,exclude:['TA/113']}");
  const explorer = context.load();
  const failedExplorer = nextRequest('/api/explorer');
  assert.equal(failedExplorer.url.searchParams.get('measure'), 'AE');
  inactive();
  failedExplorer.respond({error: 'Explorer unavailable'}, false);
  await explorer;
  assert.equal(element('error').textContent, 'Explorer unavailable');
  delayed.respond(rap('STALE RESPONSE'));
  await oldRap;
  inactive();
  assert.notEqual(element('rap-movements-coverage').textContent, 'STALE RESPONSE');
  scenarios.push('Delayed old RAP cannot refill the table or export after a new explorer selection fails');

  const currentRap = context.loadRapMovements();
  const current = nextRequest('/api/rap-movements');
  inactive();
  current.respond(rap('CURRENT RESPONSE', 'AE'));
  await currentRap;
  assert.match(element('rap-movements-table').innerHTML, /CURRENT RESPONSE/);
  assert.match(element('rap-movements-table').innerHTML, /p\. 403/);
  assert.equal(element('rap-movements-export').getAttribute('aria-disabled'), null);
  const exportQuery = new URL(element('rap-movements-export').href, 'http://test.invalid').searchParams;
  for (const [key, value] of current.url.searchParams) {
    if(['view','offset','limit'].includes(key))assert.equal(exportQuery.has(key),false,'Export must remain complete');
    else assert.equal(exportQuery.get(key), value, key);
  }
  assert.equal(exportQuery.get('download'), '1');
  scenarios.push('Only a current successful RAP response restores the export with the exact captured filters');

  const unavailable = context.loadRapMovements();
  nextRequest('/api/rap-movements').respond({error: 'RAP unavailable'}, false);
  await unavailable;
  inactive();
  assert.equal(element('rap-movements-coverage').textContent, 'RAP unavailable');
  scenarios.push('A failing current RAP request leaves its export disabled');

  run("state={...defaults,start:2024,end:2024,budget:'BG',scope:'TA',measure:'CP',constant:true,base:2020,exclude:['TA/345','TA/235'],topic:'maprimerenov',topic_mode:'without'}");
  run("data={exclusions:[{id:'TA/345',label:'Service public de l’énergie'},{id:'TA/235',label:'Performance énergétique'}],totals:[{year:2024,EXEC:{nominal_cents:123456789,value:1234567.89}}]}");
  const originalData = run('JSON.stringify(data)');
  const originalState = state();
  context.renderExclusions();
  assert.equal(Number(element('exclude-count').textContent), 3);
  assert.equal((element('exclusions').innerHTML.match(/class="exclude-chip"/g) || []).length, 3);
  assert.match(element('exclusions').innerHTML, /data-toggle-topic="maprimerenov"/);
  assert.match(element('exclusions').innerHTML, /role="switch" aria-checked="false"/);
  assert.equal(element('exclusion-warning').hidden, false);
  assert.equal(run('JSON.stringify(data)'), originalData);
  // The full dashboard rendering is unrelated to this state transition. Keep
  // its real exclusions renderer, with the real load/fetch success path.
  run('render=function(){renderExclusions()}');
  click({toggleTopic: 'maprimerenov'});
  const restored = nextRequest('/api/explorer');
  const expectedState = {...originalState, topic: '', topic_mode: 'only'};
  assert.deepEqual(state(), expectedState);
  for (const [key, value] of Object.entries(expectedState)) {
    const encoded = key === 'exclude' ? JSON.stringify(value) : key === 'constant' ? (value ? '1' : '0') : String(value);
    assert.equal(restored.url.searchParams.get(key), encoded, key);
  }
  assert.equal(run('JSON.stringify(data)'), originalData);
  restored.respond({...JSON.parse(originalData), parameters: expectedState});
  await flush();
  assert.equal(element('error').hidden, true);
  assert.equal(Number(element('exclude-count').textContent), 2);
  assert.match(element('exclusions').innerHTML, /aria-checked="true"[^>]*data-toggle-topic="maprimerenov"/);
  assert.equal((element('exclusions').innerHTML.match(/class="exclude-chip"/g) || []).length, 3);
  assert.deepEqual(JSON.parse(run('JSON.stringify(data.totals)')), JSON.parse(originalData).totals);
  assert.deepEqual(state().exclude, ['TA/345', 'TA/235']);
  assert.equal(requests.length, 0);
  scenarios.push('The third MPR exclusion is counted; restoring it preserves both programme exclusions and all other API filters and figures');

  const result = {passed: true, checked_at: new Date().toISOString(),
    source: 'public/assets/explorer.js',
    source_sha256: crypto.createHash('sha256').update(source).digest('hex'),
    runtime: process.version, browser_used: false, network_used: false,
    scenarios};
  const reportIndex = process.argv.indexOf('--report');
  if (reportIndex !== -1) {
    assert.ok(process.argv[reportIndex + 1], 'Missing --report path');
    fs.writeFileSync(path.resolve(process.argv[reportIndex + 1]), JSON.stringify(result, null, 2) + '\n');
  }
  console.log(JSON.stringify(result, null, 2));
}
main().catch(error => {console.error(error);process.exitCode = 1;});
