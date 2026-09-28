# Nos Deniers livraison actions chronologie et retouches visuelles

État prioritaire : lire POINT_DE_REPRISE-MPR-20260910.md. Correction MPR 2020/2025 et justificatifs PUBLIÉS après activation utilisateur ; contrôles HTTPS figés et SSH indépendants réussis. PUBLIC : mpr-perimetres ; ancienne version actions-chronologie conservée. Les états ci-dessous sont antérieurs.

État réel au 10 septembre 2026, publication confirmée après activation par l’utilisateur. Contrôle HTTPS figé et lecture SSH indépendants réussis. Reçu deploy/update-20260910-actions-chronologie/PUBLIC-VERIFIED.json.

- Chemin permanent : C:/Users/Jean-Christophe/Documents/ChatGPT/docker/budget. Ni ce dossier ni son parent ne sont un dépôt Git ; branche et dernier commit non applicables. Aucun travail utilisateur supprimé.
- PUBLIC vérifié : https://budget.lexmachine.net, release 20260910-actions-chronologie. Ancienne release ecologie-actions conservée et rollback.json vérifié.
- LOCAL : http://127.0.0.1:8552, image lexmachine-budget:0.3 ; conteneur lexmachine-budget-web-1. Démarrage : docker compose up -d --no-deps web. Reconstruction : docker compose build web.
- Livraison FIGÉE et PUBLIÉE : deploy/update-20260910-actions-chronologie ; serveur /home/marie/nos-deniers-update-20260910-actions-chronologie. Ne pas écraser ce paquet. Neuf empreintes vérifiées, environ 48 Mo. Activation effectuée par l’utilisateur ; aucun sudo exécuté par cette tâche.
- Installateur déjà exécuté : sudo python3 /home/marie/nos-deniers-update-20260910-actions-chronologie/update.py. Ne pas le relancer. Retour arrière : /opt/lexmachine-budget/releases/20260910-ecologie-actions, indiqué dans rollback.json.

## Contenu de la livraison

1 020 observations LFI/consommé AE/CP Écologie 2023–2025 : 780 actions et 240 sous-actions, 115 groupes pour 11 programmes selon les années. Parents multi-titres préservés, exclusions signées et sous-actions imbriquées ; aucun double comptage. P355 appartient à TA seulement jusqu’en 2023 ; son rattachement ultérieur EB n’est pas incorporé à TA. P203 EXEC AE2023 reste indisponible au détail à cause d’un écart RAP/CSV de 6 euros.

38 montants de mouvements P174 dans les RAP 2023–2025, 20 preuves à huit colonnes, 122 cellules vides préservées, 19 totaux et 30 rapprochements. API /api/rap-movements, export JSON et panneau dans Mouvements et réserves. Dates de signature ou mois d’origine ; deux liens vers l’acte existant, sans addition des registres. Les données fines/MPR non ventilées restent indisponibles. LEGIS est désormais libellé « Ajustements nets de crédits » car les colonnes sources contiennent parfois aussi des décrets.

Les neuf retouches du Word C:/Users/Jean-Christophe/Desktop/1.docx sont intégrées : pied de page avec les cinq liens centraux LexMachine vérifiés, espacement des choix et de l’export, petits textes agrandis et gris foncés, séparateurs de milliers plus visibles, unité M€ agrandie, flèche insécable avec le dernier mot, troisième exclusion MPR visible et réintégrable. Logo, palette de marque, chiffres canoniques et corpus inchangés. Preuves : reports/retouches-visuelles-20260910/applied.json ; captures du Word dans ce même dossier. Aucune nouvelle inspection visuelle au navigateur, conformément au skill Sites ; contrôles de code/HTML/VM effectués.

## Vérifications et empreintes

- 138 tests Python réussis sur l’image finale. Commande dans l’image avec /data en lecture seule : python -m unittest discover -s tests -q.
- 4 scénarios Node réussis : node tests/rap-refresh-state.cjs. Réponses RAP retardées et erreurs invalidées ; export lié à la bonne sélection ; troisième exclusion et réintégration MPR testées sans changer les deux autres exclusions ou les chiffres.
- Recettes HTTP : 271 requêtes / 12 072 assertions pour les actions, 30 requêtes / 1 869 assertions pour les mouvements RAP. Les 17 anciennes sélections publiées restent identiques.
- Paquet figé : verify.py --http http://127.0.0.1:8552 réussi ; 23 sélections, 115 groupes et 9 cas RAP. Image rechargée depuis image.tar et vérifiée hors ligne sur reports/restore-20260910-actions-mpr/data, réseau coupé, données en lecture seule, utilisateur 10001.
- Reçus : VALIDATION-VERIFIED.json et TRANSFER-VERIFIED.json dans le dossier de livraison. Image ID sha256:44b6df14f48120b3103c919e96b8f37dd6b98ab6a5bd9a83fa0a7dd6c25a7d05 ; config 22594a702c6ad806ed76e0292c5ddf7554ac5f6755a16e4486e14f7d457b3414.
- release.json SHA256 : 4128e2e7c903645490be7b6668a85878ce4d252fa3fae8de71232aeb9d7278f2. Version des actions : 673124dd11331c3bed0c27fa7e843a9777ff137b65481c2a90dd741323762d7b. Registre RAP SHA : 3f1005a89848e708c6f99084f0c3eee5e4ff3e9e8de9727db4ccf1687f2df20c ; version API : rap-p174-1e8e6df1db9150ca.
- Faits canoniques inchangés : 120 576 faits, 4 280 sources ; budget.sqlite SHA 29d8132de1fba26094f69965b85f6bd8213e7f87a6063408fdaab481231b34e7. Les 186 événements JORF d’origine sont intacts.

## Suite et limites

Publication confirmée : deployment.json indique published pour actions-chronologie, et le verify.py FIGÉ exécuté contre https://budget.lexmachine.net a réussi. La prochaine livraison devra prendre actions-chronologie comme prédécesseur ; ne pas réactiver ecologie-actions ou actions-mpr. Aucun changement applicatif pendant cette confirmation. L’audit complet reste à terminer : correspondances annuelles, extensions historiques/des mouvements, recherche documentaire et vectorielle, analyses IA. Prochain lot chiffré proposé, non implanté : suivi d’un programme entre missions, témoin P355 TA2020–2023 puis EB2024–2026, en gardant chemins et sources d’origine.

La préparation documentaire externe a été déplacée par une autre session vers D:/LexMachine/NosDeniers/preparation_20260909. Elle tourne après reboot (commande prepare.py --phase index-export, relevé PID12052, à rechercher par commande au prochain passage). E:/Marie AN 2026/. NOS DENIERS/preparation_20260909 est l’ancienne copie historique. readiness.json absent ; progression récente confirmée. Le correctif get_label() a DÉJÀ été appliqué par l’autre session : ne pas réappliquer reports/document-search-20260910/pdf-label-fix.patch. Ne pas modifier le pipeline, ses checkpoints ou sa base active. Reçu en lecture seule : reports/document-search-state-20260910/pipeline-after-reboot.json. Aucun index dans cette livraison, aucun GPU lancé.

ALERTE MAIL DE CETTE LIVRAISON NON ENVOYÉE : l’auto-review a rejeté l’envoi à jc.niquet@gmail.com contenant la nouvelle commande, estimant l’autorisation spécifique du contenu/destinataire insuffisante malgré l’accord antérieur. Aucun contournement ni nouvel essai ; commande remise dans la conversation. Le mail de la livraison précédente ecologie-actions avait été autorisé et envoyé : ne pas confondre les deux états. Informer l’utilisateur du refus ; ne pas annoncer l’alerte envoyée.
