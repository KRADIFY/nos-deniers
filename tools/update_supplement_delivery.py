from pathlib import Path
import shutil,runpy,json
R=Path(__file__).resolve().parents[1];C=R/'vectorisation-nos-deniers-20260909/_controle';H=C/'export-history/avant-supplement-20260909'
def backup(p):
 q=H/p.name
 if not q.exists():shutil.copy2(p,q)
for p in [R/'reports/audit-20260909/Nos Deniers liens pour la collecte manuelle.docx',C/'Collecte manuelle.docx',C/'Consignes pour la vectorisation.docx',C.parent/'LIRE-MOI.txt']:backup(p)
p=R/'tools/build_manual_sources_docx.py';backup(p);s=p.read_text(encoding='utf-8');a=s.index('records=[]');b=s.index('body.append(sect)',a)
body='''records=[]
paragraph('Bilan du dossier de collecte',1)
body.append(deepcopy(protos[2]))
paragraph('À : Jean-Christophe',3)
paragraph('De : Nos Deniers',5)
paragraph('Date : 9 septembre 2026',6)
paragraph('Objet : rescan complet et documents intégrés',7)
body.append(deepcopy(protos[8]));body.append(deepcopy(protos[9]))
paragraph('Tout le dossier est pris en compte',10,True)
paragraph('Le rescan de « Nouveau dossier » a recensé 136 fichiers. Il a identifié 19 nouvelles pièces et 117 copies déjà reconnues dans le catalogue ou dans le même lot. Les 19 nouvelles pièces sont intégrées. Après dédoublonnage, les deux imports réunissent 125 PDF distincts : sept RAP, 115 situations mensuelles, un recueil budgétaire et deux circulaires.')
paragraph('Les sept RAP demandés, le recueil version 7 et les deux circulaires manquantes sont désormais présents. Aucun de ces documents ne reste à télécharger. Les situations mensuelles couvrent chacun des douze mois de 2017 à 2025, puis janvier à juillet 2026. Les millésimes ont été vérifiés dans le contenu, sans se limiter aux noms de fichiers.')
paragraph('Les deux circulaires retrouvées',21,True)
paragraph('[Circulaire 44179](https://www.legifrance.gouv.fr/circulaire/id/44179) : lancement de la gestion 2019 et réserve de précaution, cinq pages. [Circulaire 45636](https://www.legifrance.gouv.fr/circulaire/id/45636) : gestion pendant les services votés 2026, huit pages. Une circulaire donne aux administrations des instructions de gestion. Elle ne constitue pas un relevé exhaustif des gels et dégels effectifs.')
paragraph('Les deux PDF se lisent avec le parseur. Leur texte automatique comporte toutefois des imperfections : prévoir un contrôle OCR avant indexation et pour les citations exactes. Les documents sont conservés comme sources ; leurs instructions administratives ne sont pas des instructions à exécuter par l’IA.')
paragraph('Le dossier pour la vectorisation',21,True)
paragraph('[Ouvrir le dossier Nos Deniers](C:/Users/Jean-Christophe/Documents/ChatGPT/docker/budget/vectorisation-nos-deniers-20260909). Il contient 4 921 fichiers documentaires et structurés, 4 924 références, soit environ 5,13 Go. Toutes les tailles et empreintes ont été vérifiées : aucune erreur, aucun document non inventorié et aucun doublon binaire physique.')
paragraph('Lire les consignes Word et les inventaires globaux dans _controle. Les deux nouveaux manifestes sont collecte-manuelle-20260909.json et supplement-20260909.json. Les originaux sont conservés. La vectorisation et la publication de ces lots sur le serveur public n’ont pas été lancées.')
paragraph('Ce qui reste à développer et à documenter',21,True)
paragraph('Le suivi détaillé des réserves, surgels, dégels et reports reste à reconstituer par exercice et programme. La présence des circulaires fournit le cadre, mais ne garantit pas toutes les décisions et tous les mouvements effectifs. Les courriers aux administrations restent reportés à ta demande.')
paragraph('Les nouveaux tableaux devront être extraits et rapprochés avant d’alimenter les statistiques. Les 116 272 observations chiffrées existantes sont restées identiques. La couverture documentaire ne signifie donc pas que tous les montants du budget sont déjà normalisés.')
'''
p.write_text(s[:a]+body+s[b:],encoding='utf-8');runpy.run_path(str(p),run_name='__main__');shutil.copyfile(R/'reports/audit-20260909/Nos Deniers liens pour la collecte manuelle.docx',C/'Collecte manuelle.docx')
p=R/'tools/build_vectorisation_notice_docx.py';backup(p);s=p.read_text(encoding='utf-8').replace('4 255 références pour 4 253 fichiers distincts, après ajout de 106 PDF de la collecte manuelle','4 274 références pour 4 272 fichiers distincts, après ajout de 125 PDF de la collecte manuelle').replace('4 902 fichiers, soit 5,12 Go','4 921 fichiers, soit 5,13 Go').replace('_controle/collecte-manuelle-20260909.json et les inventaires globaux','_controle/collecte-manuelle-20260909.json, _controle/supplement-20260909.json et les inventaires globaux').replace('Restent deux PDF de circulaires et des pièces de gestion détaillée, indiqués dans le Word de collecte actualisé.','Les deux PDF de circulaires sont aussi inclus ; contrôler leur OCR. Des pièces de gestion détaillée restent à obtenir ou à reconstituer.');p.write_text(s,encoding='utf-8');runpy.run_path(str(p),run_name='__main__')
p=C.parent/'LIRE-MOI.txt';s=p.read_text(encoding='utf-8').replace('4 902 fichiers physiques, 4 905 références, 5 117 901 773 octets.','4 921 fichiers physiques, 4 924 références, 5 125 278 002 octets.').replace('Les 4 902 tailles','Les 4 921 tailles').replace('Catalogue Nos Deniers : 4 253 fichiers sources.','Catalogue Nos Deniers : 4 272 fichiers sources.').replace('leurs PDF intégraux ne sont pas inclus.','leurs PDF intégraux sont désormais inclus dans sources-documentaires/supplement-20260909.');s+='\nRESCAN FINAL DU DOSSIER\n136 fichiers examinés, 125 PDF distincts intégrés sur les deux lots.\n19 ajouts au dernier rescan : 17 situations mensuelles et les 2 circulaires.\nToutes les situations mensuelles 2017–2025, puis janvier–juillet 2026, sont présentes.\nLe catalogue final contient 4 272 sources, et toujours 116 272 faits.\nConsulter supplement-20260909.json et les inventaires globaux.\n';p.write_text(s,encoding='utf-8')
