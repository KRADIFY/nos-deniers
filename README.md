# PLF / Nos Deniers — version en ligne du 8 octobre 2026

Sauvegarde privée : https://github.com/KRADIFY/nos-deniers.
Version du jour : branche `sauvegarde-en-ligne-20261008`, tag `en-ligne-20261008`.
La branche principale est actualisée par avance simple ; les sauvegardes précédentes sont conservées.
Site capturé : https://budget.lexmachine.net/.

## Contenu de cette version

- Code du site, moteur de recherche et configurations réellement utilisés en production.
- Base financière : **141 859 observations**, conservée dans `proofs/budget.sqlite.gz`.
- Recherche documentaire : **4 887 593 passages dans 5 275 documents** ; les trois index actifs sont référencés dans `proofs/compose.yaml`.
- Démo : trois parcours, textes et 32 extraits audio du 7 octobre, passages musicaux conservés.
- Dernière correction de placement des cartouches d'explication dans `demo/public/popover-layout.js`, `demo.js` et `floating-ui.css`.
- Styles effectivement injectés : boutons orange, cartouches accordées au graphique, consommé avec texte sombre, cumulé blanc.
- Les 984 montants supplémentaires du 7 octobre et le complément documentaire du Journal officiel du 8 octobre sont inclus.
- Reçus du complément documentaire dans `proofs/vectorisation-jorf-20261008`.

La capture a été effectuée en lecture seule. Aucun chiffre, texte, style, service ou réglage de production n'a été modifié pour réaliser la sauvegarde.

## Dépôt local et gros fichiers

Le dépôt Git local se trouve dans :
`D:/ChatGPT/docker/backups/nos-deniers-enligne-20261004/git`.
Le nom du dossier indique sa date de création, pas la date de sa dernière sauvegarde.
Il contient le code et l'historique des versions, y compris celle du 8 octobre.
Git n'enregistre une nouvelle version que lorsqu'un commit est créé ; il ne synchronise pas automatiquement les changements futurs du serveur.

Les corpus, index vectoriels et images Docker sont trop volumineux pour les objets Git.
Leur copie locale est conservée séparément dans :
`H:/Sauvegardes-Nos-Deniers/20261008-version-en-ligne`.
Consulter le manifeste de vérification dans ce dossier pour les volumes et les instructions de restauration. Les index existants ont été conservés, sans nouvelle vectorisation.

## Vérification et restauration

`proofs/VERSION-EN-LIGNE.json` fait autorité pour les fichiers capturés, leurs SHA-256, les images Docker actives, les montages et les métadonnées financières. Les autres preuves historiques décrivent leurs dates respectives.

Empreinte SHA-256 de la base financière décompressée :
`e1f379fac58ed9b5086bc925eb5c6fa229711fc2d20d2159c6e20f92d27d9b05`.

Les configurations archivées conservent les chemins du VPS. Une restauration nécessite aussi les volumes séparés et les images Docker correspondantes ; les scripts de publication historiques ne doivent pas être relancés aveuglément. Le dossier local sur H: contient les instructions et les archives. PLFSS est sauvegardé dans son propre dépôt `KRADIFY/plfss`.
