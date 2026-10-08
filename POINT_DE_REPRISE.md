# Point de reprise — sauvegarde PLF

- Chemin permanent du dépôt : `D:/ChatGPT/docker/backups/nos-deniers-enligne-20261004/git`.
- Capture : version publique du 8 octobre 2026, 141 859 montants ; 4 887 593 passages / 5 275 documents.
- Branche de capture : `sauvegarde-en-ligne-20261008` ; branche active apres sauvegarde : `main` ; tag : `en-ligne-20261008` ; copie distante privée : `KRADIFY/nos-deniers`.
- Dernier commit sûr avant cette capture : `8ebb8bb695419a0e780d2407b09f98e47c0cbcec` (7 octobre).
- Commit courant et état : `git log -1 --oneline` et `git status --short --branch` depuis cette racine.
- Capture vérifiée par SHA-256 dans `proofs/VERSION-EN-LIGNE.json` et `proofs/CAPTURE-VERIFIED-20261008.json`.
- Démarrage : configurations archivées de production dans `proofs/compose.yaml` et `demo/compose.yaml` ; ne pas les lancer avant de restaurer les volumes et les images Docker. Aucun conteneur local créé pour cette sauvegarde.
- Contrôles Git : `git fsck --full` ; contrôle des fichiers et de la base dans les reçus.
- URL locale historique de la démo : `http://127.0.0.1:18896/` ; site public : `https://budget.lexmachine.net/`.
- Données et images séparées : `H:/Sauvegardes-Nos-Deniers/20261008-version-en-ligne`.
- Travail terminé dans la capture : dernières voix, placement des explications, 984 montants et complément documentaire JORF. Aucun déploiement ni changement de production par cette sauvegarde.
- Prochaine étape lors d'une modification future : faire une nouvelle capture et un nouveau commit ; conserver ce tag pour revenir à cette version.
