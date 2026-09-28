# Nos Deniers — dossier MaPrimeRénov’

État au 8 septembre 2026. Fonction ajoutée à la version locale 0.2.

[Ouvrir le dossier, 2021–2024](http://127.0.0.1:8552/?topic=maprimerenov&topic_mode=only&start=2021&end=2024&measure=CP)

[Écologie hors MaPrimeRénov’, 2024](http://127.0.0.1:8552/?topic=maprimerenov&topic_mode=without&scope=TA&start=2024&end=2024&measure=CP)

Le filtre « Grand dossier » permet d’isoler le dispositif ou de retirer ses crédits identifiés du périmètre courant. Les tableaux, graphiques, AE/CP, euros constants, exports et sélections enregistrées suivent le même filtre. Un panneau expose les rattachements annuels et les sources, accessibles à la page du PDF.

## Ce qui est chiffré

| Exercice | Étapes disponibles en AE et CP | Périmètre |
|---|---|---|
| 2017–2019 | Non applicable | MaPrimeRénov’ n’existait pas ; le CITE reste distinct. |
| 2020 | À documenter | Lancement du dispositif. |
| 2021–2022 | Consommé | Parts publiées des P174 et P362 ; P135 nul dans ce tableau. |
| 2023 | Consommé | Parts des P174, P362 et P135. |
| 2024 | LFI, ouverts nets, consommé | Parts des P174 et P135 ; P362 nul en consommé. |
| 2025–2026 | À isoler | Regroupement sur le P135 documenté ; les enveloppes de l’Anah mélangent plusieurs aides. |

32 observations documentées sont stockées séparément des 116 272 observations générales. Elles ne sont jamais additionnées automatiquement au budget de l’État. Les PLF du dispositif et les mouvements détaillés restent à isoler.

Les montants du consommé viennent du [tableau 18, page 48 de la note Écologie 2024 de la Cour des comptes](https://www.ccomptes.fr/sites/default/files/2025-04/NEB-2024-Ecologie-developpement-mobilite-durables.pdf#page=48). Les LFI et ouverts 2024 viennent du [tableau 12, page 62 de la note Cohésion des territoires](https://www.ccomptes.fr/sites/default/files/2025-04/NEB-2024-Cohesion-territoires.pdf#page=62). Ces deux PDF sont archivés avec empreinte SHA-256 dans le volume propre Budget. La bibliothèque compte désormais 769 fichiers, dont 460 PDF ; l’ancien manifeste de collecte décrit son lot initial de 767 fichiers.

## Sens des calculs

- Les crédits de l’État et les aides payées par l’Anah aux bénéficiaires représentent des flux distincts : les additionner compterait deux fois une partie du financement.
- Les séries suivent le périmètre publié par les rapports. Les évolutions de définition des aides, notamment l’intégration de parts du P135, ne sont pas retraitées à périmètre constant. Les zéros du tableau antérieur ne signifient pas qu’aucune autre aide à la rénovation n’existait.
- Le dossier ne mesure pas toutes les dépenses de rénovation énergétique : les dépenses fiscales, CEE, autres ressources de l’Anah et dispositifs voisins restent distincts.
- Aucun programme ni aucune action entière n’est assimilé à MaPrimeRénov’. Les documents utilisés isolent une part par programme ; une demande à l’action ou à la sous-action devient indisponible si sa ventilation n’est pas vérifiée.
- Le retrait ne porte que sur les parts des programmes présents dans le périmètre sélectionné. Il intervient sur les centimes nominaux avant conversion par l’IPC. Une exclusion manuelle du même programme ne provoque pas un deuxième retrait.
- Le retrait est suspendu si le montant du dispositif, le total de départ ou le rapprochement avec le programme manque. Les montants indisponibles ne sont pas remplacés par zéro.
- Les valeurs de la Cour sont arrondies : 0,1 M€ pour la plupart du consommé, certaines lignes au M€, et 1 M€ pour LFI/ouverts 2024. Le symbole « ≈ » et l’export conservent cette limite. Les valeurs d’exécution de 2024, plus précises dans la note Écologie, ne sont pas additionnées à celles de la note Cohésion.

## Vérifications réalisées

30 tests unitaires passent, dont 14 consacrés au dossier. Les parcours navigateur général et MaPrimeRénov’ passent : filtres, données absentes, changements de mission, inflation, sélection enregistrée, export téléchargé, provenance avec soustraction, PDF et écran mobile.

Le test sur les données réelles vérifie pour Écologie 2024 en CP : 24 232 001 582,79 € de consommé général, moins environ 692 000 000 € identifiés pour MaPrimeRénov’, soit environ 23 540 001 582,79 €. Le P174 conserve ses autres crédits et le P203 conserve son montant initial. Le résultat conserve les centimes du total général mais reste approximatif du fait de l’arrondi du montant retiré.

Les rattachements ont été contrôlés dans les nomenclatures importées : mission TA pour P174, PR pour P362 et VA pour P135. Le registre est `budget_service/data/maprimerenov.json`, le moteur `budget_service/topics.py`. Résultats navigateur : `reports/ui-maprimerenov/result.json` et `reports/ui/result.json`.

Pour installer ces sources dans un nouveau volume, après la normalisation générale :

```powershell
docker compose --profile normalize run --rm -T --no-deps normalize python -m budget_service.install_topic_sources
```

## Avancement du service complet

Estimation fonctionnelle : environ 40 %, sans prétendre mesurer un taux de couverture des données ni une part du temps de développement restant.

Les tableaux, graphiques, exports, filtres ordinaires, inflation et ce premier dossier documenté sont utilisables en local. Restent notamment le détail récent LFI/consommé à l’action, les trous historiques des tables générales, les séries 2026, MaPrimeRénov’ 2020 et 2025–2026, les gels/dégels, le suivi des autres dispositifs et des périmètres constants, la recherche sémantique et l’audit IA. La publication de budget.lexmachine.net reste à faire.

Seul Budget a changé. Logo, charte générale, autres sites et corpus partagés préservés. Aucun changement d’effort, de connexion ou de secret.
