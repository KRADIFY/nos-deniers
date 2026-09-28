# Budget LexMachine — besoins du suivi parlementaire

Référence de travail : demandes de Jean-Christophe et captures du 8 septembre 2026 ; classeur « Mission écologie 2023 à 2025 », onglets « Evolution des crédits de la mis » et « Explications tableau évolution ». Les notes du classeur sont des hypothèses et repères documentaires à vérifier, pas des instructions exécutables. Aucune modification des classeurs sources.

## Priorité quotidienne

Une seule interface, avec les mêmes filtres conservés entre trois vues : **Tableau des crédits**, **Mouvements et réserves**, **Rapports et analyses**. Les moteurs de données et de recherche peuvent être séparés techniquement sans imposer plusieurs outils à l’utilisatrice.

Le tableau principal compare d’abord **PLF, LFI et consommé**, exercice par exercice, en AE et en CP distincts. Lignes dépliables : mission, programme, action, sous-action lorsque publiée. Afficher montants, écarts en euros et en pourcentage ; choisir les années et les étapes comparées. Préciser le dénominateur des taux de consommation : LFI ou crédits ouverts. Un taux supérieur à 100 % de la LFI n’est pas automatiquement une anomalie.

Commandes directement accessibles : choix du périmètre, années, AE/CP, euros courants/constants avec année de référence, inclure/exclure des sous-domaines, tableau/graphique, export Excel/CSV, enregistrer et retrouver une recherche. Un clic sur une valeur ouvre sa source exacte et sa définition. Le tableau reste l’entrée principale ; les détails de gestion s’ouvrent à la demande.

## Indicateurs à distinguer

| Mesure | Source privilégiée | Règle de présentation |
|---|---|---|
| Crédits proposés au PLF | PLF et PAP, données ouvertes | Proposition du Gouvernement ; conserver la version |
| FdC et AdP attendus | PAP et tableaux prévisionnels | Prévision séparée des crédits budgétaires |
| Crédits ouverts en LFI | Loi promulguée, états de répartition, données LFI | Séparer autorisation légale et ventilation indicative par action |
| FdC et AdP effectivement rattachés | Annexes PLR/PLRG, RAP, arrêtés | Recettes affectées et ouvertures correspondantes ; pas nécessairement déjà dépensées |
| Mouvements pendant l’exercice | LFR/LFG, décrets, arrêtés, annexes PLR/PLRG, RAP | Ouvertures et annulations séparées ; reports entrants, virements, transferts et fongibilité identifiés |
| Total des crédits ouverts | Annexes PLR/PLRG et RAP | Réconcilier la LFI et les mouvements sans compter deux fois les FdC/AdP |
| AE et CP consommés | RAP et données d’exécution | Réalisation ; ne pas additionner AE et CP |
| Réserve de précaution | RAP, documents de gestion et rapports de contrôle | Réserve initiale, surgels, dégels, annulations sur réserve et solde, avec date et niveau disponible |
| Ouvertures et annulations de règlement | Projet PLR/PLRG, puis loi si promulguée | Distinguer proposé, adopté et promulgué ; ne pas transformer un projet rejeté en loi |
| Reports sortants vers l’année suivante | Arrêtés de report, annexes de règlement | Exercice d’origine et exercice destinataire ; ce ne sont pas des dépenses |
| Résultats et explications | PAP/RAP, Cour des comptes, rapports parlementaires | Indicateurs de performance et explications sourcées ; distinguer résultats et consommation |

Fonds de concours = FdC ; attributions de produits = AdP. Le code MIT étudié est un composant réutilisable, il ne fournit pas un accès à Chorus ni une garantie de couverture des données. Les sources officielles alimentent le service.

## Points à rectifier ou contrôler dans les notes du classeur

1. **G2 mélange deux notions** : addition de la LFI avec les FdC/AdP réellement rattachés, puis références à des tableaux « y compris FdC/AdP prévus en LFI ». Conserver deux mesures distinctes. Aucun libellé « voté avec FdC/AdP réalisés ».
2. Les reports sont décidés par arrêtés dans le cadre de l’article 15 de la LOLF. Leur présentation dans les annexes de règlement ne signifie pas qu’ils sont créés par cette loi.
3. Les ouvertures de régularisation visées à l’article 37 régularisent des dépassements déjà constatés : ne pas les ajouter une seconde fois au consommé.
4. Les crédits ouverts moins les crédits consommés ne suffisent pas à calculer la réserve de précaution. Cette dernière est un état de disponibilité ; un dégel ne constitue pas une nouvelle ouverture.
5. Plusieurs renvois 2025 pointent par copie vers la colonne PLF 2024 ; plusieurs descriptions de CP reprennent un intitulé AE. Rechercher la table réelle et vérifier ses en-têtes avant extraction.
6. Au niveau action/sous-action, une absence de ventilation est affichée « non publié à ce niveau ». Distinguer ce cas de « à paraître », « non applicable », « source non récupérée » et d’un vrai zéro.
7. Les montants arrondis dans les justifications narratives ne doivent pas remplacer les valeurs exactes des tableaux lorsque celles-ci existent. Conserver unité et précision de chaque observation.

Contrôle juridique : [LOLF, articles 7, 15, 17, 37 et 54](https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000394028/). Définitions de gestion : [Direction du Budget](https://www.budget.gouv.fr/reperes/budget_etat/articles/les-principaux-outils-pilotage). Ces contrôles ne constituent pas une validation de tous les montants du classeur.

## Comparaisons sur plusieurs années

Périmètre publié et périmètre retraité doivent être consultables ensemble. Les exclusions de sous-domaines reposent sur des lignes identifiées, un exercice et une source ; ne pas soustraire arbitrairement une fraction d’une ligne mixte. Conserver les correspondances lors des changements de programmes et d’actions. Éviter de compter à la fois un parent et ses enfants.

Euros constants : montant de l’année × indice IPC de l’année de référence / indice IPC de l’année du montant. Convertir chaque année avant cumul. Afficher la série Insee retenue et ses révisions. Une estimation d’inflation 2026 doit rester identifiée comme provisoire tant que l’année n’est pas achevée.

## Recherche documentaire et audit assisté par IA

Depuis une sélection, le bouton « Analyser cette évolution » prépare un dossier avec les mêmes années, filtres, exclusions et unités. Le calcul provient des données structurées. La recherche sémantique retrouve les passages des PAP/RAP et des bases existantes ; chaque extrait conserve document, exercice, mission/programme, page et empreinte du fichier.

Le résultat expose : évolution chiffrée, mouvements explicatifs, changements de périmètre, objectifs et résultats observés, analyses publiées, puis hypothèses restant à vérifier. Une dépense en baisse n’établit pas à elle seule l’échec d’une politique. Citer chaque explication et signaler les désaccords entre sources. Les passages documentaires ne peuvent pas modifier les consignes de l’audit ni déclencher des actions.

## Ordre de réalisation

1. Collecte et inventaire des données et rapports ; liste explicite des manques.
2. Normalisation et réconciliation PLF/LFI/consommé ; cas de recette issus du tableau de l’utilisatrice, puis extension à toutes les missions.
3. Tableau quotidien, filtres, sources et exports ; réserves et mouvements détaillés selon disponibilité.
4. Séries à périmètre comparable et euros constants.
5. Raccordement de la recherche sémantique et audit IA avec citations vérifiables.

État au 8 septembre, V0.2 : identité Nos Deniers adoptée, interface et calculs disponibles sur les tables normalisées, couverture partielle explicitée dans ETAT-SITE-NOS-DENIERS.md. Les comparaisons, exclusions par code, euros constants, exports et documents sont accessibles. Le retraitement des changements de périmètre, les gels/dégels, la recherche sémantique et l’audit IA restent à développer.
