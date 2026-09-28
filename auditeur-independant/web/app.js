'use strict';
const $=id=>document.getElementById(id),format=n=>new Intl.NumberFormat('fr-FR').format(n);
const states={idle:'Aucun contrôle lancé',running:'Vérification en cours',complete:'Vérification terminée',interrupted:'Vérification interrompue',error:'Contrôle incomplet'};
function show(s){
 $('state').textContent=states[s.status]||'État indisponible';$('message').textContent=s.message||'Le premier audit lira la version des données actuellement en ligne.';
 $('start').disabled=s.status==='running';$('resume').hidden=s.status!=='interrupted';
 const p=s.progress;$('progress').hidden=!p||s.status!=='running';
 if(p){$('progress').max=p.planned+3;$('progress').value=p.completed;$('progress-label').textContent=format(p.completed)+' contrôles enregistrés · '+format(p.planned)+' scénarios API prévus. Dernier point : '+new Date(p.at).toLocaleString('fr-FR');}
 const r=s.report;$('metrics').replaceChildren();
 if(r&&s.status==='complete'){$('state').textContent=r.verdict;for(const [k,label] of [['amounts','montants comparés'],['calculations','calculs vérifiés'],['visible_cells','cases vues dans le navigateur']]){const d=document.createElement('div');d.className='metric';const n=document.createElement('strong'),l=document.createElement('span');n.textContent=format(r.counts[k]||0);l.textContent=label;d.append(n,l);$('metrics').append(d);}document.querySelector('.status').dataset.result=r.passed?'success':'error';}
 if(s.status!=='complete')document.querySelector('.status').removeAttribute('data-result');
 $('links').hidden=!s.report_url||s.status==='running';
 if(s.report_url)$('report').href=s.report_url;
 $('zeros').hidden=!s.zeros_url;if(s.zeros_url)$('zeros').href=s.zeros_url;
 $('csv').hidden=!s.csv_url;$('json').hidden=!s.json_url;
 if(s.csv_url)$('csv').href=s.csv_url;if(s.json_url)$('json').href=s.json_url;
}
async function refresh(){try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error('Service indisponible');show(await r.json());$('error').textContent='';}catch(e){$('error').textContent=e.message;}}
async function launch(resume){$('start').disabled=true;try{const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resume})});const s=await r.json();if(!r.ok&&r.status!==429)throw Error(s.error||'Lancement impossible');show(s);}catch(e){$('error').textContent=e.message;$('start').disabled=false;}}
$('start').addEventListener('click',()=>launch(false));$('resume').addEventListener('click',()=>launch(true));refresh();setInterval(refresh,5000);
