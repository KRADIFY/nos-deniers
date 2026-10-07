# Nos Deniers — sauvegarde en ligne du 7 octobre 2026

Branche `sauvegarde-en-ligne-20261007` du dépôt privé `KRADIFY/nos-deniers`.
Capture des fichiers des conteneurs actifs et des styles effectivement servis sur
https://budget.lexmachine.net/. Les sauvegardes des 28 septembre et 4 octobre sont conservées.

## Contenu actuel

- Application web dans `budget_service`, `public`, `tools`, `tests` et `requirements.txt`.
- Moteur documentaire actif dans `runtime-retrieval` ; ses trois index sont référencés dans la configuration.
- Base financière de 140 875 observations dans `proofs/budget.sqlite.gz`.
- Démo à trois parcours dans `demo`, avec les textes et les 32 nouveaux extraits audio du 7 octobre.
- Styles séparés et adaptateurs de présentation dans `presentations`.
- Cartouches : proposé bleu clair, voté bleu foncé avec texte blanc, consommé rouge avec tout le texte sombre, consommé cumulé blanc.
- Configuration de production dans `proofs/compose.yaml`, `proofs/nginx-budget.conf` et `presentations/general-locations.conf`.
- Sauvegarde du CSS précédent, contrôles ordinateur/mobile et reçus de publication dans `proofs/cartouches-20261007`.
- Reçus de publication et contrôles des voix dans `proofs/voix-20261007`.

## Vérification et restauration

`proofs/VERSION-EN-LIGNE.json` inventorie les fichiers capturés et leurs SHA-256,
les images Docker actives, les montages et les métadonnées de la base. Ce manifeste
fait autorité pour la capture actuelle ; les anciennes preuves conservées dans
l'historique ne décrivent pas la version du 7 octobre.

La base décompressée doit avoir l'empreinte
`80894c3446a0126f554861634e0140f9a16a513f67cbabf75efe5fe8a57d5413`.
Le CSS publié est `presentations/budget-refinements.css` ; la version précédente
est `proofs/cartouches-20261007/before.css`. La même version actuelle du CSS est
conservée dans la source autonome `demo/public/budget-refinements.css`.

Les configurations sont des copies de production, avec leurs chemins VPS.
Elles nécessitent les données, les images Docker et les index correspondants ;
les scripts de publication archivés sont des preuves, pas des commandes à relancer aveuglément.

Les gros corpus PDF, les index vectoriels, les images Docker et les fichiers de
données annexes restent dans leurs sauvegardes dédiées sur le VPS et en local.
Ce dépôt ne constitue donc pas une sauvegarde intégrale de tous ces volumes.
PLFSS n'est pas actualisé par cette sauvegarde. Aucun service de production n'a été modifié.
