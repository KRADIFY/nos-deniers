# Auditeur indépendant Nos Deniers — 28 septembre 2026

- Dossier permanent : `D:\ChatGPT\docker\budget\auditeur-independant`. Pas de dépôt Git.
- Site public de référence : `https://budget.lexmachine.net`, version `20260924-final`, 122 970 faits. Aucun montant ni actif public modifié par ce chantier.
- Service prévu : `auditnosdeniers.lexmachine.net`, Docker séparé ; lecture seule des données du VPS. Seul ajout prévu au site : lien de navigation.
- Prévisualisation locale : `http://127.0.0.1:8553`, lancée par `preview_service.py`. Docker local était arrêté. Ne pas déclarer le nouveau service publié.
- Tests : `python -m unittest test_auditeur test_service test_zeros test_recovery test_zero_api test_document_zeros -q` : 35 réussis. Python local bundlé, `PYTHONPATH=..\.runtime\python-libs` pour xlrd.
- Parcours rapide antérieur : 80 scénarios API, 60 840 cellules visibles contrôlées sans erreur navigateur. Quatre zéros MaPrimeRénov’ 2024 PR/362 LFI/OUVERT AE/CP sans source dans la réponse restent signalés (12 occurrences). Ne pas déclarer tout le site conforme.
- Contrôle demandé des 163 zéros PDF/HTML : 162 zéros imprimés, 1 calcul exact (P869 2018 CP ouverts = consommés 0 + solde 0). 49 PDF / 1 HTML, repères et SHA dans `document-zero-proofs.json` ; relecture indépendante via `document_zeros.py`. Les 9 repères de suivi 2019 conservent explicitement leur périmètre hors titre 2.
- Aucun blanc converti automatiquement en zéro. Les registres annexes actions/MPR ne sont pas confondus avec les 18 338 faits nuls structurés.
- Rapport ciblé : `resultats/service-local/runs/20260928-142500-016300/rapport.html`. Le script `report_document_zeros.py` refait la lecture des sources sans modifier les audits précédents.
- Les scripts `finish_document_zero_integration.py`, `integrate_zeros.py` et autres scripts de modification ponctuels NE SONT PAS à relancer : ils peuvent appliquer deux fois une modification. Les modules de production sont à la racine, listés dans `build_delivery.py`.
- Livraison : `..\deploy\audit-20260928`, construite par `build_delivery.py` (27 fichiers avec manifeste SHA). Refaire/transférer le manifeste si un fichier de production change.
- VPS : `/home/marie/nos-deniers-audit-20260928/`. L'installation demande `sudo python3 /home/marie/nos-deniers-audit-20260928/install.py` ; le compte marie exige un mot de passe interactif, donc aucun déploiement autonome effectué. L'installateur construit, teste et vérifie avant activation ; ne touche pas au service de recherche.
- Une ancienne campagne longue tourne dans `resultats/validation-complete-01` (2 018 scénarios) avec l'identité de code antérieure. Ses résultats ne doivent pas être présentés comme une validation du nouveau module des zéros. Conserver les checkpoints.

Prochaine étape : terminer la relecture ciblée, vérifier sa page, transmettre le paquet final avec empreintes vérifiées. Puis installation par sudo, tests Docker et contrôle HTTPS effectifs avant d'annoncer la mise en ligne.

Contrôle ciblé terminé : relecture des 163 repères réussie, 17 937 zéros explicites + 401 calculs nuls dans les faits structurés. Page ciblée et filtre P869 vérifiés au navigateur, aucun défaut JS, pas de débordement mobile. Paquet de 27 fichiers retransféré sur VPS et toutes les empreintes comparées avec succès. Installation non lancée ; sudo interactif reste requis.

Incident installation VPS corrigé : le port 8553 était déjà occupé par un processus Python existant, conservé. Installateur et proxy Nginx utilisent désormais 8554, testé libre sur le VPS. Contrôle préalable de disponibilité ajouté, reprise autorisée uniquement si le port appartient au conteneur auditeur. 4 nouveaux tests réussis (39 au total avec les 35 déjà validés dans Docker par l’utilisateur). Paquet de 28 fichiers transféré et empreintes vérifiées. Le site public conserve la même data_version. Relancer la même commande sudo install.py ; activation encore en attente.
