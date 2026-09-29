'use strict';
const $=id=>document.getElementById(id),run=new URLSearchParams(location.search).get('run');let page=0,timer,sequence=0;
const labels={documentary_zero:'Zéro confirmé par le tableau PDF',source_zero:'Zéro explicite dans la source',calculated_zero:'Zéro calculé depuis les cellules sources',source_blank:'Cellule source vide',source_dash:'Tiret dans la source',source_not_applicable:'Sans objet dans la source',nonzero_source:'Montant source non nul',document_review_recorded:'Relecture documentaire antérieure',undetermined:'Sens non déterminé',excluded:'Zéro dû aux exclusions',not_applicable:'Sans objet pour ce périmètre',missing:'Montant absent de la base',missing_detail:'Détail insuffisant',inflation_missing:'Conversion indisponible',referenced_zero:'Zéro de la référence avec sources',unproven_zero:'Zéro sans preuve attachée',computed_zero:'Solde nul calculé'};
const stages={PLF:'Proposé en PLF',LFI:'Voté en LFI',EXEC:'Consommé',OUVERT:'Crédits ouverts',REPORT_ENTRANT:'Reports de N−1',REPORT_SORTANT:'Reports vers N+1',FDC:'FdC et AdP rattachés',FDC_PREVU:'FdC et AdP prévus',REGLEMENT:'Mouvements réglementaires',LEGIS:'Ajustements législatifs',FONGIBILITE:'Fongibilité',PLRG_OUVERTURE:'Ouvertures en PLRG',PLRG_ANNULATION:'Annulations en PLRG'};
function text(tag,content){const n=document.createElement(tag);n.textContent=content;return n;}
async function load(){const request=++sequence;try{
 const p=new URLSearchParams({run:run||'',kind:$('kind').value,status:$('status').value,q:$('search').value,page});const response=await fetch('/api/zeros?'+p);if(!response.ok)throw Error('Relevé indisponible');const d=await response.json();if(request!==sequence)return;
 const selected=$('status').value;$('status').replaceChildren(new Option('Tous les résultats',''));for(const [s,n]of Object.entries(d.counts))$('status').add(new Option((labels[s]||s)+' · '+n.toLocaleString('fr-FR'),s));$('status').value=selected;
 $('summary').textContent=Object.entries(d.counts).map(([s,n])=>(labels[s]||s)+' : '+n.toLocaleString('fr-FR')).join(' · ');
 $('count').textContent=d.message||d.count.toLocaleString('fr-FR')+' cas correspondant aux filtres.';$('rows').replaceChildren();
 for(const item of d.items){const tr=document.createElement('tr'),where=document.createElement('td'),meaning=document.createElement('td'),raw=document.createElement('td'),proof=document.createElement('td');
  where.append(text('strong',[item.year,item.measure,stages[item.stage]||item.stage].join(' · ')),text('p',item.budget+' · '+(item.path||'Total du budget')));if(item.category||item.title)where.append(text('small','Catégorie '+(item.category||'—')+' · titre '+(item.title||'—')));
  meaning.append(text('strong',item.label||labels[item.status]||item.status),text('p',item.reason||'Motif non renseigné.'));
  if(Object.hasOwn(item,'raw'))raw.append(text('code',JSON.stringify(item.raw)),text('p',item.field||''));else if(item.selection){const s=item.selection;raw.append(text('p',(s.topic?'MaPrimeRénov’ · '+s.topic_mode:'Budget général du périmètre')+(s.exclude.length?' · exclusions : '+s.exclude.join(', '):' · aucune exclusion')));}else raw.append(text('p','Contenu de cellule non relu automatiquement.'));
  if(item.location?.kind==='pdf')raw.append(text('small','PDF · page '+item.location.page+' · repères contrôlés dans le document'));
  else if(item.location?.kind==='html')raw.append(text('small','Tableau '+item.location.table+' · ligne '+item.location.row+' · colonne '+item.location.columns.join(', ')));
  else if(item.location)raw.append(text('small','Feuille '+(item.location.sheet||'CSV')+' · ligne '+item.location.row+' · colonne(s) '+item.location.columns.join(', ')));
  const sources=item.source?[item.source]:(item.source_ids||[]);for(const source of sources){if(!/^[a-f0-9]{20}$/.test(source))continue;const link=text('a',item.source_title||'Consulter la source');link.href='https://budget.lexmachine.net/api/download/'+source;link.target='_blank';link.rel='noopener';proof.append(link,document.createElement('br'));}
  if(item.line)proof.append(text('p','Repère enregistré : '+item.line));if(!sources.length)proof.append(text('p','Aucune pièce attachée à cette case.'));
  tr.append(where,meaning,raw,proof);$('rows').append(tr);
 }
 $('previous').disabled=page===0;$('next').disabled=!d.has_more;$('page').textContent='Page '+(page+1);$('error').textContent='';
 if(run){$('download').hidden=false;$('download').href='/reports/'+encodeURIComponent(run)+'/zeros-sources.csv';}
 }catch(e){if(request===sequence)$('error').textContent=e.message;}}
for(const id of ['kind','status'])$(id).addEventListener('change',()=>{page=0;if(id==='kind')$('status').value='';load();});$('search').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{page=0;load();},250);});$('previous').addEventListener('click',()=>{page--;load();});$('next').addEventListener('click',()=>{page++;load();});load();
