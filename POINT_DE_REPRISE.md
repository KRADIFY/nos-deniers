# Version publiée et sauvegardée — 16 octobre 2026

- Chemin permanent : D:/ChatGPT/docker/backups/nos-deniers-enligne-20261004/git ; main, KRADIFY/nos-deniers. Commit courant : git log -1 ; reçu GIT-PUSH-VERIFIED.json dans budget/outputs/vectorisation-archives-pap-20261016.
- Cinq PDF officiels PAP ajoutés au catalogue et à la recherche, 90 autres déjà indexés conservés. Les deux sites Budget et Budgetécolo ont été vérifiés.
- Base documentaire SHA 8408a08b88c8d27ed8b5b9737d3580ece9d192edaa1d96e7f1a73a8494ac52fb, 142 079 faits et version financière inchangés. Sauvegarde complète compressée dans proofs/budget.sqlite.gz ; les notices RAP 2019 déjà publiées sont incluses.
- Recherche : 5683 documents / 4996538 passages. Seul le montage du supplément2 utilise la release 20261016-archives-pap-vectorisation ; anciens index conservés. Protocole tableaux et preuves dans proofs/archives-pap-vectorisation-20261016.
- Aucun changement des montants, du moteur budgétaire, du code applicatif, des styles, des démos ou de PLFSS. PDF et index massifs conservés hors Git ; références de restauration dans proofs/VERSION-EN-LIGNE-20261016-ARCHIVES.json.
- Suite : exploiter le balayage 2017–2027 déjà terminé, puis audit financier en Astra Ultra ; pas d'intégration financière automatique à partir de l'index.

## Historique conservé

# Point de reprise — Nos Deniers PLF, 15 octobre 2026

- Chemin permanent : D:/ChatGPT/docker/backups/nos-deniers-enligne-20261004/git ; branche main, remote origin https://github.com/KRADIFY/nos-deniers.git. Contrôle depuis cette racine : `git status --short --branch`, `git log -1 --oneline` et `git ls-remote origin refs/heads/main`.
- Sauvegarde autorisée : « Git en local et en ligne sur KRADIFY la version en ligne ». Commit de référence antérieur sûr : b95714b4214bc0e1fe0de18d116bc0a32c621eca. Le commit courant de sauvegarde du 15 octobre est identifié par `git log -1` et par le reçu final externe D:/ChatGPT/docker/budget/outputs/git-version-en-ligne-20261015/GIT-PUSH-VERIFIED.json.
- Version déjà publiée : lot de 3916 positions annuelles, dont 137 nouveaux faits SQLite et 3779 positions de registres ; 142079 faits au total ; 398 nouveaux fichiers sources. Aucune correction de l'audit général intégrée dans cette sauvegarde.
- Identités : SHA SQLite ef3e0846e52e82577336293de3e2ba12ef307784f1a38406f597af8201680ed5 ; data_version 522b5e8ff1e502ffa3a173fb1552e20651729eee0e1a33c0bbb52c2c90650752 ; image lexmachine-budget:20261015-complements-3916-v2.
- Preuves : proofs/VERSION-EN-LIGNE-20261015.json et proofs/integration-budget-gouv-20261015/. 92 fichiers web comparés par SHA au serveur ; quatre fichiers du lot comparés sur les quatre webs. SQLite compressé actuel dans proofs/budget.sqlite.gz et Compose publié dans proofs/compose.yaml. Reçus antérieurs conservés, aucune modification rétroactive des preuves.
- Restauration : sauvegarde de base H:/Sauvegardes-Nos-Deniers/20261008-version-en-ligne + complément du 13 octobre D:/ChatGPT/docker/backups/sauvegarde-20261013-budget-gouv + archives approved-release.tar.gz et web-image.tar.gz sous budget/outputs/audit-financier-budget-gouv-20261014/reprise-20261015/integration-3916-preview-20261015/publication/. Les index et documents massifs sont hors Git.
- URL locale http://127.0.0.1:8552 ; publique https://budget.lexmachine.net/. Aucun démarrage, reconstruction ou redéploiement n'est requis pour cette sauvegarde. Contrôles sans écriture : GET /readyz et /api/bootstrap, comparaison des empreintes au reçu courant.
- Audit général : terminé dans D:/ChatGPT/docker/budget/outputs/audit-general-nos-deniers-20261015 ; rapport Word sur le Bureau. Moteur testé sans erreur dans les contrôles exécutés ; conflits de sources, couverture, libellés et parcours restent à arbitrer. Pas de certification globale ni de recette visuelle interactive exhaustive.
- Prochaine étape : attendre la décision de Jean-Christophe sur les corrections ciblées ; préserver cette version publiée comme référence. Aucun changement de chiffres, moteur, index, site, Docker ou VPS au titre du commit/push.
