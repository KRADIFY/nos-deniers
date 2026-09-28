"""Readable audit results. Raw evidence is retained separately and never reclassified as a pass."""
import collections,csv,html,json,re
from decimal import Decimal,InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

STAGES={'PLF':'proposé en PLF','LFI':'voté en LFI','OUVERT':'crédits ouverts','EXEC':'consommé'}
RATES={'nominal_yoy':'variation annuelle en euros courants','real_yoy':'variation annuelle après inflation','real_from_start':'variation depuis la première année après inflation'}
ABSENCE_HELP='Ce compteur vérifie que les cases sans valeur dans la base restent affichées comme indisponibles, sans être remplacées par zéro. Il ne compte pas des erreurs. Une même case peut être testée plusieurs fois ; ce n’est pas un inventaire de données manquantes distinctes. Il ne prouve pas que ces données sont absentes des publications officielles.'

def number(value):
    if value is None:return 'Non calculable'
    try:
        d=Decimal(str(value));text=format(d,'f')
        if '.' in text:text=text.rstrip('0').rstrip('.')
        whole,sep,fraction=text.partition('.')
        sign='-' if text.startswith('-') else ''
        return sign+format(abs(int(whole)),',').replace(',',' ')+(','+fraction if sep else '')
    except (ValueError,InvalidOperation):return str(value)

def describe(issue):
    cell=issue.get('cell','');p=issue.get('params',{});unit='';category='Contrôle à examiner'
    where=cell;explanation='Le résultat du site diffère du résultat attendu par le contrôle. Consulter le détail avant de conclure.'
    expected=issue.get('expected');actual=issue.get('actual')
    if cell.endswith(' sources') or 'origine de la case' in cell or 'source inconnue' in cell:
        category='Justificatif documentaire';unit='référence documentaire'
        explanation='Le contrôle attend une référence qui justifie le montant. Cette alerte ne mesure pas un écart en euros.'
        expected='Au moins une référence documentaire' if expected=='références présentes' else expected
        if actual==[]:actual='Aucune référence fournie'
    elif 'nominal_yoy' in cell or 'real_yoy' in cell or 'real_from_start' in cell:
        category='Variation après exclusion' if p.get('exclude') else 'Variation';unit='%'
        explanation='Comparaison de pourcentages, pas de montants en euros. Un zéro explicite après exclusion est différent d’une donnée indisponible.'
    elif 'montant en centimes' in cell:
        category='Montant';unit='€'
        expected=None if expected is None else Decimal(str(expected))/100
        actual=None if actual is None else Decimal(str(actual))/100
        explanation='Comparaison des montants après conversion des centimes en euros.'
    elif any(w in cell for w in ('euros courants','euros affichés','LFI_PLF','EXEC_LFI','OUVERT_LFI','EXEC_OUVERT')):
        category='Montant ou différence';unit='€'
    elif 'CONSUMPTION' in cell:
        category='Taux de consommation';unit='%'
    elif issue.get('kind')=='browser':category='Affichage dans le navigateur'
    elif issue.get('kind')=='stability':category='Version du site'
    def display(v):
        if v is None:return 'Non calculable' if unit=='%' else 'Aucune valeur attendue'
        if isinstance(v,(int,float,Decimal)) or isinstance(v,str) and re.fullmatch(r'-?\d+(?:\.\d+)?',v):return number(v)+(' '+unit if unit in ('€','%') else '')
        if isinstance(v,(list,dict)):return json.dumps(v,ensure_ascii=False)
        return str(v)
    for raw,label in RATES.items():where=where.replace(raw,label)
    pipe=cell.removesuffix(' sources').split(' | ')
    if len(pipe)==5:
        budget,measure,path,year,stage=pipe
        where=f'{"MaPrimeRénov’ · " if p.get("topic")=="maprimerenov" else ""}{path} · {year} · {STAGES.get(stage,stage)} · {measure}'
    return dict(category=category,location=where,measure=p.get('measure',''),unit=unit or 'état du contrôle',expected=display(expected),actual=display(actual),explanation=explanation)

def summarize(issues):
    groups={}
    for issue in issues:
        d=describe(issue);p=issue.get('params',{})
        # Keep years, stages, AE/CP and selected exclusions distinct. Only repeated observations merge.
        key=json.dumps([d,p.get('budget'),p.get('scope'),p.get('topic'),p.get('topic_mode'),p.get('exclude',[]),p.get('constant',False),p.get('base')],ensure_ascii=False,sort_keys=True)
        if key not in groups:groups[key]=dict(d,occurrences=0,controls=[],params=p,raw_cell=issue.get('cell',''))
        g=groups[key];g['occurrences']+=1
        if issue.get('kind') not in g['controls']:g['controls'].append(issue.get('kind',''))
    findings=list(groups.values());families=collections.Counter(g['category'] for g in findings)
    return dict(finding_count=len(findings),family_count=len(families),raw_signal_count=len(issues),families=dict(families),findings=findings)

def query(p):
    return urlencode({k:json.dumps(v,separators=(',',':')) if isinstance(v,list) else int(v) if isinstance(v,bool) else v for k,v in p.items()})

def safe_csv(v):
    text=str(v)
    return "'"+text if text.startswith(('=','+','-','@')) else text

def write_outputs(out,report,url):
    out=Path(out);summary=report['summary'];esc=lambda s:html.escape(str(s));fmt=lambda n:f'{n:,}'.replace(',',' ')
    with (out/'anomalies.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['Type de signalement','Poste et étape','Crédits','Unité','Attendu','Observé','Explication','Occurrences','Lien'])
        for g in summary['findings']:
            w.writerow([safe_csv(v) for v in [g['category'],g['location'],g['measure'],g['unit'],g['expected'],g['actual'],g['explanation'],g['occurrences'],url+'/?'+query(g['params'])]])
    with (out/'anomalies-techniques.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(['Contrôle','Case','Attendu','Observé','Lien'])
        for e in report['issues']:w.writerow([safe_csv(v) for v in [e['kind'],e.get('cell',''),e.get('expected',''),e.get('actual',''),url+'/?'+query(e['params'])]])
    rows=''.join('<tr>'+''.join('<td>'+esc(g[k])+'</td>' for k in ('category','location','expected','actual','explanation','occurrences'))+'<td><a href="'+esc(url+'/?'+query(g['params']))+'">Voir la sélection</a></td></tr>' for g in summary['findings'])
    counts=report['counts'];zero=report.get('zero_source_summary',{});limits=report.get('limits',[])+report.get('excluded_sections',[])
    if report['verdict']=='INCOMPLET':lead='Le contrôle n’a pas pu terminer toutes les vérifications. Les résultats ci-dessous ne constituent pas une validation complète.'
    elif summary['finding_count']:lead=f"{summary['finding_count']} point(s) distinct(s) à examiner, regroupant {summary['raw_signal_count']} signalement(s). Chaque ligne explique ce qui est comparé et son unité."
    else:lead='Aucun écart détecté sur les contrôles terminés. Ce résultat porte sur la restitution de la référence, pas sur l’exhaustivité des documents publics.'
    families=''.join('<li>'+esc(k)+' : '+fmt(v)+' point(s)</li>' for k,v in summary['families'].items())
    cards=''.join(f'<div class="card"><strong>{fmt(n)}</strong><span>{esc(label)}</span></div>' for n,label in [(counts.get('amounts',0),'comparaisons de montants'),(counts.get('calculations',0),'contrôles de calculs'),(summary['finding_count'],'points à vérifier dans l’affichage et les calculs')])
    tech=''.join('<li>'+fmt(counts.get(k,0))+' '+label+'</li>' for k,label in [('amounts','comparaisons de montants'),('calculations','contrôles de calculs et de conditions de calcul'),('missing','vérifications de cases sans valeur dans la référence'),('export_cells','contrôles de cellules exportées'),('visible_cells','contrôles de cellules visibles')])
    coverage=report.get('document_coverage')
    documentary='<h2>Contrôle documentaire</h2><p>La couverture des tableaux n’a pas été vérifiée dans cette campagne. Un résultat conforme sur les calculs ne vaut pas preuve d’exploitation complète des documents.</p>'
    if coverage:
        documentary=f'<h2>Couverture documentaire : partielle</h2><p>{coverage["documents_read"]} annexes relues sur {coverage["documents_expected"]} attendues. La fidélité aux sources et les données repérées mais non intégrées font l’objet d’un bilan séparé. Les autres publications restent à qualifier.</p><p><a href="coverage/couverture.html">Voir les documents, rapprochements et limites</a></p>'
    if report.get('mutation_tests',{}).get('passed'):
        documentary+=f'<p>{report["mutation_tests"]["tests"]} tests du moteur réussis : cellule témoin et erreurs injectées dans des copies en mémoire.</p>'
    page=f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Résultats du contrôle · Nos Deniers</title><style>
body{{font:16px/1.6 system-ui,sans-serif;max-width:1200px;margin:auto;padding:30px;color:#143a52;background:#f5f8fc}}h1{{line-height:1.2}}a{{color:#175897}}.verdict{{padding:16px;background:white;border-left:5px solid {'#2b8063' if report['passed'] else '#a96c15'};border-radius:6px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:22px 0}}.card{{background:white;border:1px solid #d5e2ee;border-radius:12px;padding:15px}}.card strong{{font-size:28px;display:block}}.card span{{font-size:14px}}details{{background:white;padding:18px;margin:18px 0;border:1px solid #d5e2ee;border-radius:9px}}summary{{cursor:pointer;font-weight:650}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;background:white;font-size:14px}}td,th{{text-align:left;padding:12px;border:1px solid #dbe3eb;vertical-align:top;overflow-wrap:anywhere}}th{{background:#edf3f9}}.note{{color:#526477}}@media(max-width:650px){{body{{padding:16px}}.cards{{grid-template-columns:1fr}}td,th{{min-width:130px}}}} code{{overflow-wrap:anywhere}}</style></head><body>
<h1>Résultats du contrôle des chiffres</h1><p>{esc(report['at'])} · <a href="{esc(url)}">Site contrôlé</a></p>
<p>Campagne {"rapide" if report["identity"].get("quick") else "planifiée"} : {fmt(report["identity"].get("planned",report["cases"]))} scénarios API prévus ; parcours navigateur échantillonnés.</p>
<div class="verdict"><strong>{esc('POINTS À VÉRIFIER' if report['verdict']=='ANOMALIES DÉTECTÉES' else report['verdict'])}</strong><p>{esc(lead)}</p></div><div class="cards">{cards}</div>
<p>Un point à vérifier ne signifie pas que le site est en panne ni que toutes ses réponses sont fausses. Il peut concerner un justificatif manquant, un écart entre valeurs ou un contrôle à reprendre. Son effet doit être examiné pour la case concernée ; un écart de montant reste signalé.</p>
<p>Cette partie vérifie ce que le site affiche à partir de la base. La couverture des documents est évaluée séparément ci-dessous.</p>
<h2>Points à vérifier dans la restitution du site</h2><ul>{families}</ul>
<p>{'Les signalements répétés sont regroupés. « Non calculable » désigne un taux sans valeur attendue ; un pourcentage porte toujours le symbole %.' if summary['finding_count'] else 'Aucun point signalé dans les vérifications terminées.'}</p>
<p><a href="anomalies.csv">Télécharger les points à examiner · CSV</a></p>
<div class="scroll"><table><thead><tr><th>Type de signalement</th><th>Poste et étape</th><th>Attendu</th><th>Observé</th><th>Explication</th><th>Occurrences</th><th>Sélection</th></tr></thead><tbody>{rows or '<tr><td colspan="7">Aucun point à examiner dans les contrôles terminés.</td></tr>'}</tbody></table></div>
{documentary}
<h2>Portée du résultat</h2><p>Le moteur compare la restitution du site à une copie identifiée de la base structurée et de ses registres. Il refait les calculs avec ses propres formules. Une donnée absente des deux côtés ne peut pas être retrouvée par cette comparaison.</p><ul>{''.join('<li>'+esc(x)+'</li>' for x in limits)}</ul>
<details id="technical"><summary>Détail technique des vérifications</summary><p>Ces compteurs mesurent des opérations de contrôle, pas des données distinctes ni des erreurs. La même case peut être vérifiée avec plusieurs filtres.</p><ul>{tech}</ul><p>{esc(ABSENCE_HELP)}</p><p>Les calculs comprennent aussi les cas où aucun taux ne doit être calculé. AE et CP sont distingués.</p><p>{fmt(report.get('documented_disagreements',0))} groupes présentent des divergences documentaires déjà consignées dans la référence ; ils ne constituent pas automatiquement des erreurs de restitution du site.</p><p><a href="anomalies-techniques.csv">Signalements techniques bruts · CSV</a> · <a href="rapport.json">Rapport technique · JSON</a></p><p>Version des données : <code>{esc(report['identity'].get('data_version',''))}</code></p></details>
<details><summary>Vérifications des zéros dans les sources</summary><p>Un blanc n’est pas une preuve de zéro. La relecture documentaire est distincte des vérifications de calcul.</p><p><a href="zeros-sources.csv">Relevé des zéros sources · CSV</a> · <a href="zeros-sources.json">Preuves documentaires · JSON</a></p><p>{esc(zero.get('message','Les résultats et les catégories sont conservés dans le relevé documentaire.'))}</p></details>
<p class="note">Le contrôle ne modifie ni le site ni la base. Les points de reprise et les signalements bruts sont conservés.</p></body></html>'''
    (out/'rapport.html').write_text(page,'utf-8')
