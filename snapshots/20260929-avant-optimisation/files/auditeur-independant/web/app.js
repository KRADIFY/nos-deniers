'use strict';
const $=id=>document.getElementById(id),format=n=>new Intl.NumberFormat('fr-FR').format(n);
let currentRun=null,currentStatus=null,currentMode='full',stopSending=false;
const states={stopping:'Arrêt en cours',idle:'Aucun contrôle lancé',running:'Vérification en cours',complete:'Vérification terminée',interrupted:'Vérification interrompue',error:'Contrôle incomplet'};
function show(s){
 $('state').textContent=states[s.status]||'État indisponible';$('message').textContent=s.message||'Le premier audit lira la version des données actuellement en ligne.';
 currentRun=s.run_id;currentStatus=s.status;currentMode=s.mode||'full';const busy=['running','stopping'].includes(s.status);
 $('start').disabled=busy;$('delta').disabled=busy;$('resume').hidden=s.status!=='interrupted';
 $('stop').hidden=!busy;$('stop').disabled=stopSending||s.status==='stopping';$('stop').textContent=s.status==='stopping'?'Arrêt en cours…':'Arrêter la vérification';
 const p=s.progress;$('progress').hidden=!p||s.status!=='running';
 if(p){$('progress').max=p.planned+3;$('progress').value=p.completed;$('progress-label').textContent=format(p.completed)+(currentMode==='delta'?' étapes ciblées sur '+format(p.planned):' contrôles enregistrés · '+format(p.planned)+' scénarios API prévus')+'. Dernier point : '+new Date(p.at).toLocaleString('fr-FR');}
 const r=s.report;$('metrics').replaceChildren();
 if(r&&s.status==='complete'){$('state').textContent=r.verdict==='ANOMALIES DÉTECTÉES'?'Points à vérifier':r.passed&&r.document_coverage&&!r.document_coverage.global_coverage_complete?'Calculs conformes · couverture documentaire partielle':r.verdict;const stats={amounts:r.counts.amounts,calculations:r.counts.calculations,signals:r.summary?r.summary.finding_count:r.error_count};const labels=[['amounts','comparaisons de montants'],['calculations','contrôles de calculs'],['signals',r.summary?'points à vérifier dans l’affichage et les calculs':'signalements bruts (ancien rapport)']];for(const [k,label] of labels){const d=document.createElement('div');d.className='metric';const n=document.createElement('strong'),l=document.createElement('span');n.textContent=format(stats[k]||0);l.textContent=label;d.append(n,l);$('metrics').append(d);}document.querySelector('.status').dataset.result=r.passed?'success':'error';}
 if(s.status!=='complete')document.querySelector('.status').removeAttribute('data-result');
 $('links').hidden=!s.report_url||busy;
 if(s.report_url)$('report').href=s.report_url;
 $('coverage').hidden=!s.coverage_url;if(s.coverage_url)$('coverage').href=s.coverage_url;
 $('zeros').hidden=!s.zeros_url;if(s.zeros_url)$('zeros').href=s.zeros_url;
 $('csv').hidden=!s.csv_url;$('json').hidden=!s.json_url;
 if(s.csv_url)$('csv').href=s.csv_url;if(s.json_url)$('json').href=s.json_url;
}
async function refresh(){try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error('Service indisponible');show(await r.json());$('error').textContent='';}catch(e){$('error').textContent=e.message;}}
async function launch(resume,mode='full'){$('start').disabled=true;$('delta').disabled=true;try{const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resume,mode})});const s=await r.json();if(!r.ok&&r.status!==429)throw Error(s.error||'Lancement impossible');show(s);}catch(e){$('error').textContent=e.message;$('start').disabled=false;$('delta').disabled=false;}}
async function stopAudit(){
 if(stopSending||!currentRun)return;stopSending=true;$('stop').disabled=true;
 try{const r=await fetch('/api/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:currentRun})});const s=await r.json();if(!r.ok)throw Error(s.error||'Arrêt impossible');show(s);$('error').textContent='';}
 catch(e){$('error').textContent=e.message;}
 finally{stopSending=false;$('stop').disabled=currentStatus==='stopping';}
}
$('stop').addEventListener('click',stopAudit);
$('start').addEventListener('click',()=>launch(false,'full'));$('delta').addEventListener('click',()=>launch(false,'delta'));$('resume').addEventListener('click',()=>launch(true,currentMode));refresh();setInterval(refresh,5000);
