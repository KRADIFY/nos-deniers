# Nos Deniers — V0.2

Application locale de suivi des crédits du budget de l’État : http://127.0.0.1:8552/.

Tableaux PLF/LFI/consommé, AE/CP, navigation par poste, comparaisons annuelles, exclusions, euros constants, exports CSV et bibliothèque des documents collectés. Voir [ETAT-SITE-NOS-DENIERS.md](ETAT-SITE-NOS-DENIERS.md) pour la couverture réelle, les contrôles et les limites. Domaine cible budget.lexmachine.net, publication encore à réaliser.

Depuis ce dossier, Docker Desktop démarré :

```powershell
docker compose up -d --build web
docker compose --profile normalize run --rm --no-deps normalize
docker compose --profile normalize run --rm --no-deps normalize python -m budget_service.audit_data
docker compose --profile normalize run --rm --no-deps normalize python -m unittest discover -s tests -v
```

La base préparée est `/data/derived/budget.sqlite` dans `lexmachine-budget_budget_data`. Le profil `normalize` s’exécute sans réseau et remplace atomiquement cette base ; les originaux restent intacts. Relancer le contrôle des données après une nouvelle normalisation. Le site lit les deux volumes propres, données et état, sans droit d’écriture et sans accès aux secrets des connecteurs.

`/healthz` indique la santé HTTP ; `/readyz` indique la présence de la base préparée, sans certifier son exhaustivité. `/api/bootstrap` donne la couverture réelle. `/api/status` et `/diagnostic` conservent le bilan des connexions. Ces pages ne lancent aucune connexion externe.

## Collecte et connexions

La collecte reste distincte du site : `docker compose --profile collect run --rm --no-deps collect`. Inventaire et limites dans BILAN-COLLECTE.md et reports/MANIFEST-COLLECTE.json. Besoin fonctionnel dans BESOINS-PARLEMENTAIRES.md.

Les sondes se lancent avec `./run-checks.ps1`. Ce script vérifie les journaux SQLite hôtes avant lecture : une base avec journal non vide est différée, aucun journal ni corpus n’est modifié. Ce contrôle ne remplace pas un instantané cohérent pour une importation longue. Les secrets PISTE et OAuth sont réservés au profil checks, en lecture seule et hors image.

Le réseau propre Budget est 10.248.72.0/28. Ne supprimer aucun réseau d’une autre application. Les fichiers deploy/ restent des préparatifs à adapter au serveur et au certificat ; ne pas publier les montages Windows locaux tels quels.

La recherche sémantique et l’audit IA ne sont pas encore raccordés. Les gels/dégels, le détail récent par action et les années non intégrées restent signalés dans le site.
