# Nos Deniers : corrections vérifiées et livraison préparée

État final du 23 septembre 2026. Chemin permanent : D:/ChatGPT/docker/budget, hors Git.
Version : 20260923-corrections-audit. Autorisation : corrections auditées en autonomie ; seuil automatique maximal 10 EUR. Aucun transfert ni activation publique.

## État local réellement actif
- URL : http://127.0.0.1:8552/ ; web et recherche contrôlés.
- Base : 122 747 faits, 4 289 sources SQL, 4 300 sources au catalogue, 186 événements.
- SHA base : 88a132bd77a0868fbeb5f59c8147d827c2eeb25da2f5c562f1967bfd6bcaa931.
- SHA certificat : 3309dc4455a49c418d848cdef80e1d11930958ed26a7072a6dc825359e1d7c93.
- Image web lexmachine-budget:20260923-corrections-audit : sha256:124479f830c34d92f24646eaaed488e629be9cd1fb975b5313bbc55000c726ac.
- Image recherche lexmachine-budget-retrieval:20260923-expanded : sha256:b359369bee2225071130b3aa116f27638408e709fa2856c94e4c4320fcabe847.
- Recherche : 4 054 212 passages, 4 455 documents, dont 2 779 passages supplémentaires / 16 documents. Principal conservé sans recalcul.

## Corrections et preuves
- Mouvements 2017–2022 : 852 programmes-années uniques = 830 détaillés rapprochés + 18 partiels + 4 annuels. Réserves : 1 847 observations contrôlées.
- BG : 390 lignes rétablies, 899 catégories corrigées, 36 560 cellules relues. Annulations de réserve intégrées avec leur signe.
- Excel : 255 valeurs au centime corrigées, 67 sous-actions ajoutées ; adresses réelles de cellules accessibles.
- 12 corrections P200/P833 2023, ajout T2 P146/2024 AE de 461 EUR, 366 références annuelles historiques ajoutées. Rejeu total : 785 insertions et 12 remplacements depuis le prédécesseur, idempotent.
- 93 écarts d’identité ouverts restants <= 1 EUR. Les omissions ne sont jamais couvertes par la tolérance. 18 groupes d’actions en revue, détail non soustractible ; totaux parents conservés.
- Rapprochement 264 missions, 958 contrôles physiques des sources. Certificat lié à la base et aux fichiers métier exacts.
- 403 tests hôte ; Docker 287 réussis / 3 tests de préparation ignorés ; 24 tests installateur, 4 tests contrat, 17 parcours navigateur ; 32 recherches et 16 téléchargements vérifiés.
- Recette finale hors réseau UID10001 et HTTP réussie. Reçu : reports/corrections-final-staging-20260923/release-verification-receipt.json.

## Livraison et rapport
- Paquet figé : deploy/update-20260923-corrections-audit/READY.json.
- SHA release.json : e32aed8ade9b105d2a30671dbfdb405a9e782146fa29412370cc302fad894701.
- 18 fichiers, 33,57 Go avec recherche ; les gros index restent référencés à leur emplacement. Ne pas recalculer ni réexporter sans changement justifié.
- Word sur le Bureau : C:/Users/Jean-Christophe/Desktop/Nos Deniers - Corrections et livraison du 23 septembre 2026.docx.
- SHA Word : 4b4e9cb8a0538d72ee3bdee11ad820f813d749c8e2d6e6339decdbe4b5224391 ; 7 pages rendues et inspectées ; reçu : reports/corrections-final-staging-20260923/DELIVERY-RECEIPT.json.
- Audit initial conservé. Charte graphique et logo conservés. Les informations périmées sont archivées dans reports/corrections-final-staging-20260923/checkpoint-before-final-delivery.md.

## Limites à conserver visibles
- 18 groupes d’actions (16 AE, 2 CP), 18 rapprochements annuels BA partiels, 92 PDF sans récapitulation détectée : ne pas présenter ces derniers comme définitivement absents ni comme intégralement investigués.
- MaPrimeRénov’ : plusieurs étapes nationales restent non isolées, surtout 2025–2026 ; gels et mouvements du dispositif non séparables automatiquement.
- Réserves récentes : 35 exemptions, 6 sans crédits, 5 partielles, 2 non résolues. Les 22 soldes nets annuels nuls ne prouvent pas des mouvements bruts nuls.
- Analyse IA rédigée, indicateurs de performance, retraitement national complet à périmètre constant, synchronisation de comptes : développements distincts non livrés.
- Reconstitution depuis zéro, sauvegarde hors machine, audit de sécurité et charge multi-utilisateurs non annoncés comme réalisés.

## Prochaine étape : publication par l’utilisateur
Le site public reste à sa version antérieure. Aucun envoi automatique après ce point.
Dans le dossier du paquet : C:/Python314/python.exe transfer.py --send
Puis sur le serveur : sudo python3 /home/marie/nos-deniers-update-20260923-corrections-audit/update.py
Transfert reprenable ; installateur conserve l’ancienne version et vérifie les ressources, les signatures et les services. Prévoir 30 Gio libres après transfert et 5 Gio de mémoire disponible.

## Commandes locales de reprise
Ne pas redémarrer les services sans nécessité. Démarrage : docker compose -f compose.yaml -f compose.retrieval.yaml up -d --no-deps web retrieval
Tests : C:/Python314/python.exe -m unittest discover -s tests (PYTHONPATH=D:/ChatGPT/docker/budget/.runtime/python-libs pour les classeurs).
Anciennes données conservées dans /data/derived/backups/audit-20260923-before et audit-20260923-before-historical. Les ACL de cet environnement nécessitent exec escaladé ; cela ne justifie pas de réparer Docker ou Codex.
