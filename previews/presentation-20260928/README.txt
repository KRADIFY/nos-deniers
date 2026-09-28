Nos Deniers — variante de présentation locale

Version de présentation : http://127.0.0.1:8556/
Version actuelle : http://127.0.0.1:8552/

Seule présentation.css change le rendu. index.html est la copie de la page actuelle, avec cette feuille de style additionnelle et un suffixe dans le titre de l’onglet. JavaScript, logo, données et calculs sont partagés avec la version locale existante. Aucun fichier du site actuel ni de la livraison VPS modifié. Aucun déploiement public.

Démarrage : lancer serve.py avec Python depuis ce dossier. Le site local d’origine doit être accessible sur 8552 ; les requêtes API lui sont transmises sans transformation. Le serveur de présentation écoute uniquement sur 127.0.0.1:8556.

Respect de la préférence de réduction des animations, focus clavier visible et adaptations pour mobile inclus.
