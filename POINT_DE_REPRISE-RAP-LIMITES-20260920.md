# Reprise du lot limites RAP du 20 septembre 2026

Version locale 0.3 activée et vérifiée. Chemin permanent : C:/Users/Jean-Christophe/Documents/ChatGPT/docker/budget. Aucun dépôt Git reconnu : branche et commit sans objet. Aucune publication distante.

## Terminé
- Correction du filtre MaPrimeRénov’ dans les mouvements RAP : le retrait conserve les programmes non porteurs ; le mode « uniquement » filtre aussi les preuves.
- Boutons d’explication pour réserves absentes, écarts imprimés et mouvements non ventilés. Sources, contacts et demande CSV/XLSX adaptée, sans envoi automatique.
- Inventaire de 53 programmes-années concernés par les lacunes ; 48 réserves sans tableau et 22 mouvements sans récapitulation sur les 379 programmes-années audités 2023–2025. Chevauchement entre ces listes.
- P384/2025 : exemption de réserve documentée p.146, affichée Sans objet, sans montant nul inventé. P370/2023 : aucune ouverture documentée p.159 ; P370/2024 : report daté 2025, pas de fausse opération 2024.
- 15 anciens registres JSON inchangés. Aucun montant ajouté ou modifié dans ce lot. 120994 faits canoniques conservés.
- 209 tests Python Docker, 13 contrôles navigateur nouveaux, ancien contrôle navigateur des réserves et 4 contrôles de réponses différées/exclusions réussis. 24 PDF contrôlés physiquement et liens locaux accessibles. Web et recherche sains.

## Comparaison du Word fourni à 20 h 42
Le Word « Nos Deniers - Rendre disponibles les donnees manquantes.docx » décrit l’état de départ. Les 128 groupes / 223 pages / 16 tables candidates ont été retraités dans le lot précédent : aucun rejet d’extraction résiduel dans ces lots. Voir reports/recovery-20260920/integration-summary.json.
- Actions : 1401 groupes nationaux, contre 1231 au départ ; 115 groupes pilotes conservés en plus, donc 1516 groupes au total, 7900 lignes d’actions et 3010 lignes de sous-actions (comptées par exercice, étape et mesure).
- Mouvements : 354 programmes-années nationaux + 3 pilotes P174 = 357 sur 379 audités.
- Réserves : 303 programmes-années nationaux + 28 Écologie = 331 sur 379 audités 2023–2025. En plus : 48 programmes-années Écologie 2017–2022.
- MaPrimeRénov’ : lot précédent +17 observations P174, mais périmètre national complet encore partiel selon années/étapes. Aucune ventilation inventée.
- Restent externes : ventilations de dispositifs, suivi fin et daté de gestion/Chorus, table de correspondance complète 2017–2026. Aucune demande administrative envoyée.

## Fichiers et reprise
- budget_service/rap_quality.py et data/rap-coverage.json : inventaire et explications, jamais sources de faits monétaires.
- Modifiés : reserves.py, rap_movements.py, public/assets/explorer.js, public/explorer.html. Présentation générale, chiffres et autres fonctionnalités préservés.
- Outil reproductible : tools/build_rap_coverage_notes.py ; ne relancer que si l’audit des sources doit évoluer.
- Preuves et sauvegardes : reports/rap-limits-20260920 ; image précédente dans previous-image.txt ; état actif dans delivery-state.json.
- Tests : docker run --rm --network none --read-only --tmpfs /tmp:size=128m,mode=1777 lexmachine-budget:0.3 python -m unittest discover -s tests
- Activer après validation : docker compose -f compose.yaml -f compose.retrieval.yaml up -d --no-deps web
- URL locale : http://127.0.0.1:8552. PUBLIC inchangé. Aucun besoin de relancer la vectorisation.
- Les CJS navigateur nécessitent NODE_PATH du runtime et Chrome local. Tests rap-quality-ui.cjs, reserves-ui.cjs, rap-refresh-state.cjs réussis.

## Suite
L’extraction des candidats du Word est terminée ; distinguer les lacunes documentaires restantes d’un échec d’extraction. Publication sur validation de l’utilisateur ; demandes administratives uniquement sur autorisation explicite d’envoi. Ne pas présenter ces tableaux comme une couverture exhaustive de tout 2017–2026.
