> Mise à jour collecte du 8 septembre 2026 : 767 fichiers vérifiés, dont 458 PDF. Voir [BILAN-COLLECTE.md](BILAN-COLLECTE.md) pour la couverture, les contrôles et les manques. Le présent document conserve le détail des connexions et leur état précédent.

# Budget LexMachine — périmètre, accès et outils

État du 8 septembre 2026. Le service Docker local fonctionne sur http://127.0.0.1:8552/. La page montre les connexions réellement testées ; les tableaux statistiques ne sont pas encore développés. **On peut commencer le développement avec les sources disponibles ; tous les raccordements ne sont pas validés.**

## Couverture 2017–2026

Le périmètre cible couvre toutes les missions de l’État, avec programmes, actions et sous-actions lorsqu’elles sont publiées. Le degré de détail et la stabilité des codes varient selon l’exercice. Les sources repérées ne constituent pas encore une base nationale importée et réconciliée.

| Année | Points d’appui vérifiés dans la recherche | Limite avant statistiques fiables |
|---|---|---|
| 2017 | LFI et ressources PLR repérées ; exécution par mission/ministère | Détail exécuté action/sous-action à qualifier et importer |
| 2018 | API d’exécution structurée : mission, programme, action, sous-action, catégorie | Une ligne témoin lue depuis Docker ; couverture complète à importer |
| 2019 | Fichiers détaillés lus dans l’étude ; contrôle sur trois programmes et treize actions | Échantillon validé, pas tous les programmes |
| 2020 | Rappels RAP rapprochés avec 2019 dans l’étude ; contrôles de sommes | Généraliser les correspondances et contrôles |
| 2021 | Synthèse RAP XLS et sections HTML repérées | Téléchargement, extraction et rapprochement à finaliser |
| 2022 | Archives PLR/RAP repérées | Même travail de qualification et d’import |
| 2023 | Nomenclature et API des crédits accessibles | Anomalie connue dans les champs LFI : ne pas exploiter ces montants sans contrôle du fichier officiel |
| 2024 | Cycle PLF/LFI/LFG/PLRG et annexes repérés ; décret d’annulation lu par PISTE | Import national et rapprochement des mouvements à construire |
| 2025 | API PLF lue, annexe PLRG AE/CP téléchargée, RAP repérés | PDF RAP témoin filtré depuis Docker ; l’annexe PLRG de 33 lignes ne remplace pas l’exécution détaillée |
| 2026 | PLF/PAP et LFI publiés ; PAP Écologie réellement téléchargé via l’Assemblée | Exercice en cours : aucune exécution annuelle définitive à afficher ; préciser la date d’arrêté des observations disponibles |

Références : [LFI 2017](https://data.economie.gouv.fr/explore/dataset/loi-de-finances-initiale-pour-2017-lfi-2017/), [exécution détaillée 2018](https://data.economie.gouv.fr/explore/dataset/projet-de-loi-de-reglement-2019-plr-20190/), [LFI 2023](https://data.economie.gouv.fr/explore/dataset/credits-ae-et-cp-votes-nomenclature-par-destination-et-nature-lfi-2023/), [exercice 2026](https://www.budget.gouv.fr/documentation/documents-budgetaires-lois/exercice-2026). Les preuves et références complémentaires figurent dans le benchmark déjà réalisé, sans nouvelle certification de tous les millésimes.

## Accès constatés

26 sondes : **11 accessibles, 13 partielles, 2 bloquées**. Ces compteurs mélangent tests de fichiers, API et accès aux corpus ; ce ne sont pas 26 bases nationales complètes.

| Source ou outil | Connexion et rôle |
|---|---|
| PISTE / Légifrance | OAuth et lecture réelle du décret d’annulation 2024-124 réussis. Base pour collecter lois, décrets et arrêtés de gestion ; collecte des autres types d’actes à développer. |
| data.economie.gouv.fr | API PLF, nomenclature, exécution, LFI et annexe PLRG accessibles. Import local structuré prévu ; LFI2023 sous réserve de contrôle. |
| PAP / RAP | PAP2026 Écologie reçu en PDF depuis l’Assemblée. RAP2025 témoin sur Budget.gouv filtré par Incapsula : page HTML à la place du PDF. Autres publications officielles à raccorder au cas par cas. |
| Insee | API SDMX accessible, deux observations annuelles reçues. Étendre la série à 2017 et conserver les indices utilisés. |
| Assemblée / Sénat | Catalogues et documentation des amendements accessibles ; rapport public sur les gels effectivement lu. Archives et dossiers à importer. |
| data.gouv.fr | Catalogue API accessible pour trouver les jeux et suivre leurs versions. Ne pas recompter les mêmes données publiées sur plusieurs portails. |
| Corpus LexMachine | Douze fonds configurés, correspondant à plusieurs bases partagées. Onze sondes de lecture réussies ; lecture PPL désormais différée car un journal SQLite hôte est non vide. Les moteurs vectoriels ne sont pas encore raccordés ni validés dans Budget. |
| Tricoteuses MCP | Même secret et protocole que l’instance LexMachine active ; serveur OAuth HTTP401 `invalid_client`. Compte existant, problème technique à résoudre ; aucune absence de droit ou d’abonnement déduite. |
| Code MIT Data-État | Trois dépôts téléchargés et étudiés. Réutilisation de composants à sélectionner ; ni accès Chorus ni base de production fournis par la licence du code. |

Les fonds locaux comprennent AN, Sénat, PPL, PLF, questions écrites, codes/lois, JORF, circulaires, Cour des comptes, jurisprudence, KALI et CNIL. Les derniers seront mobilisés si une question précise le justifie. Les chiffres seront calculés dans une base structurée : la recherche vectorielle servira à retrouver les explications et preuves.

**Gels/dégels :** les RAP, rapports parlementaires et actes publiés apportent des éléments, sans garantir un journal exhaustif par sous-action. Les détails non publiés pourront nécessiter des documents de la Direction du Budget, des ministères/CBCM ou des commissions compétentes. [Exemple public du Sénat](https://www.senat.fr/rap/r25-702/r25-7023.html). Aucun interlocuteur extérieur n’a été contacté. Chorus ne conditionne pas le démarrage.

## Présentation et outils retenus pour le développement

1. **Filtres** : période, mission, programme, action/sous-action, thème, type de budget, titre/catégorie ; choix AE ou CP et étape budgétaire.
2. **Tableau dépliable** : années en colonnes ; total, sous-totaux, écarts en euros et pourcentage, cumul d’années. Valeurs absentes distinctes de zéro et taux non calculable lorsque la base est nulle.
3. **Périmètre personnalisable** : inclure/exclure des postes ou thèmes, enregistrer la sélection, comparer total initial, montant retiré et reste.
4. **Graphiques synchronisés** : courbe d’évolution, barres annuelles, répartition ; toujours les mêmes filtres et définitions que le tableau.
5. **Bouton euros courants / euros constants**, avec année de référence visible et méthode Insee documentée.
6. **Historique des crédits** : proposé, voté, ouvert, gelé/dégelé, annulé, consommé ; reports, virements/transferts et FdC/AdP identifiés comme événements distincts. Ne pas déduire des gels à partir d’une simple sous-consommation.
7. **Sources au clic et exports CSV/Excel** : document, page/table, date, statut du chiffre, calcul et filtres. Ces fonctions restent à développer.

Data-État peut fournir des composants et des idées d’organisation. Ses écrans doivent être adaptés au suivi parlementaire et aux conventions temporelles AE/CP. L’écran local actuel est uniquement le tableau de préparation des connexions.

## Exemple : écologie hors rénovation énergétique

Prévoir deux axes : la nomenclature officielle par exercice et des thèmes transversaux documentés. Un thème peut couvrir plusieurs actions, et une action peut contenir plusieurs thèmes. Les exclusions doivent donc porter sur les lignes financières les plus fines disponibles, avec règles valables par année et sans double compte entre parent et enfant.

L’utilisateur sélectionnera « Mission Écologie », puis « Exclure rénovation énergétique ». L’outil montrera **total de la sélection − lignes de rénovation identifiées = reste**, avec la liste des lignes retirées et les justificatifs. Les thèmes qui se chevauchent seront exclus une seule fois.

Si une enveloppe mélange rénovation et autres dépenses sans ventilation officielle, aucun pourcentage ne sera inventé. L’outil signalera la part non ventilable et qualifiera le résultat d’incomplet. Distinguer « mission Écologie » et « ensemble des dépenses écologiques de l’État », qui ne désignent pas le même périmètre. Ne pas additionner les versements de l’État à un opérateur et les dépenses de celui-ci financées par ces versements.

## Bouton inflation

Conversion prévue : **montant de l’année t × IPC de l’année de référence / IPC de l’année t**. Pour un cumul sur plusieurs années, convertir chaque année avant d’additionner. Même série, même champ et même fréquence pour toute la comparaison ; conserver les données d’origine.

Par défaut proposé : euros constants 2025, dernière année close, avec choix d’une autre année disponible. Une série d’IPC dont la base statistique est 2025 ne dispense pas du calcul par ratio. Pour 2026, pas d’indice annuel définitif avant publication : afficher une méthode provisoire explicitement choisie, ou laisser la conversion annuelle indisponible. L’inflation et les changements de périmètre administratif seront deux corrections distinctes.

## État du sous-site et prochaine étape

Docker local opérationnel, contrôle après redémarrage réussi ; page desktop/mobile vérifiée. Aucun autre site, corpus ou identifiant partagé modifié. Les secrets ne sont pas servis au navigateur.

**budget.lexmachine.net n’est pas encore publié.** Le DNS du sous-domaine et les droits Docker/sudo du serveur restent à obtenir ou retrouver. La connexion SSH marie au serveur existant fonctionne ; les fichiers Nginx/Caddy sont préparés, non installés. Aucun abonnement ajouté, aucun coût RunPod engagé.

On peut commencer par la base des montants, les correspondances annuelles et un tableau de contrôle 2019–2020, puis étendre 2017–2025 et ajouter 2026 avec un statut d’exercice en cours. L’exclusion de thèmes et le bouton inflation font partie des exigences conservées ; ils ne sont pas encore des fonctions opérationnelles.

## Charte et nom

Charte reprise depuis https://lexmachine.net/portail-assets/styles.css : Inter Display, axe optique32, bleu#173a55, encre#08183f, corail#d84b50, contours#e0edf7, fond blanc et panneaux arrondis. Réglages appliqués uniquement au sous-site Budget. Proposition de nom : **Budgétoscope — Les crédits publics à la loupe**, non encore adoptée. L’adresse cible reste budget.lexmachine.net.

Consigne graphique complémentaire : toutes les icônes et tout futur logo doivent reprendre le style du portail LexMachine (dessin au trait, palette, proportions et épaisseur cohérentes). Réutiliser ses éléments existants lorsque possible. Aucun nouveau logo ni nom définitif adopté.
