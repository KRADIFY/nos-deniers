'use strict';
(() => {
  const demoBase = new URL('.', document.currentScript.src);
  const embedded = window.parent !== window;
  function returnToSite() {
    setDemoVisible(false);
    player.stop();
    if (embedded) window.parent.postMessage({type:'nos-deniers-demo:close'}, window.location.origin);
    else if (window.location.hostname === 'budget.lexmachine.net') window.location.assign('/?demo=off');
    else $('reopen-demo').focus({preventScroll:true});
  }
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fold = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const stages = ['PLF', 'LFI', 'EXEC'];
  const stageNames = {PLF: 'PLF', LFI: 'LFI', EXEC: 'Consommé'};
  const baseline = {scope:'', view:'credits', start:2026, end:2027, measure:'CP', unit:1000000};
  let snapshot, config, narration, state = {...baseline}, player, driver, activeJourney, frenchVoice;
  let lastTarget = null;
  let demoEnabled = true;
  function setDemoVisible(enabled) {
    demoEnabled = enabled;
    document.body.classList.toggle('demo-closed', !enabled);
    $('demo-player').hidden = !enabled;
    $('exit-demo').hidden = !enabled;
    $('welcome').hidden = !enabled;
    $('reopen-demo').setAttribute('aria-expanded', String(enabled));
  }
  const unitLabel = () => ({1:'€',1000000:'M€',1000000000:'Md€'}[state.unit]);
  const money = (cell, exact = false) => cell.value == null ? 'Données non disponibles' : new Intl.NumberFormat('fr-FR', {
    minimumFractionDigits: exact ? 2 : state.unit === 1 ? 0 : 1,
    maximumFractionDigits: exact ? 2 : state.unit === 1 ? 0 : 1
  }).format(cell.value / (exact ? 1 : state.unit));
  const dataset = () => snapshot.scopes[state.scope][state.measure];
  const years = () => dataset().years.filter(year => year >= state.start && year <= state.end);
  const cells = new Map();

  function safeUrl(value) {
    try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; }
    catch { return null; }
  }
  function sourceLink(id) { return snapshot.source + '/api/download/' + encodeURIComponent(id); }
  function sourceCards(cell, year, stage, scope) {
    const fixed = scope === 'AA/105' && state.measure === 'CP' && year === 2027 && stage === 'PLF';
    const sources = fixed ? snapshot.proof.sources : (cell.sources || []).map(id => ({id, title:'Document référencé ' + id}));
    const links = sources.map(source => `<div class="source-card"><h3>${esc(source.title || source.dataset_title || source.id)}</h3><p>${esc(source.format || source.kind || 'Document source')}</p><a href="${esc(sourceLink(source.id))}" target="_blank" rel="noopener noreferrer">Ouvrir la copie du document ↗</a>${safeUrl(source.url) ? `<a href="${esc(safeUrl(source.url))}" target="_blank" rel="noopener noreferrer">Publication officielle ↗</a>` : ''}</div>`).join('');
    const rows = fixed ? snapshot.proof.rows : [];
    const references = [...new Set(rows.map(row => [row.line ? 'Ligne / repère : ' + row.line : '', row.field ? 'Champ : ' + row.field : ''].filter(Boolean).join(' · ')))].slice(0, 8);
    const status = cell.value == null ? (cell.reason || 'Aucune valeur disponible pour cette cellule dans la capture.') : (cell.coverage_reason || cell.reason || 'Montant reproduit depuis le site, avec ses références.');
    return `<p>${esc(year)} · ${esc(stageNames[stage])} · ${esc(state.measure)} · ${esc(scope || 'Ensemble des missions')}</p><p class="demo-exact">${esc(money(cell, true))}${cell.value == null ? '' : ' €'}</p><p class="demo-source-status">${esc(status)}</p>${cell.approximate ? '<p>≈ La source contient une valeur arrondie.</p>' : ''}${cell.documented_discrepancies?.length ? `<p>${cell.documented_discrepancies.length} écart(s) documenté(s) dans la capture. Consultez les explications complètes sur Nos Deniers avant de citer ce montant.</p>` : ''}${links || '<p>Pas de document directement associé dans cet exemple.</p>'}${references.map(text => `<p class="demo-proof-note">${esc(text)}</p>`).join('')}<p class="demo-proof-note">Exemple figé au ${esc(new Date(snapshot.captured_at).toLocaleDateString('fr-FR'))}. Les liens ouvrent les documents en dehors de la démo.</p>`;
  }
  function amount(cell, year, stage, scope, total) {
    const key = `${scope}|${year}|${stage}`;
    cells.set(key, {cell, year, stage, scope});
    const indicator = cell.status === 'partial' ? '*' : '';
    const warning = cell.documented_discrepancies?.length;
    return `<td><button class="amount ${cell.value == null ? 'missing-proof' : ''}" type="button" data-cell="${esc(key)}" ${total ? `data-total-proof="${year}-${stage}"` : ''} aria-haspopup="dialog">${cell.approximate && cell.value != null ? '≈ ' : ''}${esc(money(cell))}${indicator}${cell.value == null ? '<span class="proof-hint">Pourquoi ? ⓘ</span>' : warning ? `<span class="proof-hint">${warning} écart(s) documenté(s) ⓘ</span>` : ''}</button></td>`;
  }
  function renderTable() {
    const data = dataset(), selected = years();
    cells.clear();
    const rows = data.rows.filter(row => fold(row.label + ' ' + row.code).includes(fold($('row-search').value)));
    const head = `<thead><tr><th rowspan="2">${state.scope ? state.scope === 'AA' ? 'Programme' : 'Action' : 'Mission'}</th>${selected.map(year => `<th colspan="3" class="year-group">${year}</th>`).join('')}</tr><tr>${selected.map(() => stages.map(stage => `<th>${stageNames[stage]}<br><small>${unitLabel()}</small></th>`).join('')).join('')}</tr></thead>`;
    const row = (record, total = false) => {
      const label = total ? 'Total du périmètre' : `<span class="row-label"><span class="code">${esc(record.code)}</span>${snapshot.scopes[record.id] ? `<button class="drill" data-scope="${esc(record.id)}">${esc(record.label)} ›</button>` : `<button class="demo-disabled-drill" data-other-scope="${esc(record.id)}">${esc(record.label)}</button>`}</span>`;
      return `<tr${total ? ' class="total"' : ''}><td>${label}</td>${record.series.filter(item => selected.includes(item.year)).map(item => stages.map(stage => amount(item[stage], item.year, stage, record.id, total)).join('')).join('')}</tr>`;
    };
    $('credits-table').innerHTML = head + '<tbody>' + row({id:state.scope, series:data.totals}, true) + rows.map(record => row(record)).join('') + '</tbody>';
    $('table-title').textContent = state.scope === '' ? 'Les missions, en détail' : state.scope === 'AA' ? 'Les programmes de cette mission' : 'Les actions de ce programme';
    $('scope-title').textContent = data.scope_label;
    $('level-up').disabled = !state.scope;
    $('breadcrumbs').innerHTML = '<button data-scope="">Toutes les missions</button>' + (state.scope.includes('/') ? ' › <button data-scope="AA">Action extérieure de l’État</button>' : '');
  }
  function renderChart() {
    const selected = dataset().totals.filter(row => years().includes(row.year));
    const values = selected.flatMap(row => stages.map(stage => row[stage].value)).filter(value => value != null);
    const max = Math.max(1, ...values), width = 840, plot = 720, height = 160;
    let svg = '<svg viewBox="0 0 840 210" role="img" aria-label="Crédits proposés, votés et consommés dans cet exemple">';
    for (let tick = 0; tick < 4; tick++) {
      const value = max * tick / 3, y = 170 - height * tick / 3;
      svg += `<line class="grid" x1="105" y1="${y}" x2="830" y2="${y}"/><text x="95" y="${y + 4}" text-anchor="end">${esc(money({value}))}</text>`;
    }
    selected.forEach((row, index) => {
      const center = 105 + plot / selected.length * (index + .5), bar = Math.min(44, plot / selected.length / 5);
      stages.forEach((stage, j) => {
        const cell = row[stage], x = center + (j - 1.5) * bar;
        if (cell.value == null) { svg += `<text x="${x + bar / 2}" y="163" text-anchor="middle">—</text>`; return; }
        const h = Math.max(0, cell.value / max * height);
        svg += `<rect x="${x}" y="${170 - h}" width="${bar - 4}" height="${h}" rx="2" fill="${['#b2c6d5','#173a55','#d84b50'][j]}"${cell.status === 'partial' ? ' opacity="0.5"' : ''}><title>${row.year} · ${stageNames[stage]} · ${esc(money(cell, true))} €</title></rect>`;
      });
      svg += `<text x="${center}" y="198" text-anchor="middle">${row.year}</text>`;
    });
    $('chart').innerHTML = svg + '</svg>';
    $('chart-caption').textContent = `${state.measure}, en ${unitLabel()} · euros courants · exemple daté`;
  }
  function renderDocuments() {
    const query = fold($('doc-search').value);
    const sources = snapshot.proof.sources.filter(source => fold(source.title || source.dataset_title || '').includes(query));
    $('documents').innerHTML = sources.length ? sources.map(source => `<article class="document"><div class="document-icon">${esc((source.format || source.kind || 'DOC').toUpperCase())}</div><div class="document-body"><h3>${esc(source.title || source.dataset_title || source.id)}</h3><p>Source du programme 105 · PLF 2027 · document de l’exemple</p></div><a class="open" href="${esc(sourceLink(source.id))}" target="_blank" rel="noopener noreferrer">Ouvrir ↗</a></article>`).join('') : '<p class="empty">Aucun résultat dans le petit échantillon de démonstration. La bibliothèque complète se consulte sur Nos Deniers.</p>';
  }
  function exportHtml() {
    return '<p>Sur Nos Deniers, choisissez le format puis exportez le périmètre affiché.</p><ul><li><strong>Excel</strong> : pour retravailler les chiffres dans un classeur.</li><li><strong>CSV</strong> : pour les réutiliser dans un autre outil.</li><li><strong>JSON</strong> : pour conserver la sélection et ses preuves.</li></ul><p>À conserver dans la note : année, programme, AE ou CP, PLF / LFI / consommé, unité, source et limites éventuelles.</p><p class="demo-source-status">La démo propose uniquement un petit CSV de son exemple daté.</p><button type="button" class="secondary" id="download-example">Télécharger l’exemple CSV</button>';
  }
  function render() {
    $('start').value = state.start; $('end').value = state.end; $('unit').value = state.unit;
    document.querySelectorAll('[data-measure]').forEach(button => { const active = button.dataset.measure === state.measure; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); });
    $('measure-help').textContent = state.measure === 'CP' ? 'Crédits de paiement : suivre les dépenses de l’année.' : 'Autorisations d’engagement : suivre les engagements de dépenses.';
    document.querySelectorAll('[data-view]').forEach(button => { const active = button.dataset.view === state.view; button.classList.toggle('active', active); if (active) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current'); });
    for (const view of ['credits','movements','documents','coverage']) $(view + '-view').hidden = state.view !== view;
    $('page-title').textContent = ({credits:'Évolution des crédits de l’État.',movements:'Suivre la vie des crédits.',documents:'Les documents derrière les chiffres.',coverage:'Des sources visibles. Des limites explicites.'})[state.view];
    $('subtitle').textContent = state.view === 'credits' ? 'Comparez ce qui a été proposé, voté et consommé.' : 'Une démonstration des principales fonctions de Nos Deniers.';
    renderTable(); renderChart(); renderDocuments();
    $('automatic-panel').hidden = !state.panel;
    if (state.panel) {
      $('automatic-title').textContent = state.panel === 'proof' ? 'PLF · 2027 · CP — Programme 105' : 'Exporter les données';
      const cell = snapshot.scopes['AA/105'].CP.totals.find(row => row.year === 2027).PLF;
      $('automatic-content').innerHTML = state.panel === 'proof' ? sourceCards(cell, 2027, 'PLF', 'AA/105') : exportHtml();
    }
  }
  function showDialog(title, html) {
    player.pause(); driver.destroy();
    $('dialog-title').textContent = title; $('dialog-content').innerHTML = html;
    $('info-dialog').showModal();
  }
  function fitTourPopover() {
    const popover = document.querySelector('.driver-popover');
    if (!popover || !lastTarget?.isConnected) return;
    const playerTop = document.querySelector('.demo-toolbar').getBoundingClientRect().top;
    const viewportHeight = window.visualViewport?.height || window.innerHeight;
    const viewportWidth = document.documentElement.clientWidth;
    const anchor = lastTarget.getBoundingClientRect();
    const availableHeight = Math.max(1, Math.min(playerTop, viewportHeight) - 28);
    const description = popover.querySelector('.driver-popover-description');
    const driverLeft = parseFloat(popover.style.left);
    const driverRight = parseFloat(popover.style.right);
    popover.style.removeProperty('--tour-description-max-height');
    const fitted = placeTourPopover.fitWidth({viewportWidth, maxHeight:availableHeight,
      measure:width => {
        popover.style.setProperty('--tour-caption-width', width + 'px');
        return popover.getBoundingClientRect().height;
      }});
    // Only very small windows need text scrolling. Keep it inside the description,
    // never on the caption frame (whose outside arrow otherwise creates scrollbars).
    const overflow = fitted.height > availableHeight;
    if (description) {
      if (overflow) {
        const textHeight = Math.max(1, description.getBoundingClientRect().height - (fitted.height - availableHeight));
        popover.style.setProperty('--tour-description-max-height', textHeight + 'px');
        description.tabIndex = 0;
      } else description.removeAttribute('tabindex');
    }
    const preferredLeft = Number.isFinite(driverLeft) ? driverLeft
      : Number.isFinite(driverRight) ? viewportWidth - driverRight - fitted.width : anchor.left;
    const left = Math.max(14, Math.min(preferredLeft, viewportWidth - fitted.width - 14));
    popover.style.setProperty('--tour-caption-left', left + 'px');
    const placement = placeTourPopover({anchorTop:anchor.top, anchorBottom:anchor.bottom,
      height:popover.getBoundingClientRect().height, playerTop, viewportHeight,
      side:state.panel ? 'left' : 'bottom'});
    popover.style.setProperty('--tour-caption-top', placement.top + 'px');
  }
  let popoverFrame = null;
  function schedulePopoverFit() {
    if (popoverFrame !== null) return;
    popoverFrame = requestAnimationFrame(() => { popoverFrame = null; fitTourPopover(); });
  }
  const captionResize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(schedulePopoverFit);
  function showStep(step, index, total) {
    if ($('info-dialog').open) $('info-dialog').close();
    $('welcome').hidden = true;
    state = {...baseline, ...step.state};
    $('row-search').value = '';
    $('doc-search').value = step.state.search === 'sample' ? (snapshot.proof.sources[0]?.title || '') : '';
    render();
    const target = document.querySelector(step.target);
    if (!target || target.closest('[hidden]')) throw new Error('Cible absente de la démonstration : ' + step.id);
    lastTarget = target;
    driver.highlight({element: target, popover: {title: step.title,
      description: `<p>${esc(step.text)}</p><p class="demo-tour-hint">${index + 1} / ${total} · ${esc(activeJourney.title)}<br>Lecture, pause, stop et déplacements : commandes dans le lecteur flottant.</p>`,
      side: step.state.panel ? 'left' : 'bottom', align:'start'}});
    requestAnimationFrame(() => {
      const top = 12;
      const bounds = target.getBoundingClientRect();
      if (bounds.top < top + 12) window.scrollBy({top: bounds.top - top - 20, behavior:'instant'});
      driver.refresh();
      fitTourPopover();
    });
  }
  function voiceList() {
    const candidates = window.speechSynthesis?.getVoices().filter(voice => /^fr[-_]/i.test(voice.lang)) || [];
    frenchVoice = candidates.find(voice => voice.localService && voice.lang.toLowerCase() === 'fr-fr') || candidates.find(voice => voice.localService) || candidates[0];
    const recordingCount = Object.keys(narration?.steps || {}).length;
    const allRecorded = config && config.steps.every(step => narration?.steps[step.id]?.text === step.text);
    $('voice-status').textContent = allRecorded ? 'Les trois parcours utilisent la voix enregistrée. Vous pouvez couper le son ; les explications restent visibles.' : recordingCount ? 'Les premiers parcours utilisent la voix enregistrée. Le troisième parcours est encore partiellement narré par la voix du navigateur ; sans voix disponible, son texte reste affiché.' : frenchVoice ? 'Narration en français : ' + frenchVoice.name + '. Le texte reste visible et la voix peut être coupée.' : 'La voix française dépend de votre navigateur. Si aucune voix n’est disponible, les explications restent affichées et le parcours avance avec un temps de lecture.';
  }
  let currentUtterance = null;
  let currentVoiceMode = null;
  const recordedVoice = new RecordedVoice({createAudio: src => new Audio(src)});
  const voiceAdapter = {
    speak(text, callbacks, step) {
      const recording = narration?.steps[step?.id];
      if (recording && recording.text === text) {
        currentVoiceMode = 'recorded';
        return recordedVoice.speak({...recording, src:new URL(recording.src.replace(/^\//, ''), demoBase).href}, callbacks);
      }
      if (!window.speechSynthesis || !window.SpeechSynthesisUtterance || !frenchVoice) return false;
      currentVoiceMode = 'browser';
      window.speechSynthesis.cancel(); window.speechSynthesis.resume();
      const utterance = new SpeechSynthesisUtterance(text);
      currentUtterance = utterance;
      utterance.lang = 'fr-FR'; utterance.voice = frenchVoice; utterance.rate = .95;
      utterance.onend = () => { if (currentUtterance === utterance) { currentUtterance = null; callbacks.end(); } };
      utterance.onerror = () => { if (currentUtterance === utterance) { currentUtterance = null; callbacks.error(); } };
      window.speechSynthesis.speak(utterance); return true;
    },
    cancel() { currentUtterance = null; currentVoiceMode = null; recordedVoice.cancel(); window.speechSynthesis?.cancel(); },
    pause() { if (currentVoiceMode === 'recorded') recordedVoice.pause(); else window.speechSynthesis?.pause(); },
    resume() { if (currentVoiceMode === 'recorded') recordedVoice.resume(); else window.speechSynthesis?.resume(); }
  };
  function updateControls(info) {
    const playing = info.status === 'playing', paused = info.status === 'paused';
    document.body.dataset.playback = info.status;
    $('tour-progress').max = info.total;
    $('tour-progress').value = info.status === 'stopped' ? 0 : info.index + 1;
    $('start-tour').disabled = playing; $('start-tour').textContent = paused ? '▶ Reprendre' : info.status === 'ended' ? '▶ Rejouer' : '▶ Lecture';
    $('pause').disabled = !playing; $('stop').disabled = info.status === 'stopped';
    $('previous').disabled = info.index === 0; $('next').disabled = info.index === info.total - 1;
    const voiceButton = $('voice');
    const voiceAction = info.muted ? 'Activer la voix' : 'Couper la voix';
    voiceButton.innerHTML = '<svg class="voice-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4Z"/>' + (info.muted ? '<path d="m16 9 6 6m0-6-6 6"/>' : '<path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>') + '</svg><span>' + (info.muted ? 'Voix coupée' : 'Voix activée') + '</span>';
    voiceButton.setAttribute('aria-pressed', String(!info.muted));
    voiceButton.setAttribute('aria-label', 'Voix');
    voiceButton.title = voiceAction;
    $('player-status').textContent = info.status === 'stopped' ? 'Prêt · ' + activeJourney.title : info.status === 'ended' ? 'Parcours terminé · vous pouvez rejouer ou ouvrir le site.' : `${paused ? 'En pause' : 'Lecture'} · ${info.index + 1} / ${info.total} · ${activeJourney.title}`;
  }
  function chooseJourney(id, index = 0) {
    const journey = config.journeys.find(item => item.id === id);
    if (!journey) return;
    setDemoVisible(true);
    activeJourney = journey;
    player.setSteps(journey.steps.map(id => config.steps.find(step => step.id === id)));
    player.seek(index, true);
  }
  function stopForInteraction() { player.pause(); driver.destroy(); state.panel = null; }
  function csvDownload() {
    const csvCell = value => '"' + String(value ?? '').replace(/^[=+@-]/, "'$&").replace(/"/g, '""') + '"';
    const cents = value => value == null ? '' : (value < 0 ? '-' : '') + Math.floor(Math.abs(value) / 100) + ',' + String(Math.abs(value) % 100).padStart(2,'0');
    const rows = [['EXEMPLE DE DEMONSTRATION — capture', snapshot.captured_at], ['Périmètre','Année','Type de crédits','Étape','Montant EUR','Statut','Sources']];
    for (const row of dataset().totals.filter(row => years().includes(row.year))) for (const stage of stages) {
      const cell = row[stage]; rows.push([state.scope || 'Ensemble des missions',row.year,state.measure,stage,cents(cell.nominal_cents),cell.status,(cell.sources || []).join(' | ')]);
    }
    const csv = rows.map(row => row.map(csvCell).join(';')).join('\r\n');
    const url = URL.createObjectURL(new Blob(['\ufeff',csv], {type:'text/csv;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = 'Nos-Deniers-DEMO-exemple-date.csv'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function initialize() {
    const responses = await Promise.all(['snapshot.json','parcours.json','narration.json'].map(url => fetch(new URL(url, demoBase))));
    if (responses.some(response => !response.ok)) throw new Error('Fichiers de démonstration indisponibles.');
    [snapshot, config, narration] = await Promise.all(responses.map(response => response.json()));
    const ids = new Set(config.steps.map(step => step.id));
    if (ids.size !== config.steps.length || config.journeys.some(journey => journey.steps.some(id => !ids.has(id)))) throw new Error('Parcours incohérent.');
    for (const field of ['start','end']) for (const year of snapshot.scopes[''].CP.years) $(field).add(new Option(String(year),String(year)));
    $('snapshot-date').textContent = 'Exemple capturé le ' + new Date(snapshot.captured_at).toLocaleDateString('fr-FR') + '.';
    driver = window.driver.js.driver({animate: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      smoothScroll:false, allowClose:false, allowKeyboardControl:false, disableActiveInteraction:true,
      overlayColor:'#08183f', overlayOpacity:.28, popoverClass:'demo-popover', stagePadding:7, stageRadius:8,
      onPopoverRender:popover => { captionResize?.disconnect(); captionResize?.observe(popover.wrapper); captionResize?.observe($('demo-player')); schedulePopoverFit(); },
      showButtons:[], overlayClickBehavior:'none'});
    activeJourney = config.journeys[0];
    player = new DemoPlayer({steps:activeJourney.steps.map(id => config.steps.find(step => step.id === id)), voice:voiceAdapter,
      onStep:showStep, onState:updateControls,
      onVoiceError:() => { $('player-status').textContent += ' · voix indisponible, lecture du texte'; },
      onExit:() => { driver.destroy(); state = {...baseline}; $('row-search').value = ''; $('doc-search').value = ''; $('welcome').hidden = !demoEnabled; if ($('info-dialog').open) $('info-dialog').close(); render(); }});
    const journeyIcons = ['<path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6Z"/>', '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6m-14-11 2 2 4-4"/>', '<path d="M4 7h13l-3-3m3 3-3 3M20 17H7l3 3m-3-3 3-3"/>'];
    $('journeys').innerHTML = config.journeys.map((journey, index) => `<button class="demo-journey" data-journey="${esc(journey.id)}"><span class="journey-top"><span class="journey-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${journeyIcons[index]}</svg></span><span class="journey-number">0${index + 1}</span></span><strong>${esc(journey.title)}</strong><span class="journey-summary">${esc(journey.summary)}</span><span class="journey-bottom"><small>${journey.steps.length} étapes</small><b aria-hidden="true">▶</b></span></button>`).join('');
    $('start-tour').addEventListener('click', () => {
      if (player.status === 'paused' && (!driver.isActive() || $('info-dialog').open)) player.seek(player.index, true);
      else player.play();
    });
    $('pause').addEventListener('click', () => player.pause());
    $('stop').addEventListener('click', () => player.stop());
    $('next').addEventListener('click', () => player.next());
    $('previous').addEventListener('click', () => player.previous());
    $('voice').addEventListener('click', () => player.setMuted(!player.muted));
    $('exit-demo').addEventListener('click', returnToSite);
    if (embedded) document.querySelector('.demo-tools a').addEventListener('click', event => { event.preventDefault(); returnToSite(); });
    $('reopen-demo').addEventListener('click', () => {
      player.stop();
      setDemoVisible(true);
      $('journeys').querySelector('button')?.focus({preventScroll:true});
    });
    $('restart-bottom').addEventListener('click', () => chooseJourney(activeJourney.id));
    $('chapters').disabled = false;
    $('chapters').addEventListener('click', () => showDialog('Choisir un parcours ou une étape', '<div class="demo-chapters">' + config.journeys.map(journey => `<button data-journey="${esc(journey.id)}"><strong>${esc(journey.title)}</strong> · ${journey.steps.length} étapes</button>`).join('') + '<h3>Parcours actuel</h3>' + activeJourney.steps.map((id,index) => `<button data-step="${index}">${index + 1}. ${esc(config.steps.find(step => step.id === id).title)}</button>`).join('') + '</div>'));
    $('close-dialog').addEventListener('click', () => $('info-dialog').close());
    $('reset').addEventListener('click', () => { player.stop(); });
    $('level-up').addEventListener('click', () => { stopForInteraction(); state.scope = state.scope === 'AA/105' ? 'AA' : ''; render(); });
    for (const field of ['start','end','unit']) $(field).addEventListener('change', () => {
      stopForInteraction(); state[field] = Number($(field).value);
      if (state.start > state.end) state[field === 'start' ? 'end' : 'start'] = state[field];
      render();
    });
    $('row-search').addEventListener('input', () => { stopForInteraction(); renderTable(); });
    $('doc-search').addEventListener('input', renderDocuments);
    $('doc-submit').addEventListener('click', renderDocuments);
    $('export').addEventListener('click', () => showDialog('Exporter les données', exportHtml()));
    document.addEventListener('click', event => {
      const button = event.target.closest('button'); if (!button) return;
      if (button.dataset.journey) { if ($('info-dialog').open) $('info-dialog').close(); chooseJourney(button.dataset.journey); }
      else if (button.hasAttribute('data-step')) { $('info-dialog').close(); player.seek(Number(button.dataset.step), true); }
      else if (button.dataset.measure) { stopForInteraction(); state.measure = button.dataset.measure; render(); }
      else if (button.hasAttribute('data-scope')) { stopForInteraction(); state.scope = button.dataset.scope; render(); }
      else if (button.dataset.otherScope) showDialog('Périmètre de démonstration', '<p>Le parcours détaillé utilise la mission Action extérieure de l’État et le programme 105. Les autres périmètres s’explorent sur <a href="https://budget.lexmachine.net/" target="_blank" rel="noopener noreferrer">Nos Deniers ↗</a>.</p>');
      else if (button.dataset.view) { stopForInteraction(); state.view = button.dataset.view; render(); }
      else if (button.dataset.cell) { const item = cells.get(button.dataset.cell); showDialog('Traçabilité du montant', sourceCards(item.cell,item.year,item.stage,item.scope)); }
      else if (button.id === 'download-example') csvDownload();
    });
    document.addEventListener('keydown', event => {
      if (!demoEnabled) return;
      if (event.key === 'Escape' && !$('info-dialog').open) { player.stop(); return; }
      if ($('info-dialog').open || /INPUT|SELECT|TEXTAREA/.test(event.target.tagName)) return;
      if (event.key === ' ' && event.target === document.body) { event.preventDefault(); player.status === 'playing' ? player.pause() : player.play(); }
      if (event.key === 'ArrowRight' && player.status !== 'stopped') { event.preventDefault(); player.next(); }
      if (event.key === 'ArrowLeft' && player.status !== 'stopped') { event.preventDefault(); player.previous(); }
    });
    document.addEventListener('visibilitychange', () => { if (document.hidden) player.pause(); });
    window.addEventListener('pagehide', () => player.stop());
    window.addEventListener('resize', () => { if (driver.isActive()) { driver.refresh(); fitTourPopover(); } });
    window.addEventListener('scroll', schedulePopoverFit, {capture:true, passive:true});
    window.visualViewport?.addEventListener('resize', schedulePopoverFit);
    if (window.speechSynthesis) window.speechSynthesis.addEventListener('voiceschanged', voiceList);
    voiceList(); render(); player.emit();
    document.documentElement.dataset.demoReady = 'true';
    if (embedded) window.parent.postMessage({type:'nos-deniers-demo:ready'}, window.location.origin);
  }
  initialize().catch(error => { $('demo-error').hidden = false; $('demo-error').textContent = 'La démo n’a pas pu être chargée : ' + error.message; if (embedded) window.parent.postMessage({type:'nos-deniers-demo:error'}, window.location.origin); });
})();
