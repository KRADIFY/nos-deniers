# Reprise de l’audit final — 21 septembre 2026

Projet permanent : C:/Users/Jean-Christophe/Documents/ChatGPT/docker/budget. Pas de dépôt Git ni de commit. URL locale : http://127.0.0.1:8552/. Web et recherche Docker sains. Public inchangé, ancienne version du 10 septembre.

Demande : audit complet, dernières recherches, intégration des compléments fiables et avertissements, livraison Docker et mémo Word. Aucune demande administrative à envoyer. Astra très élevé conseillé ; modèle non modifié par nous.

## État validé
- Nouvelle version ACTIVÉE EN LOCAL ; image web sha256:48ef897141fd484e99ea629e1ef1c807bdfdf59699ad5a01c64937438e038697, tag de livraison lexmachine-budget:20260921-audit-final.
- 218 tests Python réussis. Audit numérique : 120994 faits canoniques, 209 empreintes sources, 25216 références, aucun échec. Inventaire : 4291 fichiers contrôlés par taille/empreinte ; 3892 références PDF contrôlées par en-tête (pas relecture de toutes les pages).
- Parcours navigateur, exclusions indépendantes, inflation, justificatifs, exports, recherche hybride, contrôles asynchrones et mobile vérifiés. Rapports conservés dans reports/audit-final-20260920.
- MPR : 68 observations, dont 12 ajoutées sans altérer les 56 anciennes. National 2020 PLF/LFI/ouverts/consommé documenté ; PLF/LFI 2021 et PLF 2022 complétés au périmètre publié. Sources supplémentaires AN/PAP vérifiées. Attention : aides connexes incluses dans le plan de relance ; pas de nomenclature constante implicite ni de double compte des 85 M€ transférés en 2020.
- Événements corrigés : retrait MPR préserve les programmes étrangers au dispositif ; mode MPR seul les filtre ; absence de ventilation n’offre pas de montant nominal utilisable comme total sélectionné. Écarts LFI + mouvements / ouverts exposés dans les justificatifs. Charte, logos et organisation générale conservés.
- Actions : 1401 groupes nationaux +115 pilotes. Mouvements : 357 programmes-années sur379. Réserves :331 sur379, plus48 historiques Écologie. Restent22 mouvements/48 réserves sans tableau intégré, dont P3842025 explicitement sans objet ; 53 cas distincts détaillés dans le Word.
- Recherche inchangée : D:/LexMachine/NosDeniers/search_20260919, 4439 documents /4051433 passages. Pas de revectorisation. Nouveaux PDF disponibles via justificatifs/bibliothèque mais pas dans cet index figé.

## Livraison prête, pas encore transférée/activée sur le serveur
Dossier : deploy/update-20260921-audit-final. READY.json = prepared_and_locally_verified, published=false. Vérification hors réseau et HTTP locale réussie (release-build.log). Paquet figé : ne pas modifier après READY. Image, 11 fichiers delta, inventaire global et installateur vérifiés. Plan de transfert : 12 fichiers /33314761874 octets, réutilise les index et l’image retrieval existants, SFTP reprenable.
Transfert utilisateur : TRANSFERER_VERS_LE_SERVEUR.cmd. Puis sur le serveur : sudo python3 /home/marie/nos-deniers-update-20260921-audit-final/update.py. Retour à la version précédente prévu en cas d’échec. Aucun transfert ni changement public effectué dans cette passe. Ne pas livrer les anciens paquets du 19 septembre.
Démarrage local : docker compose -f compose.yaml -f compose.retrieval.yaml up -d web retrieval
Tests : docker compose run --rm --no-deps web python -m unittest discover -s tests
Vérification locale figée : utiliser verify.py et les scénarios du paquet ; ne pas relancer une normalisation générale.

## Limites non closes à ne pas rebaptiser introuvables
Gestion générale 2017–2022 non intégrée malgré des archives existantes ; nomenclatures historiques complètes, analyse causale IA, navette et collaboration non livrées. Certaines ventilations MPR2021–2026 demeurent indissociables dans les sources examinées. 2026 non clos. Tricoteuses renvoie401 sur clé interne Typesense ; ne pas en déduire OAuth utilisateur invalide. Chorus inaccessible. LexMachine/Cour des comptes fonctionne. Ne pas affirmer une exhaustion universelle des recherches ni 100 % de l’audit initial implanté.

## Mémo et suite
Word final : reports/audit-final-20260920/Nos Deniers - Audit final et limites de la livraison.docx ; copie Bureau/Nos Deniers/Nos Deniers - Audit final du 21 septembre 2026.docx. Rendu Microsoft Word et inspection visuelle des11pages effectués ; aperçus word-verified-render. Les originaux utilisateur restent intacts.
Prochaine étape : remettre les liens au client ; publication par son processus habituel. Si poursuite de développement demandée, prioriser archives de gestion2017–2022 et nomenclatures, puis fonctions IA, sans relancer la vectorisation existante. Les contrôles réussis ne doivent pas être refaits sans nouveau changement.

## Reprise du 21 septembre — archives historiques
- Ajout local ciblé : `budget_service/data/actions-rap-historique.json`, 82 groupes RAP 2021–2022 retenus uniquement quand la ventilation actions/sous-actions se rapproche exactement du parent canonique. `budget_service/action_details.py` charge ce registre ; le test ciblé actions passe (16/16).
- Les faits canoniques existants n’ont pas été modifiés. Le premier rapport de 348 écarts était surévalué par les codes RAP composés (`105.0`/`105-01`) ; les totaux de programmes rapprochés concordent.
- Registre de réserves historique ajouté : `budget_service/data/reserves-historique-2017-2022.json`, 950 lignes AE/CP contrôlées, branché dans `budget_service/reserves.py`; les tests réserves passent.
- Scan hors ligne des mouvements : `reports/historique-2017-2022/mouvements-scan-candidates.json` (1 532 PDF uniques, 639 tableaux candidats, 893 sans total exploitable par ce parseur). Les candidats ne sont pas encore promus en mouvements datés, car les tableaux anciens doivent conserver les colonnes Titre 2/Autres titres et les catégories FDC/ADP/reports.
- Rapport : `reports/historique-2017-2022/RAPPORT_INTEGRATION_HISTORIQUE_20260921.md`. Docker était arrêté pendant la préparation ; reconstruire et lancer les tests dans une nouvelle release avant toute publication.
## Reconstruction Docker — 21 septembre
- Docker Desktop relancé ; image web reconstruite et conteneurs web/retrieval démarrés avec succès. `/readyz` HTTP local renvoie 200.
- Contrôle HTTP : l’exclusion `AV/421/02` sur 2021 CP passe de 182 M€ à 187 M€ ; les réserves historiques renvoient 484 lignes dont 481 tables intégrées pour 2017–2022.
- Les 893 références de mouvements non promues ont été classées : 349 contiennent encore des marqueurs de tableaux de mouvements et 475 ne contiennent aucun marqueur ; le nombre ne représente donc pas 893 données manquantes.

## Intégration OUVERT 2017–2022 — 21 septembre
- Extraction RAP contrôlée : 952 PDF possèdent les lignes AE/CP ouvertes ; 693 programmes-années ont une correspondance BG unique et ont reçu 1 386 faits OUVERT (AE/CP) avec source, page et ligne. 257 candidats n’ont pas de programme canonique dans le périmètre actuel et 2 sont ambigus ; ils restent en réserve de rapprochement, sans valeur publiée.
- Base SQLite installée dans le volume Docker avec sauvegarde préalable : 122 380 faits, intégrité SQLite `ok`, 218 tests Docker réussis. `/readyz` HTTP local = 200 ; réserves historiques = 484 lignes dont 481 tables intégrées.
- Limite inchangée : les opérations de mouvements datées 2017–2022 (ouvertures/annulations/reports/FdC-ADP) ne sont pas promues automatiquement. Les 639 candidats restent sourcés pour un parseur par millésime ; les 893 références non totalisées ont été classées et ne signifient pas 893 absences.
- Runtime actif après cette étape : image web `lexmachine-budget:0.3` et volume `lexmachine-budget_budget_data` contenant la base OUVERT reconstruite ; l’URL locale reste `http://127.0.0.1:8552`. La publication HTTPS n’a pas été modifiée par cette opération locale.

## Mouvements historiques — promotion du premier lot
- Le premier extracteur par millésime a promu 107 programmes-années 2017–2022 à partir des totaux annuels nets « Ouvertures / annulations y.c. FDC et ADP », soit 428 observations AE/CP par titre. Le registre `budget_service/data/mouvements-rap-historique.json` est chargé par l’API.
- Contrôles : chaque registre est rapproché des LFI et OUVERT, conserve la page et l’empreinte du RAP, et les 220 tests Docker passent. L’API locale renvoie 214 observations CP sur 2017–2022 et 107 rapprochements.
- Limite : ce lot ne constitue pas une chronologie détaillée des actes. Les références non promues restent classées dans `reports/historique-2017-2022/mouvements-historique-candidates.json` et donnent lieu aux avertissements du site.

## État final de la reprise des mouvements
- Le registre `mouvements-rap-historique.json` est désormais chargé par l’API. Il ajoute 107 programmes-années 2017–2022, 428 observations AE/CP par titre, et 107 rapprochements ; les sources sont vérifiées par empreinte.
- Les tests Docker sont passés à 220 réussis. La version locale est prête sur `http://127.0.0.1:8552`.
- Le paquet public préparé précédemment reste inchangé. Cette intégration est locale et doit être empaquetée dans une livraison distincte avant activation HTTPS.

## Mouvements détaillés 2017–2022 — 23 septembre 2026
- L’extracteur interrompu a été réparé : ses expressions régulières recherchaient littéralement la lettre `d` au lieu des chiffres. Les dates et les montants sont désormais reconnus, avec conservation du texte, de la page, de la catégorie, du signe et des huit colonnes AE/CP Titre 2/autres titres.
- **421 programmes-années** ont passé le rapprochement avec les crédits ouverts, soit **4 339 lignes datées**, **11 296 montants** et **2 042 totaux de contrôle**. Le registre compact est `budget_service/data/mouvements-rap-historique-detail.json`.
- Le service remplace les 47 résumés annuels qui possèdent maintenant un détail et conserve les 60 résumés annuels sans détail. La couverture historique publiée atteint donc **481 programmes-années uniques**, sans double comptage.
- Les cas non promus restent tracés : 239 ne se rapprochent pas dans la tolérance de 0,1 %, 297 ont une mission historique ambiguë, 52 n’ont pas de tableau reconnu et 9 n’ont pas de ligne datée reconnue. Ces nombres décrivent les limites du parseur et du rapprochement ; ils ne prouvent pas l’absence des documents.
- Validation : **222 tests Docker réussis**. L’API locale 2017–2022 en CP renvoie 5 716 observations, 4 399 preuves, 2 102 totaux et 481 rapprochements ; `/readyz` renvoie HTTP 200.
- Le conteneur Web local est actif sur `http://127.0.0.1:8552`. L’image locale du moteur de recherche `lexmachine-bge-m3-runtime` manque depuis le déplacement de Docker ; cette restauration relève de l’audit extensif suivant. La base vectorisée n’a pas été relancée et la version HTTPS publique reste inchangée.
