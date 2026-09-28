from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BACKUP=ROOT/'reports/reserves-et-consignes-20260909/avant-reserves'
BACKUP.mkdir(exist_ok=True)
for name in ['budget_service/web.py','public/explorer.html','public/assets/explorer.js']:
 path=ROOT/name;raw=path.read_bytes();copy=BACKUP/path.name
 if not copy.exists():copy.write_bytes(raw)
 text=raw.decode('utf-8')
 if name.endswith('web.py'):
  text=text.replace('from . import api, exports, events','from . import api, exports, events, reserves')
  old="                if path=='/api/events':"
  assert text.count(old)==1
  text=text.replace(old,"                if path=='/api/reserves':\n                    result=reserves.query(api.parameters(query),api.metadata(db))\n                    return self.reply(result,disposition='attachment; filename=nos-deniers-reserves.json' if query.get('download') else None)\n"+old)
 elif name.endswith('explorer.html'):
  old='<div class="notice"><strong>Réserve de précaution et gels</strong><p>La chronologie des gels et dégels n’est pas encore intégrée. Des crédits non consommés ne constituent pas une mesure de la réserve.</p></div>'
  assert text.count(old)==1
  new='<section class="panel"><div class="panel-heading"><div><h2>Réserves de précaution dans les RAP</h2><p id="reserves-coverage" class="hint">Première série : programme 174, Énergie, climat et après-mines, de 2017 à 2025.</p></div><a id="reserves-export" class="secondary" href="/api/reserves?download=1">Exporter les réserves et leurs preuves</a></div><div class="table-scroll"><table id="reserves-table"></table></div><p id="reserves-missing" class="table-note"></p><p class="table-note">Dégels et annulations : signes tels que publiés. — : ligne absente ou ventilation indisponible. Les autres programmes et la part MaPrimeRénov’ restent à extraire ; aucun total de mission n’est calculé.</p></section><div class="notice"><strong>Lire les réserves</strong><p>Le solde présenté précède le schéma de fin de gestion : il ne mesure pas le stock au 31 décembre. Un dégel peut précéder une annulation, sans rendre les crédits disponibles pour dépenser. Ces tableaux ne constituent pas une chronologie exhaustive ; les crédits non consommés ne mesurent pas le gel.</p></div>'
  text=text.replace(old,new)
 else:
  text=text.replace("if(view==='movements')loadEvents();","if(view==='movements'){loadEvents();loadReserves();}")
  text=text.replace("if(next==='movements')loadEvents();","if(next==='movements'){loadEvents();loadReserves();}")
  text=text.replace('Les gels, dégels et analyses IA restent à raccorder.', 'Les réserves du programme 174 sont consultables de 2017 à 2025 dans Mouvements et réserves. Les autres réserves, la chronologie détaillée et les analyses IA restent à raccorder.')
  assert 'async function loadReserves' not in text
  text+='''
let reservesRequest=0;
async function loadReserves(){
 const request=++reservesRequest;
 $('reserves-coverage').textContent='Lecture des tableaux de réserve…';
 $('reserves-table').innerHTML='';$('reserves-missing').textContent='';
 $('reserves-export').href='/api/reserves?'+params({download:'1'});
 try{
  const result=await fetchJSON('/api/reserves?'+params());if(request!==reservesRequest)return;
  $('reserves-coverage').textContent=result.coverage;
  const fields=['initial','surgels','degels','cancellations','remaining'];
  const rows=result.items.map(r=>`<tr><th scope="row">${r.year}<br><small>${esc(r.program+' · '+r.program_label)}</small></th>${fields.map(k=>{const c=r.cells[k];return `<td title="${esc(c.reason)}">${euros(c.value)}</td>`;}).join('')}<td><a href="/api/download/${esc(r.source)}#page=${r.page}" target="_blank" rel="noopener">RAP ${r.year}, p. ${r.page} ↗</a><br><small>${esc(r.note)}</small></td></tr>`).join('');
  $('reserves-table').innerHTML=`<thead><tr><th>Année et programme</th><th>Réserve initiale (${unitLabel()})</th><th>Surgels</th><th>Dégels</th><th>Annulations sur réserve</th><th>Solde avant schéma de fin de gestion</th><th>Source et portée</th></tr></thead><tbody>${rows||'<tr><td colspan="7">Aucun tableau de réserve intégré pour cette sélection. Cela ne signifie pas absence de réserve.</td></tr>'}</tbody>`;
  const reasons=[...new Set(result.items.flatMap(r=>Object.values(r.cells).filter(c=>c.status==='detail_unavailable'||c.status==='inflation_missing').map(c=>c.reason)))];
  $('reserves-missing').textContent=[...reasons,result.years_without_integrated_table.length?'Années sans tableau intégré dans cette sélection : '+result.years_without_integrated_table.join(', ')+'.':''].filter(Boolean).join(' ');
 }catch(e){if(request!==reservesRequest)return;$('reserves-coverage').textContent=e.message;$('reserves-table').innerHTML='';}
}
'''
 path.write_bytes(text.encode('utf-8'))
print('Reserve endpoint and view connected; annual budget facts untouched.')
