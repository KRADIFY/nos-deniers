# Nos Deniers — version publiée sauvegardée

Cette branche conserve le code de l’image publiée `20260924-final`, extrait de son archive Docker, puis son ajout du lien vers l’audit du 28 septembre. Les 80 empreintes du socle ont été contrôlées avant cet ajout ; les 10 ressources HTTP du résultat correspondent au site public. Le Dockerfile et les deux fichiers de cet ajout sont copiés directement depuis le serveur dans `restore/site-link-20260928/`. Voir `proofs/` et `restore/published-20260924/image-code-manifest.json`.

- Site : https://budget.lexmachine.net/
- Version des données : `f5c7830587b1cf8eb67fdd671e789c51d1f98db9ac8b6e9807ea0406a5340dac`.
- Montants structurés : **122 970**.
- Copie antérieure à la livraison des ajouts du 28 septembre 2026.

## Où sont les bases et les documents ?

Git conserve le code, les registres JSON utilisés par le site, les scripts de publication et les empreintes. Les bases SQLite, les trois index de recherche, les documents et les images Docker sont conservés séparément, avec leurs empreintes, dans :

`H:/Sauvegardes-Nos-Deniers/20260928-avant-publication`

Le fichier `restore/backup-manifest.json` liste toutes les pièces. Cette sauvegarde Git seule ne remplace donc pas la sauvegarde des données sur H.

## Restaurer sans modifier la production

Dans un dossier neuf, recopier `published-data/` depuis H comme dossier `data/`. Il contient la base structurée publiée et les documents. Recopier les scripts et images de `published-20260924/` depuis H. Décompresser `search.sqlite.zst` et `dense.faiss.zst` vers `search/search.sqlite` et `search/dense.faiss` ; vérifier les empreintes `original_sha256` du manifeste. Copier aussi `search/manifest.json`, `search-supplement/` et `search-supplement2/`.

Les images originales `image.tar` et `retrieval-image.tar.gz` évitent de reconstruire une ancienne version avec des dépendances récentes. La composition d’origine figure dans `restore/published-20260924/compose.yaml`. Pour retrouver le site actuel avec son bouton d’audit, reconstruire ensuite la petite image décrite dans `restore/site-link-20260928/Dockerfile`, avec le tag `lexmachine-budget:audit-link-20260928-145106`, et utiliser la composition dans ce même dossier. Adapter uniquement les ports d’une restauration de test pour ne pas interrompre les services existants. Les scripts de publication ne doivent pas être lancés pour simplement consulter cette sauvegarde.

La branche `preparation` sera la seconde photographie, avec les données ajoutées et la variante CSS. Les anciens paramètres de service ou secrets éventuels ne sont pas stockés dans Git.
