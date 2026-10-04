'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fold=value=>String(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const infoIcon='<svg class="info-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 7v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="4.7" r=".85" fill="currentColor"/></svg>';
const defaults={start:2023,end:2025,measure:'CP',budget:'BG',scope:'',exclude:[],constant:false,base:2025,topic:'',topic_mode:'only',denominator:'LFI'};
let state={...defaults},data=null,bootstrap=null,searchStats=null,view='credits',mode='compare',stage='EXEC',abort=null,documents=[],docLimit=40,docMode='title',documentSearchStatus=null,docSequence=0;
const pendingRestores=new Map();
const lastVisitedChild=new Map();
const labels={credits:['Évolution des crédits de l’État.','Comparez ce qui a été proposé, voté et consommé.'],movements:['Suivre la vie des crédits.','Reports, mouvements, fonds de concours et régularisations.'],documents:['Les documents derrière les chiffres.','Retrouvez et ouvrez les rapports et tableaux déjà collectés.'],coverage:['Des sources visibles. Des limites explicites.','Vérifiez les années et les niveaux de détail disponibles.']};
function params(extra={}){return new URLSearchParams({...state,constant:state.constant?'1':'0',exclude:JSON.stringify(state.exclude),...extra});}
function euros(value,exact=false){if(value==null)return '—';const unit=exact?1:Number($('unit').value);const formatter=new Intl.NumberFormat('fr-FR',{minimumFractionDigits:exact?2:unit===1?0:1,maximumFractionDigits:exact?2:unit===1?0:1,useGrouping:true});return formatter.formatToParts(value/unit).map(part=>part.type==='group'?'\u2002':part.value).join('');}
function exclusionCount(){return state.exclude.length+(state.topic==='maprimerenov'&&state.topic_mode==='without'?1:0);}
function renderExclusions(){
 const mpr=state.topic==='maprimerenov'&&state.topic_mode==='without',count=exclusionCount();
 $('exclude-count').textContent=count;
 const ecology=currentPilot()==='ecologie',fixed=['TA/345','TA/235'];
 const programmes=ecology?fixed.map(id=>({id,label:({'TA/345':'Service public de l’énergie','TA/235':'Sûreté nucléaire et radioprotection'})[id]})):[];
 const chip=(e,permanent=false)=>`<div class="exclude-chip"><span>${esc(e.label)} <small>(${esc(e.id)})</small></span>${categorySwitch(e,permanent?state.exclude.includes(e.id):true,!permanent)}</div>`;
 $('exclusions').innerHTML=programmes.map(e=>chip(e,true)).join('')+data.exclusions.filter(e=>!ecology||!fixed.includes(e.id)).map(e=>chip(e)).join('')+((mpr||ecology)?`<div class="exclude-chip"><span>MaPrimeRénov’ <small>Grand dossier transversal</small>${mpr?'<button type="button" class="text-button topic-exclusion-details" data-topic-exclusion-details="maprimerenov" aria-haspopup="dialog">Détails de l’exclusion</button>':''}</span><button type="button" class="category-switch" role="switch" aria-checked="${!mpr}" aria-label="Inclure MaPrimeRénov’ dans le calcul" title="${mpr?'Exclu du calcul. Activer pour réintégrer.':'Inclus dans le calcul. Désactiver pour exclure.'}" ${ecology?'data-toggle-topic':'data-restore-topic'}="maprimerenov"><span class="switch-track" aria-hidden="true"></span></button></div>`:'');
 $('exclusion-warning').hidden=!count;$('exclusion-warning').textContent=`${count} poste(s) exclu(s) du calcul. Les étapes sans ventilation suffisante sont marquées indisponibles.`;
}
function unitLabel(){return Number($('unit').value)===1?'€':Number($('unit').value)===1e9?'Md€':'M€';}
function renderIndexHeadline(info){
 const headline=$('index-punchline');
 if(!headline||info?.available!==true||!Number.isSafeInteger(info.passages)||info.passages<0||!Number.isSafeInteger(info.documents)||info.documents<0)return;
 const formatter=new Intl.NumberFormat('fr-FR');
 headline.textContent=`${formatter.format(info.passages)} passages indexés et sourçables dans ${formatter.format(info.documents)} documents,`;
}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,3500);}
let activeRequests=0,activeViews=0,exportPending=false,requestStartedAt=null,requestTimer=null;
function updateRequestProgress(){
 const indicator=$('request-progress'),dialog=$('source-dialog'),modalIndicator=$('dialog-request-progress');if(!indicator)return;
 const busy=activeRequests+activeViews>0||exportPending;indicator.hidden=!busy||dialog.open;modalIndicator.hidden=!busy||!dialog.open;
 indicator.querySelector('.request-wait-hint').textContent=exportPending?'Préparation de l’export en cours':'Calcul et affichage des résultats en cours';
 modalIndicator.querySelector('.request-wait-hint').textContent=exportPending?'Préparation de l’export en cours':'Recherche des justificatifs en cours';
 if(busy&&requestStartedAt===null){
  requestStartedAt=performance.now();
  const tick=()=>{const seconds=Math.floor((performance.now()-requestStartedAt)/1000);const elapsed=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');$('request-elapsed').textContent=elapsed;$('dialog-request-elapsed').textContent=elapsed;};
  tick();requestTimer=setInterval(tick,1000);
 }else if(!busy&&requestStartedAt!==null){
  clearInterval(requestTimer);requestTimer=null;requestStartedAt=null;$('request-elapsed').textContent='00:00';$('dialog-request-elapsed').textContent='00:00';
 }
}
async function fetchJSON(url,signal){
 activeRequests++;updateRequestProgress();
 try{
  let r;try{r=await fetch(url,{signal});}catch(e){if(e.name==='AbortError')throw e;throw new Error('Connexion interrompue. Vérifiez votre connexion puis réessayez la sélection.');}
  let result;try{result=await r.json();}catch(e){if(e.name==='AbortError')throw e;throw new Error(r.status>=500?'Le serveur est momentanément indisponible (HTTP '+r.status+'). Réessayez dans quelques instants.':'La réponse du serveur est illisible. Réessayez la sélection.');}
  if(!r.ok)throw new Error(result?.error||'Impossible de charger les données (HTTP '+r.status+').');return result;
 }finally{activeRequests--;updateRequestProgress();}
}
function sync(){$('topic-treatment').hidden=!state.topic;for(const key of ['start','end','budget','base','topic','topic_mode','denominator'])$(key).value=String(state[key]);$('constant').checked=state.constant;$('base').disabled=!state.constant;document.querySelectorAll('[data-measure]').forEach(b=>{const active=b.dataset.measure===state.measure;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});$('measure-help').textContent=state.measure==='CP'?'Crédits de paiement : suivre les dépenses de l’année.':'Autorisations d’engagement : suivre les engagements autorisés et consommés.';$('inflation-help').textContent=state.constant?`IPC annuel Insee · euros ${state.base}.`:'Euros courants, tels que publiés.';}
function clearFilteredMovements(){
 ++eventsRequest;++reservesRequest;
 clearRapMovements();
 for(const id of ['reserves-table','events-table','reserves-missing'])$(id).innerHTML='';
 for(const id of ['reserves-coverage','events-coverage'])$(id).textContent='Actualisation de la sélection…';
 for(const id of ['reserves-export','events-export']){$(id).removeAttribute('href');$(id).setAttribute('aria-disabled','true');}
}
async function load(){
 clearFilteredMovements();
 if(abort)abort.abort();abort=new AbortController();const controller=abort;activeViews++;updateRequestProgress();$('loading').hidden=false;$('error').hidden=true;$('export').disabled=true;
 try{const next=await fetchJSON('/api/explorer?'+params(),controller.signal);if(abort!==controller)return;data=next;state=next.parameters;history.replaceState(null,'','?'+params());sync();render();finishRestores();if(switchFocus){const f=switchFocus;switchFocus=null;const candidates=[...document.querySelectorAll('[data-exclude], [data-restore], [data-toggle-topic], [data-restore-topic]')];(candidates.find(b=>[b.dataset.exclude,b.dataset.restore,b.dataset.toggleTopic,b.dataset.restoreTopic].includes(f))||$('scope-title')).focus({preventScroll:true});}}
 catch(e){if(abort===controller&&e.name!=='AbortError'){finishRestores(true);data=null;$('topic-panel').hidden=true;$('credits-table').innerHTML='';$('movements-table').innerHTML='';$('summary').innerHTML='';$('chart').innerHTML='';$('error').textContent=e.message;$('error').hidden=false;}}
 finally{activeViews--;updateRequestProgress();if(abort===controller&&!controller.signal.aborted){$('loading').hidden=true;$('export').disabled=exportPending||!data;}}
}
function parentScope(scope){return scope.includes('/')?scope.slice(0,scope.lastIndexOf('/')):'';}
function updateLevelNavigation(){
 const parent=parentScope(state.scope),child=lastVisitedChild.get(state.scope);
 $('level-up').disabled=!state.scope;
 $('level-up').title=state.scope?'Remonter au niveau précédent':'Déjà au niveau des missions';
 $('level-down').disabled=!child||!data?.rows.some(row=>row.id===child);
 $('level-down').title=$('level-down').disabled?'Choisissez d’abord une ligne du tableau':'Revenir au niveau visité';
}
async function changeScope(scope){
 const previous=state.scope;
 if(scope!==previous&&parentScope(scope)===previous)lastVisitedChild.set(previous,scope);
 else if(scope!==previous&&parentScope(previous)===scope)lastVisitedChild.set(scope,previous);
 state.scope=scope;$('row-search').value='';await load();$('credits-table').parentElement.scrollTop=0;$('credits-table').parentElement.scrollLeft=0;
}
function render(){if(!data)return;
 renderNavigation();renderEcology();
 updateLevelNavigation();
 $('scope-title').textContent=data.scope_label;$('currency-label').textContent=`${state.measure} · ${state.constant?'Euros '+state.base:'Euros courants'}`;
 $('breadcrumbs').innerHTML='<button type="button" data-scope="">Toutes les missions</button>'+data.breadcrumbs.map(b=>`<span aria-hidden="true">/</span><button type="button" data-scope="${esc(b.id)}">${esc(b.label)}</button>`).join('');
 renderExclusions();
 $('updated').textContent='Données chiffrées : '+new Date(data.built_at).toLocaleDateString('fr-FR')+' · Catalogue : '+new Date(data.catalogue_updated_at||data.built_at).toLocaleDateString('fr-FR')+' · Version '+(bootstrap?.meta.application_version||'0.3');
 renderTopic();renderSummary();renderChart();renderTable();renderMovements();if(view==='movements'){loadEvents();loadReserves();loadRapMovements();}if(bootstrap)renderCoverage();
}
function renderTopic(){
 const topic=data.topic;$('topic-panel').hidden=!topic||topic.mode==='without';
 if(!topic)return;
 const refLink=r=>`<a href="/api/download/${esc(r.source)}#page=${r.page}" target="_blank" rel="noopener">PDF p. ${r.page} ↗</a>`;
 const table=topic.timeline.map(y=>`<tr><th scope="row">${y.year}</th><td>${y.routes.map(r=>esc(r.label)).join('<br>')||'—'}</td><td>${y.stages.length?y.stages.map(s=>esc(data.stages[s])).join('<br>'):y.year<2020?'Non applicable':'À documenter'}</td><td>${esc(y.note)}<div class="topic-references">${y.references.map(refLink).join(' ')}</div></td></tr>`).join('');
 $('topic-panel').innerHTML=`<div class="panel-heading"><div><span class="eyebrow">GRAND DOSSIER</span><h2>MaPrimeRénov’</h2></div><span class="pill">${topic.mode==='only'?'Dispositif isolé':'Dispositif retiré'}</span></div><p>${esc(topic.perimeter)}</p><p class="topic-status">${esc(topic.availability_note||'Consommé national 2021–2024 ; LFI et crédits ouverts 2024. Les disponibilités et changements de rattachement sont précisés par année ci-dessous.')}</p><p class="hint">${topic.mode==='without'?'Retrait des seules parts identifiées dans les programmes de votre sélection, avant correction de l’inflation. Les autres crédits de ces programmes sont conservés.':'Le dossier rassemble les parts identifiées dans plusieurs programmes. Les parts sont documentées par programme ; le rattachement à l’action 02 du P174 est vérifié pour les PLF 2020–2024, les LFI 2020–2023, les ouverts CP 2022 et les consommés 2020, 2023 et 2024. Aucun détail supplémentaire n’est estimé.'}</p><div class="topic-examples"><button type="button" class="secondary" data-topic-example="series">Consommé · 2021–2024</button><button type="button" class="secondary" data-topic-example="ecology">Écologie hors MaPrimeRénov’ · 2024</button></div><details><summary>Rattachements, sources et limites par année</summary><div class="table-scroll"><table class="topic-timeline"><thead><tr><th>Année</th><th>Financement identifié</th><th>Étapes chiffrées</th><th>Périmètre et source</th></tr></thead><tbody>${table}</tbody></table></div><ul>${topic.limitations.map(n=>`<li>${esc(n)}</li>`).join('')}</ul><p class="hint">Les montants n’incluent pas les dépenses fiscales ni les autres financements de la rénovation énergétique. Dossier vérifié le ${new Date(topic.updated_at+'T12:00:00').toLocaleDateString('fr-FR')}.</p></details>`;
}
function discrepancyLabel(items){
 const count=items?.length||0;
 return count?`Ce total comprend ${count} écart${count>1?'s':''} documenté${count>1?'s':''}`:'';
}
function discrepancySummary(items){
 const label=discrepancyLabel(items);if(!label)return '';
 return `<section class="source-card quality-explanation"><h3>${label}</h3><p>Programmes concernés par la sélection affichée. Les différences entre publications ne sont pas additionnées et ne modifient pas le total.</p><ul>${items.map(r=>`<li>${esc(r.year)} · Programme ${esc(r.program)}${r.program_label?' « '+esc(r.program_label)+' »':''} · ${r.kind==='RAP'?'RAP et total de référence':'publications historiques'}</li>`).join('')}</ul></section>`;
}
function renderSummary(){
 const latest=data.totals.at(-1),stages=['PLF','LFI','EXEC'];
 const cards=stages.map(s=>{const c=latest[s],warning=discrepancyLabel(c.documented_discrepancies);return `<div class="metric ${s==='EXEC'?'accent':''} ${c.status==='partial'?'partial':''}"><span>${esc(data.stages[s])} · ${latest.year}</span><strong>${c.approximate?'≈ ':''}${euros(c.value)}${c.status==='partial'?'*':''} <small>${unitLabel()}</small></strong><small>${c.value==null?'Donnée indisponible':c.status==='partial'?'Total des postes disponibles':state.measure+' · périmètre sélectionné'}</small>${state.topic||c.value==null||c.status==='partial'||warning?`<button type="button" class="metric-proof" data-year="${latest.year}" data-stage="${s}" data-cell-scope="${esc(state.scope)}" aria-haspopup="dialog">${c.value==null?'Pourquoi ce montant manque-t-il ?':warning||'Source et périmètre'} ${infoIcon}</button>`:''}</div>`;});
 const eligible=data.totals.filter(y=>['ok','excluded'].includes(y.EXEC.status));
 const complete=eligible.length===data.years.length;
 const total=complete?eligible.reduce((v,y)=>v+Math.round(y.EXEC.value*100),0)/100:null;
 const cumulativeItems=complete?eligible.flatMap(y=>y.EXEC.documented_discrepancies||[]):[];
 cards.push(`<div class="metric"><span>Consommé cumulé · ${state.start}–${state.end}</span><strong>${eligible.some(y=>y.EXEC.approximate)?'≈ ':''}${euros(total)} <small>${unitLabel()}</small></strong><small>${complete?data.years.length+' exercices additionnés':eligible.length+' / '+data.years.length+' exercices complets'}</small>${cumulativeItems.length?`<button type="button" class="metric-proof" data-cumulative-discrepancies="1" aria-haspopup="dialog">${discrepancyLabel(cumulativeItems)} ${infoIcon}</button>`:''}</div>`);
 $('summary').innerHTML=cards.join('');
}
function renderChart(){
 $('chart-caption').textContent=`${state.measure}, en ${unitLabel()} · ${state.constant?'euros '+state.base:'euros courants'} · sur le périmètre sélectionné`;
 const series=['PLF','LFI','EXEC'],colors=['#b2c6d5','#173a55','#d84b50'];
 const vals=data.totals.flatMap(y=>series.map(s=>y[s].value)).filter(v=>v!=null);
 if(!vals.length){$('chart').innerHTML='<div class="chart-empty">Aucune série chiffrée disponible sur ce périmètre.</div>';return;}
 const width=Math.max(300,Math.min(960,$('chart').clientWidth-30)),height=212,left=width<500?66:85,right=15,top=16,bottom=35,plotH=height-top-bottom,plotW=width-left-right;
 const min=Math.min(0,...vals),max=Math.max(1,...vals),span=max-min;
 const y=v=>top+(max-v)/span*plotH,zero=y(0),group=plotW/data.years.length,bar=Math.min(45,group/4.6),gap=Math.min(6,bar*.3);
 let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Comparaison annuelle des crédits proposés, votés et consommés"><title>${esc(data.scope_label)} : PLF, LFI et consommé</title>`;
 for(let i=0;i<4;i++){const v=min+(max-min)*i/3,py=y(v);svg+=`<line class="grid" x1="${left}" y1="${py}" x2="${width-right}" y2="${py}"/><text x="${left-12}" y="${py+4}" text-anchor="end">${euros(v)}</text>`;}
 data.totals.forEach((annual,i)=>{const center=left+group*(i+.5);if(group>=48||i===0||i===data.years.length-1||(i%2===0&&i<data.years.length-2))svg+=`<text x="${center}" y="${height-8}" text-anchor="middle">${annual.year}</text>`;
 series.forEach((s,j)=>{const c=annual[s],x=center+(j-1.5)*bar+gap/2;if(c.value==null){svg+=`<text x="${x+bar/2}" y="${zero-8}" text-anchor="middle">—</text>`;return;}const py=y(c.value),h=Math.max(1,Math.abs(py-zero));svg+=`<rect x="${x}" y="${Math.min(py,zero)}" width="${Math.max(1,bar-gap)}" height="${h}" rx="2" fill="${colors[j]}"${c.status==='partial'?' opacity="0.5" stroke="#876329" stroke-dasharray="3 2"':''}><title>${annual.year} · ${esc(data.stages[s])} : ${euros(c.value,true)} €${c.status==='partial'?' (partiel)':''}</title></rect>`;});});
 $('chart').innerHTML=svg+'</svg>';
}
function amountCell(c,year,s,scope,extra=''){
 const missing=`<button type="button" class="amount missing-proof" data-year="${year}" data-stage="${s}" data-cell-scope="${esc(scope)}" aria-haspopup="dialog" title="${esc(c.reason||'Voir le motif et les documents du périmètre')}" aria-label="${esc(data.stages[s])} ${year} : ${c.status==='not_applicable'?'non applicable':'données non disponibles'}. Voir le motif et les sources.">${unavailableLabel(c)} <span class="proof-hint">${c.status==='not_applicable'?'Explication':'Pourquoi ?'} ${infoIcon}</span></button>`;
 const warning=discrepancyLabel(c.documented_discrepancies),count=c.documented_discrepancies?.length||0;
 const title=[warning,c.status==='partial'?(c.coverage_reason||c.reason):c.reason||'Voir le calcul et les sources'].filter(Boolean).join(' · ');
 const content=c.value==null?missing:`<button type="button" class="amount ${c.status==='partial'?'partial':''}" data-year="${year}" data-stage="${s}" data-cell-scope="${esc(scope)}" title="${esc(title)}" aria-label="${esc(data.stages[s])} ${year} : ${euros(c.value,true)} euros. ${warning||'Voir les sources.'}">${c.approximate?'≈ ':''}${euros(c.value)}${c.status==='partial'?'*':''}${warning?`<span class="proof-hint">${count} écart${count>1?'s':''} documenté${count>1?'s':''} ${infoIcon}</span>`:''}</button>`;
 return `<td class="${extra}">${content}</td>`;
}
function renderTable(){
 $('evolution-note').hidden=mode!=='evolution';
 if(mode==='evolution'){renderEvolution();return;}
 if(mode==='ratios'){renderComparisons();return;}
 const depth=state.scope?state.scope.split('/').length:0;$('table-title').textContent=['Les missions, en détail','Les programmes de cette mission','Les actions de ce programme','Les sous-actions','Le poste sélectionné'][depth];
 const q=fold($('row-search').value);const rows=data.rows.filter(r=>fold(r.label+' '+r.code).includes(q));
 const stages=mode==='compare'?['PLF','LFI','EXEC']:[stage];
 const statsHead=mode==='series'?`<th rowspan="2">Écart ${state.start}–${state.end}<br><small>${unitLabel()}</small></th><th rowspan="2">Évolution<br><small>%</small></th><th rowspan="2">Cumul<br><small>${unitLabel()}</small></th>`:'';
 let html='<thead><tr><th scope="col" rowspan="2">'+['Mission','Programme','Action','Sous-action','Poste'][depth]+` <span class="hint">· ${rows.length}</span></th>`+data.years.map(y=>`<th scope="colgroup" class="year-group" colspan="${stages.length}">${y}</th>`).join('')+statsHead+'</tr><tr>';
 html+=data.years.map(()=>stages.map((s,i)=>`<th scope="col" class="${i===0?'year-start':''}">${mode==='compare'?({'PLF':'PLF','LFI':'LFI','EXEC':'Consommé'}[s]):esc(data.stages[s])}<br><small>${unitLabel()}</small></th>`).join('')).join('')+'</tr></thead><tbody>';
 const rowHTML=(r,total=false)=>`<tr class="${total?'total':r.excluded?'excluded':''}"><td>${total?'Total du périmètre':`${categoryLabel(r)}`}</td>`+r.series.map(y=>stages.map((s,i)=>amountCell(y[s],y.year,s,r.id,i===0?'year-start':'')).join('')).join('')+rowStatistics(r)+'</tr>';
 html+=rowHTML({id:state.scope,series:data.totals},true)+rows.map(r=>rowHTML(r)).join('');
 if(!rows.length)html+=`<tr><td colspan="${1+data.years.length*stages.length}" class="empty">${q?'Aucun poste ne correspond à cette recherche.':'Aucun détail supplémentaire importé pour ce périmètre.'}</td></tr>`;
 $('credits-table').innerHTML=html+'</tbody>';
}
function renderComparisons(){
 const q=fold($('row-search').value),rows=data.rows.filter(r=>fold(r.label+' '+r.code).includes(q));
 $('table-title').textContent='Écarts entre les étapes et taux de consommation';
 const keys=['LFI_PLF','EXEC_LFI','CONSUMPTION'],names=['LFI − PLF','Consommé − LFI','Consommé / '+(state.denominator==='OUVERT'?'ouverts':'LFI')];
 let html='<thead><tr><th rowspan="2">Périmètre</th>'+data.years.map(y=>`<th colspan="3">${y}</th>`).join('')+'</tr><tr>'+data.years.map(()=>names.map((n,i)=>`<th>${n}<br><small>${i===2?'%':unitLabel()}</small></th>`).join('')).join('')+'</tr></thead><tbody>';
 for(const row of [{id:state.scope,label:'Total du périmètre',series:data.totals,total:true},...rows]){
  html+=`<tr class="${row.total?'total':''}"><td>${row.total?esc(row.label):`${categoryLabel(row)}`}</td>`;
  for(const annual of row.series)for(const key of keys){const c=annual.comparisons[key];html+=`<td title="${esc(c.reason)}">${c.value==null?unavailableLabel(c):(c.approximate?'≈ ':'')+(c.unit==='%'?new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1}).format(c.value)+' %':euros(c.value))}</td>`;}
  html+='</tr>';
 }
 $('credits-table').innerHTML=html+'</tbody>';
}
function rowStatistics(row){
 if(mode!=='series')return '';
 const first=row.series[0][stage],last=row.series.at(-1)[stage];
 const valid=c=>c.value!=null&&['ok','excluded'].includes(c.status);
 const delta=valid(first)&&valid(last)?last.value-first.value:null;
 const pct=delta!=null&&first.value>0?delta/first.value*100:null;
 const all=row.series.every(y=>valid(y[stage]));
 const total=all?row.series.reduce((n,y)=>n+Math.round(y[stage].value*100),0)/100:null;
 const approx=row.series.some(y=>y[stage].approximate)?'≈ ':'';
 return `<td>${delta==null?'—':approx+euros(delta)}</td><td>${pct==null?'—':approx+new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1,signDisplay:'exceptZero'}).format(pct)+' %'}</td><td title="Le cumul nécessite une valeur pour chaque année sélectionnée.">${total==null?'—':approx+euros(total)}</td>`;
}
function renderMovements(){
 const ordered=['LFI','REPORT_ENTRANT','LEGIS','REGLEMENT','FDC','FONGIBILITE','OUVERT','EXEC','FDC_PREVU','PLRG_OUVERTURE','PLRG_ANNULATION','REPORT_SORTANT'];
 $('movements-table').innerHTML='<thead><tr><th scope="col">Étape · '+state.measure+'</th>'+data.years.map(y=>`<th scope="col">${y} · ${unitLabel()}</th>`).join('')+'</tr></thead><tbody>'+ordered.map(s=>`<tr class="${['OUVERT','EXEC'].includes(s)?'total':''}"><td>${esc(data.stages[s])}</td>`+data.totals.map(y=>amountCell(y[s],y.year,s,state.scope)).join('')+'</tr>').join('')+'</tbody>';
}
function renderCoverage(){
 const displayCount=n=>new Intl.NumberFormat('fr-FR').format(Number(n)||0);
 const indexed=searchStats?.available&&Number(searchStats.passages)>0;
 const indexCard=indexed?`<div class="coverage-stat featured"><strong>${displayCount(searchStats.passages)}</strong><span>passages documentaires indexés</span><small>Recherche dans le contenu de ${displayCount(searchStats.documents)} documents, avec renvoi aux sources.</small></div>`:`<div class="coverage-stat featured"><strong>${displayCount(bootstrap.meta.fact_count)}</strong><span>montants budgétaires structurés</span><small>Le cœur chiffré de l’explorateur.</small></div>`;
 const factsCard=indexed?`<div class="coverage-stat"><strong>${displayCount(bootstrap.meta.fact_count)}</strong><span>montants budgétaires structurés</span><small>Comparables selon l’année, l’étape et le périmètre disponibles.</small></div>`:`<div class="coverage-stat"><strong>${displayCount(bootstrap.meta.imported_source_count)}</strong><span>tables sources des calculs</span><small>Des données structurées, distinctes des documents de recherche.</small></div>`;
 $('coverage-highlights').innerHTML=`<div class="coverage-intro"><span class="eyebrow">LE BUDGET, À LA LOUPE</span><h2>Des millions de passages. Des chiffres que l’on peut vérifier.</h2><p>Explorez l’évolution des crédits, du budget proposé aux dépenses constatées. Les montants disponibles sont reliés à leurs documents sources, avec leur périmètre et leurs limites.</p></div><div class="coverage-stat-grid">${indexCard}${factsCard}<div class="coverage-stat"><strong>${displayCount(bootstrap.meta.source_count)}</strong><span>références au catalogue</span><small>Dont ${displayCount(bootstrap.documents)} PDF consultables.</small></div><div class="coverage-stat"><strong>11 ans</strong><span>de 2017 à 2027</span><small>2027 : crédits proposés dans le PLF. Exécution 2026 en cours.</small></div></div>`;
 const cov=bootstrap.coverage.filter(c=>c.budget===state.budget),years=Array.from({length:11},(_,i)=>2017+i),stages=['PLF','LFI','EXEC','OUVERT','FDC','REPORT_SORTANT'];
 let html='<div class="table-scroll"><table class="coverage-table"><thead><tr><th>Étape</th>'+years.map(y=>`<th>${y}</th>`).join('')+'</tr></thead><tbody>';
 for(const s of stages){html+=`<tr><td>${esc(bootstrap.stages[s])}</td>`+years.map(y=>{const c=cov.find(c=>c.year===y&&c.stage===s);if(c)return `<td class="coverage-ok">${['','Programme','Action','Sous-action'][c.grain]}<small>${c.programs} programmes</small></td>`;if(s==='FDC'&&y<=2022&&state.budget==='BG')return '<td class="unavailable" title="Des rattachements de fonds de concours figurent dans les RAP historiques, mais leur série annuelle n’est pas consolidée ici.">Dans les RAP<small>Non consolidé ici</small></td>';return '<td class="unavailable" title="Aucune série annuelle consolidée dans le tableau des crédits pour cette étape.">Non intégré</td>';}).join('')+'</tr>';}
 $('coverage').innerHTML=html+'</tbody></table></div><p class="table-note">Ce tableau décrit les chiffres consolidés de l’explorateur, pas tous les documents collectés. Pour 2017–2022, des fonds de concours figurent dans les RAP, sans série annuelle consolidée ici. Les reports repérés dans ces RAP sont des entrées dans l’exercice ; ils ne remplissent pas automatiquement la ligne « Reports vers N+1 ». Le niveau indiqué est le moins fin des données intégrées ; certains postes disposent d’un détail supplémentaire.</p>';
 $('corpus-info').textContent='Budget affiché : '+$('budget').selectedOptions[0].textContent+'. Le tableau ci-dessous montre les étapes et le niveau de détail disponibles, année par année.';
 $('ipc-source').href='/api/download/'+bootstrap.meta.inflation_source;
 const issues=bootstrap.meta.issues||[];
 const checks=issues.filter(i=>i.kind==='opening_identity');
 $('quality-notes').innerHTML=`<div class="panel-heading"><div><span class="eyebrow">POINT DE MÉTHODE</span><h2>Ce qu’il faut savoir sur les données</h2></div></div><div class="coverage-note-grid">
 <article><h3>D’où viennent les chiffres ?</h3><ul><li>Pour la LFI 2023, les montants par programme viennent des annexes PLRG : l’export officiel présente une anomalie de colonnes.</li><li>Pour 2021–2022, les montants consommés viennent des totaux AE/CP des synthèses RAP de chaque exercice.</li><li>La LFI 2026 est intégrée au niveau programme ; le PLF 2026 suit le niveau de détail indiqué dans le tableau. L’exécution annuelle 2026 est encore en cours.</li><li>Le PLF 2027 est intégré au niveau programme, avec les actions et sous-actions rapprochées disponibles. Les crédits 2027 sont proposés ; aucune LFI ni exécution 2027 n’est présentée.</li></ul></article>
 <article><h3>Jusqu’où remonte le détail ?</h3><ul><li>Actions RAP, mouvements et réserves du budget général : couverture étendue à 2023–2025.</li><li>Réserves de la mission Écologie : également disponibles pour 2017–2022.</li><li>Mouvements RAP 2017–2022 : lignes datées ou totaux annuels selon les sources. La couverture reste partielle ; certains rapprochements sont en cours de vérification. Le registre des actes juridiques datés reste partiel.</li></ul></article>
 <article><h3>Comment lire les écarts ?</h3><ul><li>Un écart supérieur à 10 € appelle une vérification ; il n’est pas validé automatiquement.</li><li>${checks.length} lignes présentent un écart entre les crédits ouverts publiés et la somme des mouvements indiqués. Les chiffres des documents sont conservés, sans fabriquer de total corrigé.</li><li>Le détail des sources et les tableaux absents se consultent dans « Mouvements et réserves ».</li></ul></article>
 <article><h3>Rapports et recherche</h3><ul><li>La disponibilité de la recherche dans le contenu et par sens est indiquée dans « Rapports et documents » ; elle dépend du service et de l’index accessibles.</li><li>Le site ne fournit pas encore d’analyse causale automatique par IA.</li>${state.topic?'<li>MaPrimeRénov’ dispose d’extractions documentées distinctes ; le tableau ci-dessus décrit les tables budgétaires générales.</li>':''}</ul></article>
 </div>`;

}
function currentPilot(){
 if(state.budget!=='BG')return '';
 if(state.topic==='maprimerenov'&&state.topic_mode==='only')return 'maprimerenov';
 if(state.scope==='TA'||state.scope.startsWith('TA/'))return 'ecologie';
 return '';
}
function renderNavigation(){
 const pilot=view==='credits'?currentPilot():'';
 const title=pilot==='ecologie'?'Mission Écologie.':pilot==='maprimerenov'?'MaPrimeRénov’.':labels[view][0];
 $('page-title').textContent=title;$('subtitle').textContent=labels[view][1];
 document.querySelectorAll('.nav button').forEach(b=>{
  const active=pilot?b.dataset.pilot===pilot:b.dataset.view===view;
  b.classList.toggle('active',active);
  if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
 });
}
async function openPilot(pilot){
 state={...state,budget:'BG',scope:pilot==='ecologie'?'TA':'',topic:pilot==='maprimerenov'?'maprimerenov':'',topic_mode:'only',exclude:[]};
 $('row-search').value='';sync();setView('credits');await load();
}
function setView(next){view=next;for(const v of Object.keys(labels))$(v+'-view').hidden=v!==next;$('shared-scope').hidden=['documents','coverage'].includes(next);renderNavigation();$('export').hidden=['documents','coverage'].includes(next);$('export-format').hidden=$('export').hidden;if(next==='documents')loadDocuments();if(next==='movements'){loadEvents();loadReserves();loadRapMovements();}if(next==='credits'&&data)renderChart();}
async function loadDocuments(){
 const sequence=++docSequence;
 try{
  const endpoint=docMode==='hybrid'?'/api/semantic-search':docMode==='text'?'/api/document-search':'/api/documents';
  $('documents').setAttribute('aria-busy','true');$('doc-search-status').textContent='Recherche en cours…';
  const result=await fetchJSON(endpoint+'?'+new URLSearchParams({q:$('doc-search').value,year:$('doc-year').value,format:$('doc-format').value}));
  if(sequence!==docSequence)return;
  documents=result.items||[];documentSearchStatus=docMode!=='title'?result:null;docLimit=40;renderDocuments();
 }catch(e){if(sequence===docSequence){$('documents').textContent=e.message;$('doc-count').textContent='Indisponible';}}
 finally{if(sequence===docSequence)$('documents').setAttribute('aria-busy','false');}
}
function safeURL(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:null;}catch{return null;}}
function renderDocuments(){
 if(docMode!=='title'){renderDocumentMatches();return;}
 $('doc-search-status').textContent='Recherche dans les titres et les noms de fichiers.';
 $('doc-count').textContent=documents.length+' documents';
 $('documents').innerHTML=documents.slice(0,docLimit).map(d=>{const origin=safeURL(d.url),domain=origin?new URL(origin).hostname:'Import fourni';return `<article class="document"><span class="document-icon" aria-hidden="true">${esc(d.format?.toUpperCase()||'DOC')}</span><div class="document-body"><h3>${esc(d.title)}</h3><p>${esc((d.years_title||[]).join(', '))} · ${d.path.includes('/rap/')?'RAP':d.path.includes('/plf/')?'PLF / PAP':d.path.includes('/plrg/')?'PLRG':''} · ${esc(domain)} · ${new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1}).format(d.bytes/1048576)} Mo${d.imported?' · intégré aux tableaux':''}${d.pages?' · '+d.pages+' pages':''}</p></div><a class="open" href="/api/download/${d.id}" target="_blank" rel="noopener">${d.format==='pdf'?'Ouvrir le PDF ↗':'Télécharger ↓'}</a>${origin?`<a class="source-link" href="${esc(origin)}" target="_blank" rel="noopener">Source</a>`:''}</article>`;}).join('')||'<p class="empty">Aucun document ne correspond à cette recherche.</p>';
 $('more-docs').hidden=docLimit>=documents.length;
}
function renderDocumentMatches(){
 const info=documentSearchStatus||{};
 $('more-docs').hidden=true;
 if(!info.available){
  $('doc-count').textContent=info.state==='preparing'?'Index en préparation':'Momentanément indisponible';$('doc-search-status').textContent=info.message||'Le texte intégral est en cours de préparation.';
  $('documents').innerHTML=`<div class="document-search-unavailable"><strong>Recherche documentaire indisponible</strong><p>${esc(info.message||'La recherche par titre reste utilisable dès maintenant.')}</p><button type="button" class="secondary" data-doc-mode="title">Revenir aux titres</button></div>`;return;
 }
 const query=$('doc-search').value.trim();
 $('doc-search-status').textContent=`${new Intl.NumberFormat('fr-FR').format(info.documents||0)} documents · ${new Intl.NumberFormat('fr-FR').format(info.passages||0)} passages indexés. ${docMode==='hybrid'?'Recherche par sens et mots clés':'Recherche par mots clés'}, avec sources.`;
 $('doc-count').textContent=query?`${documents.length} résultat${documents.length>1?'s':''} affiché${documents.length>1?'s':''}`:'Texte intégral prêt';
 if(!query){$('documents').innerHTML='<p class="empty">Saisissez un mot ou une expression pour chercher dans le contenu des rapports.</p>';return;}
 $('documents').innerHTML=documents.map(match=>{
  const citations=match.citations||[],first=citations[0]||{},years=[...new Set(citations.flatMap(c=>c.years||[]))].sort(),meta=[years.join(', '),first.stage,first.locator].filter(Boolean).join(' · ');
  const links=citations.map((c,index)=>{const origin=safeURL(c.url),page=String(c.locator||'').match(/^page:(\d+)(?:\/|$)/),local=c.local_available&&c.source_id?`<a class="open" href="/api/download/${esc(c.source_id)}${page?'#page='+page[1]:''}" target="_blank" rel="noopener">${index?'Document local':'Ouvrir le document'} ↗</a>`:'',official=origin?`<a class="source-link" href="${esc(origin)}" target="_blank" rel="noopener">Source officielle ↗</a>`:'';return local+official;}).join('');
  return `<article class="document document-match"><span class="document-icon" aria-hidden="true">TXT</span><div class="document-body"><h3>${esc(first.title||'Document budgétaire')}</h3><p class="document-excerpt">${esc(match.excerpt)}</p><p>${esc(meta||'Passage documentaire')} · Les montants de ce passage ne sont pas additionnés automatiquement.</p><div class="document-actions">${links}${/^[a-f0-9]{64}$/.test(match.id)?`<button type="button" class="secondary" data-passage="${match.id}">Lire le passage complet</button>`:''}</div></div></article>`;
 }).join('')||'<p class="empty">Aucun passage ne correspond à cette recherche et à ces filtres.</p>';
}
function setDocumentMode(next){
 clearTimeout(docTimer);docMode=['text','hybrid'].includes(next)?next:'title';$('doc-submit').hidden=docMode==='title';document.querySelectorAll('[data-doc-mode]').forEach(button=>{const active=button.dataset.docMode===docMode;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
 $('doc-search').placeholder=docMode==='hybrid'?'Ex. Pourquoi les crédits de rénovation ont-ils baissé ?':docMode==='text'?'Réserve de précaution, dégel, rénovation…':'Écologie, justice, RAP, PAP…';
 $('doc-hint').textContent=docMode!=='title'?'Recherche dans le contenu extrait des documents publics. Le filtre d’année porte sur le document, pas nécessairement sur chaque montant cité.':'Recherche par titre dans les documents collectés. Le filtre d’année ci-dessous est propre à la bibliothèque.';
 loadDocuments();
}
async function showPassage(id){
 const dialog=$('source-dialog');dialog.querySelector('.eyebrow').textContent='PASSAGE DU DOCUMENT SOURCE';$('source-title').textContent='Passage documentaire';$('source-content').textContent='Chargement…';dialog.showModal();
 try{const p=await fetchJSON('/api/document-passage/'+id);if(!p.text)throw new Error(p.message||'Passage indisponible.');
 const first=p.citations?.[0]||{};$('source-title').textContent=first.title||'Passage documentaire';
 $('source-content').innerHTML=`<p class="hint">${esc(first.locator||'')} · Empreinte du passage : <code>${esc(p.text_sha256)}</code></p><p class="document-excerpt">${esc(p.text)}</p><p class="hint">Vérifiez les en-têtes et les unités dans la page source avant de reprendre un montant.</p>`;
 }catch(e){$('source-content').textContent=e.message;}
}
function sourceCalculation(p){
 const c=p.calculation;if(!c)return '';
 const value=n=>n==null?'Données non disponibles':euros(n,true)+' €';
 const outside=(p.evidence||[]).some(e=>e.kind==='outside_scope');
 const unchanged=outside&&c.subtracted_nominal===0;
 const emptyScope=p.topic_mode!=='without'&&outside&&c.result_nominal===0;
 let html='<section class="source-card"><h3>'+((unchanged||emptyScope||c.status==='not_applicable')?'Périmètre documenté':'Calcul du montant affiché')+'</h3>';
 if(p.topic_mode==='without'){
  html+=`<p>Total du périmètre après les autres exclusions : <strong>${value(c.base_nominal)}</strong>.</p>`;
  html+=unchanged?'<p>Retrait MaPrimeRénov’ : <strong>non applicable dans ce périmètre</strong>. Le total est conservé ; aucune dépense nulle n’est déduite d’une cellule vide.</p>':`<p>Part MaPrimeRénov’ à retirer : <strong>${value(c.subtracted_nominal)}</strong>.</p>`;
  html+=`<p>Résultat ${unchanged?'conservé':'calculé'} en euros courants : <strong>${value(c.result_nominal)}</strong>.</p>`;
 }else html+=emptyScope?'<p>Aucun crédit MaPrimeRénov’ à isoler dans ce périmètre documenté. Ce résultat repose sur une règle de périmètre ; ce n’est pas un montant national nul publié.</p>':c.status==='not_applicable'?'<p>MaPrimeRénov’ est hors du périmètre documenté pour cette année. Ce statut ne correspond pas à un montant nul publié.</p>':`<p>Montant propre à MaPrimeRénov’ en euros courants : <strong>${value(c.result_nominal)}</strong>.</p>`;
 if(c.constant&&!emptyScope&&c.status!=='not_applicable')html+=`<p>Montant affiché en euros ${esc(c.base_year)} : <strong>${value(c.displayed_value)}</strong>. ${p.topic_mode==='without'?'La correction par l’IPC annuel est appliquée après le retrait.':'La correction utilise l’IPC annuel Insee.'}</p>`;
 return html+'</section>';
}
function sourceEvidence(p){
 return (p.evidence||[]).map(e=>`<section class="source-card"><h3>${e.kind==='outside_scope'?'Justification du périmètre':'Documents de référence'}</h3><p><strong>${esc(e.label||'')}</strong></p><p>${esc(e.explanation||'')}</p>${(e.references||[]).map(r=>`<a href="/api/download/${esc(r.source)}#page=${r.page}" target="_blank" rel="noopener">${esc(r.label||'Document de périmètre')} · PDF p. ${r.page} ↗</a>`).join(' ')}</section>`).join('');
}
function sourceComparisons(items){
 return (items||[]).map(w=>{
  const reference=Number(w.canonical_cents),rap=Number(w.rap_cents);if(!Number.isFinite(reference)||!Number.isFinite(rap))return '';
  const difference=Math.abs(rap-reference),percentage=reference?new Intl.NumberFormat('fr-FR',{maximumFractionDigits:8}).format(difference*100/Math.abs(reference))+' %':'non calculable (référence nulle)';
  const links=(w.citations||[]).map((c,i)=>/^[a-f0-9]{20}$/.test(c.source||'')?`<a href="/api/download/${esc(c.source)}${c.page?'#page='+Number(c.page):''}" target="_blank" rel="noopener">${i===0?'RAP':'Source de référence'}${c.page?' · PDF p. '+Number(c.page):''} ↗</a>`:'').filter(Boolean).join(' ');
  return `<section class="source-card"><h3>Programme ${esc(w.program)}${w.program_label?' « '+esc(w.program_label)+' »':''} · ${esc(w.year)} : deux sources donnent des totaux différents</h3><dl><dt>Total de référence retenu pour le programme</dt><dd><strong>${euros(reference/100,true)} €</strong></dd><dt>Total publié dans le RAP</dt><dd><strong>${euros(rap/100,true)} €</strong></dd><dt>Différence entre ces deux totaux</dt><dd><strong>${euros(difference/100,true)} €</strong> — soit ${percentage} du total de référence.</dd></dl><p>Ces deux montants concernent le programme complet, avant les exclusions et la correction de l’inflation. Les actions reprennent les chiffres du RAP ; la différence n’est pas répartie artificiellement entre elles.</p><p>C’est une divergence entre publications : elle ne démontre pas, à elle seule, une erreur de calcul du site.</p>${links?`<p>${links}</p>`:''}</section>`;
 }).join('');
}
function historicalDiscrepancy(x){
 if(!x)return '';
 const percentage=x.other_publication_cents?new Intl.NumberFormat('fr-FR',{maximumFractionDigits:6}).format(Math.abs(x.difference_cents)*100/Math.abs(x.other_publication_cents))+' %':'non calculable (total comparé nul)';
 const status=x.status==='Rapprochement exact (documents)'?'Rapprochement documentaire reconstitué ; confirmation administrative encore nécessaire':x.status==='Référentiel étayé, pont à compléter'?'Périmètres de publication différents ; rapprochement au centime manquant':x.status==='Hypothèse T2 non démontrée'?'Piste relative aux dépenses de personnel, non démontrée':'Cause de la différence non établie';
 const pdf=x.source_id?`<a href="/api/download/${esc(x.source_id)}${x.source_page?'#page='+Number(x.source_page):''}" target="_blank" rel="noopener">Ouvrir le PDF rapproché${x.source_page?' à la page '+Number(x.source_page):''} ↗</a>`:'';
 const links=(x.links||[]).map(url=>safeURL(url)?`<li><a href="${esc(safeURL(url))}" target="_blank" rel="noopener">${esc(new URL(url).hostname)} ↗</a></li>`:'').join('');
 return `<section class="source-card quality-explanation"><h3>Deux publications donnent des montants différents pour le programme ${esc(x.program)} en ${esc(x.year)}</h3><p><strong>${esc(status)}.</strong> Il s’agit du programme entier, en euros courants, avant exclusions et correction de l’inflation.</p><dl><dt>Montant conservé dans Nos Deniers</dt><dd><strong>${euros(x.site_cents/100,true)} €</strong></dd><dt>Montant de l’autre publication, selon le registre</dt><dd><strong>${euros(x.other_publication_cents/100,true)} €</strong></dd><dt>Différence entre les publications</dt><dd><strong>${euros(Math.abs(x.difference_cents)/100,true)} €</strong>, soit ${percentage} du montant comparé.</dd></dl><p>${esc(x.finding)}</p><p><strong>Ce que les pièces ne démontrent pas encore :</strong> ${esc(x.limit)}</p><p>Cette différence ne prouve pas une erreur de calcul du site. Elle n’est pas ajoutée aux autres écarts éventuels.</p><details><summary>Pièces citées et vérification encore nécessaire</summary><p>${esc(x.needed)}</p>${pdf}${links?`<ul>${links}</ul>`:''}</details></section>`;
}
function sourceExplanation(x){
 if(!x)return '';
 const ref=r=>{const page=Number(r.page),hasPage=Number.isInteger(page)&&page>0,local=/^[a-f0-9]{20}$/.test(r.source||''),url=local?'/api/download/'+r.source+(hasPage?'#page='+page:''):(safeURL(r.url)?(hasPage?safeURL(r.url).split('#')[0]+'#page='+page:safeURL(r.url)):''),label=esc(r.label||'Justificatif')+(hasPage?' · PDF p. '+page:r.locator?' · '+esc(r.locator):'');return url?`<a href="${esc(url)}" target="_blank" rel="noopener">${label} ↗</a>`:label;};
 const known=(x.known_components||[]).map(r=>`<li><strong>${esc(r.label)} : ${euros(r.cents/100,true)} €</strong> <small>(précision : ${esc(r.precision)})</small> · ${ref(r)}</li>`).join('');
 const contextual=(x.contextual_amounts||[]).map(r=>`<article class="quality-context"><strong>${esc(r.label)} : ${euros(r.cents/100,true)} € courants</strong><p>${esc(r.caution)}</p>${ref(r)}</article>`).join('');
 const contacts=(x.contacts||[]).map(c=>`<li><strong>${esc(c.name)}</strong><p>${esc(c.role)}</p><a href="${esc(safeURL(c.url)||'#')}" target="_blank" rel="noopener">${esc(c.label)} ↗</a>${c.email&&/^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+$/.test(c.email)?`<br><a href="mailto:${esc(c.email)}">${esc(c.email)}</a>`:''}${c.address?`<p>${esc(c.address)}</p>`:''}</li>`).join('');
 const missingPrograms=(x.missing_programs||[]).length>1?`<details><summary>Voir les ${x.missing_programs.length} programmes non renseignés</summary><ul>${x.missing_programs.map(r=>`<li>Programme ${esc(r.code)}${r.label?' « '+esc(r.label)+' »':''}</li>`).join('')}</ul></details>`:'';
 const technicalNote=x.technical_note?`<details><summary>Précisions techniques</summary><p>${esc(x.technical_note)}</p></details>`:'';
 const comparisons=sourceComparisons(x.source_comparisons);
 const opening=(x.opening_reconciliation_details||[]).length?`<details class="source-card"><summary>Autre contrôle : rapprochement des crédits ouverts (${x.opening_reconciliation_details.length} lignes)</summary><p>Il s’agit de comparer les crédits ouverts publiés à l’addition de leurs mouvements. ${comparisons?'Ces écarts sont distincts de la comparaison des deux totaux ci-dessus : ils ne s’additionnent pas pour expliquer cette différence.':'Ce contrôle porte sur les lignes sources, pas sur une addition effectuée par le site.'}</p><ul>${x.opening_reconciliation_details.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></details>`:'';
 return comparisons+`<section class="source-card quality-explanation"><h3>${esc(x.title)}</h3><p>${esc(x.summary)}</p>${(x.details||[]).map(t=>`<p>${esc(t)}</p>`).join('')}${missingPrograms}${technicalNote}${known?`<h4>Parts connues — total demandé encore incomplet</h4><ul>${known}</ul>`:''}${contextual?`<h4>${esc(x.contextual_title||'Chiffres trouvés, non retenus comme total du dispositif')}</h4>${contextual}`:''}${(x.references||[]).length?`<details><summary>Documents qui expliquent cette limite</summary><ul>${x.references.map(r=>`<li>${ref(r)}</li>`).join('')}</ul></details>`:''}${x.research_note?`<p class="hint">${esc(x.research_note)}</p>`:''}${contacts?`<details class="quality-requests"><summary>Comment obtenir le détail manquant ?</summary><p>Ces coordonnées officielles permettent de demander les documents. Elles ne garantissent pas l’existence de la ventilation.</p><ul>${contacts}</ul>${x.request_text?`<label for="quality-request">Demande adaptée à cette année, cette étape et ce périmètre</label><textarea id="quality-request" rows="9" readonly>${esc(x.request_text)}</textarea><button type="button" class="secondary" data-copy-quality="1">Copier la demande</button><span class="hint"> Aucun envoi automatique.</span>`:''}</details>`:''}</section>`+opening;
}
const rapExplanations=new Map();let rapExplanationId=0;
function clearRapExplanations(prefix){for(const key of rapExplanations.keys())if(key.startsWith(prefix+'-'))rapExplanations.delete(key);}
function rapExplanationButton(prefix,explanation,label,title){
 const key=prefix+'-'+(++rapExplanationId);rapExplanations.set(key,{explanation,title});
 return `<button type="button" class="cell ${explanation.status==='published'?'':'missing-label'}" data-rap-explanation="${key}" aria-label="${esc(title+' : '+label)}">${esc(label)} ${infoIcon}</button>`;
}
function showRapExplanation(key){
 const entry=rapExplanations.get(key);if(!entry)return;
 ++sourceRequest;$('source-title').textContent=entry.title;
 $('source-content').innerHTML=sourceExplanation(entry.explanation);$('source-dialog').showModal();
}
function rapYearExplanations(result,prefix){
 return (result.year_explanations||[]).map(r=>rapExplanationButton(prefix,r.explanation,r.year+' · Pourquoi ?',`RAP ${r.year} · ${state.measure}`)).join(' ');
}
let sourceRequest=0;
async function copyQualityRequest(){
 const field=$('quality-request');if(!field)return;
 try{await navigator.clipboard.writeText(field.value);toast('Demande copiée.');}
 catch{field.focus();field.select();toast('Texte sélectionné : utilisez Copier.');}
}
async function showSource(button){
 const request=++sourceRequest;
 const dialog=$('source-dialog');$('source-title').textContent=`${data.stages[button.dataset.stage]} · ${button.dataset.year} · ${state.measure}`;$('source-content').textContent='Lecture des sources…';dialog.showModal();
 try{const p=await fetchJSON('/api/provenance?'+params({year:button.dataset.year,stage:button.dataset.stage,cell_scope:button.dataset.cellScope}));if(request!==sourceRequest)return;
 let html=discrepancySummary(p.documented_discrepancies)+(p.historical_discrepancies?.length?p.historical_discrepancies.map(historicalDiscrepancy).join(''):historicalDiscrepancy(p.historical_discrepancy))+sourceExplanation(p.explanation)+sourceCalculation(p)+(p.note&&!p.explanation?`<p class="notice">${esc(p.note)}</p>`:'')+sourceEvidence(p)+(p.count?`<p class="hint">${p.count} lignes sources contribuent au montant. Valeurs ci-dessous en euros courants, avant correction de l’inflation.${state.constant?' Affichage du tableau en euros '+state.base+' selon l’IPC annuel Insee.':''}</p>`:'');
 html+=p.sources.map(s=>{const url=safeURL(s.url),pages=[...new Set([...p.rows,...(p.citations||[])].filter(r=>r.source===s.id&&r.page).map(r=>Number(r.page)).filter(page=>Number.isInteger(page)&&page>0))];return `<article class="source-card"><h3>${esc(s.title)}</h3><p>${esc(s.dataset_title||'')} · ${esc(s.license||'Licence non renseignée dans cet inventaire')}</p><p>Collecté le ${esc(s.checked_at?.slice(0,10)||'8 septembre 2026')} · Empreinte SHA-256 : <code>${esc(s.sha256)}</code></p><a href="/api/download/${s.id}${pages.length?'#page='+pages[0]:''}" target="_blank" rel="noopener">${pages.length?'Ouvrir le PDF à la page '+pages[0]:'Ouvrir le fichier local'} ↗</a>${pages.map(page=>`<a href="/api/download/${s.id}#page=${page}" target="_blank" rel="noopener">Page PDF ${page} ↗</a>`).join('')}${url?`<a href="${esc(url)}" target="_blank" rel="noopener">Source officielle ↗</a>`:''}</article>`;}).join('');
 if(p.rows.length)html+='<div class="table-scroll source-rows"><table><thead><tr><th>Poste</th><th>Ligne / page</th><th>Champ source</th><th>Montant (€ courants)</th></tr></thead><tbody>'+p.rows.map(r=>`<tr><td>${esc(r.program+' '+r.program_label)}${r.action?'<br>'+esc(r.action+' '+r.action_label):''}${r.subaction?'<br>'+esc(r.subaction+' '+r.subaction_label):''}<br><small>${esc(r.operation==='subtract_action'?(r.subaction?'À retirer : sous-action exclue':'À retirer : action exclue'):r.operation==='subtract'?'À retirer : MaPrimeRénov’':r.operation==='subset'?'Part MaPrimeRénov’':r.category?'Catégorie '+r.category:r.title?'Titre '+r.title:'')}</small></td><td>${r.page?`<a href="/api/download/${r.source}#page=${r.page}" target="_blank" rel="noopener">PDF p. ${r.page}</a>`:r.line}</td><td>${esc(r.field)}</td><td>${r.approximate?'≈ ':''}${euros(r.cents/100,true)}</td></tr>`).join('')+'</tbody></table></div>';
 if(p.truncated)html+='<p class="hint">Aperçu limité aux 300 premières lignes. Le fichier source contient l’ensemble des lignes.</p>';
 if(!p.count&&!p.calculation&&!p.explanation&&!(p.evidence||[]).length)html='<p>'+esc(p.note||'Ce montant ne comporte aucune ligne conservée après exclusions.')+'</p>';
 $('source-content').innerHTML=html;
 }catch(e){if(request===sourceRequest)$('source-content').textContent=e.message;}
}
function showCumulativeDiscrepancies(){
 const years=data.totals.filter(y=>['ok','excluded'].includes(y.EXEC.status));
 if(years.length!==data.years.length)return;
 const items=years.flatMap(y=>y.EXEC.documented_discrepancies||[]);if(!items.length)return;
 ++sourceRequest;
 $('source-title').textContent=`Consommé cumulé · ${state.start}–${state.end} · ${state.measure}`;
 $('source-content').innerHTML=discrepancySummary(items)+years.map(y=>(y.EXEC.historical_discrepancies||[]).map(historicalDiscrepancy).join('')+sourceComparisons(y.EXEC.source_disagreements)).join('');
 $('source-dialog').showModal();
}
function showTopicExclusion(){
 const topic=data?.topic;if(!topic||topic.mode!=='without')return;
 const details=$('topic-panel').querySelector('details');if(!details)return;
 $('source-title').textContent='Exclusion de MaPrimeRénov’';
 $('source-content').innerHTML='<p>Le filtre « hors MaPrimeRénov’ » retire les seules parts identifiées dans les sources, avant correction de l’inflation. Pour les années où le dispositif est documenté hors du périmètre sélectionné, le total est conservé.</p><p class="hint">'+esc(topic.perimeter)+'</p>'+(topic.availability_note?'<p>'+esc(topic.availability_note)+'</p>':'');
 const copy=details.cloneNode(true);copy.open=true;$('source-content').appendChild(copy);
 $('source-dialog').showModal();
}
function readSaved(){try{const value=JSON.parse(localStorage.getItem('nos-deniers-selections')||'[]');return Array.isArray(value)?value.slice(0,20):[];}catch{return [];}}
function renderSaved(){$('saved').innerHTML=readSaved().map((s,i)=>`<div class="saved-row"><button type="button" data-saved="${i}">${esc(s.label)}</button><button type="button" data-delete-saved="${i}" aria-label="Supprimer cette sélection">×</button></div>`).join('');}
function restore(id){state.exclude=state.exclude.filter(e=>e!==id);load();}
function beginRestore(button,included=true){
 if(pendingRestores.has(button)||button.getAttribute?.('aria-busy')==='true')return false;
 const previous=button.getAttribute?.('aria-checked');pendingRestores.set(button,previous==null?String(!included):previous);button.setAttribute?.('aria-checked',String(included));button.setAttribute?.('aria-busy','true');return true;
}
function finishRestores(failed=false){
 for(const [button,previous] of pendingRestores){if(failed)button.setAttribute?.('aria-checked',previous);button.removeAttribute?.('aria-busy');}
 pendingRestores.clear();
}
function toggleExclusion(button,id,restoreOnly=false){
 const topic=id==='maprimerenov',currentlyIncluded=button.getAttribute?.('aria-checked');
 const included=restoreOnly?true:currentlyIncluded==null?(topic?state.topic==='maprimerenov'&&state.topic_mode==='without':state.exclude.includes(id)):currentlyIncluded!=='true';
 if(!beginRestore(button,included))return;
 switchFocus=id;
 if(topic){state.topic=included?'':'maprimerenov';state.topic_mode=included?'only':'without';sync();}
 else if(included)state.exclude=state.exclude.filter(e=>e!==id);
 else if(!state.exclude.includes(id))state.exclude.push(id);
 load();
}
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.rapExplanation){showRapExplanation(b.dataset.rapExplanation);return;}
 if(b.dataset.copyQuality){copyQualityRequest();return;}
 if(b.dataset.view){if((b.dataset.view==='credits'&&currentPilot())||(b.dataset.view==='movements'&&currentPilot()==='maprimerenov')){state={...state,scope:'',topic:'',exclude:[]};$('row-search').value='';sync();setView(b.dataset.view);load();}else setView(b.dataset.view);}
 if(b.dataset.docMode)setDocumentMode(b.dataset.docMode);
 if(b.dataset.pilot)openPilot(b.dataset.pilot);
 if(b.dataset.ecologyPreset){state={...state,budget:'BG',scope:'TA',topic:b.dataset.ecologyPreset==='selected'?'maprimerenov':'',topic_mode:'without',exclude:b.dataset.ecologyPreset==='selected'?['TA/345','TA/235']:[]};$('row-search').value='';sync();setView('credits');load();}
 if(b.dataset.topicExample){state={...state,budget:'BG',topic:'maprimerenov',exclude:[],measure:'CP',scope:b.dataset.topicExample==='ecology'?'TA':'',topic_mode:b.dataset.topicExample==='ecology'?'without':'only',start:b.dataset.topicExample==='ecology'?2024:2021,end:2024};$('row-search').value='';sync();setView('credits');load();}
 if(b.dataset.passage)showPassage(b.dataset.passage);
 if(b.dataset.scope!==undefined)changeScope(b.dataset.scope);
 if(b.dataset.measure){state.measure=b.dataset.measure;sync();load();}
 if(b.dataset.mode){mode=b.dataset.mode;document.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('active',x===b));$('stage-label').hidden=!['series','evolution'].includes(mode);$('denominator-label').hidden=mode!=='ratios';renderTable();}
 if(b.dataset.exclude)toggleExclusion(b,b.dataset.exclude);
 if(b.dataset.restore)toggleExclusion(b,b.dataset.restore,true);
 if(b.dataset.restoreTopic==='maprimerenov')toggleExclusion(b,'maprimerenov',true);
 if(b.dataset.toggleTopic==='maprimerenov')toggleExclusion(b,'maprimerenov');
 if(b.dataset.topicExclusionDetails==='maprimerenov')showTopicExclusion();
 if(b.dataset.cumulativeDiscrepancies)showCumulativeDiscrepancies();
 else if(b.dataset.evolution)showEvolution(b);
 else if(b.dataset.year)showSource(b);
 if(b.dataset.saved!==undefined){const saved=readSaved()[Number(b.dataset.saved)];if(saved){state={...defaults,...saved.state};sync();load();toast('Sélection restaurée.');}}
 if(b.dataset.deleteSaved!==undefined){const saved=readSaved();saved.splice(Number(b.dataset.deleteSaved),1);try{localStorage.setItem('nos-deniers-selections',JSON.stringify(saved));renderSaved();}catch{toast('Enregistrement impossible dans ce navigateur.');}}
});
for(const id of ['start','end','budget','base'])$(id).addEventListener('change',()=>{state[id]=id==='budget'?$(id).value:Number($(id).value);if(id==='budget'){state.scope='';state.exclude=[];}if(state.start>state.end){if(id==='start')state.end=state.start;else state.start=state.end;}sync();load();});
for(const id of ['topic','topic_mode'])$(id).addEventListener('change',()=>{
 state[id]=$(id).value;
 if(id==='topic'&&!state.topic){state.scope='';state.exclude=[];state.topic_mode='only';$('row-search').value='';}
 if(state.topic&&state.budget!=='BG'){state.budget='BG';state.scope='';state.exclude=[];}
 sync();if(id==='topic')setView('credits');load();
});
$('constant').addEventListener('change',()=>{state.constant=$('constant').checked;sync();load();});
$('denominator').addEventListener('change',()=>{state.denominator=$('denominator').value;load();});
$('unit').addEventListener('change',render);$('stage').addEventListener('change',()=>{stage=$('stage').value;renderTable();});$('row-search').addEventListener('input',renderTable);
$('reset').addEventListener('click',()=>{state={...defaults,exclude:[]};$('row-search').value='';sync();load();});
async function exportExcel(){
 if(exportPending)return;
 exportPending=true;$('export').disabled=true;$('error').hidden=true;updateRequestProgress();
 try{
  let response;try{response=await fetch('/api/export.xlsx?'+params());}catch{throw new Error('Connexion interrompue pendant l’export. Vérifiez votre connexion puis réessayez.');}
  if(!response.ok){const result=await response.json().catch(()=>null);throw new Error(result?.error||(response.status>=500?'Le serveur est momentanément indisponible (HTTP '+response.status+'). Réessayez l’export dans quelques instants.':'Impossible de préparer l’export (HTTP '+response.status+').'));}
  if(!(response.headers.get('Content-Type')||'').startsWith('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))throw new Error('Le serveur n’a pas renvoyé un classeur Excel. Réessayez l’export.');
  let file;try{file=await response.blob();}catch{throw new Error('Téléchargement interrompu. Réessayez l’export.');}
  const url=URL.createObjectURL(file),link=document.createElement('a');
  link.href=url;link.download='nos-deniers.xlsx';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
 }catch(e){$('error').textContent=e.message;$('error').hidden=false;}
 finally{exportPending=false;updateRequestProgress();$('export').disabled=activeViews>0||!data;}
}
$('export').addEventListener('click',()=>{const format=$('export-format').value;if(format==='xlsx'){exportExcel();return;}location.href=(format==='selection'?'/api/selection':'/api/export')+'?'+params();});
$('save').addEventListener('click',()=>{if(!data)return;const saved=readSaved(),count=exclusionCount(),label=`${data.scope_label} · ${state.start}–${state.end} · ${state.measure}${count?' · '+count+' exclusion(s)':''}${state.constant?' · € '+state.base:''}`;saved.unshift({label,state:JSON.parse(JSON.stringify(state))});try{localStorage.setItem('nos-deniers-selections',JSON.stringify(saved.slice(0,20)));renderSaved();toast('Périmètre enregistré.');}catch{toast('Enregistrement impossible dans ce navigateur.');}});
$('level-up').addEventListener('click',()=>{if(state.scope)changeScope(parentScope(state.scope));});
$('level-down').addEventListener('click',()=>{const child=lastVisitedChild.get(state.scope);if(child&&data?.rows.some(row=>row.id===child))changeScope(child);});
$('close-source').addEventListener('click',()=>$('source-dialog').close());$('source-dialog').addEventListener('click',e=>{if(e.target===$('source-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
let docTimer;$('doc-search').addEventListener('input',()=>{clearTimeout(docTimer);if(docMode==='title')docTimer=setTimeout(loadDocuments,250);else $('doc-search-status').textContent='Appuyez sur Entrée ou sur Rechercher.';});$('doc-submit').addEventListener('click',loadDocuments);$('doc-search').addEventListener('keydown',e=>{if(e.key==='Enter'){clearTimeout(docTimer);loadDocuments();}});for(const id of ['doc-year','doc-format'])$(id).addEventListener('change',loadDocuments);$('more-docs').addEventListener('click',()=>{docLimit+=40;renderDocuments();});
let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(data&&view==='credits')renderChart();},100);});
async function init(){
 for(let year=2017;year<=2027;year++){for(const id of ['start','end','doc-year'])$(id).add(new Option(String(year),String(year)));if(year<=2025)$('base').add(new Option(String(year),String(year)));}
 try{const q=new URLSearchParams(location.search);for(const k of ['start','end','base'])if(q.has(k))state[k]=Number(q.get(k));for(const k of ['budget','measure','scope','topic','topic_mode','denominator'])if(q.has(k))state[k]=q.get(k);state.constant=q.get('constant')==='1';if(q.has('exclude')){const ex=JSON.parse(q.get('exclude'));if(Array.isArray(ex))state.exclude=ex;}}catch{state={...defaults,exclude:[]};}
 sync();renderSaved();
 try{bootstrap=await fetchJSON('/api/bootstrap');for(const [key,label] of Object.entries(bootstrap.stages))$('stage').add(new Option(label,key));$('stage').value=stage;await load();fetchJSON('/api/semantic-search/status').then(info=>{searchStats=info;renderIndexHeadline(info);renderCoverage();}).catch(()=>{});}
 catch(e){$('loading').hidden=true;$('error').textContent=e.message;$('error').hidden=false;}
}
init();

let eventsRequest=0;
async function loadEvents(){
 const request=++eventsRequest;
 $('events-coverage').textContent='Lecture des actes publiés…';
 $('events-export').removeAttribute('href');$('events-export').setAttribute('aria-disabled','true');
 try{
  const result=await fetchJSON('/api/events?'+params());if(request!==eventsRequest)return;
  $('events-coverage').textContent=result.coverage;
  $('events-export').href='/api/events?'+params({download:'1'});$('events-export').removeAttribute('aria-disabled');
  const rows=result.items.map(r=>`<tr><td>${esc(r.publication_date)}</td><td>${esc(r.act_title)}<br><small>${esc(r.program+' · '+r.program_label)}</small></td><td>${r.value==null?'—':euros(r.value)}<br><small>${esc(r.reason||'Annulation de crédits')}</small></td><td><a href="${esc(safeURL(r.url)||'#')}" target="_blank" rel="noopener">Annexe officielle ↗</a><br><a href="/api/download/${esc(r.source)}" target="_blank" rel="noopener">Copie conservée ↓</a><br><small>Ligne ${r.line} · ${r.measure}</small></td></tr>`).join('');
  $('events-table').innerHTML=`<thead><tr><th>Publication</th><th>Acte et programme</th><th>Montant (${unitLabel()})</th><th>Preuve</th></tr></thead><tbody>${rows||'<tr><td colspan="4">Aucun acte intégré correspondant à cette sélection. Cela ne signifie pas absence de mouvement.</td></tr>'}</tbody>`;
 }catch(e){if(request===eventsRequest){$('events-coverage').textContent=e.message;$('events-table').innerHTML='';}}
}

let reservesRequest=0;
async function loadReserves(){
 const request=++reservesRequest;
 clearRapExplanations('reserves');
 $('reserves-coverage').textContent='Lecture des tableaux de réserve…';
 $('reserves-table').innerHTML='';$('reserves-missing').textContent='';
 $('reserves-export').removeAttribute('href');$('reserves-export').setAttribute('aria-disabled','true');
 try{
  const result=await fetchJSON('/api/reserves?'+params());if(request!==reservesRequest)return;
  const coverage=document.querySelector('link[href="/presentation/general.css"]')?result.coverage.replace(/^Réserves Écologie : [^.]*\.\s*/u,'').replace(' ; la part MaPrimeRénov’ n’est pas isolée',''):result.coverage;
  $('reserves-coverage').textContent=coverage;
  $('reserves-export').href='/api/reserves?'+params({download:'1'});$('reserves-export').removeAttribute('aria-disabled');
  const fields=['initial','surgels','degels','cancellations','remaining'];
  const rows=result.items.map(r=>`<tr><th scope="row">${r.year}<br><small>${esc(r.program+' · '+r.program_label)}</small></th>${fields.map(k=>{const c=r.cells[k],label=c.value===null?(c.status==='not_applicable'?'Sans objet':'Données non disponibles')+' · Pourquoi ?':euros(c.value);return `<td title="${esc(c.reason)}">${c.explanation?rapExplanationButton('reserves',c.explanation,label,`Réserves · ${r.year} · P${r.program} · ${r.measure}`):euros(c.value)}</td>`;}).join('')}<td><a href="/api/download/${esc(r.source)}#page=${r.page}" target="_blank" rel="noopener">RAP ${r.year}, p. ${r.page} ↗</a>${(r.context_pages||[]).filter(p=>p!==r.page).map(p=>`<br><a href="/api/download/${esc(r.source)}#page=${p}" target="_blank" rel="noopener">Commentaire p. ${p} ↗</a>`).join('')}<br><small>${esc(r.note)}</small></td></tr>`).join('');
  $('reserves-table').innerHTML=`<thead><tr><th>Année et programme</th><th>Réserve initiale (${unitLabel()})</th><th>Surgels</th><th>Dégels</th><th>Annulations sur réserve</th><th>Solde avant schéma de fin de gestion</th><th>Source et portée</th></tr></thead><tbody>${rows||'<tr><td colspan="7">Aucun tableau de réserve intégré pour cette sélection. Cela ne signifie pas absence de réserve.</td></tr>'}</tbody>`;
  const reasons=[...new Set(result.items.flatMap(r=>Object.values(r.cells).filter(c=>c.status==='detail_unavailable'||c.status==='inflation_missing').map(c=>c.reason)))];
  $('reserves-missing').textContent=[...reasons,result.years_without_integrated_table.length?'Années sans tableau intégré dans cette sélection : '+result.years_without_integrated_table.join(', ')+'.':''].filter(Boolean).join(' ');
  $('reserves-missing').insertAdjacentHTML('beforeend',' '+rapYearExplanations(result,'reserves'));
 }catch(e){if(request!==reservesRequest)return;$('reserves-coverage').textContent=e.message;$('reserves-table').innerHTML='';}
}

let rapMovementsRequest=0;
function clearRapMovements(){
 ++rapMovementsRequest;
 clearRapExplanations('movements');$('rap-movements-gaps').innerHTML='';
 $('rap-annual-adjustments').hidden=true;$('rap-annual-adjustments').innerHTML='';
 $('rap-movements-coverage').textContent='Actualisation de la sélection…';
 $('rap-movements-table').innerHTML='';$('rap-movements-notes').textContent='';
 $('rap-movements-export').removeAttribute('href');$('rap-movements-export').setAttribute('aria-disabled','true');
 $('rap-movements-more').hidden=true;rapMovementNextOffset=0;rapMovementSelectionId='';
}
let rapMovementNextOffset=0,rapMovementSelectionId='';
function renderAnnualAdjustments(result){
 const block=$('rap-annual-adjustments'),rows=result.annual_adjustments||[];
 block.hidden=!rows.length;
 if(!rows.length){block.innerHTML='';return;}
 const amount=r=>r.value_cents!=null?euros(r.value_cents/100,Number($('unit').value)===1):rapExplanationButton('movements',{
  status:r.status,title:'Portée de la reprise annuelle',summary:r.reason||r.note,
  details:[r.note].filter(Boolean),references:r.citation?[{source:r.source,page:r.page,label:r.citation.label}]:[]
 },'Données non disponibles · Pourquoi ?',`Reprise annuelle · ${r.year} · P${r.program} · ${r.measure}`);
 block.innerHTML=`<h3>Rapprochement annuel : reprises et recyclages d’AE</h3><p class="hint">Ces montants annuels sont présentés séparément des mouvements datés du RAP. Ils expliquent le passage au total de l’annexe annuelle ; aucune date d’acte n’est déduite.</p><div class="table-scroll"><table><thead><tr><th>Exercice et programme</th><th>Montant (${unitLabel()})</th><th>Source et portée</th></tr></thead><tbody>${rows.map(r=>`<tr><th scope="row">${esc(r.year+' · P'+r.program)}<br><small>${esc(r.program_label||'')}</small></th><td>${amount(r)}<br><small>${esc(r.measure)}</small></td><td>${r.citation?`<a href="${esc(r.citation.url)}" target="_blank" rel="noopener">${esc(r.citation.label)} ↗</a><br>`:''}<small>${esc([r.note,r.reason].filter(Boolean).join(' '))}</small></td></tr>`).join('')}</tbody></table></div>`;
}
$('rap-movements-more').addEventListener('click',()=>loadRapMovements(true));
async function loadRapMovements(append=false,restarted=false){
 if(!append)clearRapMovements();const request=rapMovementsRequest;
 $('rap-movements-more').disabled=true;
 $('rap-movements-coverage').textContent='Lecture des récapitulations des RAP…';
 const query=params();query.set('view','summary');query.set('offset',String(append?rapMovementNextOffset:0));query.set('limit','500');
 try{
  const result=await fetchJSON('/api/rap-movements?'+query);if(request!==rapMovementsRequest)return;
  if(append&&rapMovementSelectionId&&result.selection_id!==rapMovementSelectionId)return loadRapMovements(false,true);
  rapMovementSelectionId=result.selection_id||'';
  const exportQuery=params();exportQuery.set('download','1');$('rap-movements-export').href='/api/rap-movements?'+exportQuery;$('rap-movements-export').removeAttribute('aria-disabled');
  const displayed=result.displayed_count??result.items.length,total=result.count??result.items.length;
  $('rap-movements-coverage').textContent=(restarted?'Les sources ont changé : affichage repris depuis la première page. ':'')+result.coverage+' '+displayed.toLocaleString('fr-FR')+' / '+total.toLocaleString('fr-FR')+' montants affichés.';
  const rows=result.items.map(r=>{
   const annual=r.date_precision==='annual'||r.date_kind==='annual';
   const date=annual?'Exercice '+(r.year??r.date.slice(0,4)):r.date_precision==='month'?new Intl.DateTimeFormat('fr-FR',{month:'long',year:'numeric'}).format(new Date(Number(r.date.slice(0,4)),Number(r.date.slice(5,7))-1,1)):r.date.split('-').reverse().join('/');
   const dateKind=annual?(r.kind==='TOTAL'?'Total annuel ; date non connue':'Date non publiée ; exercice indiqué'):r.date_kind==='month'?'Mois indiqué dans le RAP':'Signature indiquée dans le RAP';
   const amount=r.value==null?rapExplanationButton('movements',r.explanation,(r.status==='not_applicable'?'Sans objet':'Données non disponibles')+' · Pourquoi ?',`Mouvement · ${r.year} · P${r.program} · ${r.measure}`):(r.value>0?'+':'')+euros(r.value);
   const citation=r.citation?`<a href="${esc(r.citation.url)}" target="_blank" rel="noopener">${esc(r.citation.label)} ↗</a>`:'<span class="missing-label">Source non vérifiée</span>';
   const linked=r.linked_act_id==='JORFTEXT000049180270'?'<br><small><a href="https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000049180270" target="_blank" rel="noopener">Même opération que dans « Actes publiés » ↗</a></small>':'';
   return `<tr><th scope="row">${esc(date)}<br><small>${esc(dateKind)}</small></th><td>${esc(r.kind_label)}<br><small>${esc(r.program+' · '+r.program_label)} · ${esc(r.title_label)}</small></td><td title="${esc(r.reason)}">${amount}<br><small>${esc(r.measure)}${r.annual_reconciliation_status==='annual_reference_unavailable'?'<br>Tableau détaillé vérifié ; rapprochement annuel indisponible.':''}</small></td><td>${citation}${linked}<br><small>${esc(r.reason||r.field)}</small></td></tr>`;
  }).join('');
  if(append)$('rap-movements-body').insertAdjacentHTML('beforeend',rows);
  else $('rap-movements-table').innerHTML=`<thead><tr><th>Date indiquée</th><th>Mouvement et programme</th><th>Montant signé (${unitLabel()})</th><th>Source et portée</th></tr></thead><tbody id="rap-movements-body">${rows||'<tr><td colspan="4">Aucun mouvement de RAP intégré pour cette sélection. Cela ne signifie pas absence de mouvement.</td></tr>'}</tbody>`;
  rapMovementNextOffset=result.next_offset??0;$('rap-movements-more').hidden=!result.has_more;
  renderAnnualAdjustments(result);
  const reasons=[...new Set(result.items.filter(r=>r.reason).map(r=>r.reason))];
  const discrepancies=[...new Set((result.reconciliations||[]).filter(r=>['source_difference','annual_reference_unavailable'].includes(r.status)).map(r=>`${r.year} · P${r.program} · ${r.measure} : ${r.note}`))];
  $('rap-movements-notes').textContent=[...reasons,...discrepancies,result.years_without_integrated_rows.length?'Années sans mouvement de RAP intégré dans cette sélection : '+result.years_without_integrated_rows.join(', ')+'.':'','L’export conserve les huit colonnes des tableaux sources, y compris les cellules vides, au niveau du programme.'].filter(Boolean).join(' ');
  $('rap-movements-notes').insertAdjacentHTML('beforeend',' '+rapYearExplanations(result,'movements'));
  const gaps=result.programmes_without_recap||[];
  $('rap-movements-gaps').innerHTML=gaps.length?`<details><summary>${gaps.length} programme(s)-année(s) sans récapitulation datée intégrée</summary><p class="hint">Ces absences ne signifient pas zéro. Les totaux annuels déjà documentés restent consultables dans « La vie des crédits ».</p><ul>${gaps.map(r=>`<li>${esc(r.year+' · P'+r.program+' · '+r.program_label)} — ${rapExplanationButton('movements',r.explanation,'Voir l’explication',`Mouvements · ${r.year} · P${r.program} · ${state.measure}`)}</li>`).join('')}</ul></details>`:'';
 }catch(e){if(request!==rapMovementsRequest)return;$('rap-movements-coverage').textContent=e.message;if(!append)$('rap-movements-table').innerHTML='';}
 finally{if(request===rapMovementsRequest)$('rap-movements-more').disabled=false;}
}

function renderEcology(){
 $('ecology-panel').hidden=currentPilot()!=='ecologie';
 const chosen=state.topic==='maprimerenov'&&state.topic_mode==='without'&&['TA/345','TA/235'].every(x=>state.exclude.includes(x));
 $('ecology-perimeter').textContent=chosen?'Trois exclusions appliquées':state.exclude.length||state.topic?'Périmètre personnalisé':'Mission complète';
}
function renderEvolution(){
 const q=fold($('row-search').value),rows=data.rows.filter(r=>fold(r.label+' '+r.code).includes(q));
 $('table-title').textContent='Variations annuelles · '+data.stages[stage];
 let html='<thead><tr><th rowspan="2">Périmètre</th>'+data.years.map(y=>`<th colspan="4">${y}</th>`).join('')+'</tr><tr>'+data.years.map(()=>`<th>Montant<br><small>${unitLabel()}</small></th><th>Variation annuelle<br><small>€ courants · %</small></th><th>Variation annuelle<br><small>Inflation corrigée · %</small></th><th>Depuis ${state.start}<br><small>Inflation corrigée · %</small></th>`).join('')+'</tr></thead><tbody>';
 for(const row of [{id:state.scope,label:'Total du périmètre',series:data.totals,total:true},...rows]){
  html+=`<tr class="${row.total?'total':row.excluded?'excluded':''}"><td>${row.total?esc(row.label):`${categoryLabel(row)}`}</td>`;
  for(const a of row.series){
   html+=amountCell(a[stage],a.year,stage,row.id,'year-start');
   for(const key of ['nominal_yoy','real_yoy','real_from_start']){
    const c=a.evolution[stage][key];const label=c.value==null?unavailableLabel(c):(c.approximate?'≈ ':'')+new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1,signDisplay:'exceptZero'}).format(c.value)+' %';
    html+=`<td><button type="button" class="amount ${c.value==null?'unavailable-rate':''}" data-evolution="${key}" data-year="${a.year}" data-stage="${stage}" data-cell-scope="${esc(row.id)}" title="${esc(c.reason)}">${label}</button></td>`;
   }
  }
  html+='</tr>';
 }
 $('credits-table').innerHTML=html+'</tbody>';
}
function showEvolution(button){
 const row=button.dataset.cellScope===state.scope?{series:data.totals}:data.rows.find(r=>r.id===button.dataset.cellScope);
 const a=row?.series.find(y=>y.year===Number(button.dataset.year)),c=a?.evolution[button.dataset.stage]?.[button.dataset.evolution];if(!c)return;
 $('source-title').textContent='Calcul de la variation · '+data.stages[button.dataset.stage]+' · '+a.year;
 $('source-content').innerHTML=`<p>${esc(c.reason)}</p><p><strong>${c.value==null?'Taux indisponible':new Intl.NumberFormat('fr-FR',{maximumFractionDigits:4,signDisplay:'exceptZero'}).format(c.value)+' %'}</strong></p><p>${esc(c.formula)}</p><div class="table-scroll"><table><thead><tr><th>Année</th><th>Montant courant (€)</th><th>IPC annuel</th><th>Source du montant</th></tr></thead><tbody>${c.operands.map(op=>`<tr><td>${op.year}</td><td>${op.nominal_cents==null?'—':euros(op.nominal_cents/100,true)}</td><td>${op.ipc??'—'}</td><td><button type="button" class="text-button" data-year="${op.year}" data-stage="${button.dataset.stage}" data-cell-scope="${esc(button.dataset.cellScope)}">Voir les lignes et les sources</button></td></tr>`).join('')}</tbody></table></div><p class="hint">Les montants restent ceux du périmètre publié après les exclusions choisies. La correction de l’inflation ne neutralise pas les changements de mission ou de programme.</p><a href="/api/download/${esc(bootstrap.meta.inflation_source)}" target="_blank" rel="noopener">Série Insee utilisée ↗</a>`;
 $('source-dialog').showModal();
}

let switchFocus=null;
function unavailableLabel(c){return `<span class="unavailable missing-label" title="${esc(c.reason||'Aucune valeur vérifiée pour cette sélection.')}" aria-label="${esc(c.reason||'Données non disponibles')}">${c.status==='not_applicable'?'Non applicable':'Données non disponibles'}</span>`;}
function categorySwitch(row,excluded,restoreOnly=false){
 const inherited=excluded&&!state.exclude.includes(row.id),hasData=!row.series||row.series.some(a=>Object.keys(data.stages).some(s=>a[s]?.nominal!=null));
 const disabled=inherited||(!excluded&&!hasData),included=!excluded;
 const hint=inherited?'Réintégrez d’abord le poste parent dans les exclusions.':!hasData&&!excluded?'Données non disponibles pour cette sélection.':included?'Inclus dans le calcul. Désactiver pour exclure.':'Exclu du calcul. Activer pour réintégrer.';
 return `<button type="button" class="category-switch" role="switch" aria-checked="${included}" aria-label="Inclure ${esc(row.label)} dans le calcul" title="${esc(hint)}" ${restoreOnly?'data-restore':'data-exclude'}="${esc(row.id)}" ${disabled?'disabled':''}><span class="switch-track" aria-hidden="true"></span></button>`;
}
function categoryLabel(row){
 const depth=state.scope?state.scope.split('/').length:0;
 const missing=!row.excluded&&!row.series.some(a=>Object.keys(data.stages).some(s=>a[s]?.nominal!=null));
 return `<div class="row-label ${missing?'row-unavailable':''}"><span class="code">${esc(row.code)}</span><button type="button" class="drill" data-scope="${esc(row.id)}" ${depth>=3||(state.topic&&state.topic_mode==='only'&&!row.has_children)?'disabled':''}>${esc(row.label)}${row.has_children?'&nbsp;›':''}</button>${categorySwitch(row,row.excluded)}</div>`;
}

$('source-dialog').addEventListener('close',()=>{sourceRequest++;$('source-dialog').querySelector('.eyebrow').textContent='TRAÇABILITÉ DU MONTANT';updateRequestProgress();});
