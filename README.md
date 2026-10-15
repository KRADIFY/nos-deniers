# PLF / Nos Deniers — version publiée du 15 octobre 2026

Version publique : https://budget.lexmachine.net/. Dépôt privé : https://github.com/KRADIFY/nos-deniers.

Cette sauvegarde conserve la version déjà publiée du lot de 3 916 positions annuelles : 137 faits supplémentaires dans SQLite et 3 779 positions dans les registres applicatifs. La base contient 142 079 faits. Les compléments précédents du 13 octobre restent conservés. La sauvegarde Git n'applique aucune correction issue de l'audit général et ne modifie pas le site.

Le reçu courant est `proofs/VERSION-EN-LIGNE-20261015.json`. Les 92 fichiers applicatifs suivis sous `budget_service`, `public` et `requirements.txt` ont été comparés par SHA-256 au serveur web. Les quatre fichiers du lot ont aussi été vérifiés sur les quatre instances publiées. L'image est `lexmachine-budget:20261015-complements-3916-v2`, identifiant `sha256:c883bb343e204f4f91e070125b2837844e4eddf8fdf32fd7c6ce02507e8bfc6e`.

`proofs/budget.sqlite.gz` contient la base actuelle. Sa décompression doit produire le SHA-256 `ef3e0846e52e82577336293de3e2ba12ef307784f1a38406f597af8201680ed5`, identique à la base publiée et à la base locale. Version de données : `522b5e8ff1e502ffa3a173fb1552e20651729eee0e1a33c0bbb52c2c90650752`. `proofs/compose.yaml` conserve la configuration publiée ; les reçus détaillés sont dans `proofs/integration-budget-gouv-20261015/`. Les reçus datés des 8 et 13 octobre et les anciens commits restent historiques.

Les PDF et les index volumineux restent sauvegardés séparément. Une restauration complète utilise la sauvegarde initiale `H:/Sauvegardes-Nos-Deniers/20261008-version-en-ligne`, le complément `D:/ChatGPT/docker/backups/sauvegarde-20261013-budget-gouv`, puis les archives du 15 octobre dans `D:/ChatGPT/docker/budget/outputs/audit-financier-budget-gouv-20261014/reprise-20261015/integration-3916-preview-20261015/publication/` : `approved-release.tar.gz` (base et 398 nouveaux fichiers sources notamment) et `web-image.tar.gz` (image applicative). Leurs tailles et empreintes sont inscrites dans le reçu courant. Git seul ne contient pas tout le corpus documentaire et les index.

L'audit général du 15 octobre est terminé, avec des limites et arbitrages documentés ; il ne certifie pas globalement tous les chiffres ou l'exhaustivité des PAP/RAP. Son rapport Word et ses reçus sont conservés séparément dans `D:/ChatGPT/docker/budget/outputs/audit-general-nos-deniers-20261015`. Aucune de ses corrections proposées n'est appliquée par cette sauvegarde.

Dépôt local permanent : `D:/ChatGPT/docker/backups/nos-deniers-enligne-20261004/git`, branche `main`. Ce dépôt sauvegarde la version publiée ; il ne faut pas lancer une intégration, un déploiement ou un recalcul pour le synchroniser. PLFSS conserve son propre dépôt et sa version.
