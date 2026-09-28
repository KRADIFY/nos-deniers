# Recherches complémentaires terminées

Dossier permanent : D:/ChatGPT/docker/budget. Pas de dépôt Git.
Recherche du 23 septembre, validation locale du 24 septembre 2026.
URL : http://127.0.0.1:8552/

## Version locale
- Image : lexmachine-budget:20260923-mysteres (alias 0.3), SHA 7215737cdc50c331ec73c0b4c661d1cd30f83a497c872eb7b56e78a9949ebe89.
- Base : 122 970 faits, 4 291 sources SQL, 4 303 sources au catalogue. SHA 6a096bb731a751accfdd55bb1b1a73938e817ad5346129994380a6e51b4c93f1.
- Certificat : SHA db9c1e169590f3203893c1362d218611ceac334f089053439875f5998980f5a7 ; 1 055 sources contrôlées.
- Sauvegarde : /data/derived/backup-mysteries-20260923-before.
- Index de recherche inchangé : 4 054 212 passages / 4 455 documents. Trois nouvelles pièces accessibles dans les justificatifs et la bibliothèque ; pas encore ajoutées à l’index vectoriel.
- Aucun changement sur le serveur public. Le paquet READY complements-finaux du 23 septembre concerne la version précédente. Aucun nouveau paquet de publication préparé pour ce lot.

## Résultats
- Neuf cellules historiques résolues : huit zéros publiés et une reconstruction exacte (P869 2018 CP ouverts). Les 122 961 anciens faits et les totaux indépendants sont conservés.
- P224 2023 AE : action 07 reconstituée à 803 056 563,70 €, avec trois sources. Parent inchangé. Seize groupes d’actions et les sous-actions P169/09 restent en revue.
- P370 2025 : exemption permanente prouvée par la circulaire 6379/SG, sans flux nul inventé. Réserves : un cas non résolu (P367 2023), cinq partiels.
- MaPrimeRénov’ : ajout P174 2021 OUVERT CP 740 M€ ; explication P362 2022 (818 + 47,2 + 5 = 870,2 M€). Six observations mixtes P135 2024 retirées des montants du seul dispositif et conservées en contexte Anah. Soixante-cinq observations MPR actives. P174 Écologie inchangé.
- MaPrimeRénov’ 2025–2026 : complément financé par une subvention Anah dont les proportions ne sont pas définies dans les sources examinées.

## Contrôles
466 tests du projet réussis ; 350 tests Docker réussis et trois tests de préparation sautés. Cent requêtes HTTP, 19 fichiers cités et leurs empreintes, deux CSV et deux XLSX vérifiés. Rejeu borné de 323 sources réussi. Les 14 fichiers de présentation sont identiques.
L’outil Browser échoue sur les ACL avant navigation : aucun nouveau contrôle visuel du site.
Dossier consolidé : reports/mysteries-final-20260923. Reçus et Word dans ce dossier.
Preuves par sujet : reports/mysteries-actions-20260923, mysteries-historical-20260923, mysteries-reserves-20260923 et mysteries-mpr-20260923.

## Commandes
Démarrage : docker compose -f compose.yaml -f compose.retrieval.yaml up -d --no-deps web
Tests PowerShell : définir $env:PYTHONPATH sur .runtime/python-libs puis C:/Python314/python.exe -m unittest discover -s tests
Recette HTTP : C:/Python314/python.exe reports/mysteries-final-20260923/verify_http.py
Ne pas rejouer prepare.py ou activate_local.py : lot déjà intégré et sauvegardé.

## Suite
Bilan Word final remis sur le Bureau : Nos Deniers - Bilan des recherches complémentaires du 24 septembre 2026.docx. Préparer un nouveau paquet de publication seulement lors de la prochaine demande de livraison. Les limites ne démontrent pas l’inexistence de données internes. Tricoteuses search_recipes renvoie 401 (clé Typesense) ; LexMachine et les publications officielles ont permis les recherches.
