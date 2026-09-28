"""Human report of document coverage, distinct from the site calculation verdict."""
import csv,html,json
from pathlib import Path
from decimal import Decimal
from oracle import STAGES

def write_report(out,r,catalog,cells):
    out=Path(out);esc=lambda v:html.escape(str(v));fmt=lambda n:f'{n:,}'.replace(',',' ')
    def csvfile(name,fields,rows):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f,delimiter=';');w.writerow(fields)
            for row in rows:w.writerow(["'"+str(x) if str(x).startswith(('=','+','-','@')) else str(x) for x in row])
    euro=lambda v:'' if v is None else f'{Decimal(v)/100:,.2f}'.replace(',',' ').replace('.',',')
    csvfile('couverture-cellules.csv',['Année','Programme','Crédits','Étape','État','Source EUR','Base EUR','Écart EUR (base moins source)','Écart % de la source','Document','Page','Texte source','Justification'],[[c['year'],c['program'],c['measure'],STAGES.get(c['stage'],c['stage']),r['labels'][c['status']],euro(c['expected_cents']),' | '.join(euro(v) for v in c['actual_cents']),euro(c['gap_cents']),c['gap_percent'] or '',c['source'],c['page'],c['raw'],c['explanation']] for c in cells])
    csvfile('catalogue-exploitation.csv',['Document','Titre','Montants dans la base','Citations dans les registres','État de traceabilité','URL','Limite'],[[c['source'],c['title'],c['facts'],', '.join(c['registries']),c['status'],c['url'],c['meaning']] for c in catalog])
    statuses=''.join(f'<tr><td>{esc(r["labels"][k])}</td><td>{fmt(v)}</td></tr>' for k,v in r['counts'].items())
    examples=[c for c in cells if c['status']=='missing'][:20]
    rows=''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [c['year'],'P'+c['program'],c['measure'],STAGES.get(c['stage'],c['stage']),euro(c['expected_cents'])+' €',c['page']])+'</tr>' for c in examples)
    problems=''.join('<li>'+esc(p)+'</li>' for p in r['parse_issues'])
    page=f'''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Documents et données · contrôle indépendant</title><style>body{{font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:auto;padding:28px;background:#f5f8fc;color:#163b53}}a{{color:#175897}}.box,details{{padding:18px;background:white;border:1px solid #d8e4ee;border-radius:10px;margin:20px 0}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{text-align:left;padding:10px;border:1px solid #d8e4ee}}summary{{cursor:pointer;font-weight:650}}.scroll{{overflow:auto}}h1{{line-height:1.2}}code{{overflow-wrap:anywhere}}</style>
<h1>Les documents sont-ils réellement exploités ?</h1><p>Contrôle du {esc(r['at'][:10])} à {esc(r['at'][11:16])}</p><div class="box"><strong>Couverture documentaire partielle, explicitement délimitée.</strong><p>Ce contrôle complète la vérification des calculs. Il cherche les tableaux et montants présents dans les documents, même quand ils ne figurent pas dans la base. Il ne déclare pas que toutes les publications budgétaires ont été exploitées.</p></div>
<h2>Le périmètre relu directement</h2><p>{esc(r['scope'])}.</p><p><strong>{r['documents_read']} documents relus sur {r['documents_expected']} attendus</strong> · {fmt(r['programme_credit_rows'])} lignes de programme et type de crédits · {fmt(r['cells'])} cellules rapprochées.</p>
<p>Les textes sont relus avec un autre lecteur PDF. Programme, AE/CP, étape, page, unité, montant imprimé et coordonnées sont conservés. La base est lue sans modification. Une différence entre deux publications reste une différence, pas une panne du site.</p>
<table><tr><th>Résultat de la comparaison documentaire</th><th>Cellules</th></tr>{statuses}</table><p>Les lignes ci-dessus portent sur des observations de source. Elles ne sont ni des dépenses à additionner ni un nombre de réponses fausses. Les écarts, y compris les petits arrondis possibles, restent consultables avec leur montant et leur pourcentage.</p>
<p>Ampleur des divergences : {esc(' · '.join(k+' : '+fmt(v) for k,v in r.get('difference_bands',{}).items()))}. Les petits écarts ne sont pas effacés ; ces seuils servent à lire le bilan.</p>
<p><a href="couverture-cellules.csv">Toutes les cellules, écarts et preuves · CSV</a></p>
<h2>Premiers montants repérés sans justification d’intégration</h2><p>Cette liste indique un travail de qualification. Elle ne transforme aucune case du site en zéro et n’importe aucun montant automatiquement.</p><div class="scroll"><table><tr><th>Année</th><th>Programme</th><th>Crédits</th><th>Étape</th><th>Source</th><th>Page</th></tr>{rows or '<tr><td colspan="6">Aucune case de cette catégorie.</td></tr>'}</table></div>
<details><summary>Tableaux dont la lecture reste à vérifier ({len(r['parse_issues'])} signalements)</summary><ul>{problems}</ul><p>Un tableau non reconnu n’est jamais considéré comme un tableau vide ou entièrement traité.</p></details>
<details><summary>Traçabilité de l’ensemble du catalogue</summary><p>{fmt(r['catalog_documents'])} références sont recensées. Des fichiers peuvent être utiles à la recherche documentaire sans alimenter les calculs. Une citation ne démontre pas que tous les tableaux sont exploités ; l’absence de citation ne démontre pas que le fichier contient des montants manquants.</p><p><a href="catalogue-exploitation.csv">Inventaire et traces d’exploitation · CSV</a></p><ul>{''.join('<li>'+esc(k)+' : '+fmt(v)+'</li>' for k,v in r['catalog_counts'].items())}</ul></details>
<h2>Ce que ce contrôle ne prouve pas encore</h2><ul>{''.join('<li>'+esc(x)+'</li>' for x in r['limits'])}</ul><p>Les autres documents restent à qualifier. « Non retrouvé » ne signifie pas « non publié ». Les exceptions devront toujours être justifiées par une source et un périmètre.</p>
<details><summary>Version et preuves techniques</summary><p>Base : <code>{esc(r['database_sha256'])}</code></p><p>Contrat des documents attendus : <code>{esc(r['contract_sha256'])}</code></p><a href="coverage.json">Bilan technique</a></details></html>'''
    (out/'couverture.html').write_text(page,'utf-8')
