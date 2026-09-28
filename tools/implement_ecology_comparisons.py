"""Apply the next targeted audit lot; preserve source databases and packages."""
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/comparaisons-ecologie-20260909';OUT.mkdir(parents=True,exist_ok=True)
names=['budget_service/api.py','budget_service/exports.py','public/explorer.html','public/assets/explorer.js']
backup=OUT/'avant-comparaisons.zip'
if not backup.exists():
 with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as z:
  for name in names:z.write(ROOT/name,name)
def change(name,fn):
 p=ROOT/name;s=p.read_text(encoding='utf-8');t=fn(s);assert t!=s,name;p.write_bytes(t.encode('utf-8'))

def api(s):
 s=s.replace('from .comparisons import compare','from .comparisons import compare\nfrom . import evolution')
 needle='        return result\n    rows=[]'
 assert s.count(needle)==1
 s=s.replace(needle,'        evolution.attach(result,indices)\n'+needle)
 s=s.replace("    result['data_version']=", "    result['calculation_version']=evolution.VERSION\n    result['data_version']=")
 # Keep CSV facts in their existing rows; append the three rates with statuses.
 s=s.replace("                    (['Dossier','Traitement du dossier','Montant retiré EUR courants','Périmètre du dispositif','Note de disponibilité'] if thematic else []))", "                    (['Dossier','Traitement du dossier','Montant retiré EUR courants','Périmètre du dispositif','Note de disponibilité'] if thematic else [])+\n                    ['Variation annuelle courante %','Statut variation courante','Variation annuelle réelle %','Statut variation réelle','Variation réelle depuis début %','Statut variation depuis début','Année de référence depuis début','Sources des variations','Motifs des variations'])")
 needle="                    (['MaPrimeRénov’','Isoler le dispositif' if p['topic_mode']=='only' else 'Retirer le dispositif identifié',\n                      str(c.get('topic_subtracted_nominal','')).replace('.',','),safe_csv(data['topic']['perimeter']),safe_csv(c.get('reason',''))] if thematic else []))"
 assert s.count(needle)==1
 s=s.replace(needle,needle[:-2]+"+list(exports.evolution_csv(annual,stage,p['start'])))")
 return s
change(names[0],api)

def exports(s):
 s=s.replace('from .comparisons import COMPARISONS','from .comparisons import COMPARISONS\nfrom .evolution import LABELS')
 s=s.replace("'inflation','topic_version')", "'inflation','topic_version','calculation_version')")
 needle='def xlsx(data,sources):'
 extra='''def evolution_rows(data):
    yield ['Périmètre','Code','Année','AE / CP','Étape','Indicateur','Valeur %','Statut','Année de référence','Explication','Sources','Opérandes et indices']
    for row in [dict(id=data['parameters']['scope'],label=data['scope_label'],series=data['totals'])]+data['rows']:
        for annual in row['series']:
            for stage,metrics in annual.get('evolution',{}).items():
                for key,c in metrics.items():
                    yield [row['label'],row['id'],annual['year'],data['parameters']['measure'],STAGES[stage],LABELS[key],c['value'],c['status'],c['reference_year'],c['reason'],', '.join(c['sources']),json.dumps(c['operands'],ensure_ascii=False)]

def evolution_csv(annual,stage,first):
    metrics=annual.get('evolution',{}).get(stage,{})
    for key in LABELS:
        c=metrics.get(key,{})
        yield str(c['value']).replace('.',',') if c.get('value') is not None else ''
        yield c.get('status','unavailable')
    yield first
    yield ' '.join(sorted({s for c in metrics.values() for s in c['sources']}))
    yield ' | '.join(dict.fromkeys(c['reason'] for c in metrics.values() if c['status']!='ok'))

'''
 s=s.replace(needle,extra+needle)
 s=s.replace("    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'", "    sheets.append(('Évolution annuelle',evolution_rows(data)))\n    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'")
 s=s.replace("[['Version des données',data['data_version']],", "[['Version des calculs',data.get('calculation_version','')],['Version des données',data['data_version']],")
 return s
change(names[1],exports)

def html(s):
 panel='<section id="ecology-panel" class="panel topic-panel" aria-label="Périmètre Mission Écologie" hidden><div class="panel-heading"><div><span class="eyebrow">DOSSIER ÉCOLOGIE</span><h2>Choisir le périmètre à comparer</h2></div><span id="ecology-perimeter" class="pill"></span></div><p>Comparer la mission complète ou retirer MaPrimeRénov’, le programme 345 « Service public de l’énergie » et le programme 235 « Sûreté nucléaire et radioprotection », créé en 2025.</p><div class="topic-examples"><button type="button" class="secondary" data-ecology-preset="full">Mission complète</button><button type="button" class="secondary" data-ecology-preset="selected">Appliquer les trois exclusions</button></div><p class="hint">Les années et l’inflation sont conservées. Ce choix remplace les exclusions précédentes. Les changements de nomenclature ne sont pas tous neutralisés ; si la part MaPrimeRénov’ manque, le reste est indisponible.</p></section>'
 needle=' <section id="credits-view">'
 assert s.count(needle)==1
 s=s.replace(needle,needle+'\n  '+panel)
 s=s.replace('<button type="button" data-mode="ratios">Écarts et taux</button>', '<button type="button" data-mode="ratios">Écarts et taux</button><button type="button" data-mode="evolution">Variations annuelles</button>')
 s=s.replace('  <p class="table-note" id="precision-legend">','  <p class="table-note" id="evolution-note" hidden>Les taux annuels comparent deux années consécutives de la sélection. La variation depuis le début utilise sa première année. Les taux réels corrigent l’inflation même si les montants affichés sont en euros courants. Cliquez sur un taux pour consulter le calcul. Une donnée partielle ou une référence nulle ne donne pas de pourcentage.</p>\n  <p class="table-note" id="precision-legend">')
 return s
change(names[2],html)

def js(s):
 s=s.replace(' renderNavigation();\n', ' renderNavigation();renderEcology();\n',1)
 s=s.replace('function renderTable(){\n',"function renderTable(){\n $('evolution-note').hidden=mode!=='evolution';\n if(mode==='evolution'){renderEvolution();return;}\n")
 s=s.replace("$('stage-label').hidden=mode!=='series';", "$('stage-label').hidden=!['series','evolution'].includes(mode);")
 s=s.replace(' if(b.dataset.year)showSource(b);'," if(b.dataset.evolution)showEvolution(b);\n else if(b.dataset.year)showSource(b);")
 needle=" if(b.dataset.pilot)openPilot(b.dataset.pilot);"
 assert s.count(needle)==1
 s=s.replace(needle,needle+"\n if(b.dataset.ecologyPreset){state={...state,budget:'BG',scope:'TA',topic:b.dataset.ecologyPreset==='selected'?'maprimerenov':'',topic_mode:'without',exclude:b.dataset.ecologyPreset==='selected'?['TA/345','TA/235']:[]};$('row-search').value='';sync();setView('credits');load();}")
 s+='''
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
  html+=`<tr class="${row.total?'total':row.excluded?'excluded':''}"><td>${row.total?esc(row.label):`<button type="button" class="drill" data-scope="${esc(row.id)}">${esc(row.label)}</button>`}</td>`;
  for(const a of row.series){
   html+=amountCell(a[stage],a.year,stage,row.id,'year-start');
   for(const key of ['nominal_yoy','real_yoy','real_from_start']){
    const c=a.evolution[stage][key];const label=c.value==null?'—':(c.approximate?'≈ ':'')+new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1,signDisplay:'exceptZero'}).format(c.value)+' %';
    html+=`<td><button type="button" class="amount" data-evolution="${key}" data-year="${a.year}" data-stage="${stage}" data-cell-scope="${esc(row.id)}" title="${esc(c.reason)}">${label}</button></td>`;
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
'''
 return s
change(names[3],js)
print('Annual comparisons and Ecology preset applied.')
