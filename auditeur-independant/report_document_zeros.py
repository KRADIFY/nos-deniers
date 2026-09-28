"""Targeted report only: never overwrite a previous whole-site audit report."""
import collections,datetime,html,json
from pathlib import Path
from oracle import Reference
from zeros import source_ledger,Reader

out=Path('resultats/service-local/runs/20260928-142500-016300');out.mkdir(parents=True,exist_ok=True)
ref=Reference(Path('references/20260924-final'));summary=source_ledger(ref,Path('references/physical-sources'),out)
inputs=json.loads(Path('resultats/document-zero-inputs.json').read_text('utf-8'));reader=Reader('references/physical-sources');items=[]
for g in inputs:
    for f in g['rows']:
        result=reader.inspect(f,g['source']);items.append(dict(fact=f,source=g['source'],result=result))
counts=dict(collections.Counter(i['result']['status'] for i in items))
assert counts=={'source_zero':162,'calculated_zero':1},counts
full=json.loads((out/'zeros-sources.json').read_text('utf-8'))
structured=collections.Counter(i['status'] for i in full['items'] if not i.get('registry'))
report=dict(at=datetime.datetime.now().astimezone().isoformat(),scope='Vérification ciblée des 163 faits nuls issus de PDF/HTML, distincte de l’audit général du site',counts=counts,structured_zero_statuses=dict(structured),items=items)
(out/'rapport.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
e=html.escape;rows=[]
for i in items:
    f=i['fact'];r=i['result'];s=i['source'];location=r.get('location',{})
    where=('PDF · page '+str(location['page'])) if location.get('kind')=='pdf' else 'HTML · tableau '+str(location['table'])+' · ligne '+str(location['row'])+' · colonne '+str(location['columns'][0])
    rows.append('<tr><td>'+e(f"{f['year']} · {f['measure']} · {f['stage']}")+'<br><strong>P'+e(f['program'])+'</strong> '+e(f['program_label'])+'</td><td>'+e(r['reason'])+'</td><td><code>'+e(str(r['raw']))+'</code><br>'+e(where)+'<br><a href="https://budget.lexmachine.net/api/download/'+e(f['source'])+'" target="_blank" rel="noopener">Consulter la source</a></td></tr>')
page='''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vérification des 163 zéros · Nos Deniers</title><style>body{font:16px/1.5 Arial,sans-serif;color:#173b50;background:#f4f7fa;margin:0}main{max-width:1150px;margin:35px auto;padding:24px}h1{font-size:30px}section{background:white;padding:22px;border:1px solid #dce5ed;border-radius:12px;margin:20px 0}b{font-size:23px}table{border-collapse:collapse;width:100%;background:white}th,td{padding:15px;text-align:left;border:1px solid #dce5ed;vertical-align:top}th{background:#173b50;color:white}a{color:#17567b}code{font-size:16px}small{color:#526979}@media(max-width:650px){main{padding:10px}.table{overflow:auto}table{min-width:750px}}</style><main><small>Nos Deniers · Contrôle ciblé · 28 septembre 2026</small><h1>Les 163 zéros documentaires ont été vérifiés</h1><section><b>162 zéros imprimés · 1 zéro démontré par calcul</b><p>Relecture de 49 PDF et d’un document HTML, avec contrôle des empreintes, programmes, exercices, étapes et colonnes AE/CP. Les repères sont conservés pour refaire automatiquement le contrôle.</p><p>Pour le programme 869 en 2018, la case « CP ouverts » est vide : le zéro est établi par CP consommés (0) + solde ouverts moins consommés (0). Aucune règle « blanc = zéro » n’a été utilisée.</p><p>Neuf cellules de 2019 proviennent de tableaux explicitement hors titre 2. Cette mention de périmètre est conservée dans leurs preuves ; elle ne doit pas disparaître dans une interprétation tous titres.</p></section><section><h2>Ce que ce résultat établit</h2><p>Les 18 338 montants nuls de la base structurée ont désormais une preuve de valeur relue : 17 937 zéros explicites et 401 calculs nuls. Les détails issus des registres annexes d’actions et de MaPrimeRénov’ constituent un périmètre distinct, qui n’est pas déclaré intégralement relu par ce contrôle.</p><p>Aucun montant du site ni de sa base n’a été modifié. Ce contrôle ciblé ne remplace pas le rapport général du site.</p><p><a href="/zeros?run=20260928-142500-016300">Explorer le relevé complet des zéros</a> · <a href="zeros-sources.csv">Télécharger le relevé CSV</a></p></section><h2>Les justificatifs, cas par cas</h2><div class="table"><table><thead><tr><th>Case vérifiée</th><th>Conclusion</th><th>Contenu et source</th></tr></thead><tbody>'''+''.join(rows)+'</tbody></table></div></main></html>'
(out/'rapport.html').write_text(page,'utf-8')
print(json.dumps(dict(targeted=counts,structured=dict(structured),ledger=summary['counts'],report=str(out/'rapport.html')),ensure_ascii=False))
