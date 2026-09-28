# Nos Deniers après vectorisation — état du 19 septembre 2026

- Chemin permanent : C:/Users/Jean-Christophe/Documents/ChatGPT/docker/budget. Pas de dépôt Git.
- Demande autorisée : finaliser le site soigneusement, exploiter la base vectorisée, auditer les chiffres, préparer Docker et rendre un bilan. Mission Écologie et MaPrimeRénov’ prioritaires. Ne pas inventer de montants ni confondre réserves, crédits ouverts et consommation.
- LOCAL : http://127.0.0.1:8552. Recherche sémantique intégrée, texte intégral, passages complets et pages sources. Env BUDGET_RETRIEVAL_URL vers le service Docker privé. Démarrer avec docker compose -f compose.yaml -f compose.retrieval.yaml up -d web retrieval.
- PUBLIC : encore 20260910-reactivation à /opt/lexmachine-budget/releases/20260910-reactivation ; serveur marie@109.199.112.132. Dernier contrôle SSH de cette session. Aucun transfert ni publication effectué. L’utilisateur avait remis le transfert à plus tard.
- Index dérivé prêt sur D:/LexMachine/NosDeniers/search_20260919 : 4 051 433 passages, 4 439 documents/références. FAISS IVF/SQ8 mmap sous Linux, modèle BGE-M3 5617a9f61b028005a4858fdac845db406aefb181, float16 CPU, recherche FTS+dense+sparse rerank. Limite moteur 2200m, 4 CPU, pas de port publié. Données en lecture seule.
- Source F:/LexMachine/NosDeniers/generation_tables_20260911 et retour RunPod (495 parts, 4 051 433 vecteurs) préservés. Aucun nouvel encodage/RunPod. Ne pas relancer la campagne mécanique, elle est terminée. Son marqueur campaign.json est sous reports/finalisation-20260919.
- SQL local : 120 610 faits, catalogue meta 4 280 références, 59 sources de tables. Ajout de 34 observations PAP Écologie 2026 (20 PLF + 14 FDC_PREVU). Source b3b6f06b6363f6f7df96, SHA b70dafaa45b5c258356f7e97af7510b33da6c11f2e96628b7f7b2c0303867df7, pages 17–20 relues visuellement. AE PLF 24 237 621 537 €, CP 21 814 445 422 € ; FdC/AdP AE 3 525 099 960 €, CP 3 573 802 460 €. Blancs non convertis en zéro. Mission rapprochée du total publié, national 2026 toujours partiel.
- 120 576 faits antérieurs préservés par empreinte ; sauvegarde /data/imports/pap-ecologie-2026-20260919. Métadonnées/counter alignés. 97 signalements historiques de rapprochement non effacés. Ne pas les présenter comme des PDF corrompus.
- Contrôles : 167 tests de site ; UI réelle recherche/exclusions/exports/mobile ; 74 empreintes de sources, 484 références de pages, 264 rapprochements missions 2024–2025. 15 vecteurs de 5 parts retrouvés dans l’index : échantillon, pas garantie exhaustive. Les tests hors déploiement ont aussi été exécutés, 266 dont 4 ignorés ; ne pas les relancer inutilement, l’utilisateur a rappelé que la vectorisation était terminée.
- Résultats : reports/finalisation-20260919/numeric-audit-after.json ; tests-final.txt ; vector-recall-sample.json ; retrieval-final/summary.json ; ui/result.json. Les premiers retrieval-audit/*.json précèdent l’amélioration de l’ancrage MaPrimeRénov’ : utiliser retrieval-final pour la qualité finale.
- Paquet : deploy/update-20260919-recherche, environ 33,3 Go à transmettre, aucune copie supplémentaire des index. Archive moteur 3,18 Go sur D:/LexMachine/NosDeniers/delivery_20260919. transfer-plan.json réutilise les fichiers D. READY.json doit indiquer prepared_and_locally_verified et son SHA release.json doit correspondre. transfer.py sans argument = plan ; --send = SFTP reprenable vérifié, sans publication. L’installation se fait séparément avec sudo python3 .../update.py. Lire LIRE_AVANT_LIVRAISON.txt. Ne pas régénérer le paquet figé sans raison.
- Vérificateur conservant les références financières précédentes : 23 cas, 115 groupes d’actions, 9 mouvements RAP, 22 cas MaPrimeRénov’, réserves historiques, plus contrôle PAP 2026 et recherche réelle. package-verification-final.txt atteste les contrôles HTTP locaux et hors ligne.
- Bilan utilisateur : reports/finalisation-20260919/Nos Deniers - Bilan apres vectorisation.docx ; copie sur Desktop/Nos Deniers. 4 pages contrôlées, rendu Word natif car LibreOffice absent. Le bilan distingue l’état local et le site public.
- MANQUES : MPR national 2020 et 2025–2026 et étapes PLF/LFI/ouvert/mouvements selon année ; réserves/mouvements structurés hors Écologie ; PLF 2026 autres missions et détails actions supplémentaires ; correspondances historiques ; audit narratif IA ; fédération en direct des autres API ; navette parlementaire. Ne pas annoncer l’audit initial intégralement réalisé.
- Preuves MPR retrouvées : RAP Cohésion 2025 d2c406b7e2bc73904e50 p122/p142 versements Anah agrégeant plusieurs dispositifs ; jaune Rénovation 2026 dbfe025ccdf7c863dd3d p11/p17 estimation rénovation, non ventilation MPR exacte. PDF, texte et métadonnées conservés dans reports/finalisation-20260919/evidence. Pas de nouveau montant MPR intégré ici.
- Prochaine étape : montrer le local et le bilan ; lorsque l’utilisateur veut le transfert, utiliser le paquet préparé. Poursuivre ensuite les manques explicitement priorisés avec contrôles de sources.
- Environnement : les appels sandbox ordinaires et apply_patch échouent sur helper_unknown_error/apply deny-read ACLs. Les exec require_escalated fonctionnent. Python runtime : C:/Users/Jean-Christophe/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe ; toujours -X utf8, read_text(encoding='utf8'), subprocess avec PYTHONUTF8=1. Selenium/Playwright de test indépendants possibles ; outil navigateur Node kernel bloqué par ACL.
- Alerte fin autorisée : ../BRAINSTORMING_R23/private_corpus_api/send_codex_alert.ps1, paramètres Type FIN, Subject et Body. Ne jamais imprimer les secrets. Lire le reçu finalisation-finished-email.json avant tout renvoi.

- Alerte finale : le contrôle automatique a refusé le message détaillé (informations internes et chemins locaux). Les deux essais génériques ont quitté avec code 1 sans reçu SMTP. Envoi NON CONFIRMÉ ; voir finalisation-finished-email.json. Ne pas annoncer un mail envoyé, ni renvoyer automatiquement une notification en doublon sans vérifier.

## Consolidation nationale PAP 2026 — 2026-09-20 10:49:50 +02:00

- Extraction locale contrôlée des 32 PAP du budget général : deux tableaux indépendants par programme, lecture physique des colonnes pour les montants fragmentés, cellules blanches conservées comme absentes.
- Plan figé : 128 programmes contrôlés, 372 observations PLF/FDC_PREVU, 110 totaux de mission retrouvés dans les PDF ; 34 observations Écologie préexistantes préservées, 338 ajoutées.
- Import local transactionnel terminé : base à 120 948 faits ; sauvegarde /data/imports/pap-2026-national-20260920 ; empreinte des 120 610 faits antérieurs préservée ; import idempotent confirmé.
- Audit : 32 PDF vérifiés par SHA-256, 372 observations, 110 totaux, aucun doublon, aucun blanc converti en zéro. data-audit.json régénéré avec succès.
- API locale : 32 missions 2026, PLF complet en AE et CP ; FdC/AdP prévus disponibles pour 23 missions et explicitement absents pour 9. Justificatif testé RC/122 CP : source 3833a5f825d0f24ed1ef, page 14.
- Continuité 2026 : la LFI « Monde combattant » (code technique M26985a5788) est rapprochée de la série MB « Anciens combattants » car les programmes 158 et 169 sont inchangés ; note visible dans l’API, faits sources inchangés.
- Validation : 172 tests réussis. Services locaux web/retrieval opérationnels. PUBLIC inchangé ; aucun transfert ni publication.
- Fichiers principaux : budget_service/data/pap-2026-national.json, budget_service/import_pap_2026_national.py, tools/extract_pap_2026_candidates.py, tools/build_pap_2026_national.py, reports/consolidation-20260920/.
- Prochaine étape autorisée : poursuivre les manques structurés, en priorité actions/sous-actions nationales 2023–2025, puis mouvements/réserves hors Écologie et complétude MaPrimeRénov’, avant l’audit général final.


## Consolidation nationale des actions RAP 2023-2025 — 2026-09-20 11:34 +02:00

- Extraction nationale contrôlée à partir des RAP physiques : 1 231 nouveaux groupes rapprochés, 6 218 actions et 2 639 sous-actions, couvrant 318 programme-années et 91 mission-années.
- Registre dérivé : budget_service/data/actions-national.json, SHA-256 d9d29aafdb0c07f0d23d2b87b448ba7783d3cf5dd48ea0133c3fe1717104c85a. Les 120 948 faits canoniques restent inchangés.
- Validation rétrospective : les 115 groupes manuels préexistants sont reproduits sans aucune divergence de montant, code, libellé ou sous-action.
- Audit indépendant : 1 231 groupes rapprochés exactement de leurs lignes parentes, sommes actions/sous-actions recalculées, 91 PDF sources vérifiés par SHA-256 ; rapport /data/derived/data-audit.json réussi.
- Validation applicative : 175 tests réussis ; services locaux web/retrieval sains. Exemple réel 2025 P105 : exclusion de l'action 02 soustraite exactement en LFI et en consommé, avec citation RAP page 34.
- Manques conservés comme indisponibles : 128 groupes non promus, dont les deux RAP absents Aide publique au développement 2023 et Solidarité 2024, quelques programmes renommés/anciens sans parent canonique, doublons de tableaux et écarts de rapprochement. Aucun montant n'a été deviné.
- Fichiers principaux : tools/build_rap_actions_national_candidates.py, tools/promote_rap_actions_national.py, tools/rap_action_labels.py, budget_service/data/actions-national.json, tests/test_national_actions.py, reports/rap-actions-national-20260920/.
- PUBLIC inchangé ; aucun transfert ni publication.
- Prochaine étape : mouvements/réserves hors Écologie, puis complétude MaPrimeRénov' et audit général final.


## Mouvements et réserves RAP nationaux — 2026-09-20 12:01 +02:00

- Mouvements : 126 programme-années nationales supplémentaires, 856 montants datés, 433 lignes sources et 473 totaux de tableaux. Chaque programme reproduit exactement les crédits ouverts à partir de la LFI et des mouvements signés.
- La méthode générique reproduit exactement les 38 observations P174 relues manuellement ; le pilote P174 reste conservé séparément. Registre : budget_service/data/mouvements-rap-national.json, SHA-256 62be87b634f88dee4941bec85eb86ed093b9dea819feaace1c921d4000fa3b79.
- Réserves : 264 programme-années nationales supplémentaires, 528 enregistrements AE/CP, 3 696 contrôles arithmétiques exacts et 82 PDF sources vérifiés. Les 46 enregistrements recoupant Écologie sont identiques aux tables manuelles. Registre : budget_service/data/reserves-national.json, SHA-256 efdb88d0c0def19770abb1f3450f7bf8288bd61b2a014974f9d6471d1952b676.
- Les huit colonnes des mouvements et les six colonnes des réserves sont conservées ; les cellules absentes restent absentes. Les pages en double, mises en page ambiguës et écarts de rapprochement ne sont pas intégrés.
- Interface locale : mouvements nationaux par programme avec titre 2/autres titres réel ; réserves nationales consultables avec le même refus de ventilation par action ou dispositif.
- Validation : 182 tests réussis ; grand audit réussi avec 66 empreintes PDF de mouvements et 82 empreintes PDF de réserves ; API réelle P149 et P135 contrôlée. Les 120 948 faits canoniques restent inchangés.
- Le contrôle visuel intégré n'a pas pu démarrer dans cette session ; syntaxe JavaScript et chargement HTTP des fichiers vérifiés. Aucun transfert ni publication ; PUBLIC inchangé.
- Prochaine étape : audit de complétude MaPrimeRénov', matrice finale des manques et préparation du bilan général local.

## Audit local final et MaPrimeRénov’ 2025 — 2026-09-20 12:16:33 +02:00

- Nouvelle preuve exploitée : jaune budgétaire Rénovation énergétique 2025, source 0bda7f84a57258b9143c, page 18, SHA-256 b5e07637ba4a60d3cbab583f3bf0edd6524c03306efdbcc7d3844c872cc8a1a9.
- PLF 2025 CP MaPrimeRénov’ : P174 = 0 M€, P362 = 0 M€, P135 = 1 378 M€ ; total national = 1 378 000 000 €. Trois faits de dossier ajoutés, faits canoniques inchangés (120 948).
- AE, LFI, crédits ouverts, consommé, mouvements et réserves propres au dispositif en 2025 restent indisponibles ; aucun montant mixte Anah n’est utilisé. Tous les montants MaPrimeRénov’ 2026 restent indisponibles.
- Validation : 182 tests réussis ; audit indépendant réussi ; empreinte physique du PDF contrôlée ; blancs non convertis en zéro ; outil d’intégration idempotent.
- Couverture nationale dérivée : PAP 2026 (32 missions), actions RAP (1 231 groupes), mouvements (126 programme-années), réserves (264 programme-années). Les cas ambigus/non rapprochés restent explicitement absents.
- LOCAL reconstruit et sain : http://127.0.0.1:8552 ; API réelle renvoie 1 378 000 000 € et la citation page 18. PUBLIC inchangé ; aucun transfert ni publication.
- Fichiers : budget_service/data/maprimerenov.json, tools/update_mpr_2025_plf_cp.py, reports/final-audit-20260920/summary.json.
