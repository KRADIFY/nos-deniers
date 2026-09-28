# Nos Deniers — état du site au 8 septembre 2026

Version locale 0.2 : http://127.0.0.1:8552/. Le sous-domaine public budget.lexmachine.net reste à publier.

L’application utilise le logo SVG fourni, la police Inter Display locale et les couleurs de LexMachine. Seul le service Budget a été modifié et redémarré.

## Fonctions utilisables

- Tableau PLF / LFI / consommé, avec choix AE ou CP et années 2017 à 2026. Les années sans données restent visibles et indisponibles.
- Navigation mission → programme → action → sous-action, selon la finesse effective des sources. Recherche dans les lignes du niveau courant.
- Vue d’une étape sur plusieurs années, écarts en euros et en pourcentage, cumuls lorsque chaque année est disponible.
- Exclusions explicites par code, réintégration, conservation du périmètre dans l’URL et enregistrement de sélections dans ce navigateur.
- Bouton inflation : euros constants de l’année choisie, à partir de l’IPC annuel Insee 011814639, ensemble des ménages, France, ensemble des produits. Indices disponibles de 2017 à 2025. Conversion de chaque année avant le cumul.
- Graphique annuel, unité euros / millions / milliards, export CSV avec contexte, statuts, précision et liens sources. Une colonne distingue les totaux des détails pour éviter de les additionner ensemble.
- Mouvements : ouverts, reports entrants et sortants disponibles, mouvements législatifs et réglementaires nets, FdC/AdP rattachés, prévisions disponibles, fongibilité, ouvertures et annulations proposées en PLRG.
- Source consultable depuis chaque montant : fichier original, ligne, champ, montants d’origine, URL officielle et empreinte SHA-256.
- Bibliothèque des 769 fichiers collectés, dont 460 PDF, avec recherche par titre, année, format et téléchargement. Les filtres documentaires sont propres à la bibliothèque.
- Écran de couverture et accès conservé au diagnostic des connexions à `/diagnostic`.

## Dossier transversal MaPrimeRénov’

Filtre « Grand dossier » avec modes isoler et retirer. 32 observations sourcées, distinctes de la base générale : consommé 2021–2024, LFI et ouverts 2024. Suivi des parts des programmes 174, 362 et 135, sans retirer un programme entier. Les pages PDF, arrondis, limites annuelles et changements de périmètre sont visibles. Inflation, tableaux, graphiques, CSV et sélections utilisent le dossier. 2020, 2025–2026 et les PLF du dispositif restent à isoler.

Voir [le bilan MaPrimeRénov’](DOSSIER-MAPRIMERENOV.md). Les 30 tests unitaires et les deux parcours navigateur passent. Estimation du service complet envisagé : environ 40 % fonctionnel ; ce chiffre ne mesure pas l’exhaustivité des données.

## Couverture des principaux tableaux du budget général

| Étape | 2017–2020 | 2021–2022 | 2023–2025 | 2026 |
|---|---|---|---|---|
| PLF | Action, avec sous-actions selon source | Action et sous-action selon source | Action et sous-action selon source | Pas encore intégré |
| LFI | Action, avec sous-actions selon source | Action et sous-action selon source | Programme / titre 2 et hors titre 2 | Pas encore intégré |
| Consommé | Action, avec sous-actions selon source | Pas encore intégré | Programme / titre 2 et hors titre 2 | Pas encore intégré |
| Mouvements | Pas encore intégré | Pas encore intégré | Programme, suivant les colonnes publiées | Pas encore intégré |

Les budgets annexes, comptes d’affectation spéciale et comptes de concours financiers se consultent séparément. Leur couverture propre est affichée dans l’application ; elle n’est pas uniforme sur toutes les années. Une somme entre ces budgets pourrait compter plusieurs fois des flux internes : aucun total consolidé de l’État n’est inventé.

54 tables sources alimentent 116 272 observations chiffrées : un exercice, une étape budgétaire, AE ou CP, un poste et sa source. Il s’agit d’agrégats budgétaires, pas des transactions de Chorus. Les fichiers de nomenclature servent aussi à retrouver les libellés.

## Contrôles et limites

- Les 54 empreintes des tables utilisées correspondent au manifeste collecté. Les originaux n’ont pas été modifiés.
- 264 rapprochements des crédits ouverts et consommés de 2024–2025 avec les états indépendants par mission passent à deux centimes près. Quatre montants témoins du programme 105 vérifient séparément AE et CP, LFI et consommé.
- L’export détaillé LFI 2023 comporte des colonnes anormales, répétant la valeur 4. Il est exclu des montants LFI ; les annexes PLRG fournissent les montants par programme.
- Les annexes 2023 comportent des arrondis, parfois en notation scientifique. 97 lignes présentent un écart entre le total publié et la somme de ses mouvements. Les montants publiés restent distincts du calcul de rapprochement ; les notations scientifiques sont marquées « ≈ » et signalées dans le CSV.
- Une valeur absente ne devient jamais zéro. Une exclusion d’action rend le consommé indisponible si celui-ci n’est connu qu’au programme. Aucune répartition proportionnelle n’est inventée.
- Les crédits ouverts incluent déjà les fonds de concours et attributions de produits rattachés. Les propositions en PLRG ne sont pas présentées comme une loi promulguée. La fongibilité est nommée selon le champ source.
- Les séries suivent la nomenclature publiée. Le maintien d’un code ne garantit pas un périmètre économique constant. Le retraitement des changements de périmètre reste à développer.
- Les gels et dégels, le détail récent du consommé par action, les exécutions 2021–2022 et les montants 2026 restent à intégrer. Les PDF disponibles peuvent déjà être consultés.
- Recherche documentaire par titre uniquement à ce stade. Recherche sémantique et audit IA sourcé restent à raccorder aux bases existantes. Les autres applications et corpus partagés n’ont pas été modifiés.

## Exploitation

Depuis le dossier `budget`, Docker Desktop démarré :

```powershell
docker compose up -d --build web
docker compose --profile normalize run --rm --no-deps normalize
docker compose --profile normalize run --rm --no-deps normalize python -m budget_service.audit_data
docker compose --profile normalize run --rm --no-deps normalize python -m unittest discover -s tests -v
```

La normalisation travaille hors réseau dans le volume propre `lexmachine-budget_budget_data`, sous `/data/derived`. Elle remplace atomiquement la base préparée et conserve les originaux sous `/data/raw`. Le site monte ce volume en lecture seule, sans secrets de connexion. La collecte historique et les sondes existantes conservent leurs commandes et profils séparés.

Validation de l’interface : `tests/explorer-ui.cjs`, avec le Node et Playwright du runtime fourni et Chrome local. Captures et résultat dans `reports/ui`. Contrôles : navigation, inflation, sources, exclusions, sauvegarde, mouvements, documents PDF, CSV et écran mobile.
