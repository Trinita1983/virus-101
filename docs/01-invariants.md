# Phase 1b : invariants de la base

Rédigé le 2026-10-13, après la revue du schéma (`docs/01b-arbitrage.md`). Chaque invariant a un numéro, repris dans les commentaires de `db/schema.sql`. Second passage le même jour, après réception du rapport du relecteur : I2 et I33 passent en SQL, I25 couvre `value_status`, I50 à I59 sont ajoutés. Le 2026-10-14 : I53 et I54 révisés, I60 ajouté, I26 et I50 vérifiés par la relecture des bruts (D30, D31).

## Règle de placement (décision D25)

1. **SQL** quand la règle s'écrit sur les colonnes d'une ligne (`CHECK`), comme une unicité (index unique, partiel ou sur expression) ou comme une clé étrangère, éventuellement composite, sur des colonnes **déjà présentes**. La base refuse alors l'écriture, quel que soit le code qui écrit (pipeline ou session `sqlite3` manuelle). Les fonctions de date et `json_valid` sont permises dans ces `CHECK` (D15 révisée) : ce sont des validations propres à SQLite, remplacées en PostgreSQL par les types `TIMESTAMPTZ`, `DATE`, `JSONB` et par `EXTRACT`.
2. **Python, avec un test nommé**, dans les autres cas. Il y a deux raisons de ne pas mettre la règle en SQL :
   - il faudrait un trigger (refusé par D15 : non portable tel quel vers PostgreSQL, logique cachée hors du code testé) ;
   - il faudrait dénormaliser, par exemple copier `source_code` ou `period_type` dans les ~500 000 lignes d'`observations` pour écrire une clé composite. La petite table `report_versions` est l'exception : y recopier `source_code` et `external_id` ne coûte presque rien.
3. **Vérification avant envoi** : si une règle Python est vérifiable après coup, elle a aussi une ligne dans la vue `controle_invariants`. À l'étape 6 de l'exécution quotidienne, la base n'est envoyée que si ces conditions sont toutes remplies :
   - `PRAGMA integrity_check` = `ok` ;
   - `PRAGMA foreign_key_check` vide ;
   - `controle_invariants` vide ;
   - taille de l'asset compressé sous le seuil (I58).

   Une base incohérente peut donc exister dans le runner, mais jamais être publiée.

Colonnes des tableaux :
- **Où** : `SQL` (avec le type de contrainte), `Python + vue`, ou `Python` seul (non vérifiable après coup dans la base).
- **Vérification** : `CE-xx` est un contre-exemple de l'arbitrage et `Kn` une preuve du relecteur (constat *n*). Les deux sont rejoués par `db/check_invariants.py` (résultats dans `docs/01b-preuves.md`). Les noms `tests/...` sont ceux des tests à écrire en phase 2. Les cas des invariants SQL deviendront le test paramétré `tests/test_schema.py::test_contre_exemple[<code>]`, qui réutilisera les listes `CASES` et `REVIEW_CASES` du script.

## 1. Général

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I1 | Chaque connexion active les clés étrangères (`PRAGMA foreign_keys = ON`). Sans cela, toutes les clés étrangères, dont les clés composites I12 à I17, sont inertes | Python : fabrique de connexion unique | SQLite n'a pas de réglage persistant pour cela | `tests/test_db.py::test_connexion_active_les_cles_etrangeres` ; contrôle `PRAGMA foreign_key_check` ; CE-G1 |
| I2 | Horodatages en UTC, forme exacte `YYYY-MM-DDTHH:MM:SSZ`, date et heure valides ; dates `YYYY-MM-DD` valides | SQL `CHECK (x IS strftime('%Y-%m-%dT%H:%M:%SZ', x))` et `CHECK (x IS date(x))` ; Python : conversion en UTC avant insertion, par une seule fonction | `LIKE` est insensible à la casse et `_` accepte tout caractère (K11a). `strftime` renvoie NULL ou une autre chaîne pour une date impossible, une minuscule, un fuseau ou une fraction de seconde | K11a, K11b ; `tests/test_db.py::test_horodatage_converti_en_utc` |
| I3 | Aucune suppression physique de données métier ; seule la purge vide les corps de `raw_payloads` | Python | Interdire `DELETE` exige un trigger | `tests/test_db.py::test_aucun_delete_hors_purge` (analyse des requêtes du code) |

## 2. Exécutions et écart 0 (point A, décision D24)

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I4 | `en_cours` ⇔ `finished_at` NULL ; `finished_at ≥ started_at` ; `echec` ou `partiel` ⇒ `error_kind` | SQL `CHECK` | Une ligne | `tests/test_schema.py::test_contrainte[I4]` |
| I5 | Au plus une exécution `en_cours` par source | SQL index unique partiel | Unicité | CE-A7 |
| I6 | Aucune exécution `en_cours` dans une base envoyée | Python + vue | L'état `en_cours` est légitime pendant l'exécution, seul l'état final est fautif | `tests/test_pipeline.py::test_echec_de_source_ferme_l_execution` ; CE-A8 |
| I7 | `succes` ou `inchange` ⇒ `seen_count = expected_count` quand les deux sont connus | SQL `CHECK` | Une ligne | CE-A4 |
| I8 | Exécution OMS complète ⇒ `expected_count` et `seen_count` renseignés, et `Id` reçus tous distincts (sinon exécution `partiel`, `error_kind = 'controle'`) | SQL `CHECK` (comptages renseignés) ; Python (`Id` distincts) | Les comptages tiennent sur une ligne ; l'unicité des `Id` reçus n'existe qu'en mémoire pendant la pagination | CE-A6 ; `tests/test_oms.py::test_pagination_complete_sans_doublon` |
| I9 | **Écart 0** : pour la dernière exécution OMS non échouée, si elle est complète, le nombre de DON dont `last_seen_run_id` est cette exécution est égal à `seen_count` | Python + vue | Compte des lignes d'une autre table | `tests/test_oms.py::test_ecart_zero_sur_les_presents` ; CE-A1, CE-A5 |
| I10 | **Retrait** : `removed_run_id` est la 3e exécution OMS complète postérieure à `last_seen_run_id`, NULL s'il y en a moins de 3. Une exécution partielle ne compte pas. Un DON qui réapparaît redevient présent (`removed_run_id` NULL) | SQL `CHECK` (`removed_run_id > last_seen_run_id`) + Python + vue (`reports_presence`) | Compter des exécutions est une règle entre tables ; la partie « postérieur » s'écrit sur la ligne | `tests/test_oms.py::test_retrait_a_la_troisieme_absence`, `::test_execution_partielle_ne_compte_pas`, `::test_reapparition_annule_le_retrait` ; CE-A1, CE-A2, CE-A3 |
| I11 | `absent_count`, `removed_count`, `reappeared_count` de l'exécution décrivent l'état de `reports_presence` à la fin de cette exécution | Python seul | Photo à un instant : une réapparition ultérieure la rend non recalculable | `tests/test_oms.py::test_compteurs_d_absence_journalises` |

## 3. Références entre sources (point B)

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I12 | `raw_payloads.first_run_id` est une exécution de la même source | SQL clé composite `(first_run_id, source_code)` | Colonnes déjà présentes | CE-X3 |
| I13 | `reports.raw_payload_id` et `reports.figures_payload_id` désignent une version brute **de ce DON** (même source, `resource_key = external_id`) | SQL clé composite `(…, source_code, external_id)` → `raw_payloads (id, source_code, resource_key)` | Colonnes déjà présentes | CE-X1, CE-X2 |
| I14 | `first_seen_run_id`, `last_seen_run_id`, `removed_run_id` sont des exécutions de la même source ; `first ≤ last` | SQL clés composites + `CHECK` | Colonnes déjà présentes | CE-X6 |
| I15 | `observations.run_id` et `observations.raw_payload_id` viennent de la source de la série | Python + vue | Une clé composite exigerait de copier `source_code` dans chaque observation | `tests/test_observations.py::test_observation_rattachee_a_la_source_de_sa_serie` ; CE-X4, CE-X5 |
| I16 | `report_figures.raw_payload_id` est une version brute du même DON | Python + vue | Une clé composite exigerait de copier `source_code` et `external_id` dans chaque chiffre | `tests/test_chiffres.py::test_chiffre_rattache_a_une_version_de_son_don` ; CE-X7 |
| I17 | `report_figures.country_iso3` est un pays listé dans `report_countries` pour ce rapport (NULL = ensemble du rapport) | SQL clé composite `(report_id, country_iso3)` | Colonnes déjà présentes | CE-X8 |
| I18 | Type d'alerte ↔ référence : `anomalie` ⇔ `anomaly_id` ; `nouveau_rapport`, `rapport_retire` ⇔ `report_id` ; incidents de source ⇒ `run_id` | SQL `CHECK` | Une ligne | `tests/test_schema.py::test_contrainte[I18]` |

## 4. Révisions des observations (point B)

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I19 | `(series_id, period_start, version)` unique ; `version ≥ 1` | SQL `UNIQUE`, `CHECK` | Unicité | `docs/01-validation.md` §4.4 |
| I20 | Au plus une version ouverte (`valid_to` NULL) par point | SQL index unique partiel | Unicité | `docs/01-validation.md` §4.4 |
| I21 | Versions numérotées 1..n sans trou | Python + vue | Règle entre lignes | `tests/test_observations.py::test_versions_numerotees_sans_trou` ; CE-R2 |
| I22 | Chaque version fermée l'est à l'instant exact où la suivante s'ouvre (`valid_to = valid_from` suivant) ; la dernière version est ouverte. Une valeur retirée par la source donne une nouvelle version `value` NULL, jamais une fermeture sans suite. Avec I20, chaque date a au plus une valeur connue, sans trou | Python + vue | Règle entre lignes (trigger refusé) | `tests/test_observations.py::test_fermeture_egale_ouverture_suivante`, `::test_retrait_cree_une_version_nulle` ; CE-R1, CE-R3 |
| I23 | `valid_to > valid_from` (strict) : une version de durée nulle serait invisible à toute date | SQL `CHECK` | Une ligne | CE-R4 |
| I24 | `valid_from` = `started_at` de l'exécution `run_id` (vintage reproductible) | Python + vue | Règle entre tables | `tests/test_observations.py::test_valid_from_egale_debut_d_execution` ; CE-R9 |
| I25 | Deux versions consécutives diffèrent sur un champ versionné (`value`, `value_low`, `value_up` ou `value_status`) | Python + vue | Règle entre lignes | `tests/test_observations.py::test_valeur_inchangee_ne_cree_pas_de_version` ; CE-R5 |
| I26 | **Ajout seul** : la seule mise à jour permise sur `observations` est `valid_to` de NULL vers une valeur | Python + contrôle de relecture des bruts (D31) | Un trigger serait nécessaire (écarté) ; la relecture compare chaque version au brut qu'elle cite (I60) | `tests/test_observations.py::test_ecriture_par_ajout_seul`, `tests/test_controle.py::test_relecture_detecte_valeur_reecrite` ; CE-R8 |
| I27 | `value` NULL ⇒ bornes NULL ; `value_low ≤ value ≤ value_up` | SQL `CHECK` | Une ligne | CE-R6 |
| I28 | Anomalie `ouverte` ⇒ version courante ; `remplacee` ⇒ version fermée | Python + vue | Règle entre tables | `tests/test_detection.py::test_revision_remplace_l_anomalie` ; CE-R7 |
| I29 | `anomalies.observed_value` = `value` de la version évaluée ; `observed_value > threshold_value` | Python + vue (égalité) ; SQL `CHECK` (seuil) | L'égalité est entre tables, le seuil sur la ligne | `tests/test_detection.py::test_anomalie_reprend_la_valeur_observee` ; CE-R10 |

## 5. Semaines ISO (point B)

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I30 | `iso_year` entre 1950 et 2100 (refuse un `YYYYWW` Sentiweb rangé tel quel) ; `iso_week` entre 1 et 53 | SQL `CHECK` | Une ligne | CE-W1 |
| I31 | `iso_week` NULL ⇔ série annuelle (`series.period_type = 'annee'`) | Python + vue | `period_type` est dans `series` ; une clé composite exigerait de le copier dans chaque observation | `tests/test_semaines.py::test_type_de_periode_coherent` ; CE-W2, CE-W3 |
| I32 | Point annuel : `period_start = 'AAAA-01-01'`, `period_end = 'AAAA-12-31'`, `AAAA = iso_year` | SQL `CHECK` (concaténation de texte, sans fonction de date) | Une ligne | CE-W4 |
| I33 | Point hebdomadaire : `period_start` = lundi de la semaine ISO `(iso_year, iso_week)` ; la semaine 53 n'est acceptée que pour une année ISO qui en compte 53 ; `period_end = period_start + 6 jours`. Avec I20, deux points courants ne peuvent donc pas porter la même semaine | SQL `CHECK` : lundi (`strftime('%w')`), fin (`date(…, '+6 days')`), année et semaine ISO lues sur le jeudi de la semaine. Python (`date.fromisocalendar`) pour calculer les périodes | Une ligne. Formule vérifiée contre `date.isocalendar()` pour tous les lundis de 1990 à 2030 | CE-W5 à CE-W8, K6a, K6b ; `tests/test_semaines.py::test_lundi_de_la_semaine_iso`, `::test_semaine_53_refusee_si_annee_a_52_semaines`, `::test_annee_iso_differente_de_l_annee_civile` |
| I34 | Lecture des semaines des sources : Sentiweb `YYYYWW` → `(iso_year, iso_week)` ; Odissé : `semaine` (`AAAA-Sss`) et `date_complet` désignent la même semaine, sinon l'exécution échoue (`error_kind = 'format'`) | Python | Règle de lecture, avant toute écriture | `tests/test_sources.py::test_semaine_sentiweb`, `::test_odisse_semaine_et_date_complet_concordent` |

## 6. Chiffres des rapports (point D, décision D23)

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I35 | Méthode `llm` ⇒ statut `incertain` ou `valide`, jamais `auto` (règle de CONTEXTE) | SQL `CHECK` | Une ligne | CE-D3 |
| I36 | Un seul chiffre par (version brute, rapport, pays ou ensemble, mesure, définition, période) | SQL index unique sur expression (`COALESCE` pour que deux NULL se heurtent) | Unicité | CE-D4 ; `tests/test_chiffres.py::test_un_chiffre_par_pays_et_par_mesure` (CE-D1) |
| I37 | `value ≥ 0` ; `period_start ≤ as_of` ; `evidence` non vide | SQL `CHECK` | Une ligne | `tests/test_schema.py::test_contrainte[I37]` |
| I38 | `figures_payload_id` et `figures_extractor_version` sont renseignés ensemble (NULL = jamais traité) | SQL `CHECK` | Une ligne | `tests/test_schema.py::test_contrainte[I38]` |

## 7. Classification

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I39 | `classification_status = 'non_classe'` ⇔ `disease_code` NULL | SQL `CHECK` | Une ligne | `tests/test_schema.py::test_contrainte[I39]` |
| I40 | Au plus un pays principal par rapport ; code en 3 lettres majuscules ; code présent dans la liste ISO 3166-1 alpha-3 | SQL index unique partiel, `CHECK` ; Python (liste) | La liste ISO n'est pas en base | `tests/test_classification.py::test_code_iso3_existant` |
| I41 | `geo_scope = 'pays'` ⇒ exactement un pays, principal ; `multi_pays` ⇒ au moins deux pays | Python + vue | Compte des lignes d'une autre table | `tests/test_classification.py::test_portee_geographique_et_pays_concordent` |

## 8. Bruts

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I42 | `(source_code, resource_key, sha256)` unique ; corps en clair ou compressé (un seul), ou aucun après purge | SQL `UNIQUE`, `CHECK` | Unicité, une ligne | `docs/01-validation.md` §4.4 (relance idempotente) |
| I43 | `sha256` et `byte_size` portent sur le contenu non compressé | Python | Calcul d'empreinte | `tests/test_bruts.py::test_empreinte_sur_contenu_non_compresse` |

## 9. Alertes (point C, décision D19)

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I44 | `(channel, dedup_key)` unique | SQL `UNIQUE` | Unicité | CE-C1 |
| I45 | `dedup_key` déterministe : type + identifiant de l'objet (`Id` OMS, point de série et version, source et jour), jamais l'heure d'envoi ni le numéro de tentative | Python | Construction de la clé | `tests/test_alertes.py::test_cle_de_dedup_deterministe` |
| I46 | Une alerte est écrite (`a_envoyer`) dans la même transaction que l'événement qui la déclenche, donc avant tout appel Telegram. Elle ne passe à `envoyee` qu'après une réponse `ok` de Telegram | Python | Ordre des opérations | `tests/test_alertes.py::test_alerte_ecrite_avec_son_evenement`, `::test_alerte_journalisee_avant_envoi` ; CE-C2 |
| I47 | `envoyee` ⇔ `sent_at` ; `envoyee` ou `echec` ⇒ `attempts ≥ 1` ; `echec` ⇒ `last_error` ; `sent_at ≥ created_at` | SQL `CHECK` | Une ligne | CE-C3, CE-C4, CE-C5 |

## 10. Séries

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I48 | Clé naturelle `(source_code, dataset, metric, geo_level, geo_code, age_group)` unique | SQL `UNIQUE` | Unicité | `tests/test_schema.py::test_contrainte[I48]` |
| I49 | Une série Sentinelles n'a jamais `geo_code = 'FR'` (la métropole est `FR-MET`, D22) | SQL `CHECK` | Une ligne (le code de source est écrit dans la contrainte, comme pour I8) | CE-S1 |

## 11. Ajouts après le rapport du relecteur

| N° | Invariant | Où | Pourquoi là | Vérification |
|---|---|---|---|---|
| I50 | **Révision** : une modification d'un champ versionné (`value`, `value_low`, `value_up`, `value_status`) crée une version ; une republication identique, même avec un autre `source_version`, n'en crée pas | Python + contrôle de relecture des bruts (D31) | La relecture du dernier brut de chaque jeu, à chaque exécution, compare la donnée reçue à la série courante | K4 ; `tests/test_observations.py::test_revision_des_bornes_cree_une_version`, `::test_republication_identique_sans_version`, `tests/test_controle.py::test_relecture_detecte_revision_manquee` |
| I51 | **Chronologie des contenus d'un DON** (`report_versions`) : chaque version désigne un brut de ce DON et une exécution de sa source ; versions 1..n ; chaque version change de contenu ; exécutions croissantes ; la dernière version est `reports.raw_payload_id` ; tout DON a au moins une version | SQL clés composites, clé primaire, `UNIQUE (report_id, run_id)` ; Python + vue pour le reste | Provenance sur des colonnes présentes ; ordre et dernière version entre lignes | CE-V1, K5 ; `tests/test_oms.py::test_changement_de_contenu_cree_une_version` |
| I52 | Un DON a changé si le hash reçu diffère de celui du **contenu courant** (`reports.raw_payload_id`), et non s'il est absent de l'archive. Un retour à un contenu déjà archivé crée une version qui pointe vers l'ancien brut | Python seul | Décision prise à la lecture de l'API | K5 ; `tests/test_oms.py::test_retour_a_un_contenu_anterieur_cree_une_version` |
| I53 | Seuls les exports CSV d'Odissé peuvent être purgés : JSON OMS, réponses Sentinelles et réponses du catalogue Odissé (preuves de licence) sont conservés sans limite | SQL `CHECK (purged_at IS NULL OR (source_code = 'spf_odisse' AND content_type = 'text/csv'))` | Une ligne | CE-P1 |
| I54 | **Licence par jeu** : toute série cite un jeu de `datasets` ; un jeu publiable a une licence déclarée et une fenêtre de publication ouverte (`publishable_since`, sans `not_publishable_since`) ; une preuve `catalogue_api` cite un brut de la même source ; aucune observation d'un jeu jamais publiable, ni collectée après la fin de sa fenêtre (les observations antérieures restent, D30) | SQL clés étrangères et `CHECK` ; Python + vue (observations) | La base est publique : stocker des données d'un jeu non publiable revient à les publier | K9, CE-L1, CE-L2 ; `tests/test_sources.py::test_jeu_sans_licence_non_ingere`, `::test_licence_relue_a_chaque_execution`, `::test_licence_retiree_garde_les_donnees_anterieures` |
| I55 | `value` NULL ⇔ `value_status` ∈ {`retiree`, `non_diffusee`, `secret_statistique`, `absente_sans_motif`} ; la provisionalité (`provisoire`) est un statut de la valeur, distinct de la fiabilité de la source | SQL `CHECK` | Une ligne | K10b |
| I56 | `value` et `value_low` ne descendent pas sous `series.value_min` (NULL = pas de borne ; aucune valeur n'est ramenée à 0) | Python + vue | Règle entre tables | K10c ; `tests/test_observations.py::test_valeur_dans_le_domaine_de_la_serie` |
| I57 | `report_figures.as_of` vient du texte du DON, jamais de `published_at` ni de la date de collecte. Les chiffres d'un DON ne sont ni additionnés entre définitions, pays ou dates, ni comparés aux séries | Python seul | Règle d'extraction et d'export | K2 ; `tests/test_chiffres.py::test_as_of_jamais_deduit_de_la_publication`, `tests/test_export.py::test_chiffres_don_jamais_compares_aux_series` |
| I58 | Taille de l'asset compressé : alerte au-delà de 1 Gio, envoi bloqué au-delà de 1,5 Gio (limite d'un asset de release : 2 GiB) ; `VACUUM` après chaque purge | Python (contrôle avant envoi) | Mesure du fichier, hors base | K13 ; `tests/test_pipeline.py::test_taille_de_l_asset_bornee` |
| I59 | `anomalies.parameters` est un JSON valide | SQL `CHECK (json_valid(parameters))` | Une ligne | K14b |
| I60 | Chaque version d'observation cite le brut d'où vient sa valeur, de la source de sa série (I15) | SQL `NOT NULL` ; vue (même source, I15) | Condition de la relecture (D31) | `docs/01-validation.md` §3 ; `tests/test_observations.py::test_version_cite_son_brut` |

## 12. Bilan

| Placement | Invariants |
|---|---|
| SQL seul | I4, I5, I7, I12, I13, I14, I17, I18, I19, I20, I23, I27, I30, I32, I33, I35, I36, I37, I38, I39, I42, I44, I47, I48, I49, I53, I55, I59 (28) |
| SQL et Python | I2, I8, I10, I29, I40, I51, I54, I60 (8) |
| Python + vue `controle_invariants` | I6, I9, I15, I16, I21, I22, I24, I25, I28, I31, I41, I56, plus I10, I29, I51 et I54 (12 en propre) |
| Python + contrôle de relecture des bruts (D31) | I26, I50 (2) |
| Python seul (test ; I1 et I58 aussi contrôlés avant envoi) | I1, I3, I11, I34, I43, I45, I46, I52, I57, I58 (10) |

Trois invariants protègent l'historique publié sans pouvoir être imposés par la base :
- I3 (aucune suppression). Une suppression laisse souvent une trace : une version supprimée au milieu d'une chaîne casse I21 ou I22, et un brut ou une exécution supprimés cassent une clé étrangère ;
- **I26** (ajout seul). Une valeur réécrite ne laisse aucune trace (CE-R8) ;
- **I50** (toute révision crée une version). Une révision manquée ne laisse pas de trace non plus (K4, phase 1).

I26 et I50 sont vérifiés par la relecture des bruts (D31, décidée le 2026-10-14), possible parce que chaque version cite son brut (I60). Risque résiduel : versions dont l'export Odissé est purgé (R15).

Méta-test : `tests/test_controle.py::test_vue_controle_vide_sur_base_coherente`. Une vue qui produit de fausses alertes bloquerait chaque envoi. Les deux états de départ de `db/check_invariants.py` le vérifient déjà : 0 ligne.
