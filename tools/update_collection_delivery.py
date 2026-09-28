from pathlib import Path
import shutil,runpy
R=Path(__file__).resolve().parents[1];C=R/'vectorisation-nos-deniers-20260909/_controle';H=C/'export-history/avant-collecte-manuelle-20260909'
def backup(p):
    q=H/p.name
    if not q.exists():shutil.copy2(p,q)
manual=R/'reports/audit-20260909/Nos Deniers liens pour la collecte manuelle.docx'
for p in [manual,C/'Collecte manuelle.docx',C/'Consignes pour la vectorisation.docx',C.parent/'LIRE-MOI.txt']:backup(p)
builder=R/'tools/build_manual_sources_docx.py';backup(builder);s=builder.read_text(encoding='utf-8');start=s.index("paragraph('Sources à récupérer',1)");end=s.index('body.append(sect)',start)
content='''records=[]
paragraph('Bilan de la collecte manuelle',1)
body.append(deepcopy(protos[2]))
paragraph('À : Jean-Christophe',3)
paragraph('De : Nos Deniers',5)
paragraph('Date : 9 septembre 2026',6)
paragraph('Objet : documents reçus et dernières pièces à chercher',7)
body.append(deepcopy(protos[8]));body.append(deepcopy(protos[9]))
paragraph('Les documents reçus',10,True)
paragraph('Les 106 PDF de « Nouveau dossier » sont intégrés au catalogue local et au dossier de vectorisation. Le lot comprend les sept RAP précédemment demandés, 98 situations mensuelles et le recueil des règles de comptabilité budgétaire version 7 de septembre 2025. La situation au 28 février 2026 est incluse.')
paragraph('Les RAP reçus couvrent Aide publique au développement 2023 ; Solidarité, insertion et égalité des chances 2024 ; et, pour 2025, Défense, Écologie, Investir France 2030, Plan de relance et Développement agricole et rural. Il est inutile de les télécharger à nouveau.')
paragraph('Le contrôle des 2 596 pages a décodé leurs flux de contenu et extrait le texte des trois premières pages de chaque PDF. Aucun échec ni doublon binaire avec le dossier existant n’a été détecté. Ce contrôle ne certifie pas encore l’extraction de tous les tableaux.')
paragraph('Les deux PDF de circulaires encore à essayer',21,True)
paragraph('Gestion 2019 et mise en place de la réserve : [notice Légifrance 44179](https://www.legifrance.gouv.fr/circulaire/id/44179), puis [téléchargement du PDF](https://www.legifrance.gouv.fr/download/pdf/circ?id=44179). Le précédent téléchargement automatique renvoyait une erreur 403. La notice est déjà conservée ; le PDF intégral reste à récupérer.')
paragraph('Services votés 2026 : [notice Légifrance 45636](https://www.legifrance.gouv.fr/circulaire/id/45636). Utiliser le lien vers le document proposé sur cette page. La notice est conservée ; aucun PDF intégral n’est présent dans ce nouveau lot. L’accès n’a pas été retesté pendant cet import.')
paragraph('Les limites qui restent',21,True)
paragraph('Ces deux circulaires ne suffisent pas à compléter le suivi des gels. Il reste à obtenir ou reconstituer les décisions et séries détaillées de mise en réserve, surgel, dégel et reports, selon les exercices et programmes. Aucun téléchargement public complet de ces séries n’est confirmé. Les courriers aux administrations restent reportés à ta demande.')
paragraph('Les rapports et textes déjà présents dans les bases existantes restent à exploiter. La collecte documentaire ne signifie pas que chaque montant est déjà structuré : les 116 272 observations numériques existantes sont inchangées. Les nouveaux tableaux devront être extraits et rapprochés avant de servir aux statistiques.')
paragraph('Le dossier prêt pour la session suivante',21,True)
paragraph('[Ouvrir le dossier de vectorisation](C:/Users/Jean-Christophe/Documents/ChatGPT/docker/budget/vectorisation-nos-deniers-20260909). Il contient désormais 4 902 fichiers documentaires et structurés, représentant 4 905 références et environ 5,12 Go. Le contrôle global des tailles et empreintes ne relève aucune erreur ni aucun fichier documentaire non inventorié.')
paragraph('Lire « Consignes pour la vectorisation.docx » dans _controle. Les anciens inventaires sont complétés par collecte-manuelle-20260909.json ; les inventaires globaux font foi pour la liste consolidée. La vectorisation et la publication de ce lot sur le serveur public n’ont pas été lancées. Les originaux du Bureau sont conservés.')
'''
s=s[:start]+content+s[end:];builder.write_text(s,encoding='utf-8');runpy.run_path(str(builder),run_name='__main__')
shutil.copyfile(manual,C/'Collecte manuelle.docx')
builder=R/'tools/build_vectorisation_notice_docx.py';backup(builder);s=builder.read_text(encoding='utf-8')
s=s.replace('Le lot principal représente 4 149 références pour 4 147 fichiers distincts.', 'Le catalogue exporté représente désormais 4 255 références pour 4 253 fichiers distincts, après ajout de 106 PDF de la collecte manuelle.')
s=s.replace('Le bilan consolidé vérifie 4 796 fichiers, soit 5,05 Go, sans erreur de taille ou d’empreinte.', 'Lire également _controle/collecte-manuelle-20260909.json et les inventaires globaux. Le bilan consolidé vérifie 4 902 fichiers, soit 5,12 Go, sans erreur de taille ou d’empreinte.')
s=s.replace('Restent les sept RAP du Word de collecte et des pièces de gestion détaillée.', 'Les sept RAP demandés sont désormais inclus. Restent deux PDF de circulaires et des pièces de gestion détaillée, indiqués dans le Word de collecte actualisé.')
builder.write_text(s,encoding='utf-8');runpy.run_path(str(builder),run_name='__main__')
p=C.parent/'LIRE-MOI.txt';s=p.read_text(encoding='utf-8').replace('4 796 fichiers physiques, 4 799 références, 5 053 420 974 octets.', '4 902 fichiers physiques, 4 905 références, 5 117 901 773 octets.').replace('Les 4 796 tailles','Les 4 902 tailles').replace('Catalogue Nos Deniers : 4 147 fichiers sources.', 'Catalogue Nos Deniers : 4 253 fichiers sources.')
s+='\nCOLLECTE MANUELLE DU 9 SEPTEMBRE 2026\n106 PDF ajoutés : 7 RAP, 98 situations mensuelles, 1 recueil budgétaire.\nInventaire complémentaire : _controle/collecte-manuelle-20260909.json.\nLes inventaires globaux réunissent ce lot et les références précédentes.\nbudget.sqlite a été actualisé : 4 253 sources, 116 272 faits inchangés.\nLes instantanés antérieurs dans _controle sont historiques et non à indexer.\n'
p.write_text(s,encoding='utf-8')
