# Nos Deniers — préparation du 28 septembre 2026

Deux versions sont préservées dans ce dépôt privé :

| Version | Branche | Repère immuable | Montants structurés |
| --- | --- | --- | ---: |
| Site effectivement en ligne, avec bouton d’audit | `main` | `en-ligne-2026-09-28` | 122 970 |
| Ajouts du jour et présentation à essayer | `preparation` | `preparation-2026-09-28` | 135 155 |

**Cette version préparée n’a pas été publiée.** Le site public est inchangé par cette sauvegarde.

## Ce que contient la préparation

- Corrections et ajouts des classeurs 10 et 11, puis annexes de gestion 2017–2022 : 12 189 montants supplémentaires et retrait de quatre zéros en double, soit +12 185 montants nets depuis le site public.
- Code du site, registre des preuves, scripts d’intégration et contrôles, plans et reçus de chaque lot.
- Paquet cumulatif `deploy/update-20260928-annexes/`, avec les empreintes de sa base et des documents dans `release.json`.
- Variante visuelle séparée dans `previews/presentation-20260928/`. La CSS d’essai n’est pas imposée à la présentation habituelle. Après démarrage du site local sur le port 8552, lancer `python previews/presentation-20260928/serve.py` puis ouvrir http://127.0.0.1:8556/.
- Code de l’auditeur indépendant dans `auditeur-independant/`.

## Données et restauration

Les bases, les PDF et les trois index vectoriels sont conservés avec empreintes dans la sauvegarde indépendante :

`H:/Sauvegardes-Nos-Deniers/20260928-avant-publication`

Git conserve leur inventaire, pas les lourds fichiers de données. `restore/backup-manifest.json` décrit cette sauvegarde. `restore/current-archive-files.json` détaille chaque fichier de l’archive `nos-deniers-code-base-et-preuves.zip`.

Pour restaurer la préparation dans un **nouveau dossier** :

1. Vérifier l’empreinte de l’archive avec le manifeste, puis décompresser `nos-deniers-code-base-et-preuves.zip`. Elle restitue un dossier `budget/`, avec le paquet de livraison, la base de 135 155 faits et les PDF complémentaires.
2. Pour reconstituer un répertoire de données autonome, copier d’abord `published-data/` depuis la sauvegarde, puis y superposer `budget/deploy/update-20260928-annexes/data/` extrait de l’archive. La base finale attendue est `aa11479b90fb9c2d79003234b0223cc2a25198fb09c10f4ac2ef4c5ced5da7ba`.
3. Les trois index de recherche sont inchangés. Les retrouver dans `published-20260924/` ; décompresser les deux `.zst` du principal dans `search/` et contrôler leurs empreintes `original_sha256`. Conserver les deux compléments et les manifestes. Aucune nouvelle vectorisation n’est nécessaire pour restaurer.
4. L’image Docker d’origine et le moteur de recherche sont aussi sauvegardés. Le paquet cumulatif fournit son propre installateur et refuse une base publique différente. **Ne pas exécuter cet installateur pour simplement consulter les fichiers : il sert à publier.**

Le détail de restauration de la version publique figure dans le README de la branche `main`. L’ajout déjà publié du bouton d’audit est sauvegardé dans `restore/site-link-20260928/`.

## Contrôles et limites conservés

Les reçus du lot indiquent 473 tests exécutés, deux contrôles de préparation de corpus non applicables, 11 672 nouveaux montants vérifiés et 13 185 contrôles numériques indépendants sans erreur de calcul. Ils conservent aussi deux alertes de provenance MaPrimeRénov’ déjà présentes, ainsi que 344 cellules de gestion en attente de rapprochement. La sauvegarde n’efface pas ces limites et ne vaut pas nouvel audit exhaustif.

`proofs/prepared-files.json` permet de contrôler les fichiers préparés. Les fichiers de l’application en ligne ont été extraits de l’image d’origine et rapprochés des ressources réellement servies avant la première sauvegarde.
