'use strict';
// Exercise the real provenance renderer and delegated click handler without
// network or a browser. Monetary fixtures are server results, never recomputed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const sourcePath = path.resolve(__dirname, '../public/assets/explorer.js');
const source = fs.readFileSync(sourcePath, 'utf8');
assert.equal((source.match(/^init\(\);\s*$/gm) || []).length, 1);
const elements = new Map(), listeners = new Map(), requests = [];
function element(id) {
  if (!elements.has(id)) {
    const attrs = new Map();
    elements.set(id, {
      innerHTML: '', textContent: '', value: id === 'unit' ? '1000000000' : '',
      hidden: false, disabled: false, checked: false, open: false, children: [],
      addEventListener() {}, focus() {}, showModal() { this.open = true; }, close() { this.open = false; },
      appendChild(child) { this.children.push(child); },
      querySelector(selector) { return selector === 'details' ? this.details || null : null; },
      setAttribute(key, value) { attrs.set(key, String(value)); },
      removeAttribute(key) { attrs.delete(key); },
      getAttribute(key) { return attrs.get(key) ?? null; },
      classList: {toggle() {}}
    });
  }
  return elements.get(id);
}
const context = vm.createContext({
  URL, URLSearchParams, AbortController, Intl, Date, console, setTimeout, clearTimeout,
  fetch: (url, options) => new Promise(resolve => requests.push({
    url: new URL(url, 'http://test.invalid'), options,
    respond(body) { resolve({ok: true, json: async () => body}); }
  })),
  document: {getElementById: element, querySelectorAll: () => [],
    addEventListener(type, callback) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(callback);
    }},
  window: {addEventListener() {}}, history: {replaceState() {}}, location: {search: ''},
  localStorage: {getItem: () => '[]', setItem() {}}
});
vm.runInContext(source.replace(/^init\(\);\s*$/m, ''), context, {filename: sourcePath});
const run = code => vm.runInContext(code, context);
const setState = value => run('state={...defaults,...' + JSON.stringify(value) + '}');
const setData = value => run('data=' + JSON.stringify(value));
const display = value => context.euros(value, true) + ' €';
const data = {stages: {EXEC: 'Consommé', LFI: 'Voté en LFI', PLF: 'Proposé en PLF'}, exclusions: []};
const sources = [
  {id: 'd5dc9d71f6165da67f38', title: 'Exécution 2024', url: 'https://budget.gouv.fr/execution', sha256: 'a'.repeat(64)},
  {id: '113330a8d3bb90c96604', title: 'RAP Écologie 2024', url: 'https://budget.gouv.fr/rap', sha256: 'b'.repeat(64)}
];
const fixture = {
  year: 2024, stage: 'Consommé', topic_mode: 'without', count: 2, truncated: false,
  note: 'Retrait des crédits propres au dispositif.', evidence: [],
  calculation: {base_nominal: 3797447109.97, subtracted_nominal: 692017721,
    result_nominal: 3105429388.97, displayed_value: 3105429388.97,
    constant: false, base_year: 2025, status: 'ok', scope: 'TA/174', measure: 'CP'},
  sources,
  citations: [{source: sources[1].id, page: 446}],
  rows: [
    {program: '174', program_label: 'Énergie, climat et après-mines', line: 61,
      source: sources[0].id, field: 'Depenses_constatees', cents: 379744710997, operation: 'base'},
    {program: '174', program_label: 'Énergie, climat et après-mines', action: '02', action_label: 'Accompagnement de la transition énergétique',
      page: 446, source: sources[1].id, field: 'MaPrimeRénov’', cents: -69201772100, operation: 'subtract'}
  ]
};
async function show(payload, dataset = {year: '2024', stage: 'EXEC', cellScope: 'TA/174'}) {
  const promise = context.showSource({dataset});
  assert.equal(element('source-dialog').open, true);
  const request = requests.shift();
  assert.equal(request.url.pathname, '/api/provenance');
  request.respond(payload);
  await promise;
  return {html: element('source-content').innerHTML, request};
}
async function main() {
  const scenarios = [];
  setState({start: 2017, end: 2025, scope: 'TA', topic: 'maprimerenov', topic_mode: 'without', exclude: ['TA/345', 'TA/235']});
  setData(data);
  let {html, request} = await show(fixture);
  for (const [key, value] of Object.entries({year: '2024', stage: 'EXEC', cell_scope: 'TA/174', scope: 'TA', topic: 'maprimerenov', topic_mode: 'without', exclude: '["TA/345","TA/235"]'})) assert.equal(request.url.searchParams.get(key), value, key);
  assert.match(html, /Total du périmètre après les autres exclusions/);
  for (const number of [3797447109.97, 692017721, 3105429388.97]) assert.ok(html.includes(display(number)), String(number));
  assert.ok(html.indexOf('Calcul du montant affiché') < html.indexOf('<article class="source-card">'));
  assert.ok(html.indexOf('Résultat calculé') < html.indexOf('RAP Écologie 2024'));
  assert.match(html, /À retirer : MaPrimeRénov’/);
  assert.ok(html.includes(context.euros(-692017721, true)));
  assert.ok(html.includes('/api/download/113330a8d3bb90c96604#page=446'));
  scenarios.push('P174 2024: exact server total minus MPR and result precede signed source rows; all filters are preserved');

  setState({topic: 'maprimerenov', topic_mode: 'without', constant: true, base: 2017});
  const converted = structuredClone(fixture);
  converted.calculation = {...converted.calculation, constant: true, base_year: 2017, displayed_value: 2712345678.91};
  converted.truncated = true;
  converted.count = 301;
  converted.rows = [fixture.rows[1]];
  ({html, request} = await show(converted));
  assert.ok(html.includes(display(2712345678.91)));
  assert.ok(html.includes(display(3105429388.97)));
  assert.match(html, /Montant affiché en euros 2017/);
  assert.match(html, /appliquée après le retrait/);
  assert.match(html, /300 premières lignes/);
  assert.equal(request.url.searchParams.get('constant'), '1');
  assert.equal(request.url.searchParams.get('base'), '2017');
  scenarios.push('IPC result uses the server value in exact euros even with Md€ selected and truncated monetary rows');

  const transferSource = {id: 'd2c406b7e2bc73904e50', title: 'RAP Cohésion 2025', sha256: 'c'.repeat(64)};
  const outside = {kind: 'outside_scope', label: 'Transfert vers le programme 135', explanation: 'En 2025, le financement relève du P135 ; le total national reste à documenter.', references: [{source: transferSource.id, page: 142, label: 'Rattachement 2025'}]};
  const unchanged = {...structuredClone(fixture), year: 2025, rows: [], count: 0,
    sources: [transferSource], evidence: [outside], citations: [{source: transferSource.id, page: 142}, {source: transferSource.id, page: 143}],
    calculation: {base_nominal: 16039686749.26, subtracted_nominal: 0, result_nominal: 16039686749.26, displayed_value: 16039686749.26, constant: false, base_year: 2025, status: 'ok', scope: 'TA', measure: 'CP'}};
  setState({topic: 'maprimerenov', topic_mode: 'without'});
  ({html} = await show(unchanged, {year: '2025', stage: 'EXEC', cellScope: 'TA'}));
  assert.match(html, /Périmètre documenté/);
  assert.match(html, /non applicable dans ce périmètre/);
  assert.match(html, /Résultat conservé/);
  assert.ok(html.includes(display(16039686749.26)));
  assert.doesNotMatch(html, /<strong>0,00 €/);
  assert.match(html, /Justification du périmètre/);
  assert.match(html, /total national reste à documenter/);
  assert.ok(html.includes('/api/download/d2c406b7e2bc73904e50#page=142'));
  assert.ok(html.includes('/api/download/d2c406b7e2bc73904e50#page=143'));
  scenarios.push('2025 scope evidence survives zero monetary rows, preserves the mission total and never presents an inferred published zero; citation pages remain linked');

  const nonApplicable = {...unchanged, topic_mode: 'only', note: 'Hors du périmètre documenté.', calculation: {...unchanged.calculation, status: 'not_applicable', base_nominal: null, subtracted_nominal: null, result_nominal: null, displayed_value: null}};
  setState({topic: 'maprimerenov', topic_mode: 'only'});
  ({html} = await show(nonApplicable));
  assert.match(html, /Ce statut ne correspond pas à un montant nul publié/);
  assert.match(html, /Justification du périmètre/);
  assert.ok(html.includes('#page=142'));
  assert.doesNotMatch(html, /<strong>0,00 €/);
  const unknown = {...nonApplicable, note: 'Montant national 2025 non isolé.', sources: [], evidence: [], citations: [], calculation: {...nonApplicable.calculation, status: 'missing'}};
  ({html} = await show(unknown));
  assert.match(html, /Montant national 2025 non isolé/);
  assert.match(html, /Données non disponibles/);
  assert.doesNotMatch(html, /0,00 €/);
  scenarios.push('Only-mode non-applicability retains scope proofs; missing national 2025 remains unknown without a fictitious zero');

  const outsideOnly = {...nonApplicable, calculation: {...nonApplicable.calculation, status: 'ok', result_nominal: 0, displayed_value: 0, constant: true}};
  ({html} = await show(outsideOnly));
  assert.match(html, /Aucun crédit MaPrimeRénov’ à isoler dans ce périmètre documenté/);
  assert.match(html, /règle de périmètre/);
  assert.match(html, /ce n’est pas un montant national nul publié/);
  assert.doesNotMatch(html, /0,00 €|Montant propre à MaPrimeRénov’ en euros courants/);
  assert.ok(html.includes('#page=142'));
  scenarios.push('Only-mode 2025 calculated zero with outside-scope evidence is explained as a scope rule, including with IPC enabled');

  const missing = {value: null, status: 'not_applicable', reason: 'Périmètre <contrôlé> & documenté'};
  const markup = context.amountCell(missing, 2025, 'EXEC', 'TA/174');
  assert.match(markup, /<button[^>]*class="amount(?: [^"]*)?"/);
  assert.match(markup, /data-year="2025"/);
  assert.match(markup, /aria-haspopup="dialog"/);
  assert.match(markup, /Non applicable/);
  assert.match(markup, /&lt;contrôlé&gt; &amp; documenté/);
  const button = {dataset: {year: '2025', stage: 'EXEC', cellScope: 'TA/174'}};
  for (const callback of listeners.get('click') || []) callback({target: {closest: selector => selector === 'button' ? button : null}});
  const clickRequest = requests.shift();
  assert.equal(clickRequest.url.pathname, '/api/provenance');
  assert.equal(clickRequest.url.searchParams.get('cell_scope'), 'TA/174');
  clickRequest.respond(nonApplicable);
  await new Promise(resolve => setImmediate(resolve));
  assert.match(element('source-content').innerHTML, /Justification du périmètre/);
  setState({topic: ''});
  assert.match(context.amountCell(missing, 2025, 'EXEC', 'TA/174'), /<button[^>]*class="amount missing-proof"/);
  scenarios.push('Missing MPR and general cells remain accessible buttons and the real delegated click opens the correct provenance endpoint');

  const escaped = context.sourceEvidence({evidence: [{...outside, label: '<script>alert(1)</script>', explanation: '<img src=x>', references: [{source: transferSource.id, page: 142, label: '<b>preuve</b>'}]}]});
  assert.doesNotMatch(escaped, /<script>|<img|<b>/);
  assert.match(escaped, /&lt;script&gt;/);
  scenarios.push('Evidence labels and explanations are escaped as text');

  const topic = {mode: 'without', perimeter: 'Crédits propres au dispositif', availability_note: '2025 : <national inconnu> ; Écologie documentée.', timeline: [], limitations: [], updated_at: '2026-09-10'};
  setData({...data, topic});
  setState({topic: 'maprimerenov', topic_mode: 'without'});
  context.renderTopic();
  context.renderExclusions();
  assert.equal(element('topic-panel').hidden, true);
  assert.match(element('exclusions').innerHTML, /Détails de l’exclusion/);
  assert.match(element('topic-panel').innerHTML, /&lt;national inconnu&gt;/);
  assert.match(element('topic-panel').innerHTML, /Écologie hors MaPrimeRénov’ · 2024/);
  assert.match(element('topic-panel').innerHTML, /Consommé · 2021–2024/);
  element('topic-panel').details = {cloneNode(deep) { assert.equal(deep, true); return {open: false}; }};
  context.showTopicExclusion();
  assert.match(element('source-content').innerHTML, /le total est conservé/);
  assert.match(element('source-content').innerHTML, /&lt;national inconnu&gt;/);
  assert.equal(element('source-content').children.at(-1).open, true);
  setData({...data, topic: {...topic, mode: 'only'}});
  context.renderTopic();
  assert.equal(element('topic-panel').hidden, false);
  scenarios.push('The hidden without-mode topic card, sidebar details, original presets and server availability note are preserved');

  const legacy = {rows: fixture.rows.slice(0, 1), sources: sources.slice(0, 1), count: 1, truncated: false};
  ({html} = await show(legacy));
  assert.match(html, /Depenses_constatees/);
  assert.doesNotMatch(html, /Calcul du montant affiché|Justification du périmètre/);
  ({html} = await show({rows: [], sources: [], count: 0, note: 'Aucune ligne après exclusions.'}));
  assert.equal(html, '<p>Aucune ligne après exclusions.</p>');
  assert.equal(requests.length, 0);
  scenarios.push('Legacy non-topic provenance and its empty-result message remain compatible');
  console.log(JSON.stringify({passed: true, source: 'public/assets/explorer.js', source_sha256: crypto.createHash('sha256').update(source).digest('hex'), runtime: process.version, network_used: false, browser_used: false, scenarios}, null, 2));
}
main().catch(error => {console.error(error); process.exitCode = 1;});
