# Point de reprise — Nos Deniers PLF, 13 octobre 2026

- Chemin permanent : D:/ChatGPT/docker/backups/nos-deniers-enligne-20261004/git ; branche main. État/commit : git status --short --branch et git log -1 --oneline depuis cette racine.
- Version intégrée : 141 942 faits ; +83 globaux, 134 détails, deux positions d'appui Sénat, cinq PDF et 83 notices. Correctif source de cinq lignes ; aucun ancien fait remplacé.
- Réception : proofs/VERSION-EN-LIGNE-20261013.json et proofs/integration-budget-gouv-20261013/. Les réserves historiques de l'auditeur restent visibles ; aucune certification globale.
- VPS : /opt/nos-deniers/compose.yaml ; image lexmachine-budget:20261013-complements-budget-gouv ; quatre web vérifiés. Recherche et démo inchangées.
- Docker local D:/ChatGPT/docker/budget actualisé et redémarré sur demande : même image et même base que le VPS, 141 942 faits. Site http://127.0.0.1:8552 ; démonstration http://127.0.0.1:18896 ; recherche disponible. WSL reste à 6 Go. Contrôle : proofs/integration-budget-gouv-20261013/local-retry/LOCAL-FINAL-VERIFIED.json.
- Contrôles : 217 montants, 134 exclusions, notices et cinq téléchargements PDF ; 264 comparaisons CSV. Scripts/reçus : D:/ChatGPT/docker/budget/outputs/integration-budget-gouv-20261013.
- Sauvegarde : D:/ChatGPT/docker/backups/sauvegarde-20261013-budget-gouv. Base/index historiques immuables : H:/Sauvegardes-Nos-Deniers/20261008-version-en-ligne ; tag en-ligne-20261008 conservé. Restauration : base historique + overlay du 13 octobre et image web sauvegardée.
- Prochaine étape : attendre Jean-Christophe ; ne corriger aucun autre chiffre ni reprendre les réserves sans l'avertir.
