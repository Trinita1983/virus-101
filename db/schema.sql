-- =============================================================================
-- Observatoire des maladies infectieuses : schéma de base, version 1
-- =============================================================================
-- Moteur : SQLite >= 3.37 (tables STRICT). Portable vers PostgreSQL : voir la
-- liste des divergences dans docs/01-architecture.md, section 6.
--
-- Conventions :
--   * Horodatages : TEXT ISO 8601 en UTC, forme exacte 'YYYY-MM-DDTHH:MM:SSZ'.
--     Dates : TEXT 'YYYY-MM-DD'. Ils sont fixés par le code Python, jamais par
--     une fonction SQL (pas de DEFAULT CURRENT_TIMESTAMP), pour rester portable
--     et testable.
--   * Booléens : INTEGER 0/1 avec CHECK.
--   * Valeurs énumérées : CHECK (... IN (...)), en français sans accents.
--   * Aucune suppression physique de données métier : on ferme des versions
--     (observations.valid_to) ou on marque (reports.removed_at).
--   * Aucun trigger : la logique (fermeture de version, déduplication) est dans
--     le code Python, en transaction.
--   * Aucune donnée personnelle : la base est publiée (release d'un dépôt public).
--
-- SQLite n'applique les clés étrangères que si chaque connexion exécute :
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
CREATE TABLE ingestion_runs (
    id                INTEGER PRIMARY KEY,
    source_code       TEXT NOT NULL REFERENCES sources(code),
    started_at        TEXT NOT NULL CHECK (started_at LIKE '____-__-__T__:__:__Z'),
    finished_at       TEXT CHECK (finished_at LIKE '____-__-__T__:__:__Z'),
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
    http_requests     INTEGER NOT NULL DEFAULT 0 CHECK (http_requests >= 0),
    http_retries      INTEGER NOT NULL DEFAULT 0 CHECK (http_retries >= 0),
    field_fingerprint TEXT,                                -- sha256 de la liste triée des champs reçus
    error_kind        TEXT
        CHECK (error_kind IN ('reseau', 'http', 'quota', 'format', 'validation', 'controle', 'autre')),
    error_message     TEXT,
    CHECK ((status = 'en_cours') = (finished_at IS NULL)),
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK (status NOT IN ('echec', 'partiel') OR error_kind IS NOT NULL)
) STRICT;

CREATE INDEX ingestion_runs_by_source ON ingestion_runs (source_code, started_at);


-- -----------------------------------------------------------------------------
-- raw_payloads : contenu brut archivé, dédupliqué par empreinte
-- -----------------------------------------------------------------------------
-- OMS : un enregistrement par DON et par version de contenu (resource_key = Id).
-- Sentiweb / Odissé : une réponse ou un export complet (resource_key = jeu).
-- Le hash porte sur le contenu non compressé. Un contenu identique déjà archivé
-- n'est pas réinséré (relance idempotente).
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
    source_modified_at TEXT CHECK (source_modified_at LIKE '____-__-__T__:__:__Z'),  -- OMS : LastModified
    first_run_id       INTEGER NOT NULL REFERENCES ingestion_runs(id),
    retrieved_at       TEXT NOT NULL CHECK (retrieved_at LIKE '____-__-__T__:__:__Z'),
    purged_at          TEXT CHECK (purged_at LIKE '____-__-__T__:__:__Z'),  -- corps effacé par la rétention
    UNIQUE (source_code, resource_key, sha256),
    CHECK (
        (purged_at IS NULL AND ((body_text IS NULL) <> (body_gzip IS NULL)))
        OR (purged_at IS NOT NULL AND body_text IS NULL AND body_gzip IS NULL)
    )
) STRICT;


-- -----------------------------------------------------------------------------
-- reports : événements narratifs (OMS DON), état courant
-- -----------------------------------------------------------------------------
-- Une ligne par DON, mise à jour quand la source modifie le DON. L'historique
-- des versions est dans raw_payloads (une ligne par contenu distinct).
-- Correspondance avec les champs réels de l'API OMS (fixtures/who_don_sample.json) :
--   external_id  <- Id                      (GUID, unique sur 3199/3199)
--   external_ref <- DonId                   (NON unique : 14 valeurs en doublon ; '' -> NULL)
--   slug         <- UrlName                 (unique sur 3199/3199)
--   title        <- OverrideTitle si UseOverrideTitle et non vide, sinon Title
--                   (règle vérifiée : c'est le <h1> affiché sur who.int)
--   published_at <- PublicationDateAndTime  (et non PublicationDate, faux pour 1360 enregistrements)
--   source_modified_at <- LastModified
CREATE TABLE reports (
    id                    INTEGER PRIMARY KEY,
    source_code           TEXT NOT NULL REFERENCES sources(code),
    external_id           TEXT NOT NULL,
    external_ref          TEXT CHECK (external_ref <> ''),
    slug                  TEXT NOT NULL,
    url                   TEXT NOT NULL,
    title                 TEXT NOT NULL,
    summary               TEXT,                            -- texte brut (HTML retiré), pour l'affichage
    published_at          TEXT NOT NULL CHECK (published_at LIKE '____-__-__T__:__:__Z'),
    date_quality          TEXT NOT NULL CHECK (date_quality IN ('ok', 'a_verifier')),
    source_modified_at    TEXT CHECK (source_modified_at LIKE '____-__-__T__:__:__Z'),

    -- Classification (maladie, zone) : extraite du titre par règles
    disease_code          TEXT REFERENCES diseases(code),
    geo_scope             TEXT NOT NULL
        CHECK (geo_scope IN ('pays', 'multi_pays', 'region', 'mondial', 'inconnu')),
    classification_status TEXT NOT NULL
        CHECK (classification_status IN ('non_classe', 'auto', 'incertain', 'valide')),

    -- Chiffres extraits (un couple cas / décès par DON en v1)
    cases                 INTEGER CHECK (cases >= 0),
    deaths                INTEGER CHECK (deaths >= 0),
    figures_as_of         TEXT CHECK (figures_as_of LIKE '____-__-__'),  -- date « au ... » citée dans le texte
    figures_method        TEXT CHECK (figures_method IN ('regle', 'llm', 'manuel')),
    figures_status        TEXT NOT NULL DEFAULT 'non_extrait'
        CHECK (figures_status IN ('non_extrait', 'auto', 'incertain', 'valide')),
    figures_evidence      TEXT,                            -- phrase source des chiffres
    extractor_version     TEXT,

    raw_payload_id        INTEGER NOT NULL REFERENCES raw_payloads(id),  -- version brute courante
    first_seen_at         TEXT NOT NULL CHECK (first_seen_at LIKE '____-__-__T__:__:__Z'),
    last_seen_at          TEXT NOT NULL CHECK (last_seen_at LIKE '____-__-__T__:__:__Z'),
    removed_at            TEXT CHECK (removed_at LIKE '____-__-__T__:__:__Z'),  -- absent de l'API

    UNIQUE (source_code, external_id),
    UNIQUE (source_code, slug),
    CHECK ((classification_status = 'non_classe') = (disease_code IS NULL)),
    CHECK ((figures_status = 'non_extrait') = (figures_method IS NULL)),
    CHECK (figures_status <> 'non_extrait' OR (cases IS NULL AND deaths IS NULL)),
    CHECK (figures_status = 'non_extrait' OR cases IS NOT NULL OR deaths IS NOT NULL),
    -- Règle de CONTEXTE : une extraction par LLM n'est jamais « auto », toujours à valider.
    CHECK (figures_method <> 'llm' OR figures_status IN ('incertain', 'valide')),
    CHECK (last_seen_at >= first_seen_at)
) STRICT;

CREATE INDEX reports_by_disease_date ON reports (disease_code, published_at);
CREATE INDEX reports_by_date ON reports (published_at);


-- -----------------------------------------------------------------------------
-- report_countries : pays concernés par un rapport (ISO 3166-1 alpha-3)
-- -----------------------------------------------------------------------------
CREATE TABLE report_countries (
    report_id    INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    country_iso3 TEXT NOT NULL CHECK (length(country_iso3) = 3),
    is_primary   INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    PRIMARY KEY (report_id, country_iso3)
) STRICT;

-- Au plus un pays principal par rapport.
CREATE UNIQUE INDEX report_countries_one_primary ON report_countries (report_id) WHERE is_primary = 1;
CREATE INDEX report_countries_by_country ON report_countries (country_iso3);


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
    is_active             INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (source_code, dataset, metric, geo_level, geo_code, age_group)
) STRICT;


-- -----------------------------------------------------------------------------
-- observations : valeurs des séries, versionnées (gestion des révisions)
-- -----------------------------------------------------------------------------
-- Chaque révision d'une valeur par la source crée une nouvelle ligne (version + 1)
-- et ferme la précédente (valid_to = valid_from de la nouvelle), dans une même
-- transaction. Une valeur inchangée ne crée pas de ligne.
--   * version courante  : valid_to IS NULL (au plus une, garanti par index unique partiel)
--   * valeur connue au jour D : valid_from <= D AND (valid_to IS NULL OR valid_to > D)
-- valid_from = date à laquelle NOUS avons vu la version (pas la date de publication
-- par la source, inconnue en général ; voir source_published_at).
CREATE TABLE observations (
    id                  INTEGER PRIMARY KEY,
    series_id           INTEGER NOT NULL REFERENCES series(id),
    period_start        TEXT NOT NULL CHECK (period_start LIKE '____-__-__'),  -- lundi de la semaine ISO, ou 1er janvier
    period_end          TEXT NOT NULL CHECK (period_end LIKE '____-__-__'),
    iso_year            INTEGER NOT NULL,
    iso_week            INTEGER CHECK (iso_week BETWEEN 1 AND 53),  -- NULL pour une série annuelle
    version             INTEGER NOT NULL CHECK (version >= 1),
    value               REAL,                              -- NULL : valeur retirée ou non diffusée dans cette version
    value_low           REAL,                              -- bornes d'intervalle (Sentiweb inc_low / inc_up)
    value_up            REAL,
    source_version      TEXT,                              -- identifiant de version côté source
    source_published_at TEXT CHECK (source_published_at LIKE '____-__-__T__:__:__Z'),
    valid_from          TEXT NOT NULL CHECK (valid_from LIKE '____-__-__T__:__:__Z'),
    valid_to            TEXT CHECK (valid_to LIKE '____-__-__T__:__:__Z'),
    run_id              INTEGER NOT NULL REFERENCES ingestion_runs(id),
    raw_payload_id      INTEGER REFERENCES raw_payloads(id),
    UNIQUE (series_id, period_start, version),
    CHECK (period_end >= period_start),
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    CHECK (value IS NOT NULL OR (value_low IS NULL AND value_up IS NULL)),
    CHECK (value_low IS NULL OR value_up IS NULL OR value_low <= value_up)
) STRICT;

-- Au plus une version courante par point de série ; sert aussi à lire la série courante.
CREATE UNIQUE INDEX observations_one_current
    ON observations (series_id, period_start) WHERE valid_to IS NULL;


-- -----------------------------------------------------------------------------
-- anomalies : dépassements de seuil détectés en production
-- -----------------------------------------------------------------------------
-- Rattachées à la version exacte de l'observation évaluée : une révision crée une
-- nouvelle évaluation, l'ancienne passe en 'remplacee'. v1 : hausses uniquement.
-- Les résultats de backtest ne sont pas stockés ici.
CREATE TABLE anomalies (
    id              INTEGER PRIMARY KEY,
    observation_id  INTEGER NOT NULL REFERENCES observations(id),
    method          TEXT NOT NULL,                         -- ex. 'baseline_saisonniere'
    method_version  TEXT NOT NULL,                         -- paramètres figés par version
    parameters      TEXT NOT NULL,                         -- JSON : années de référence, fenêtre, seuil
    observed_value  REAL NOT NULL,
    expected_value  REAL NOT NULL,
    threshold_value REAL NOT NULL,
    score           REAL,
    severity        TEXT NOT NULL CHECK (severity IN ('moderee', 'elevee')),
    status          TEXT NOT NULL DEFAULT 'ouverte'
        CHECK (status IN ('ouverte', 'confirmee', 'faux_positif', 'remplacee')),
    detected_at     TEXT NOT NULL CHECK (detected_at LIKE '____-__-__T__:__:__Z'),
    code_version    TEXT NOT NULL,
    UNIQUE (observation_id, method, method_version),
    CHECK (observed_value > threshold_value)
) STRICT;


-- -----------------------------------------------------------------------------
-- alerts_log : alertes à envoyer ou envoyées (Telegram en v1)
-- -----------------------------------------------------------------------------
-- dedup_key rend l'envoi idempotent : une relance ne renvoie pas la même alerte.
-- Le destinataire (identifiant de discussion Telegram) n'est PAS stocké ici :
-- il est dans les secrets GitHub.
CREATE TABLE alerts_log (
    id          INTEGER PRIMARY KEY,
    alert_type  TEXT NOT NULL CHECK (alert_type IN (
                    'anomalie', 'nouveau_rapport', 'source_en_echec', 'format_modifie',
                    'donnees_perimees', 'ecart_comptage')),
    channel     TEXT NOT NULL CHECK (channel IN ('telegram', 'email')),
    dedup_key   TEXT NOT NULL,                             -- ex. 'anomalie:42', 'source_en_echec:sentinelles:2026-10-13'
    anomaly_id  INTEGER REFERENCES anomalies(id),
    report_id   INTEGER REFERENCES reports(id),
    run_id      INTEGER REFERENCES ingestion_runs(id),
    message     TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('a_envoyer', 'envoyee', 'echec')),
    attempts    INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    created_at  TEXT NOT NULL CHECK (created_at LIKE '____-__-__T__:__:__Z'),
    sent_at     TEXT CHECK (sent_at LIKE '____-__-__T__:__:__Z'),
    last_error  TEXT,
    UNIQUE (channel, dedup_key),
    CHECK ((alert_type = 'anomalie') = (anomaly_id IS NOT NULL)),
    CHECK ((alert_type = 'nouveau_rapport') = (report_id IS NOT NULL)),
    CHECK (alert_type IN ('anomalie', 'nouveau_rapport') OR run_id IS NOT NULL),
    CHECK ((status = 'envoyee') = (sent_at IS NOT NULL))
) STRICT;


-- -----------------------------------------------------------------------------
-- Vues
-- -----------------------------------------------------------------------------
CREATE VIEW observations_current AS
SELECT o.id, o.series_id, o.period_start, o.period_end, o.iso_year, o.iso_week,
       o.version, o.value, o.value_low, o.value_up, o.valid_from, o.source_version
FROM observations AS o
WHERE o.valid_to IS NULL;

CREATE VIEW reports_active AS
SELECT * FROM reports WHERE removed_at IS NULL;


-- Version du schéma (spécifique SQLite ; en PostgreSQL : table de migrations).
PRAGMA user_version = 1;
