"""Write an additive quality handoff; never modify the package being processed."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
SUP=ROOT/'complement-vectorisation-20260909'
CONTROL=SUP/'_controle'
QA=ROOT/'reports/developpement-20260909/qa-word'
QA.mkdir(parents=True,exist_ok=True)
old=ROOT/'vectorisation-nos-deniers-20260909'
quality=[]
for r in json.loads((old/'_controle/fonds-existants.json').read_text(encoding='utf-8'))['items']:
    quality.append(dict(original_relative_path=r['relative_path'],sha256=r['sha256'],source_kind='derived_database_text',
        table_layout='not_certified',numeric_status='not_validated_budget_fact',allow_automatic_numeric_fact=False,
        semantic_use=True,reason='Export textuel d’articles SQL. Une annexe aplatie ne permet pas de certifier les colonnes AE et CP.'))
for r in json.loads((old/'_controle/complements-manifest.json').read_text(encoding='utf-8'))['items']:
    if r.get('status')=='export_text_from_existing_chunks':
        quality.append(dict(original_relative_path=r['filepath'],sha256=r['sha256'],source_kind='reconstructed_cour_text',
            table_layout='not_certified',numeric_status='not_validated_budget_fact',allow_automatic_numeric_fact=False,
            semantic_use=True,reuse_existing_vectors=True,cour_document_id=r['cour_document_id'],
            reason='Texte récupéré dans les chunks Cour ; mise en page du PDF non certifiée.'))
assert len(quality)==197
CONTROL.mkdir(exist_ok=True)
(CONTROL/'qualite-sources.json').write_text(json.dumps(dict(
    original_root=str(old),rules=quality,
    other_sources_policy='Les tableaux extraits de PDF, HTML, CSV ou XLS restent raw_not_validated_facts tant que leurs cellules et totaux ne sont pas contrôlés.',
    verified_numeric_store='donnees-structurees/budget.sqlite',
    act_replacement={'act':'JORFTEXT000049180270','old_group':'decret-2024-124','prefer_table':'sources/JORFTEXT000049180270.html','validated_events':'donnees-structurees/events.sqlite'},
    implementation='Appliquer ces indicateurs aux documents, aux preuves et aux chunks associés. Ne pas détruire les sources ou embeddings existants. Ces règles sont un contrat à intégrer, pas une correction automatiquement appliquée au pipeline en cours.'
),ensure_ascii=False,indent=2),encoding='utf-8')
contract=(ROOT/'reports/audit-20260909/qa-liens/artifact.md').read_text(encoding='utf-8')
(QA/'artifact.md').write_text(contract+'\nAdaptation de contenu : complément de vectorisation du 9 septembre 2026, mêmes prototypes et parties préservées. Dossier source en cours de traitement inchangé. Titre et intertitres en mots simples.\n',encoding='utf-8')
source=(ROOT/'tools/build_vectorisation_notice_docx.py').read_text(encoding='utf-8')
prefix=source.split('records=[]')[0]
prefix=prefix.replace("OUT = ROOT / 'reports/audit-20260909'", "OUT = ROOT / 'reports/developpement-20260909'")
prefix=prefix.replace("TARGET = ROOT / 'vectorisation-nos-deniers-20260909/_controle/Consignes pour la vectorisation.docx'", "TARGET = ROOT / 'complement-vectorisation-20260909/Consignes complémentaires avant vectorisation.docx'")
exec(prefix)
records=[]
paragraph('Complément pour la vectorisation',1)
body.append(deepcopy(protos[2]))
paragraph('À : la session qui prépare Nos Deniers',3)
paragraph('De : chantier Nos Deniers',5)
paragraph('Date : 9 septembre 2026',6)
paragraph('Objet : intégrer ce complément avant le calcul des vecteurs',7)
body.append(deepcopy(protos[8]));body.append(deepcopy(protos[9]))
paragraph('Continuer les extractions déjà engagées',10,True)
paragraph('Ce complément précise la qualité des textes et apporte des données nouvelles. Il ne justifie pas de recommencer le corpus entier. Le dossier initial est conservé intact. Intégrer les règles ci-dessous dans la préparation, puis vérifier leur application avant d’exporter le paquet destiné au calcul BGE-M3. Aucun lancement GPU ni arrêt de traitement n’est effectué par ce document.')
paragraph('[Ouvrir le dossier complémentaire](C:/Users/Jean-Christophe/Documents/ChatGPT/docker/budget/complement-vectorisation-20260909). Lire _controle/manifest.json et _controle/qualite-sources.json. Les fichiers de contrôle et cette notice ne sont pas à vectoriser.')
paragraph('Distinguer texte retrouvé et chiffre contrôlé',21,True)
paragraph('Une empreinte conforme garantit l’intégrité du fichier exporté, pas la fidélité de ses tableaux. Les 146 exports juridiques SQL et 51 textes reconstruits de la Cour sont identifiés par chemin et SHA dans qualite-sources.json. Cette liste de 197 fichiers définit une précaution de traitement ; elle ne signifie pas que 197 fichiers sont corrompus ou contiennent des chiffres faux.')
paragraph('Conserver ces textes pour la recherche, les explications et leurs citations, avec source_kind dérivé ou reconstruit, table_layout non certifié, numeric_status non validé et allow_automatic_numeric_fact false. Faire suivre ces indicateurs dans les métadonnées des documents, des preuves et des chunks. Ils ne doivent pas devenir automatiquement des faits chiffrés.')
paragraph('Préserver les tableaux originaux',21,True)
paragraph('Pour chaque tableau, conserver l’exercice, l’étape, AE ou CP, l’unité, les en-têtes, les cellules vides, les lignes, les colonnes et les cellules fusionnées. Répéter les en-têtes dans les passages de tableau. Une colonne ou une unité ambiguë reste à vérifier : ne pas compléter par déduction. Un tableau extrait, même depuis un PDF valide, reste une preuve brute tant que ses montants ne sont pas rapprochés.')
paragraph('Utiliser les nouvelles données chiffrées',21,True)
paragraph('Le complément contient une copie cohérente de budget.sqlite : 119 746 observations, dont 3 110 nouvelles lignes de consommé 2021–2022 et 364 lignes de LFI 2026. Cette copie devient la version chiffrée à référencer ; ne pas additionner ses lignes aux 116 272 lignes de l’ancien instantané. Conserver celui-ci comme historique. Les anciennes observations sont reproduites à l’identique, et une reconstruction temporaire a été vérifiée.')
paragraph('Les montants sont stockés en centimes. Les calculs doivent interroger les faits SQL validés, pas additionner des chiffres retrouvés dans les chunks. Conserver les versions, sources et positions de cellule. Les chemins /data sont logiques : les résoudre avec l’inventaire initial et celui du complément. Les 57 sources numériques ne constituent pas une couverture complète de toutes les étapes budgétaires.')
paragraph('Ajouter le premier acte chiffré',21,True)
paragraph('events.sqlite contient 186 lignes AE/CP pour 93 programmes du seul décret d’annulation 2024-124. Les montants absents restent NULL ; le signe −1 est séparé du montant brut. Soixante contrôles portent sur les totaux publiés ou les absences correspondantes. Ce registre ne mesure ni les gels ni toutes les annulations et ne s’ajoute pas aux crédits ouverts annuels.')
paragraph('Le HTML PISTE du décret conserve les colonnes de son annexe ; il est à privilégier pour les tableaux sur l’ancien export aplati du même acte. Garder le JSON original comme preuve, sans double vectorisation. Les HTML et JSON de LFI 2026 déjà présents dans le dossier initial sont recopiés ici pour la provenance : dédupliquer par SHA et conserver leurs relations.')
paragraph('Contrôler avant le calcul des vecteurs',21,True)
paragraph('Vérifier les empreintes du complément, l’application effective des indicateurs de qualité et le rattachement de chaque passage à sa source. Réutiliser les vecteurs Cour existants quand leurs identifiants correspondent. Conserver les paramètres BGE-M3 déjà retenus et les extractions terminées ; ne retraiter que les documents ou métadonnées concernés.')
paragraph('Faire trois essais : distinguer les AE et CP d’une ligne du décret 2024-124 ; conserver une cellule vide sans la convertir en zéro ; retrouver une ligne de LFI 2026 avec sa source. Vérifier enfin que la recherche ne présente pas un texte dérivé comme un tableau numériquement certifié. Signaler les exceptions avant de lancer le calcul payant.')
builder_source=(ROOT/'tools/build_vectorisation_notice_docx.py').read_text(encoding='utf-8')
footer=builder_source[builder_source.index('body.append(sect)'):]
footer=footer.replace("(OUT/'qa-liens/vectorisation-word-controle.json')","(OUT/'qa-word/vectorisation-word-controle.json')")
footer=footer.replace("Nos Deniers dossier de vectorisation","Nos Deniers complément avant vectorisation")
exec(footer)
text='\n\n'.join(''.join(p.itertext()) for p in body.findall('w:p',NS))
(CONTROL/'consignes.txt').write_text(text,encoding='utf-8')
print('Quality rules',len(quality))
