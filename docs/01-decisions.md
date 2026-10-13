# Phase 1 : décisions, questions ouvertes et risques

Rédigé le 2026-10-13. Chaque décision renvoie aux faits de `docs/00-sources.md`, `docs/01-architecture.md` et `docs/01-validation.md`.

## 1. Décisions

### Stockage et exécution

| # | Décision | Alternatives écartées | Pourquoi |
|---|---|---|---|
| D1 | **Base SQLite dans une release GitHub** (`db`) : asset courant compressé, plus un instantané par semaine | Fichier commité dans le dépôt ; `.gz` commité ; artefacts ou cache Actions ; PostgreSQL hébergé | Volume mesuré : 82 Mo pour le périmètre v1, au-dessus de l'avertissement GitHub (50 MiB) et proche du blocage (100 MiB). Un commit quotidien d'un binaire gonfle l'historique. Les artefacts et le cache ne sont pas durables. Un PostgreSQL hébergé contredit « zéro serveur ». Release : moins de 2 GiB par fichier, pas de limite totale (vérifié). Détail dans architecture §5 |
| D2 | **Une exécution quotidienne** (`schedule` à 05:47 UTC), sérialisée par `concurrency` | Plusieurs exécutions par jour ; déclenchement par source | CONTEXTE : quotidien. Les sources publient au mieux chaque semaine. L'horaire hors début d'heure suit la documentation GitHub. La sérialisation évite deux écritures concurrentes sur la base |
| D3 | **Une transaction par source**, l'échec d'une source n'arrête pas les autres ni la publication du site | Tout ou rien sur l'ensemble des sources | Une panne de Sentinelles ne doit pas bloquer l'OMS. Le site affiche les dernières données avec leur date |

### Modèle de données

| # | Décision | Alternatives écartées | Pourquoi |
|---|---|---|---|
| D4 | **Révisions par versions ajoutées** dans `observations` (`version`, `valid_from`, `valid_to`) avec un index unique partiel (une seule version courante) | Écraser la valeur ; table d'historique séparée ; versions sans `valid_to`, lues par fonction de fenêtre | Écraser perd l'historique et fausse tout backtest futur. Une table séparée double les écritures à synchroniser. `valid_from`/`valid_to` donnent la valeur connue à une date D par une requête simple (démontré dans la validation §4.2) |
| D5 | **`reports` = état courant ; historique des DON dans `raw_payloads`** | Versionner `reports` comme `observations` | Un DON modifié est un texte retouché, pas une série révisée. Le brut horodaté suffit pour retracer, avec une ligne par contenu distinct (sha256) |
| D6 | **Identité d'un DON : `Id`** (GUID) ; `DonId` stocké sans contrainte d'unicité ; `UrlName` unique | `DonId` ou `UrlName` comme clé | Décision de phase 0. `Id` est unique sur 3199/3199 ; `DonId` a 14 doublons. L'unicité de `UrlName`, vérifiée sur les 3199, est imposée pour qu'un changement chez l'OMS fasse échouer l'ingestion au lieu de passer inaperçu |
| D7 | **Date de publication = `PublicationDateAndTime`**, avec un drapeau `date_quality` | `PublicationDate` ; date déduite de `UrlName` | `PublicationDate` est faux pour 1360 enregistrements. `PublicationDateAndTime` est cohérent avec l'année du `DonId` sauf dans 11 cas, et avec le titre sauf dans 2. `UrlName` a trois formes différentes (architecture §3.4) |
| D8 | **Titre = `OverrideTitle` si `UseOverrideTitle` et non vide, sinon `Title`** | Toujours `Title` | C'est le `<h1>` affiché sur who.int (vérifié sur 2 DON). 170 enregistrements ont un `OverrideTitle` différent de `Title`, dont un « Chikungunya - France » dont le `Title` cite Mayotte et La Réunion |
| D9 | **Chiffres en colonnes de `reports`** (un couple cas/décès, date « au », méthode, statut, phrase source). Un `CHECK` interdit le statut `auto` pour une extraction LLM | Table `report_figures` (plusieurs chiffres par pays et par définition de cas) | CONTEXTE demande cas et décès avec un statut. Une table dédiée serait plus fidèle aux DON multi-pays, mais c'est de la complexité avant d'en avoir besoin. À revoir en phase 3 si l'extraction le justifie |
| D10 | **Table `report_countries`** (ISO 3166-1 alpha-3, au plus un pays principal) en plus de `geo_scope` | Une seule colonne pays ; liste JSON dans `reports` | Des DON couvrent plusieurs pays. Une colonne unique perd l'information ; le JSON est moins portable et moins indexable |
| D11 | **Table `series`** séparée d'`observations` (écart à la liste de tables demandée) | Répéter dans chaque observation source, jeu, mesure, zone et âge | La clé naturelle d'un point a 6 colonnes. Une série la porte une fois ; détection d'anomalies, unicité et requêtes travaillent sur `series_id`. Le niveau géographique fait partie de la clé, car les codes INSEE de région et de département se recouvrent (`11`) |
| D12 | **Table `diseases`** (référentiel commun) | Code de maladie en texte libre | Croiser l'OMS et la France exige un vocabulaire commun. Une clé étrangère empêche les variantes de saisie |
| D13 | **Valeurs énumérées en `CHECK (... IN (...))`**, en français sans accents (`valide`, `incertain`, `officielle`) | Tables de référence ; types `ENUM` PostgreSQL | Listes courtes et stables ; portable tel quel ; aucun problème d'encodage |

### Bruts, types et portabilité

| # | Décision | Alternatives écartées | Pourquoi |
|---|---|---|---|
| D14 | **Bruts dédupliqués par sha256** ; JSON OMS en clair (`body_text`), exports volumineux compressés (`body_gzip`) ; corps purgeables (`purged_at`) en gardant les métadonnées | Tout garder en clair ; bruts hors base (fichiers en release) | En clair, le JSON OMS reste lisible et interrogeable : 15 Mo au total. Les exports Odissé sont de gros fichiers re-exportés chaque semaine. La purge limite la croissance sans perdre la trace (hash, date, URL) |
| D15 | **Tables `STRICT`, dates en `TEXT` ISO 8601 UTC, aucune fonction de date SQL, aucun trigger, aucun `DEFAULT` calculé** | Types `DATE`/`TIMESTAMP` déclarés (affinité NUMERIC en SQLite) ; triggers pour fermer les versions | `STRICT` refuse un mauvais type, ce qui protège un mainteneur seul. Sans triggers ni fonctions de date, le schéma et les requêtes restent portables (architecture §6) et la logique est testable en Python |
| D16 | **Version de schéma par `PRAGMA user_version`** et fichiers de migration numérotés, appliqués par un petit script | Alembic ou un ORM | Pas de sur-ingénierie pour un seul mainteneur et un seul moteur en v1. À remplacer par une table de migrations lors d'un passage à PostgreSQL |

### Site, alertes et périmètre

| # | Décision | Alternatives écartées | Pourquoi |
|---|---|---|---|
| D17 | **Le site lit des exports JSON produits par Python**, pas la base SQLite | Lire SQLite depuis Astro (module natif Node) | Garde le côté Node simple, sans dépendance native ; contrôle exactement ce qui est publié ; respecte la limite Cloudflare de 25 MiB par fichier |
| D18 | **Déploiement Cloudflare Pages par envoi direct** (`wrangler`) depuis Actions | Intégration Git de Cloudflare (build chez Cloudflare) | Le build a besoin de la base, téléchargée dans Actions. Hébergeur choisi en phase 0 |
| D19 | **Alertes dédupliquées par `(channel, dedup_key)`** ; envoi avant l'envoi de la base | Envoi après l'envoi de la base | Si l'envoi de la base échoue après celui d'une alerte, la relance renverra l'alerte : un doublon Telegram, rare et sans gravité. L'ordre inverse peut perdre une alerte |
| D20 | **Anomalies : production seulement, hausses seulement** (`CHECK observed_value > threshold_value`). Résultats de backtest hors base | Stocker aussi les backtests (colonne `mode`) | Les backtests sont des analyses ponctuelles (rapports dans `docs/`). Les mélanger aux anomalies de production risquerait des alertes erronées |
| D21 | **Aucune donnée personnelle dans la base** | Stocker abonnés et destinataires | La base est publique (release d'un dépôt public). Les e-mails de la v2 (double opt-in, RGPD) iront dans un stockage séparé, à concevoir en v2 |
| D22 | **Zones géographiques distinctes : `FR` (France entière) et `FR-MET` (métropole)** | Un seul code `FR` | Sentinelles ne couvre que la métropole (vérifié en phase 0). Mélanger les deux fausserait toute comparaison |

## 2. Questions ouvertes

| # | Question | Proposition par défaut |
|---|---|---|
| Q1 | Rétention des exports bruts Odissé (les plus volumineux) : combien de temps garder le contenu avant purge ? | 26 semaines ; hash, URL et date gardés sans limite |
| Q2 | Périmètre géographique et classes d'âge v1 pour Odissé (`départements` ? toutes les classes d'âge ?) | National et régions, toutes les classes d'âge au national, « tous âges » seulement par région. Volume mesuré sur l'hypothèse haute |
| Q3 | Si un DON est modifié par l'OMS après validation humaine de ses chiffres, faut-il repasser le statut à `incertain` ? | Oui si un des champs texte a changé |
| Q4 | Faut-il une surveillance externe du workflow (alerte si aucune exécution depuis 48 h) ? Elle seule détecte un arrêt complet | Oui, avec un service gratuit de type « dead man's switch » : choix du service à valider, car c'est une dépendance tierce |
| Q5 | Classement de fiabilité de Sentinelles : `officielle` ou `semi_officielle` ? | `officielle` (réseau de surveillance national INSERM / Sorbonne Université, partenaire de Santé publique France) |
| Q6 | Licence du code du dépôt (public, sans fichier `LICENSE` aujourd'hui) | À choisir par vous (par exemple MIT ou AGPL) ; ne concerne pas les données |
| Q7 | Données Sentinelles de moins de 3 semaines (point ouvert depuis la phase 0) : l'API n'expose une semaine qu'avec le bulletin, ce qui semble respecter la condition | Les afficher dès qu'elles sont dans l'API, marquées « provisoires » ; à confirmer avec le réseau Sentinelles |

## 3. Risques

| # | Risque | Effet | Parade |
|---|---|---|---|
| R1 | **Backtest optimiste** : aucune archive des valeurs « telles que connues à l'époque » n'existe pour 2024-25 ; le backtest se fera sur des données déjà révisées | Taux de faux positifs mesuré plus bas que la réalité | Le dire dans le rapport de backtest ; collecter les versions dès la mise en production (le schéma le permet, D4) ; refaire la mesure après une saison réelle |
| R2 | Quota Sentinelles : 15 requêtes / 600 s **par IP**, et les runners GitHub partagent leurs IP | 429 sans faute de notre part ; blocage possible | 9 requêtes au plus par exécution, appel `/version` d'abord, aucun nouvel essai sur 429 |
| R3 | `schedule` désactivé après 60 jours sans activité (dépôt public, vérifié) ; avec la base en release, aucun commit n'est automatique | Plus aucune mise à jour, sans alerte | Commit hebdomadaire de `data/etat.json`. Non vérifié : qu'un commit du bot compte comme activité. À tester, et Q4 |
| R4 | Exécution planifiée retardée ou abandonnée par GitHub en forte charge (vérifié) | Un jour sans mise à jour | Horaire décalé ; seuils de péremption en jours, pas en heures |
| R5 | **Perte ou corruption de la base**, qui est la seule archive des révisions | Historique des versions perdu ; seule la dernière version est récupérable aux sources | Instantané hebdomadaire ; contrôle d'intégrité avant chaque envoi ; procédure de restauration écrite en phase 5 |
| R6 | La base publique redistribue des textes OMS (usage non commercial avec citation) et des données Sentinelles (citation sans modification) | Manquement aux conditions de réutilisation | Fichier de mentions joint à la release ; table `sources.attribution` affichée sur le site ; v1 sans publicité (décision de phase 0) |
| R7 | Contrainte `UNIQUE (source_code, slug)` : un renommage côté OMS fait échouer l'ingestion | Ingestion OMS bloquée jusqu'à correction | Voulu (échec visible plutôt qu'erreur silencieuse) ; alerte `format_modifie` |
| R8 | **Unités Odissé non vérifiées** (`taux_passages_grippe_sau` : pour 10 000 passages ? pour 100 000 habitants ?) | Chiffres mal libellés sur le site | Lire `ira-methodologies` et la documentation des jeux en phase 2, avant de remplir `series.unit` |
| R9 | Odissé « France » : DROM inclus ou non (non vérifié) | Comparaison erronée avec Sentinelles (métropole) | `FR` et `FR-MET` distincts (D22) ; vérifier en phase 2 |
| R10 | Pagination OMS : 733 enregistrements partagent un horodatage | Pages qui se chevauchent, donc doublons ou manques | Tri secondaire sur `Id`, à tester en phase 2 ; le contrôle `seen_count = expected_count` et l'unicité sur `Id` détectent l'erreur |
| R11 | Classification des maladies et pays de l'OMS à partir de titres libres (3 formats d'`UrlName`, titres variables) | DON non classés ou mal classés | Statut `non_classe` / `incertain` affiché ; taux de classification mesuré en phase 3. Pour « DON concernant la France », inclure les codes ISO des DROM (REU, MYT, GLP, MTQ, GUF) |
| R12 | Version de SQLite sur les runners GitHub (≥ 3.37 exigé par `STRICT`) non vérifiée | Échec du schéma en CI | Vérifier dès le premier workflow (phase 2) |
| R13 | L'envoi d'un asset de release remplace l'ancien de façon non atomique | Fenêtre où la base courante est absente ou partielle | Instantanés hebdomadaires ; vérification de taille et de hash après envoi |
