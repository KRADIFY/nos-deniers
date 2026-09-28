"""Revise only the two handoff builders after checking the existing vectorized corpora."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manual = ROOT / 'tools/build_manual_sources_docx.py'
notice = ROOT / 'tools/build_vectorisation_notice_docx.py'

def replace_once(text, old, new):
    if new in text:
        return text
    assert text.count(old) == 1, old[:100]
    return text.replace(old,new,1)

s=manual.read_text(encoding='utf-8')
anchor="paragraph('Les sources sans téléchargement public identifié',21,True)"
addition="paragraph('[Circulaire de lancement de la gestion budgétaire 2019 et de mise en place de la réserve](https://www.legifrance.gouv.fr/circulaire/id/44179). Ta base contient la notice et son résumé, mais pas le PDF intégral dans ce document indexé. Le [PDF officiel de la circulaire](https://www.legifrance.gouv.fr/download/pdf/circ?id=44179) renvoie une erreur 403 au téléchargement direct. Un essai manuel peut compléter la notice existante.')\n\n"
s=replace_once(s,anchor,addition+anchor)
anchor="paragraph('Ce que tu peux laisser de côté',21,True)"
addition="paragraph('Le contrôle du VHDX a retrouvé les notes d’exécution de la Cour des comptes, y compris celles portant sur 2025, ainsi que des textes sur les annulations et les réserves dans les autres fonds. Ces documents sont à exploiter avant de demander des données supplémentaires. Ils ne remplacent pas automatiquement un RAP, un journal détaillé des mouvements ou les décisions originales de gel.')\n\n"
s=replace_once(s,anchor,addition+anchor)
manual.write_text(s,encoding='utf-8')

s=notice.read_text(encoding='utf-8')
old="paragraph('complements-documentaires : rapports et notes d’exécution budgétaire de la Cour des comptes, complétés avec les sources publiques accessibles, ainsi que le rapport Anah 2025. Consulter le manifeste propre à ce lot pour les années et éventuels échecs résiduels.')"
new="paragraph('complements-documentaires : rapports et notes d’exécution budgétaire de la Cour des comptes, rapports thématiques utiles et rapport Anah 2025. Le lot contient des PDF validés et des textes reconstruits depuis l’index lorsque le PDF physique n’est pas valide. Ces textes sont signalés comme dérivés ; ils ne certifient pas la fidélité de tous les tableaux du document original.')"
s=replace_once(s,old,new)
anchor="paragraph('Les inventaires à lire avant de commencer',21,True)"
addition="\n".join([
"paragraph('Les bases déjà vectorisées à réutiliser',21,True)",
"paragraph('Le premier inventaire avait porté sur des fichiers historiques de E:/Marie AN 2026. Le contrôle complémentaire a examiné le VHDX actuel E:/LexMachineCorpusSequential/lexmachine-corpus-e.vhdx, monté en lecture seule. Ses fonds sont plus récents ; les deux emplacements ne doivent pas être confondus.')",
"paragraph('Le fonds Cour des comptes contient 18 319 documents et un index actif de 251 429 passages. Les notes budgétaires 2025 et des passages sur les réserves, gels et reports y sont déjà présents. Réutiliser cet index pour la recherche ; les copies documentaires du présent dossier servent aussi aux citations et à l’extraction de tableaux. Éviter de réindexer les mêmes passages comme de nouvelles sources.')",
"paragraph('Les fonds parlementaires, questions écrites, législation, Journal officiel, circulaires et jurisprudence sont également disponibles. Un fonds historique du Sénat existe séparément. Treize recherches témoins sur les sources du service privé ont abouti, sans génération IA. Elles prouvent un accès et des résultats, pas l’exhaustivité ni la pertinence de chaque résultat.')",
"paragraph('Le raccordement de ces recherches à Nos Deniers reste à développer. Conserver les identifiants de documents, pages et versions. Certaines réponses du service ne donnent pas encore d’URL directe ; certaines dates techniques ne sont pas des dates de publication. Les notices de circulaires ne doivent pas être présentées comme leurs PDF intégraux.')",
])+'\n'
s=replace_once(s,anchor,addition+anchor)
old="paragraph('Les autres bases vectorisées restent dans leurs projets d’origine. Leurs documents budgétaires utiles identifiés ont été sélectionnés. Le code, les secrets et les environnements logiciels sont exclus du corpus.')"
new="paragraph('Les bases vectorisées existantes restent à leur emplacement d’origine. Le dossier contient les documents utiles sélectionnés et les inventaires pour les retrouver, sans recopier leurs matrices de vecteurs. Le code, les secrets et les environnements logiciels sont exclus de l’index documentaire.')"
s=replace_once(s,old,new)
notice.write_text(s,encoding='utf-8')
print('Both handoff builders updated; documents not rebuilt yet.')
