# Nos Deniers — interrupteurs et dernière livraison du 10 septembre 2026

- Chemin permanent : C:/Users/Jean-Christophe/Documents/ChatGPT/docker/budget. Dossier et parent sans Git ; aucune branche ni commit.
- État : PUBLIÉE par l’utilisateur. Vérifications indépendantes HTTPS complète et SSH réussies ; reçu deploy/update-20260910-reactivation/PUBLIC-VERIFIED.json.
- PUBLIC actif vérifié par SSH et HTTPS : 20260910-reactivation. Ancienne version mpr-perimetres conservée, rollback.json contrôlé. LOCAL actif : 20260910-reactivation, image lexmachine-budget:0.3, conteneur lexmachine-budget-web-1, http://127.0.0.1:8552.
- Paquet figé : deploy/update-20260910-reactivation. Ne pas modifier la charge utile. Neuf fichiers distants SHA-256 identiques ; reçu TRANSFER-VERIFIED.json.
- Installation utilisateur terminée : ne pas relancer update.py. Toute prochaine livraison doit prendre 20260910-reactivation comme prédécesseur.
- Changé : interrupteurs de mission, programme, action, sous-action et filtres latéraux ; clic simple avec état bleu/gris immédiat, attente du recalcul, autres postes indépendants, restauration du focus et nouvelle tentative après erreur. Protection contre les anciennes réponses/erreurs. Les trois contrôles Écologie P345, P235 et MPR restent visibles dans les deux états ; compteur limité aux exclusions effectives. Les autres postes restent réversibles dans les tableaux.
- Préservé : données, calculs, préréglages, CSS, HTML, sources, PDF et corpus vectorisé. Aucun changement financier dans cette livraison.
- Tests : 153 tests Python dans l’image ; 7 nouveaux scénarios VM + 9 MPR + 4 RAP. Références figées conservées : 23 cas annuels, 115 groupes actions, 9 cas RAP, 22 preuves MPR. Vérifications du paquet hors ligne et HTTP local réussies. Pas de contrôle visuel dans un navigateur réel : outil indisponible.
- Mini-audit : consommé Écologie avec P345/P235/MPR exclus disponible sur les 9 exercices 2017–2025 en AE et CP ; 2024 LFI/EXEC disponibles. Aucun double retrait parent/enfant identifié. Inflation, sources et exports restent couverts par les tests existants ; ne pas prétendre une nouvelle revue exhaustive.
- Limites : PLF 2024 hors MPR et total national MPR 2025 restent indisponibles, avec explication. Plus généralement ventilations MPR historiques et mouvements/réserves propres au dispositif encore incomplets. Les enfants exclus par un parent et postes sans données sont volontairement désactivés avec explication.
- Démarrage local : docker compose up -d --no-deps web. Build : docker build -t lexmachine-budget:0.3 .
- Tests : docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --mount type=volume,src=lexmachine-budget_budget_data,dst=/data,readonly --tmpfs /tmp:size=64m lexmachine-budget:0.3 python -m unittest discover -s tests -q
- Publication vérifiée et terminée. Prochaine étape fonctionnelle selon demande utilisateur : ventilations MaPrimeRénov’ manquantes, priorité Mission Écologie, avec justificatifs documentaires ; ne pas inventer les sommes indisponibles.
- Historique détaillé et données MPR : POINT_DE_REPRISE-MPR-20260910.md. Préparation documentaire externe D:/LexMachine/NosDeniers/preparation_20260909 intacte.

- Incident résolu : incoming initialement en 0700 empêchait UID10001 de lire /bundle. Dossier seul corrigé en 0755, fichiers intacts, puis utilisateur a relancé avec succès la publication et ses contrôles. HTTPS et SSH vérifiés indépendamment. Pour les prochains transferts : dossier public de livraison traversable par UID10001 dès sa création.
