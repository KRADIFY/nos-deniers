# PLF / Nos Deniers — version du 13 octobre 2026

Version publique : https://budget.lexmachine.net/. Dépôt privé : https://github.com/KRADIFY/nos-deniers.

Le complément approuvé de Budget.gouv ajoute 83 positions globales, dont deux nouvellement repérées et 81 candidats antérieurs, et comble 134 détails manquants. Deux positions d'appui complètent la hiérarchie du Sénat. Les 141 859 anciens faits restent identiques ; la base compte désormais 141 942 faits.

Les cinq PDF justificatifs et les 83 notices sont conservés. Un correctif de cinq lignes précise les mentions PAP/FdC des nouveaux détails, sans changer les calculs. PLFSS, la démo, les autres fichiers de l'image et les index de recherche restent inchangés : 5 275 documents / 4 887 593 passages.

Les 217 positions et 134 exclusions sont vérifiées sur la base préparée puis sur les services réels ; 264 comparaisons avec les CSV officiels concordent. L'audit global n'est pas déclaré validé : quatre écarts d'agrégats historiques et un écart de 58 centimes entre un registre historique et la base étaient déjà présents. Ils sont conservés dans les reçus.

Le reçu actuel est proofs/VERSION-EN-LIGNE-20261013.json. Les preuves datées du 8 octobre et le tag en-ligne-20261008 restent historiques. proofs/budget.sqlite.gz conserve la base actuelle ; les gros documents/index restent hors Git.

Sauvegarde de la mise à jour : D:/ChatGPT/docker/backups/sauvegarde-20261013-budget-gouv. Le paquet contient la nouvelle base, les cinq PDF et une copie exacte de l'image web du VPS. Les autres documents et index sont restaurables depuis la sauvegarde immuable H:/Sauvegardes-Nos-Deniers/20261008-version-en-ligne ; le paquet du 13 octobre complète cette base.

Le Docker local a ensuite été mis à jour et redémarré le 13 octobre, après arrêt des projets inactifs par Jean-Christophe. Son image et sa base sont identiques à la version publique ; le site, la recherche et la démonstration sont sains. Le plafond WSL reste à 6 Go et les autres conteneurs existants ont été préservés.

Dépôt local permanent : D:/ChatGPT/docker/backups/nos-deniers-enligne-20261004/git. Git conserve les versions à chaque commit ; la synchronisation ne se fait pas automatiquement. PLFSS conserve son propre dépôt et sa version.
