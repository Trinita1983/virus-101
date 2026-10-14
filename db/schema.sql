-- =============================================================================
-- Observatoire des maladies infectieuses : schéma de base, version 1
-- =============================================================================
-- Moteur : SQLite >= 3.39 (tables STRICT : 3.37 ; json_valid intégré : 3.38 ;
-- IS DISTINCT FROM dans les vues de contrôle : 3.39). Portable vers PostgreSQL :
-- voir la liste des divergences dans docs/01-architecture.md, section 6.
--
-- Conventions :
--   * Horodatages : TEXT ISO 8601 en UTC, forme exacte 'YYYY-MM-DDTHH:MM:SSZ'.
--     Dates : TEXT 'YYYY-MM-DD'. Ils sont fixés par le code Python, jamais par
--     une fonction SQL (pas de DEFAULT CURRENT_TIMESTAMP).
--   * Fonctions de date et JSON SQL : uniquement dans des CHECK de validation
--     (I2, I33, I59), jamais dans les requêtes (D15). Ces CHECK sont propres à
--     SQLite : en PostgreSQL, les types TIMESTAMPTZ, DATE et JSONB les remplacent,
--     et le CHECK du calendrier ISO est réécrit avec EXTRACT (architecture §6).
--     « x IS strftime(..., x) » refuse une date impossible, un fuseau autre que
--     Z, des minuscules et des fractions de seconde (strftime renvoie alors NULL
--     ou une autre chaîne).
--   * Booléens : INTEGER 0/1 avec CHECK.
--   * Valeurs énumérées : CHECK (... IN (...)), en français sans accents.
--   * Aucune suppression physique de données métier : on ferme des versions
--     (observations.valid_to) ou on marque (reports.removed_run_id).
--   * Aucun trigger (décision D15) : la logique (fermeture de version,
--     déduplication, retrait) est dans le code Python, en transaction.
--   * Aucune donnée personnelle : la base est publiée (release d'un dépôt public).
--
-- Invariants : chaque règle porte un numéro (I1, I2...) défini dans
-- docs/01-invariants.md. Une règle qui s'exprime sur les colonnes d'une ligne,
-- ou par une clé étrangère (éventuellement composite) sur des colonnes déjà
-- présentes, est écrite ici. Les autres (règles entre lignes ou entre tables)
-- sont appliquées par le code Python, couvertes par un test nommé, et vérifiées
-- par la vue controle_invariants, qui doit être vide avant tout envoi de la base.
--
-- SQLite n'applique les clés étrangères que si chaque connexion exécute (I1) :
PRAGMA foreign_keys = ON;


-- -----------------------------------------------------------------------------
-- sources : une ligne par fournisseur de données
-- -----------------------------------------------------------------------------
CREATE TABLE sources (
    code                  TEXT PRIMARY KEY,                -- 'oms_don', 'sentinelles', 'spf_odisse'
    name                  TEXT NOT NULL,
    publisher             TEXT NOT NULL,
    homepage_url          TEXT NOT NULL,
    api_base_url          TEXT,
    reliability           TEXT NOT NULL
        CHECK (reliability IN ('officielle', 'semi_officielle', 'presse', 'communautaire')),
    license_name          TEXT NOT NULL,
    license_url           TEXT NOT NULL,                   -- lien vers le texte officiel
    commercial_use        TEXT NOT NULL
        CHECK (commercial_use IN ('autorise', 'interdit', 'sur_autorisation', 'inconnu')),
    attribution           TEXT NOT NULL,                   -- mention exacte à afficher sur le site
    publication_frequency TEXT NOT NULL
        CHECK (publication_frequency IN ('quotidienne', 'hebdomadaire', 'annuelle', 'irreguliere')),
    max_staleness_days    INTEGER NOT NULL CHECK (max_staleness_days > 0),  -- au-delà : alerte « données périmées »
    is_active             INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    notes                 TEXT
) STRICT;


-- -----------------------------------------------------------------------------
-- diseases : référentiel commun aux rapports (OMS) et aux séries (France)
-- -----------------------------------------------------------------------------
CREATE TABLE diseases (
    code     TEXT PRIMARY KEY,                             -- 'grippe', 'cholera', 'mpox'...
    label_fr TEXT NOT NULL,
    label_en TEXT
) STRICT;


-- -----------------------------------------------------------------------------
-- ingestion_runs : une ligne par exécution d'ingestion d'une source
-- -----------------------------------------------------------------------------
-- Exécution OMS « complète » : statut 'succes' ou 'inchange' (pagination terminée,
-- seen_count = expected_count). Seules les exécutions complètes comptent pour le
-- retrait d'un DON absent (I10, décision D24).
CREATE TABLE ingestion_runs (
    id                INTEGER PRIMARY KEY,
    source_code       TEXT NOT NULL REFERENCES sources(code),
    started_at        TEXT NOT NULL CHECK (started_at IS strftime('%Y-%m-%dT%H:%M:%SZ', started_at)),
    finished_at       TEXT CHECK (finished_at IS strftime('%Y-%m-%dT%H:%M:%SZ', finished_at)),
    status            TEXT NOT NULL
        CHECK (status IN ('en_cours', 'succes', 'inchange', 'partiel', 'echec')),
    triggered_by      TEXT NOT NULL CHECK (triggered_by IN ('planifie', 'manuel', 'reprise')),
    code_version      TEXT NOT NULL,                       -- SHA git du code exécuté
    ci_run_url        TEXT,                                -- lien vers l'exécution GitHub Actions
    source_version    TEXT,                                -- Sentiweb : /version ; Odissé : data_processed
    expected_count    INTEGER CHECK (expected_count >= 0), -- OMS : @odata.count annoncé par l'API
    seen_count        INTEGER CHECK (seen_count >= 0),     -- enregistrements réellement reçus
    inserted_count    INTEGER NOT NULL DEFAULT 0 CHECK (inserted_count >= 0),
    updated_count     INTEGER NOT NULL DEFAULT 0 CHECK (updated_count >= 0),
    absent_count      INTEGER CHECK (absent_count >= 0),     -- OMS : DON non retirés en base, absents de l'API
    removed_count     INTEGER CHECK (removed_count >= 0),    -- OMS : DON retirés par cette exécution (3e absence)
    reappeared_count  INTEGER CHECK (reappeared_count >= 0), -- OMS : DON absents ou retirés, revenus dans l'API
    http_requests     INTEGER NOT NULL DEFAULT 0 CHECK (http_requests >= 0),
    http_retries      INTEGER NOT NULL DEFAULT 0 CHECK (http_retries >= 0),
    field_fingerprint TEXT,                                -- sha256 de la liste triée des champs reçus
    error_kind        TEXT
        CHECK (error_kind IN ('reseau', 'http', 'quota', 'format', 'validation', 'controle', 'autre')),
    error_message     TEXT,
    UNIQUE (id, source_code),                              -- cible des clés composites (I12, I14)
    CHECK ((status = 'en_cours') = (finished_at IS NULL)),                       -- I4
    CHECK (finished_at IS NULL OR finished_at >= started_at),                    -- I4
    CHECK (status NOT IN ('echec', 'partiel') OR error_kind IS NOT NULL),        -- I4
    -- I7 : une exécution réussie a reçu exactement ce que la source annonçait.
    CHECK (status NOT IN ('succes', 'inchange') OR expected_count IS NULL OR seen_count = expected_count),
    -- I8 : une exécution OMS complète porte ses deux comptages (sinon l'écart 0 n'est pas mesurable).
    CHECK (source_code <> 'oms_don' OR status NOT IN ('succes', 'inchange')
           OR (expected_count IS NOT NULL AND seen_count IS NOT NULL))
) STRICT;

CREATE INDEX ingestion_runs_by_source ON ingestion_runs (source_code, started_at);
-- I5 : au plus une exécution en cours par source.
CREATE UNIQUE INDEX ingestion_runs_one_running ON ingestion_runs (source_code) WHERE status = 'en_cours';


-- -----------------------------------------------------------------------------
-- raw_payloads : contenu brut archivé, dédupliqué par empreinte
-- -----------------------------------------------------------------------------
-- OMS : un enregistrement par DON et par version de contenu (resource_key = Id).
-- Sentiweb / Odissé : une réponse ou un export complet (resource_key = jeu).
-- Le hash porte sur le contenu non compressé (I43). Un contenu identique déjà
-- archivé n'est pas réinséré (relance idempotente). Conséquence : cette table
-- stocke des contenus, pas une chronologie. Une suite A -> B -> A n'y laisse que
-- deux lignes ; la chronologie des contenus d'un DON est dans report_versions
-- (D26), celle des séries dans observations.
-- Rétention (I53, D29) : seuls les exports CSV d'Odissé peuvent être purgés. Le
-- JSON OMS, les réponses Sentinelles et les réponses du catalogue Odissé (preuves
-- de licence, D30) sont conservés sans limite ; ils servent aussi au contrôle de
-- relecture (D31).
CREATE TABLE raw_payloads (
    id                 INTEGER PRIMARY KEY,
    source_code        TEXT NOT NULL REFERENCES sources(code),
    resource_key       TEXT NOT NULL,
    request_url        TEXT NOT NULL,
    content_type       TEXT NOT NULL,                      -- 'application/json', 'text/csv'
    sha256             TEXT NOT NULL CHECK (length(sha256) = 64),
    byte_size          INTEGER NOT NULL CHECK (byte_size >= 0),
    body_text          TEXT,                               -- contenu en clair (un DON : ~6,5 Ko en moyenne)
    body_gzip          BLOB,                               -- contenu compressé (exports volumineux)
    source_modified_at TEXT CHECK (source_modified_at IS strftime('%Y-%m-%dT%H:%M:%SZ', source_modified_at)),  -- OMS : LastModified
    first_run_id       INTEGER NOT NULL,
    retrieved_at       TEXT NOT NULL CHECK (retrieved_at IS strftime('%Y-%m-%dT%H:%M:%SZ', retrieved_at)),
    purged_at          TEXT CHECK (purged_at IS strftime('%Y-%m-%dT%H:%M:%SZ', purged_at)),  -- corps effacé par la rétention
    UNIQUE (source_code, resource_key, sha256),            -- I42
    UNIQUE (id, source_code, resource_key),                -- cible des clés composites (I13, I51)
    UNIQUE (id, source_code),                              -- cible de la clé composite de datasets (I54)
    -- I12 : le brut a été récupéré par une exécution de sa propre source.
    FOREIGN KEY (first_run_id, source_code) REFERENCES ingestion_runs (id, source_code),
    CHECK (                                                -- I42
        (purged_at IS NULL AND ((body_text IS NULL) <> (body_gzip IS NULL)))
        OR (purged_at IS NOT NULL AND body_text IS NULL AND body_gzip IS NULL)
    ),
    -- I53 : seuls les exports CSV d'Odissé peuvent être purgés.
    CHECK (purged_at IS NULL OR (source_code = 'spf_odisse' AND content_type = 'text/csv'))
) STRICT;


-- -----------------------------------------------------------------------------
-- reports : événements narratifs (OMS DON), état courant
-- -----------------------------------------------------------------------------
-- Une ligne par DON, mise à jour quand la source modifie le DON. Les contenus
-- sont dans raw_payloads (un par contenu distinct), leur chronologie dans
-- report_versions (D26) : raw_payload_id = contenu de la dernière version (I51).
-- Un DON a changé si le hash reçu diffère de celui de raw_payload_id (contenu
-- courant), et non s'il est absent de l'archive (I52).
-- Correspondance avec les champs réels de l'API OMS (fixtures/who_don_sample.json) :
--   external_id  <- Id                      (GUID, unique sur 3199/3199)
--   external_ref <- DonId                   (NON unique : 14 valeurs en doublon ; '' -> NULL)
--   slug         <- UrlName                 (unique sur 3199/3199)
--   title        <- OverrideTitle si UseOverrideTitle et non vide, sinon Title
--                   (règle vérifiée : c'est le <h1> affiché sur who.int)
--   published_at <- PublicationDateAndTime  (et non PublicationDate, faux pour 1360 enregistrements)
--   LastModified : dans raw_payloads.source_modified_at de la version courante
-- Présence dans l'API (décision D24) : last_seen_run_id = dernière exécution qui a
-- reçu ce DON. « Absent » = 1 ou 2 exécutions complètes sans lui ; « retiré » à la
-- 3e (removed_run_id). Calcul dans la vue reports_presence.
-- Les chiffres (cas, décès) sont dans report_figures (décision D23).
CREATE TABLE reports (
    id                    INTEGER PRIMARY KEY,
    source_code           TEXT NOT NULL REFERENCES sources(code),
    external_id           TEXT NOT NULL,
    external_ref          TEXT CHECK (external_ref <> ''),
    slug                  TEXT NOT NULL,
    url                   TEXT NOT NULL,
    title                 TEXT NOT NULL,
    summary               TEXT,                            -- texte brut (HTML retiré), pour l'affichage
    published_at          TEXT NOT NULL CHECK (published_at IS strftime('%Y-%m-%dT%H:%M:%SZ', published_at)),
    date_quality          TEXT NOT NULL CHECK (date_quality IN ('ok', 'a_verifier')),

    -- Classification (maladie, zone) : extraite du titre par règles
    disease_code          TEXT REFERENCES diseases(code),
    geo_scope             TEXT NOT NULL
        CHECK (geo_scope IN ('pays', 'multi_pays', 'region', 'mondial', 'inconnu')),
    classification_status TEXT NOT NULL
        CHECK (classification_status IN ('non_classe', 'auto', 'incertain', 'valide')),

    -- Passage de l'extracteur de chiffres (les chiffres eux-mêmes : report_figures)
    figures_payload_id        INTEGER,                     -- version brute lue ; NULL : jamais traité
    figures_extractor_version TEXT,

    raw_payload_id        INTEGER NOT NULL,                -- version brute courante
    first_seen_run_id     INTEGER NOT NULL,
    last_seen_run_id      INTEGER NOT NULL,
    removed_run_id        INTEGER,                         -- exécution de la 3e absence ; NULL : non retiré

    UNIQUE (source_code, external_id),
    UNIQUE (source_code, slug),
    UNIQUE (id, source_code, external_id),                   -- cible de la clé composite de report_versions (I51)
    -- I13 : les versions brutes citées sont celles de CE DON, dans la même source.
    FOREIGN KEY (raw_payload_id, source_code, external_id)
        REFERENCES raw_payloads (id, source_code, resource_key),
    FOREIGN KEY (figures_payload_id, source_code, external_id)
        REFERENCES raw_payloads (id, source_code, resource_key),
    -- I14 : les exécutions citées sont des exécutions de la même source.
    FOREIGN KEY (first_seen_run_id, source_code) REFERENCES ingestion_runs (id, source_code),
    FOREIGN KEY (last_seen_run_id, source_code)  REFERENCES ingestion_runs (id, source_code),
    FOREIGN KEY (removed_run_id, source_code)    REFERENCES ingestion_runs (id, source_code),
    CHECK (last_seen_run_id >= first_seen_run_id),                                 -- I14
    CHECK (removed_run_id IS NULL OR removed_run_id > last_seen_run_id),           -- I10 (partie SQL)
    CHECK ((classification_status = 'non_classe') = (disease_code IS NULL)),       -- I39
    CHECK ((figures_payload_id IS NULL) = (figures_extractor_version IS NULL))     -- I38
) STRICT;

CREATE INDEX reports_by_disease_date ON reports (disease_code, published_at);
CREATE INDEX reports_by_date ON reports (published_at);


-- -----------------------------------------------------------------------------
-- report_countries : pays concernés par un rapport (ISO 3166-1 alpha-3)
-- -----------------------------------------------------------------------------
CREATE TABLE report_countries (
    report_id    INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    country_iso3 TEXT NOT NULL CHECK (length(country_iso3) = 3 AND country_iso3 = upper(country_iso3)),  -- I40
    is_primary   INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    PRIMARY KEY (report_id, country_iso3)
) STRICT;

-- I40 : au plus un pays principal par rapport.
CREATE UNIQUE INDEX report_countries_one_primary ON report_countries (report_id) WHERE is_primary = 1;
CREATE INDEX report_countries_by_country ON report_countries (country_iso3);


-- -----------------------------------------------------------------------------
-- report_versions : chronologie des contenus d'un DON (décision D26)
-- -----------------------------------------------------------------------------
-- Une ligne chaque fois que le contenu courant d'un DON change, y compris pour
-- revenir à un contenu déjà archivé (A -> B -> A donne 3 versions et 2 bruts).
-- La date d'une version est le début de son exécution (run_id).
-- source_code et external_id sont recopiés (table petite : ~3 200 lignes plus les
-- modifications) pour que les clés composites imposent la provenance (I51).
CREATE TABLE report_versions (
    report_id      INTEGER NOT NULL,
    version        INTEGER NOT NULL CHECK (version >= 1),
    source_code    TEXT NOT NULL,
    external_id    TEXT NOT NULL,
    raw_payload_id INTEGER NOT NULL,
    run_id         INTEGER NOT NULL,
    PRIMARY KEY (report_id, version),
    UNIQUE (report_id, run_id),                         -- une version au plus par exécution
    FOREIGN KEY (report_id, source_code, external_id) REFERENCES reports (id, source_code, external_id),
    FOREIGN KEY (raw_payload_id, source_code, external_id)
        REFERENCES raw_payloads (id, source_code, resource_key),
    FOREIGN KEY (run_id, source_code) REFERENCES ingestion_runs (id, source_code)
) STRICT;


-- -----------------------------------------------------------------------------
-- report_figures : chiffres extraits d'un rapport (décision D23)
-- -----------------------------------------------------------------------------
-- Un chiffre = une mesure (cas ou décès), pour un pays du rapport ou pour
-- l'ensemble du rapport (country_iso3 NULL), selon une définition de cas, sur
-- une période [period_start, as_of], lu dans une version brute précise du DON.
-- Exemple réel (2024-DON528, Mpox - African Region) : Burundi, 142 cas confirmés
-- au 2024-08-17 ; Kenya, 1 cas confirmé au 2024-08-13 ; Rwanda, 4 cas confirmés
-- et 0 décès au 2024-08-07.
-- Les lignes ne sont jamais supprimées : un DON modifié est relu et ses nouveaux
-- chiffres portent la nouvelle version brute. Chiffres affichés : vue
-- report_figures_current (version lue par le dernier passage de l'extracteur).
CREATE TABLE report_figures (
    id                INTEGER PRIMARY KEY,
    report_id         INTEGER NOT NULL REFERENCES reports(id),
    raw_payload_id    INTEGER NOT NULL REFERENCES raw_payloads(id),  -- version du DON lue (I16)
    country_iso3      TEXT,                                -- NULL : ensemble du rapport
    measure           TEXT NOT NULL CHECK (measure IN ('cas', 'deces')),
    case_definition   TEXT NOT NULL
        CHECK (case_definition IN ('total', 'confirme', 'probable', 'suspect', 'non_precise')),
    -- Précision du nombre tel qu'écrit dans le texte (D33) : « about 200 » -> 'environ', « at least
    -- 40 » -> 'au_moins', « up to 30 » -> 'au_plus', « between 120 and 150 » -> deux lignes,
    -- 'fourchette_basse' (120) et 'fourchette_haute' (150). Pas de valeur par défaut : l'extraction
    -- doit toujours la renseigner.
    precision         TEXT NOT NULL
        CHECK (precision IN ('exact', 'environ', 'au_moins', 'au_plus',
                             'fourchette_basse', 'fourchette_haute')),    -- I62
    period_start      TEXT CHECK (period_start IS date(period_start)),   -- NULL : depuis le début de l'événement
    as_of             TEXT CHECK (as_of IS date(as_of)),          -- date « au ... » citée ; NULL : non citée
    value             INTEGER NOT NULL CHECK (value >= 0),           -- I37
    method            TEXT NOT NULL CHECK (method IN ('regle', 'llm', 'manuel')),
    status            TEXT NOT NULL CHECK (status IN ('auto', 'incertain', 'valide')),
    evidence          TEXT NOT NULL CHECK (evidence <> ''),          -- phrase source (I37)
    extractor_version TEXT NOT NULL,                                 -- version de l'extracteur, ou 'manuel'
    -- I17 : un chiffre par pays ne vise qu'un pays listé pour ce rapport.
    FOREIGN KEY (report_id, country_iso3) REFERENCES report_countries (report_id, country_iso3),
    -- I35 (règle de CONTEXTE) : une extraction par LLM n'est jamais « auto », toujours à valider.
    CHECK (method <> 'llm' OR status IN ('incertain', 'valide')),
    CHECK (period_start IS NULL OR as_of IS NULL OR period_start <= as_of)          -- I37
) STRICT;

-- I36 : un seul chiffre par version, pays (ou ensemble), mesure, définition et période.
-- COALESCE : sans lui, deux lignes « ensemble du rapport » (NULL) ne se heurteraient pas.
-- La précision entre dans la clé sous forme de « rôle » (D33) : les deux bornes d'une fourchette
-- ont chacune leur rôle et coexistent ; exact, environ, au_moins et au_plus partagent le rôle
-- 'point', donc un même chiffre ne peut avoir qu'une seule de ces lectures.
CREATE UNIQUE INDEX report_figures_one_value ON report_figures (
    raw_payload_id, report_id, COALESCE(country_iso3, ''), measure, case_definition,
    COALESCE(period_start, ''), COALESCE(as_of, ''),
    (CASE WHEN precision IN ('fourchette_basse', 'fourchette_haute') THEN precision ELSE 'point' END));
CREATE INDEX report_figures_by_report ON report_figures (report_id);


-- -----------------------------------------------------------------------------
-- datasets : jeux de données suivis, avec leur licence propre (décision D27)
-- -----------------------------------------------------------------------------
-- La licence d'un fournisseur (sources.license_name) ne vaut pas pour chacun de
-- ses jeux : 35 jeux Odissé n'ont aucune licence déclarée (phase 0). La licence
-- est relevée par jeu, avec sa date et sa preuve :
--   * 'catalogue_api' : métadonnée license lue dans le catalogue, réponse archivée
--     dans raw_payloads (license_payload_id) ;
--   * 'verification_manuelle' : page de conditions lue par une personne (date et
--     page dans license_note).
-- Un jeu non publiable ne reçoit plus d'observations (I54) : la base est publique.
-- Si la licence d'un jeu change après collecte (décision D30), les observations
-- collectées avant not_publishable_since restent : la Licence Ouverte 2.0 accorde
-- un droit de réutilisation sans limite de durée. La preuve de l'ancienne licence
-- reste dans les réponses du catalogue, jamais purgées (I53).
CREATE TABLE datasets (
    source_code         TEXT NOT NULL REFERENCES sources(code),
    dataset             TEXT NOT NULL,
    title               TEXT,
    license_name        TEXT,                              -- licence déclarée pour CE jeu ; NULL : aucune
    license_url         TEXT,
    license_evidence    TEXT NOT NULL CHECK (license_evidence IN ('catalogue_api', 'verification_manuelle')),
    license_payload_id  INTEGER,                           -- réponse du catalogue lue
    license_checked_at  TEXT NOT NULL CHECK (license_checked_at IS strftime('%Y-%m-%dT%H:%M:%SZ', license_checked_at)),
    license_note        TEXT,
    is_publishable      INTEGER NOT NULL CHECK (is_publishable IN (0, 1)),
    -- Fenêtre de publication : depuis le premier relevé d'une licence valable
    -- (NULL : jamais publiable) jusqu'au changement de licence (NULL : toujours publiable).
    publishable_since     TEXT
        CHECK (publishable_since IS strftime('%Y-%m-%dT%H:%M:%SZ', publishable_since)),
    not_publishable_since TEXT
        CHECK (not_publishable_since IS strftime('%Y-%m-%dT%H:%M:%SZ', not_publishable_since)),
    PRIMARY KEY (source_code, dataset),
    FOREIGN KEY (license_payload_id, source_code) REFERENCES raw_payloads (id, source_code),   -- I54
    CHECK ((license_evidence = 'catalogue_api') = (license_payload_id IS NOT NULL)),        -- I54
    CHECK (is_publishable = 0 OR license_name IS NOT NULL),                                  -- I54
    CHECK ((is_publishable = 1) = (publishable_since IS NOT NULL AND not_publishable_since IS NULL)),  -- I54
    CHECK (not_publishable_since IS NULL OR not_publishable_since > publishable_since)       -- I54
) STRICT;


-- -----------------------------------------------------------------------------
-- series : définition d'une série hebdomadaire ou annuelle (SPF, Sentinelles)
-- -----------------------------------------------------------------------------
-- Une série = un indicateur d'un jeu de données, pour une zone et une classe d'âge.
-- Exemples réels :
--   sentinelles / inc-3-PAY-ds2 / inc100 / grippe / pays FR-MET / tous
--   spf_odisse  / grippe-passages-aux-urgences-et-actes-sos-medecins-france /
--                 taux_passages_grippe_sau / grippe / pays FR / '00-14 ans'
-- Les codes de région INSEE et de département se recouvrent ('11' = Île-de-France
-- ou Aude) : geo_level fait partie de la clé.
CREATE TABLE series (
    id                    INTEGER PRIMARY KEY,
    source_code           TEXT NOT NULL REFERENCES sources(code),
    dataset               TEXT NOT NULL,                   -- identifiant du jeu côté source
    metric                TEXT NOT NULL,                   -- nom du champ côté source
    disease_code          TEXT NOT NULL REFERENCES diseases(code),
    geo_level             TEXT NOT NULL CHECK (geo_level IN ('pays', 'region', 'departement')),
    geo_code              TEXT NOT NULL,                   -- 'FR' (France entière), 'FR-MET' (métropole), code INSEE
    geo_label             TEXT NOT NULL,
    age_group             TEXT NOT NULL DEFAULT 'tous',
    period_type           TEXT NOT NULL CHECK (period_type IN ('semaine_iso', 'annee')),
    value_kind            TEXT NOT NULL
        CHECK (value_kind IN ('incidence', 'taux_incidence', 'cumul', 'taux')),
    unit                  TEXT NOT NULL,                   -- 'cas', 'pour 100 000 habitants'...
    case_status           TEXT NOT NULL
        CHECK (case_status IN ('confirme', 'probable', 'suspect', 'syndromique', 'non_precise')),
    date_basis            TEXT NOT NULL                    -- à quoi correspond la période
        CHECK (date_basis IN ('consultation', 'passage_urgences', 'debut_signes', 'declaration', 'non_precise')),
    underreporting_likely INTEGER NOT NULL DEFAULT 0 CHECK (underreporting_likely IN (0, 1)),
    value_min             REAL,                            -- plus petite valeur admissible (I56) ; NULL : pas de borne
    is_active             INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (source_code, dataset, metric, geo_level, geo_code, age_group),         -- I48
    FOREIGN KEY (source_code, dataset) REFERENCES datasets (source_code, dataset), -- I54
    -- I49 : Sentinelles ne couvre que la métropole (FR-MET), jamais la France entière (D22).
    CHECK (source_code <> 'sentinelles' OR geo_code <> 'FR')
) STRICT;


-- -----------------------------------------------------------------------------
-- observations : valeurs des séries, versionnées (gestion des révisions)
-- -----------------------------------------------------------------------------
-- Chaque révision par la source d'un champ versionné (value, value_low, value_up,
-- value_status : I50) crée une nouvelle ligne (version + 1) et ferme la précédente
-- (valid_to = valid_from de la nouvelle), dans une même transaction. Une
-- republication identique (même avec un autre source_version) ne crée pas de
-- ligne. Une valeur retirée par la source crée une version avec value NULL et
-- son motif (value_status) : la dernière version d'un point reste ouverte (I22).
--   * version courante  : valid_to IS NULL (exactement une par point : I20, I22)
--   * valeur connue au jour D : valid_from <= D AND (valid_to IS NULL OR valid_to > D)
-- valid_from = started_at de l'exécution qui a vu la version (I24), pas la date
-- de publication par la source (inconnue en général ; voir source_published_at).
-- iso_year : année ISO de la semaine pour une série hebdomadaire ; année civile
-- pour une série annuelle (iso_week NULL).
CREATE TABLE observations (
    id                  INTEGER PRIMARY KEY,
    series_id           INTEGER NOT NULL REFERENCES series(id),
    period_start        TEXT NOT NULL CHECK (period_start IS date(period_start)),  -- lundi de la semaine ISO, ou 1er janvier
    period_end          TEXT NOT NULL CHECK (period_end IS date(period_end)),
    iso_year            INTEGER NOT NULL CHECK (iso_year BETWEEN 1950 AND 2100),   -- I30 (refuse un 'YYYYWW')
    iso_week            INTEGER CHECK (iso_week BETWEEN 1 AND 53),                -- I30 ; NULL pour une série annuelle
    version             INTEGER NOT NULL CHECK (version >= 1),
    value               REAL,                              -- NULL : absente, motif dans value_status
    value_low           REAL,                              -- bornes d'intervalle (Sentiweb inc_low / inc_up)
    value_up            REAL,
    -- I55 : statut de la valeur, distinct de la fiabilité de la source (sources.reliability).
    value_status        TEXT NOT NULL DEFAULT 'publiee' CHECK (value_status IN (
                            'publiee', 'provisoire',                          -- valeur présente
                            'retiree', 'non_diffusee', 'secret_statistique', 'absente_sans_motif')),
    source_version      TEXT,                              -- identifiant de version côté source
    source_published_at TEXT CHECK (source_published_at IS strftime('%Y-%m-%dT%H:%M:%SZ', source_published_at)),
    valid_from          TEXT NOT NULL CHECK (valid_from IS strftime('%Y-%m-%dT%H:%M:%SZ', valid_from)),
    valid_to            TEXT CHECK (valid_to IS strftime('%Y-%m-%dT%H:%M:%SZ', valid_to)),
    run_id              INTEGER NOT NULL REFERENCES ingestion_runs(id),        -- même source que la série (I15)
    -- I60 : chaque version cite le brut d'où vient sa valeur (relecture, D31) ; même source que la série (I15).
    raw_payload_id      INTEGER NOT NULL REFERENCES raw_payloads(id),
    UNIQUE (series_id, period_start, version),                                 -- I19
    CHECK (period_end >= period_start),
    CHECK (valid_to IS NULL OR valid_to > valid_from),                         -- I23 : durée strictement positive
    CHECK (value IS NOT NULL OR (value_low IS NULL AND value_up IS NULL)),     -- I27
    CHECK (value_low IS NULL OR value >= value_low),                           -- I27
    CHECK (value_up IS NULL OR value <= value_up),                             -- I27
    CHECK ((value IS NOT NULL) = (value_status IN ('publiee', 'provisoire'))),   -- I55
    -- I32 : un point annuel couvre exactement l'année civile iso_year.
    CHECK (iso_week IS NOT NULL OR (period_start = CAST(iso_year AS TEXT) || '-01-01'
                                    AND period_end = CAST(iso_year AS TEXT) || '-12-31')),
    -- I33 : un point hebdomadaire est la semaine ISO (iso_year, iso_week), du lundi au
    -- dimanche. Le jeudi (lundi + 3 jours) porte l'année ISO ; son quantième donne la
    -- semaine. Refuse donc un début hors lundi, une fin fausse, une semaine 53
    -- inexistante et une année civile prise pour l'année ISO. Vérifié contre
    -- date.isocalendar() pour tous les lundis de 1990 à 2030.
    CHECK (iso_week IS NULL OR (
        strftime('%w', period_start) = '1'
        AND period_end = date(period_start, '+6 days')
        AND CAST(strftime('%Y', period_start, '+3 days') AS INTEGER) = iso_year
        AND (CAST(strftime('%j', period_start, '+3 days') AS INTEGER) - 1) / 7 + 1 = iso_week))
) STRICT;

-- I20 : au plus une version courante par point de série ; sert aussi à lire la série courante.
CREATE UNIQUE INDEX observations_one_current
    ON observations (series_id, period_start) WHERE valid_to IS NULL;


-- -----------------------------------------------------------------------------
-- anomalies : dépassements de seuil détectés en production
-- -----------------------------------------------------------------------------
-- Rattachées à la version exacte de l'observation évaluée : une révision crée une
-- nouvelle évaluation, l'ancienne passe en 'remplacee' (I28). v1 : hausses
-- uniquement. Les résultats de backtest ne sont pas stockés ici.
CREATE TABLE anomalies (
    id              INTEGER PRIMARY KEY,
    observation_id  INTEGER NOT NULL REFERENCES observations(id),
    method          TEXT NOT NULL,                         -- ex. 'baseline_saisonniere'
    method_version  TEXT NOT NULL,                         -- paramètres figés par version
    parameters      TEXT NOT NULL CHECK (json_valid(parameters)),  -- JSON : années de référence, fenêtre, seuil (I59)
    observed_value  REAL NOT NULL,                         -- copie de observations.value (I29)
    expected_value  REAL NOT NULL,
    threshold_value REAL NOT NULL,
    score           REAL,
    severity        TEXT NOT NULL CHECK (severity IN ('moderee', 'elevee')),
    status          TEXT NOT NULL DEFAULT 'ouverte'
        CHECK (status IN ('ouverte', 'confirmee', 'faux_positif', 'remplacee')),
    detected_at     TEXT NOT NULL CHECK (detected_at IS strftime('%Y-%m-%dT%H:%M:%SZ', detected_at)),
    code_version    TEXT NOT NULL,
    UNIQUE (observation_id, method, method_version),
    CHECK (observed_value > threshold_value)                                   -- I29
) STRICT;


-- -----------------------------------------------------------------------------
-- alerts_log : alertes à envoyer ou envoyées (Telegram en v1)
-- -----------------------------------------------------------------------------
-- Livraison « au moins une fois » (décision D19) : la ligne est écrite et validée
-- ('a_envoyer') avant l'appel à Telegram, puis passe à 'envoyee' après la réponse
-- de Telegram. (channel, dedup_key) empêche de renvoyer une alerte déjà marquée
-- 'envoyee' dans la base de départ. Un doublon reste possible si ce statut
-- n'atteint pas la base publiée (risque R14).
-- Le destinataire (identifiant de discussion Telegram) n'est PAS stocké ici :
-- il est dans les secrets GitHub.
CREATE TABLE alerts_log (
    id          INTEGER PRIMARY KEY,
    alert_type  TEXT NOT NULL CHECK (alert_type IN (
                    'anomalie', 'nouveau_rapport', 'rapport_retire', 'source_en_echec',
                    'format_modifie', 'donnees_perimees', 'ecart_comptage')),
    channel     TEXT NOT NULL CHECK (channel IN ('telegram', 'email')),
    dedup_key   TEXT NOT NULL,                             -- déterministe (I45), ex. 'nouveau_rapport:oms_don:<Id>'
    anomaly_id  INTEGER REFERENCES anomalies(id),
    report_id   INTEGER REFERENCES reports(id),
    run_id      INTEGER REFERENCES ingestion_runs(id),
    message     TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('a_envoyer', 'envoyee', 'echec')),
    attempts    INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    created_at  TEXT NOT NULL CHECK (created_at IS strftime('%Y-%m-%dT%H:%M:%SZ', created_at)),
    sent_at     TEXT CHECK (sent_at IS strftime('%Y-%m-%dT%H:%M:%SZ', sent_at)),
    last_error  TEXT,
    UNIQUE (channel, dedup_key),                                                     -- I44
    CHECK ((alert_type = 'anomalie') = (anomaly_id IS NOT NULL)),                    -- I18
    CHECK ((alert_type IN ('nouveau_rapport', 'rapport_retire')) = (report_id IS NOT NULL)),  -- I18
    CHECK (alert_type IN ('anomalie', 'nouveau_rapport', 'rapport_retire') OR run_id IS NOT NULL),  -- I18
    CHECK ((status = 'envoyee') = (sent_at IS NOT NULL)),                            -- I47
    CHECK (status = 'a_envoyer' OR attempts >= 1),                                   -- I47
    CHECK (status <> 'echec' OR last_error IS NOT NULL),                             -- I47
    CHECK (sent_at IS NULL OR sent_at >= created_at)                                 -- I47
) STRICT;


-- -----------------------------------------------------------------------------
-- Vues de lecture
-- -----------------------------------------------------------------------------
CREATE VIEW observations_current AS
SELECT o.id, o.series_id, o.period_start, o.period_end, o.iso_year, o.iso_week,
       o.version, o.value, o.value_low, o.value_up, o.value_status, o.valid_from, o.source_version
FROM observations AS o
WHERE o.valid_to IS NULL;

CREATE VIEW reports_active AS
SELECT * FROM reports WHERE removed_run_id IS NULL;

-- Présence des DON dans l'API (décision D24). missing_runs = exécutions complètes
-- de la source depuis la dernière où le DON a été reçu. expected_removed_run_id =
-- 3e de ces exécutions : c'est la valeur que removed_run_id doit avoir (I10).
CREATE VIEW reports_presence AS
SELECT x.report_id, x.slug, x.last_seen_run_id, x.removed_run_id, x.missing_runs,
       x.expected_removed_run_id,
       CASE WHEN x.missing_runs = 0 THEN 'present'
            WHEN x.missing_runs < 3 THEN 'absent'
            ELSE 'retire' END AS presence
FROM (
    SELECT r.id AS report_id, r.slug, r.last_seen_run_id, r.removed_run_id,
           (SELECT count(*) FROM ingestion_runs AS g
            WHERE g.source_code = r.source_code AND g.status IN ('succes', 'inchange')
              AND g.id > r.last_seen_run_id) AS missing_runs,
           (SELECT g.id FROM ingestion_runs AS g
            WHERE g.source_code = r.source_code AND g.status IN ('succes', 'inchange')
              AND g.id > r.last_seen_run_id
            ORDER BY g.id LIMIT 1 OFFSET 2) AS expected_removed_run_id
    FROM reports AS r
) AS x;

-- Chiffres de la version du DON lue par le dernier passage de l'extracteur.
CREATE VIEW report_figures_current AS
SELECT f.*
FROM report_figures AS f
JOIN reports AS r ON r.id = f.report_id AND r.figures_payload_id = f.raw_payload_id;


-- -----------------------------------------------------------------------------
-- controle_invariants : violations des invariants que SQL n'impose pas
-- -----------------------------------------------------------------------------
-- Une ligne par violation : numéro d'invariant (docs/01-invariants.md), table,
-- identifiant de la ligne fautive. Doit être VIDE avant tout envoi de la base
-- (étape 6 de l'exécution quotidienne), comme PRAGMA foreign_key_check.
CREATE VIEW controle_invariants AS
-- I6 : aucune exécution restée « en cours »
SELECT 'I6' AS invariant, 'ingestion_runs' AS table_name, g.id AS row_id
FROM ingestion_runs AS g
WHERE g.status = 'en_cours'
UNION ALL
-- I9 : écart 0 sur les présents, mesuré sur la dernière exécution OMS non échouée si elle est complète
SELECT 'I9', 'ingestion_runs', g.id
FROM ingestion_runs AS g
WHERE g.id = (SELECT max(h.id) FROM ingestion_runs AS h
              WHERE h.source_code = 'oms_don' AND h.status IN ('succes', 'inchange', 'partiel'))
  AND g.status IN ('succes', 'inchange')
  AND g.seen_count <> (SELECT count(*) FROM reports AS r WHERE r.last_seen_run_id = g.id)
UNION ALL
-- I10 : retrait exactement à la 3e exécution complète sans le DON
SELECT 'I10', 'reports', p.report_id
FROM reports_presence AS p
WHERE p.removed_run_id IS DISTINCT FROM p.expected_removed_run_id
UNION ALL
-- I15 : exécution et brut d'une observation viennent de la source de sa série
SELECT 'I15', 'observations', o.id
FROM observations AS o
JOIN series AS s ON s.id = o.series_id
JOIN ingestion_runs AS g ON g.id = o.run_id
LEFT JOIN raw_payloads AS p ON p.id = o.raw_payload_id
WHERE g.source_code <> s.source_code OR p.source_code <> s.source_code
UNION ALL
-- I16 : un chiffre vient d'une version brute de son propre DON
SELECT 'I16', 'report_figures', f.id
FROM report_figures AS f
JOIN reports AS r ON r.id = f.report_id
JOIN raw_payloads AS p ON p.id = f.raw_payload_id
WHERE p.source_code <> r.source_code OR p.resource_key <> r.external_id
UNION ALL
-- I21 : versions numérotées 1..n sans trou
SELECT 'I21', 'observations', min(o.id)
FROM observations AS o
GROUP BY o.series_id, o.period_start
HAVING min(o.version) <> 1 OR max(o.version) <> count(*)
UNION ALL
-- I22 : chaque version est fermée à l'ouverture de la suivante ; la dernière est ouverte
SELECT 'I22', 'observations', x.id
FROM (SELECT o.id, o.valid_to,
             LEAD(o.valid_from) OVER (PARTITION BY o.series_id, o.period_start ORDER BY o.version)
                 AS next_valid_from
      FROM observations AS o) AS x
WHERE x.valid_to IS DISTINCT FROM x.next_valid_from
UNION ALL
-- I24 : valid_from = début de l'exécution qui a vu la version
SELECT 'I24', 'observations', o.id
FROM observations AS o
JOIN ingestion_runs AS g ON g.id = o.run_id
WHERE o.valid_from <> g.started_at
UNION ALL
-- I25 : deux versions consécutives diffèrent sur au moins un champ versionné
SELECT 'I25', 'observations', x.id
FROM (SELECT o.id, o.value, o.value_low, o.value_up, o.value_status,
             LAG(o.id)           OVER w AS prev_id,
             LAG(o.value)        OVER w AS prev_value,
             LAG(o.value_low)    OVER w AS prev_low,
             LAG(o.value_up)     OVER w AS prev_up,
             LAG(o.value_status) OVER w AS prev_status
      FROM observations AS o
      WINDOW w AS (PARTITION BY o.series_id, o.period_start ORDER BY o.version)) AS x
WHERE x.prev_id IS NOT NULL
  AND x.value IS NOT DISTINCT FROM x.prev_value
  AND x.value_low IS NOT DISTINCT FROM x.prev_low
  AND x.value_up IS NOT DISTINCT FROM x.prev_up
  AND x.value_status = x.prev_status
UNION ALL
-- I51 : chronologie des contenus d'un DON : versions 1..n, chaque version change de
-- contenu, la dernière est le contenu courant, tout DON a au moins une version
SELECT 'I51', 'reports', r.id
FROM reports AS r
LEFT JOIN report_versions AS v ON v.report_id = r.id
GROUP BY r.id, r.raw_payload_id
HAVING count(v.report_id) = 0 OR min(v.version) <> 1 OR max(v.version) <> count(*)
    OR r.raw_payload_id IS DISTINCT FROM
       (SELECT v2.raw_payload_id FROM report_versions AS v2
        WHERE v2.report_id = r.id ORDER BY v2.version DESC LIMIT 1)
UNION ALL
SELECT 'I51', 'report_versions', x.report_id
FROM (SELECT v.report_id, v.raw_payload_id, v.run_id,
             LAG(v.raw_payload_id) OVER w AS prev_payload,
             LAG(v.run_id)         OVER w AS prev_run
      FROM report_versions AS v
      WINDOW w AS (PARTITION BY v.report_id ORDER BY v.version)) AS x
WHERE x.raw_payload_id = x.prev_payload OR x.run_id <= x.prev_run
UNION ALL
-- I54 : aucune observation d'un jeu jamais publiable, ni collectée après la fin de
-- sa fenêtre de publication (la base est publique ; les observations antérieures
-- restent, D30)
SELECT 'I54', 'observations', min(o.id)
FROM observations AS o
JOIN series AS s ON s.id = o.series_id
JOIN datasets AS d ON d.source_code = s.source_code AND d.dataset = s.dataset
WHERE d.publishable_since IS NULL OR o.valid_from >= d.not_publishable_since
GROUP BY s.id
UNION ALL
-- I56 : valeur dans le domaine admissible de sa série
SELECT 'I56', 'observations', o.id
FROM observations AS o
JOIN series AS s ON s.id = o.series_id
WHERE o.value < s.value_min OR o.value_low < s.value_min
UNION ALL
-- I28 : anomalie ouverte sur une version courante ; remplacée sur une version fermée
SELECT 'I28', 'anomalies', a.id
FROM anomalies AS a
JOIN observations AS o ON o.id = a.observation_id
WHERE (a.status = 'ouverte' AND o.valid_to IS NOT NULL)
   OR (a.status = 'remplacee' AND o.valid_to IS NULL)
UNION ALL
-- I29 : l'anomalie reprend la valeur de la version évaluée
SELECT 'I29', 'anomalies', a.id
FROM anomalies AS a
JOIN observations AS o ON o.id = a.observation_id
WHERE a.observed_value IS DISTINCT FROM o.value
UNION ALL
-- I31 : semaine renseignée si et seulement si la série est hebdomadaire
SELECT 'I31', 'observations', o.id
FROM observations AS o
JOIN series AS s ON s.id = o.series_id
WHERE (s.period_type = 'annee') <> (o.iso_week IS NULL)
UNION ALL
-- I61 : pour une même fourchette, la borne basse est inférieure ou égale à la borne haute
SELECT 'I61', 'report_figures', lo.id
FROM report_figures AS lo
JOIN report_figures AS hi
  ON hi.raw_payload_id = lo.raw_payload_id AND hi.report_id = lo.report_id
 AND hi.country_iso3 IS lo.country_iso3 AND hi.measure = lo.measure
 AND hi.case_definition = lo.case_definition
 AND hi.period_start IS lo.period_start AND hi.as_of IS lo.as_of
WHERE lo.precision = 'fourchette_basse' AND hi.precision = 'fourchette_haute'
  AND lo.value > hi.value
UNION ALL
-- I41 : portée géographique cohérente avec les pays listés
SELECT 'I41', 'reports', r.id
FROM reports AS r
LEFT JOIN report_countries AS c ON c.report_id = r.id
GROUP BY r.id, r.geo_scope
HAVING (r.geo_scope = 'pays' AND (count(c.report_id) <> 1 OR COALESCE(sum(c.is_primary), 0) <> 1))
    OR (r.geo_scope = 'multi_pays' AND count(c.report_id) < 2);


-- Version du schéma (spécifique SQLite ; en PostgreSQL : table de migrations).
-- Reste 1 : aucune base n'a été créée avec la version de la phase 1 (commit e8f65a6).
PRAGMA user_version = 1;
