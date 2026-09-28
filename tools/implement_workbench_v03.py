from pathlib import Path
R=Path(__file__).resolve().parents[1]
def edit(name,changes):
 p=R/name;s=p.read_text(encoding='utf-8')
 for a,b in changes:
  assert a in s,(name,a[:90]);s=s.replace(a,b,1)
 p.write_text(s,encoding='utf-8')
edit('budget_service/api.py',[
 ('from . import topics','from . import topics, exports\nfrom .comparisons import compare'),
 ("    return dict(start=start,end=end", "    denominator=one('denominator','LFI')\n    if denominator not in ('LFI','OUVERT'): raise ValueError('Dénominateur invalide')\n    return dict(denominator=denominator,start=start,end=end"),
 ("                annual[stage]=c\n            result.append(annual)","                annual[stage]=c\n            annual['comparisons']=compare(annual,p.get('denominator','LFI'))\n            result.append(annual)"),
 ("    return result\n\ndef bootstrap", "    result['data_version']=meta.get('data_version') or meta['built_at']\n    result['catalogue_updated_at']=meta.get('catalogue_updated_at',meta['built_at'])\n    result['inflation']={'source':meta.get('inflation_source'),'indices':meta['indices'],'base':p['base'],'method':'Montant annuel × IPC de référence ÷ IPC annuel ; arrondi au centime.'}\n    import hashlib\n    result['topic_version']=hashlib.sha256(json.dumps(topics.load(),sort_keys=True).encode()).hexdigest() if hasattr(topics,'load') else hashlib.sha256((Path(__file__).parent/'data/maprimerenov.json').read_bytes()).hexdigest()\n    result['selection_id']=exports.fingerprint(result)\n    return result\n\ndef bootstrap"),
 ("meta['source_count']+=len(topics.sources())", "meta['application_version']='0.3'\n    meta['source_count']+=len(topics.sources())"),
 ])
# Additional CSV columns preserve the missing-value reason and the selection version.
p=R/'budget_service/api.py';s=p.read_text(encoding='utf-8');s=s.replace("'Identifiants sources']+", "'Identifiants sources','Motif de disponibilité','Version des données','Empreinte de sélection']+",1)
s=s.replace("' '.join(c.get('sources',[]))]+", "' '.join(c.get('sources',[])),safe_csv(c.get('reason','')),data.get('data_version',data['built_at']),data.get('selection_id','')]+",1);p.write_text(s,encoding='utf-8')
edit('public/explorer.html',[
 ('<button type="button" class="primary" id="export">','<div><label for="export-format" class="sr-only">Format d’export</label><select id="export-format"><option value="xlsx">Classeur Excel</option><option value="csv">Tableau CSV</option><option value="selection">Sélection et preuves JSON</option></select><button type="button" class="primary" id="export">'),
 ('Exporter les données <span aria-hidden="true">↓</span></button></div>','Exporter les données <span aria-hidden="true">↓</span></button></div></div>'),
 ('<button type="button" data-mode="series">Une étape sur plusieurs années</button>','<button type="button" data-mode="series">Une étape sur plusieurs années</button><button type="button" data-mode="ratios">Écarts et taux</button>'),
 ('<select id="stage"></select></label></div>','<select id="stage"></select></label><label id="denominator-label" hidden>Taux calculé sur <select id="denominator"><option value="LFI">les crédits votés en LFI</option><option value="OUVERT">les crédits ouverts</option></select></label></div>')])
edit('public/assets/explorer.js',[
 ("topic_mode:'only'};","topic_mode:'only',denominator:'LFI'};"),
 ("['start','end','budget','base','topic','topic_mode']","['start','end','budget','base','topic','topic_mode','denominator']"),
 ('bar=Math.min(45,group/4.6);','bar=Math.min(45,group/4.6),gap=Math.min(6,bar*.3);'),
 ('(j-1.5)*bar+3','(j-1.5)*bar+gap/2'),
 ('width="${bar-6}"','width="${Math.max(1,bar-gap)}"'),
 ('function renderTable(){','function renderTable(){\n if(mode===\'ratios\'){renderComparisons();return;}'),
 ("$('stage-label').hidden=mode!=='series';renderTable();","$('stage-label').hidden=mode!=='series';$('denominator-label').hidden=mode!=='ratios';renderTable();"),
 ("location.href='/api/export?'+params();","const format=$('export-format').value;location.href=(format==='xlsx'?'/api/export.xlsx':format==='selection'?'/api/selection':'/api/export')+'?'+params();"),
 ("['budget','measure','scope','topic','topic_mode']","['budget','measure','scope','topic','topic_mode','denominator']"),
 ("$('unit').addEventListener('change',render);","$('denominator').addEventListener('change',()=>{state.denominator=$('denominator').value;load();});\n$('unit').addEventListener('change',render);"),
 ("$('export').hidden=['documents','coverage'].includes(next);","$('export').hidden=['documents','coverage'].includes(next);$('export-format').hidden=$('export').hidden;"),
 ("$('updated').textContent='Données préparées le '+new Date(data.built_at).toLocaleDateString('fr-FR');", "$('updated').textContent='Données chiffrées : '+new Date(data.built_at).toLocaleDateString('fr-FR')+' · Catalogue : '+new Date(data.catalogue_updated_at||data.built_at).toLocaleDateString('fr-FR')+' · Version '+(bootstrap?.meta.application_version||'0.3');")])
p=R/'public/assets/explorer.js';s=p.read_text(encoding='utf-8');marker='function rowStatistics(row){';new='''function renderComparisons(){
 const q=fold($('row-search').value),rows=data.rows.filter(r=>fold(r.label+' '+r.code).includes(q));
 $('table-title').textContent='Écarts entre les étapes et taux de consommation';
 const keys=['LFI_PLF','EXEC_LFI','CONSUMPTION'],names=['LFI − PLF','Consommé − LFI','Consommé / '+(state.denominator==='OUVERT'?'ouverts':'LFI')];
 let html='<thead><tr><th rowspan="2">Périmètre</th>'+data.years.map(y=>`<th colspan="3">${y}</th>`).join('')+'</tr><tr>'+data.years.map(()=>names.map((n,i)=>`<th>${n}<br><small>${i===2?'%':unitLabel()}</small></th>`).join('')).join('')+'</tr></thead><tbody>';
 for(const row of [{id:state.scope,label:'Total du périmètre',series:data.totals,total:true},...rows]){
  html+=`<tr class="${row.total?'total':''}"><td>${row.total?esc(row.label):`<button type="button" class="drill" data-scope="${esc(row.id)}">${esc(row.label)}</button>`}</td>`;
  for(const annual of row.series)for(const key of keys){const c=annual.comparisons[key];html+=`<td title="${esc(c.reason)}">${c.value==null?'—':(c.approximate?'≈ ':'')+(c.unit==='%'?new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1}).format(c.value)+' %':euros(c.value))}</td>`;}
  html+='</tr>';
 }
 $('credits-table').innerHTML=html+'</tbody>';
}
''';assert marker in s;s=s.replace(marker,new+marker,1);p.write_text(s,encoding='utf-8')
