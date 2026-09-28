# Bilan de collecte — Budget LexMachine

8 septembre 2026. **Le lot récupéré est vérifié ; l’historique national n’est pas encore exhaustif.**

## Fichiers disponibles

767 fichiers sources, 1 592 586 165 octets (environ 1,59 Go) :

- 458 PDF, soit 71 560 pages.
- 259 CSV, totalisant 1 143 471 lignes de données. Ces lignes couvrent des jeux qui se recoupent : ce n’est pas un nombre de dépenses distinctes.
- 46 classeurs : 26 XLSX, 19 XLS et 1 ODS.
- 3 archives : 2 ZIP et 1 7z.
- 1 série XML Insee : IPC annuel, ensemble des ménages, France, base 2025, observations 2017–2025.

Le PDF fourni du programme 205 est inclus à l’identique : 56 pages, SHA-256 d6aa85c270f6d7161db2b6dc4eebda23e28fa9e6ce199f123b3a95b4babc2265.

## Couverture documentaire

| Exercice | RAP de missions/comptes reçus | PAP identifiés reçus | Autres éléments |
|---|---:|---:|---|
| 2017 | 0 rapport complet | 0 | 13 fichiers d’exécution data.gouv, jeux PLF/LFI, texte du PLR |
| 2018–2020 | 0 rapport complet | 0 | Jeux annuels PLF/LFI et données PLR selon catalogue ; textes PLR |
| 2021–2022 | 0 rapport complet | 0 | Jeux PLF/LFI selon catalogue ; textes PLR ; exécution détaillée à compléter |
| 2023 | 47 | 42 | Annexes PLRG et autres documents PLF |
| 2024 | 47 | 48 | Annexes PLRG et autres documents PLF |
| 2025 | 43 + extrait P205 fourni | 48 | Annexes PLRG et autres documents PLF |
| 2026 | Pas de RAP annuel définitif pendant l’exercice | 47 | Annexes PLF, budget vert ; exécution annuelle non définitive |

Les nombres recensent les documents présents dans les listes officielles consultées, sans certifier qu’elles sont complètes. Ils incluent des comptes spéciaux et budgets annexes. Des tableaux d’une année peuvent rappeler l’année précédente ; cela ne remplace pas le RAP complet manquant. La couverture chiffrée exacte par action, étape et exercice sera établie pendant la normalisation.

Manques visibles : RAP Aide publique au développement 2023 ; Solidarité 2024 ; pour 2025, Défense, Écologie, Développement agricole et rural, Investir pour la France de 2030 et Plan de relance ne figuraient pas dans la liste AN. À vérifier et compléter via le catalogue budgétaire. Les anciens RAP et PAP complets restent à récupérer. Voir [les liens et la procédure manuelle](reports/RECUPERATION-MANUELLE-RAP.md).

## Contrôles effectués

Toutes les empreintes SHA-256 ont été recalculées depuis le volume : 767 correspondances, aucun fichier attendu absent, aucune divergence de taille. Les 458 PDF s’ouvrent avec le lecteur PDF, leur nombre de pages a été lu et le texte des premières pages extrait. Les 45 classeurs Excel s’ouvrent. L’ODS est un conteneur valide dont le XML et les feuilles ont été lus. Les ZIP ont passé le contrôle CRC ; le 7z a été intégralement décompressé vers une sortie jetée, sans extraction de fichiers sur disque.

34 premières copies PDF étaient tronquées. Elles ont été retéléchargées ; quatre ont nécessité une reprise depuis Windows. Le collecteur contrôle désormais la taille HTTP annoncée et la présence de la fin du PDF, avec trois tentatives au maximum. Un contrôle indépendant a confirmé la lecture des nouvelles copies. Test ciblé réussi : une réponse HTTP volontairement tronquée est refusée et ne crée aucun fichier final.

68 fichiers temporaires ou copies incomplètes et leurs anciens reçus ont été supprimés, libérant 95 785 993 octets. Chaque copie complète correspondante a été vérifiée avant suppression. Les journaux de diagnostic sont conservés. Deux groupes de fichiers identiques ont été repérés ; les deux provenances restent enregistrées. Le CSV identique publié en PLF puis LFI représente deux étapes budgétaires et ne doit pas entraîner la suppression d’une observation.

Ces contrôles établissent l’intégrité et la lisibilité des fichiers. **Ils ne constituent pas encore une extraction intégrale des tableaux PDF, une réconciliation de tous les montants, ni une indexation vectorielle.**

## Stockage et inventaire

Volume Docker persistant : `lexmachine-budget_budget_data`, monté sous `/data` dans le collecteur. Il est porté par le disque Docker `D:/DockerDesktopData/DockerDesktopWSL/disk/docker_data.vhdx`. Ne pas manipuler directement le VHDX.

- `/data/raw/api/` : exports et pièces du catalogue data.economie.gouv.fr.
- `/data/raw/data-gouv/2017/` : compléments d’exécution 2017.
- `/data/raw/rap/` : RAP et annexes de règlement 2023–2025.
- `/data/raw/plf/` : PAP et annexes 2023–2026.
- `/data/raw/plrg/` : projets de règlement annuels 2017–2025.
- `/data/raw/insee/` : série IPC.
- `/data/manual/2025/` : PDF fourni.
- `/data/metadata/` : manifestes, contrôles, inventaire et provenance.

Inventaire lisible dans [INVENTAIRE-CORPUS.csv](reports/INVENTAIRE-CORPUS.csv). Contrôle détaillé dans [VALIDATION-CORPUS.json](reports/VALIDATION-CORPUS.json).

## Connexions et suite

PISTE/Légifrance a passé un appel réel dans les contrôles précédents. Le MCP Tricoteuses reste en erreur OAuth `invalid_client` avec les identifiants de l’application LexMachine active, y compris avec les deux méthodes d’authentification testées. Les widgets Tricoteuses présents utilisent l’API publique parlement.tricoteuses.fr ; leur fonctionnement ne valide pas cet accès OAuth MCP. Aucun secret partagé n’a été changé.

Les bases documentaires existantes restent en place et en lecture seule ; leur recherche vectorielle n’est pas encore raccordée à Budget. Le corpus PPL attend une méthode de lecture sûre de son journal actif. Aucun journal de base existante n’a été supprimé.

L’organisation fonctionnelle suit le [besoin quotidien de l’assistante parlementaire](BESOINS-PARLEMENTAIRES.md) : PLF/LFI/consommé en priorité, puis mouvements/réserves et recherche dans les rapports. La prochaine étape est la normalisation des chiffres, leur rapprochement avec les tableaux de référence et l’inventaire des cases réellement disponibles par exercice et niveau.

L’interface locale http://127.0.0.1:8552/ reste une page de diagnostic. Les statistiques et l’audit IA ne sont pas encore développés. Le domaine budget.lexmachine.net reste à publier : accès DNS et privilèges Docker du serveur à résoudre. Présentation, logo et autres applications inchangés. Aucune alerte mail demandée pendant cette phase : utilisateur présent à l’écran.
