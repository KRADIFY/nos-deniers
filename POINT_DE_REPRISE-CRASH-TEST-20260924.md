# État du 24 septembre 2026

- Projet permanent : D:\ChatGPT\docker\budget ; pas de dépôt Git, donc branche/commit sans objet.
- Site local : http://127.0.0.1:8552 ; application active testée en lecture seule, sans reconstruction ni publication.
- Démarrage usuel du service existant : docker compose up -d --no-deps web (Docker requis). Ne pas relancer les autres applications.
- Demande traitée : crash test de solidité ET contrôle des chiffres affichés.
- Lanceur final : tools\LANCER-CRASH-TEST.cmd ; déjà exécuté, aucune relance nécessaire maintenant.
- Résultat : 586 scénarios réussis, 0 échec restant. 122 970 faits, 80 129 cellules, 722 565 conversions d'inflation, 13 353 affichages de montants. API, CSV/XLSX, graphiques, filtres, exclusions, états asynchrones et parcours navigateur contrôlés.
- Charge locale jusqu'à 4 clients : résultats stables ; maximum observé 8,76 s. Ne pas en déduire une capacité de production.
- 16 groupes d'actions soumis à revue, 158 cellules bloquées ; 95 signalements de source conservés. Pas de nouvelle certification humaine de chaque document, ni de preuve d'exhaustivité des sources publiques.
- Trois attentes de test obsolètes corrigées (HTTP 400 pour identifiant invalide, fixture de mouvement sans kind TOTAL, boutons d'explication désormais généraux). Corrections de tests uniquement. Versions précédentes et premier rapport conservés sous reports/crash-test-site-20260924/initial-campaign et test-fixtures-before-update.
- Reprise testée : seuls les checkpoints numériques passent à docker exec, évitant WinError 206. Relance identique en trois secondes, sans répéter les contrôles terminés. Les 581 succès précédents restent horodatés ; trois contrôles ont été rejoués et deux ajoutés.
- Rapports : reports/crash-test-site-20260924/rapport.html, report.json, et Nos Deniers Controle de solidite et des chiffres.docx (2 pages rendues et inspectées).
- Identités figées : SQL, assets, image Docker et scripts de test. Après modification, utiliser un nouveau --output ; ne pas effacer les anciens rapports.
- Dernière décision utilisateur : arrêter les recherches pour cette livraison et conserver les indisponibilités documentées. Le complément de vectorisation viendra après ; aucune nouvelle recherche ou dépense RunPod à lancer sur cette seule décision.
- La base vectorisée principale reste disponible. Son complément préparé n'est pas requis pour les tableaux et calculs.
- Étape suivante : préparer la livraison de la version locale contrôlée selon le processus existant, puis contrôles après activation. Aucun déploiement public effectué pendant cette campagne.
- Seuls les scripts/tests/rapports/points de reprise ont changé ; code, présentation et données du site inchangés.
