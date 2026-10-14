"""Validation du schéma (phase 1).

Applique db/schema.sql et db/seed.sql sur une base temporaire, insère les 5 DON de
fixtures/who_don_sample.json et des observations hebdomadaires fictives avec une
révision, puis exécute les requêtes de contrôle et les tests de contraintes.
Le résultat est écrit en Markdown.

Ce script n'est pas le pipeline : la classification des 5 DON est saisie à la main.

Usage :
    python db/check_schema.py --out docs/01-validation.md
    python db/check_schema.py --out docs/01-validation.md --volume   # + mesure de volume
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import sqlite3
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
SEED = ROOT / "db" / "seed.sql"
FIXTURE = ROOT / "fixtures" / "who_don_sample.json"

# Horodatage fixe pour un résultat reproductible.
NOW = "2026-10-13T18:00:00Z"

# Taille moyenne du JSON d'un DON (20 683 214 caractères / 3199 enregistrements, phase 0).
AVG_DON_JSON_CHARS = 6466

# Classification saisie à la main pour le test (le pipeline le fera par règles).
MANUAL_CLASSIFICATION: dict[str, dict[str, Any]] = {
    "2026-DON620": {"disease": "pneumonie_indeterminee", "scope": "pays", "countries": ["RUS"]},
    "2024-DON528": {"disease": "mpox", "scope": "region", "countries": []},
    "2022-DON398_1": {"disease": "cholera", "scope": "pays", "countries": ["SOM"]},
    "2008_01_21-en": {"disease": "grippe_aviaire", "scope": "pays", "countries": ["IDN"]},
    "1996_01_22a-en": {"disease": "cholera", "scope": "mondial", "countries": []},
}

# Chiffres relevés à la main dans le texte du DON 2008_01_21-en (champ Overview).
MANUAL_FIGURES = {
    "2008_01_21-en": {
        "country": "IDN",
        "cases": 119,
        "deaths": 97,
        "as_of": "2008-01-21",
        "evidence": "Of the 119 cases confirmed to date in Indonesia, 97 have been fatal.",
    }
}


class Report:
    """Accumule le Markdown produit."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str = "") -> None:
        self.lines.append(text)

    def sql(self, query: str) -> None:
        self.add("```sql")
        self.add(query.strip())
        self.add("```")

    def table(self, cursor: sqlite3.Cursor) -> None:
        rows = cursor.fetchall()
        headers = [d[0] for d in cursor.description]
        self.add("| " + " | ".join(headers) + " |")
        self.add("|" + "---|" * len(headers))
        for row in rows:
            self.add("| " + " | ".join("NULL" if v is None else str(v) for v in row) + " |")
        self.add(f"\n{len(rows)} ligne(s).\n")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.executescript(SEED.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = ON")


def canonical_json(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def strip_html(fragment: str | None, limit: int = 300) -> str | None:
    if not fragment:
        return None
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()
    return text[:limit] or None


def display_title(record: dict[str, Any]) -> str:
    """Titre affiché sur who.int (<h1>) : OverrideTitle si UseOverrideTitle et non vide."""
    override = (record.get("OverrideTitle") or "").strip()
    return override if record.get("UseOverrideTitle") and override else record["Title"]


def start_run(conn: sqlite3.Connection, source: str, started: str, finished: str, **counts: int) -> int:
    cur = conn.execute(
        """INSERT INTO ingestion_runs (source_code, started_at, finished_at, status, triggered_by,
                                       code_version, expected_count, seen_count, inserted_count, updated_count)
           VALUES (?, ?, ?, 'succes', 'manuel', 'check_schema', ?, ?, ?, ?)""",
        (source, started, finished, counts.get("expected"), counts.get("seen", 0), counts.get("inserted", 0),
         counts.get("updated", 0)),
    )
    return int(cur.lastrowid)


def insert_dons(conn: sqlite3.Connection, records: list[dict[str, Any]], run_id: int) -> None:
    for rec in records:
        body = canonical_json(rec)
        raw_id = conn.execute(
            """INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256,
                                         byte_size, body_text, source_modified_at, first_run_id, retrieved_at)
               VALUES ('oms_don', ?, ?, 'application/json', ?, ?, ?, ?, ?, ?)""",
            (
                rec["Id"],
                "https://www.who.int/api/news/diseaseoutbreaknews",
                hashlib.sha256(body.encode("utf-8")).hexdigest(),
                len(body.encode("utf-8")),
                body,
                rec["LastModified"],
                run_id,
                NOW,
            ),
        ).lastrowid
        cls = MANUAL_CLASSIFICATION[rec["UrlName"]]
        fig = MANUAL_FIGURES.get(rec["UrlName"])
        report_id = conn.execute(
            """INSERT INTO reports (source_code, external_id, external_ref, slug, url, title, summary,
                                    published_at, date_quality, disease_code, geo_scope, classification_status,
                                    figures_payload_id, figures_extractor_version,
                                    raw_payload_id, first_seen_run_id, last_seen_run_id)
               VALUES ('oms_don', ?, ?, ?, ?, ?, ?, ?, 'ok', ?, ?, 'valide', ?, ?, ?, ?, ?)""",
            (
                rec["Id"],
                rec["DonId"] or None,
                rec["UrlName"],
                f"https://www.who.int/emergencies/disease-outbreak-news/item/{rec['UrlName']}",
                display_title(rec),
                strip_html(rec.get("Summary")) or strip_html(rec.get("Overview")),
                rec["PublicationDateAndTime"],
                cls["disease"],
                cls["scope"],
                raw_id if fig else None,
                "manuel" if fig else None,
                raw_id,
                run_id,
                run_id,
            ),
        ).lastrowid
        conn.execute(
            """INSERT INTO report_versions (report_id, version, source_code, external_id, raw_payload_id, run_id)
               VALUES (?, 1, 'oms_don', ?, ?, ?)""",
            (report_id, rec["Id"], raw_id, run_id),
        )
        for i, iso3 in enumerate(cls["countries"]):
            conn.execute(
                "INSERT INTO report_countries (report_id, country_iso3, is_primary) VALUES (?, ?, ?)",
                (report_id, iso3, 1 if i == 0 else 0),
            )
        if fig:
            for measure, value in (("cas", fig["cases"]), ("deces", fig["deaths"])):
                conn.execute(
                    """INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure,
                                                   case_definition, precision, as_of, value, method, status,
                                                   evidence, extractor_version)
                       VALUES (?, ?, ?, ?, 'confirme', 'exact', ?, ?, 'manuel', 'valide', ?, 'manuel')""",
                    (report_id, raw_id, fig["country"], measure, fig["as_of"], value, fig["evidence"]),
                )


def iso_week_bounds(year: int, week: int) -> tuple[str, str]:
    monday = date.fromisocalendar(year, week, 1)
    return monday.isoformat(), (monday + timedelta(days=6)).isoformat()


def insert_observation(conn: sqlite3.Connection, series_id: int, year: int, week: int, value: float | None,
                       seen_at: str, run_id: int, source_version: str, raw_payload_id: int,
                       value_low: float | None = None, value_up: float | None = None,
                       value_status: str = "publiee") -> None:
    """Insère une valeur ; si un champ versionné diffère de la version courante, crée une révision.

    Champs versionnés (invariant I50) : value, value_low, value_up, value_status. Un
    source_version différent seul n'est pas une révision. raw_payload_id : brut d'où
    vient la valeur (I60), relu par le contrôle de relecture (D31).
    """
    start, end = iso_week_bounds(year, week)
    current = conn.execute(
        """SELECT version, value, value_low, value_up, value_status FROM observations
           WHERE series_id = ? AND period_start = ? AND valid_to IS NULL""",
        (series_id, start),
    ).fetchone()
    if current and current[1:] == (value, value_low, value_up, value_status):
        return  # republication identique : aucune ligne
    with conn:
        if current:
            conn.execute(
                "UPDATE observations SET valid_to = ? WHERE series_id = ? AND period_start = ? AND valid_to IS NULL",
                (seen_at, series_id, start),
            )
        conn.execute(
            """INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
                                         value, value_low, value_up, value_status, source_version, valid_from, run_id,
                                         raw_payload_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (series_id, start, end, year, week, (current[0] + 1) if current else 1, value, value_low, value_up,
             value_status, source_version, seen_at, run_id, raw_payload_id),
        )


def insert_raw(conn: sqlite3.Connection, source: str, resource_key: str, body: str, run_id: int,
               retrieved_at: str) -> int:
    """Archive un contenu brut (JSON ou CSV en clair) et renvoie son identifiant."""
    data = body.encode("utf-8")
    return int(conn.execute(
        """INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,
                                     body_text, first_run_id, retrieved_at)
           VALUES (?, ?, 'https://example.invalid', 'text/csv', ?, ?, ?, ?, ?)""",
        (source, resource_key, hashlib.sha256(data).hexdigest(), len(data), body, run_id, retrieved_at),
    ).lastrowid)


def expect_error(rep: Report, conn: sqlite3.Connection, label: str, query: str, params: tuple[Any, ...]) -> None:
    rep.add(f"**{label}**\n")
    rep.sql(query)
    try:
        with conn:
            cur = conn.execute(query, params)
        rep.add(f"Résultat : **aucune erreur**, {cur.rowcount} ligne(s) modifiée(s).\n")
    except sqlite3.IntegrityError as exc:
        rep.add(f"Résultat : rejeté, `sqlite3.IntegrityError: {exc}`\n")


def validate(rep: Report) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "validation.sqlite"
        conn = connect(db_path)
        apply_schema(conn)

        rep.add("## 1. Application du schéma\n")
        rep.add(f"- Moteur : SQLite {sqlite3.sqlite_version} (module `sqlite3` de Python ; "
                "l'outil en ligne de commande `sqlite3` n'est pas installé sur ce poste).")
        rep.add("- `db/schema.sql` puis `db/seed.sql` exécutés sans erreur.")
        rep.add(f"- `PRAGMA user_version` = {conn.execute('PRAGMA user_version').fetchone()[0]}")
        rep.add(f"- `PRAGMA integrity_check` = {conn.execute('PRAGMA integrity_check').fetchone()[0]}")
        rep.add(f"- `PRAGMA foreign_key_check` : {len(conn.execute('PRAGMA foreign_key_check').fetchall())} violation(s)\n")
        rep.sql("SELECT type, name FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name;")
        rep.table(conn.execute("SELECT type, name FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"))

        # --- Échantillon OMS ---------------------------------------------------
        records = json.loads(FIXTURE.read_text(encoding="utf-8"))["value"]
        with conn:
            run_oms = start_run(conn, "oms_don", "2026-10-13T17:59:00Z", NOW, expected=len(records),
                                seen=len(records), inserted=len(records))
            insert_dons(conn, records, run_oms)

        rep.add("## 2. Les 5 DON de l'échantillon\n")
        q = """SELECT r.slug, r.external_ref, r.title, substr(r.published_at, 1, 10) AS publie_le,
       r.disease_code, r.geo_scope,
       (SELECT group_concat(c.country_iso3) FROM report_countries AS c WHERE c.report_id = r.id) AS pays,
       (SELECT group_concat(f.measure || ' ' || f.value || ' (' || f.status || ')')
        FROM report_figures_current AS f WHERE f.report_id = r.id) AS chiffres
FROM reports AS r
ORDER BY r.published_at DESC;"""
        rep.sql(q)
        rep.table(conn.execute(q))

        # --- Observations fictives avec révision -------------------------------
        series_id = conn.execute(
            """INSERT INTO series (source_code, dataset, metric, disease_code, geo_level, geo_code, geo_label,
                                   age_group, period_type, value_kind, unit, case_status, date_basis)
               VALUES ('sentinelles', 'inc-3-PAY-ds2', 'inc100', 'grippe', 'pays', 'FR-MET',
                       'France métropolitaine', 'tous', 'semaine_iso', 'taux_incidence',
                       'pour 100 000 habitants', 'syndromique', 'consultation')"""
        ).lastrowid
        conn.commit()
        # valid_from = début de l'exécution (invariant I24)
        run_a = start_run(conn, "sentinelles", "2026-09-30T17:18:00Z", "2026-09-30T17:19:00Z", inserted=2)
        raw_a = insert_raw(conn, "sentinelles", "inc-3-PAY-ds2", "week,inc100\n202638,50\n202639,60", run_a,
                           "2026-09-30T17:18:00Z")
        insert_observation(conn, series_id, 2026, 38, 50.0, "2026-09-30T17:18:00Z", run_a, "v-a", raw_a)
        insert_observation(conn, series_id, 2026, 39, 60.0, "2026-09-30T17:18:00Z", run_a, "v-a", raw_a)
        run_b = start_run(conn, "sentinelles", "2026-10-07T17:18:00Z", "2026-10-07T17:19:00Z", inserted=1, updated=1)
        raw_b = insert_raw(conn, "sentinelles", "inc-3-PAY-ds2", "week,inc100\n202638,50\n202639,63\n202640,70",
                           run_b, "2026-10-07T17:18:00Z")
        insert_observation(conn, series_id, 2026, 38, 50.0, "2026-10-07T17:18:00Z", run_b, "v-b", raw_b)  # inchangée
        insert_observation(conn, series_id, 2026, 39, 63.0, "2026-10-07T17:18:00Z", run_b, "v-b", raw_b)  # révision
        insert_observation(conn, series_id, 2026, 40, 70.0, "2026-10-07T17:18:00Z", run_b, "v-b", raw_b)  # nouvelle
        conn.commit()

        rep.add("## 3. Observations hebdomadaires fictives\n")
        rep.add("Série : Sentinelles `inc-3-PAY-ds2` / `inc100`, France métropolitaine. **Valeurs fictives.** "
                "Exécution A (2026-09-30) : S38 = 50, S39 = 60. Exécution B (2026-10-07) : S38 inchangée (50), "
                "S39 révisée à 63, S40 = 70.\n")
        q = """SELECT id, iso_year, iso_week, period_start, version, value, valid_from, valid_to, run_id
FROM observations ORDER BY period_start, version;"""
        rep.sql(q)
        rep.table(conn.execute(q))

        rep.add("## 4. Requêtes demandées\n")
        rep.add("### 4.1 Dernière version d'une observation (S39)\n")
        q = """SELECT period_start, iso_week, version, value, valid_from
FROM observations_current
WHERE series_id = :series_id AND period_start = '2026-09-21';"""
        rep.sql(q)
        rep.table(conn.execute(q, {"series_id": series_id}))

        rep.add("Série courante complète (ce que le site affiche) :\n")
        q = """SELECT iso_week, value, version FROM observations_current
WHERE series_id = :series_id ORDER BY period_start;"""
        rep.sql(q)
        rep.table(conn.execute(q, {"series_id": series_id}))

        rep.add("### 4.2 Historique d'une révision (S39)\n")
        q = """SELECT version, value, valid_from, valid_to, source_version, run_id
FROM observations
WHERE series_id = :series_id AND period_start = '2026-09-21'
ORDER BY version;"""
        rep.sql(q)
        rep.table(conn.execute(q, {"series_id": series_id}))

        rep.add("Valeur telle qu'elle était connue le 2026-10-03 (requête « as-of », utile au backtest) :\n")
        q = """SELECT version, value
FROM observations
WHERE series_id = :series_id AND period_start = '2026-09-21'
  AND valid_from <= :as_of AND (valid_to IS NULL OR valid_to > :as_of);"""
        rep.sql(q)
        rep.table(conn.execute(q, {"series_id": series_id, "as_of": "2026-10-03T00:00:00Z"}))

        rep.add("### 4.3 DON d'une maladie sur 12 mois\n")
        rep.add("Les bornes sont calculées en Python et passées en paramètres "
                "(pas de fonction de date SQL, pour la portabilité).\n")
        q = """SELECT slug, title, substr(published_at, 1, 10) AS publie_le
FROM reports_active
WHERE disease_code = :disease AND published_at >= :since AND published_at < :until
ORDER BY published_at DESC;"""
        for disease, since, until in (
            ("pneumonie_indeterminee", "2025-10-13T18:00:00Z", NOW),
            ("cholera", "2022-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
        ):
            rep.add(f"Paramètres : `disease = '{disease}'`, `since = '{since}'`, `until = '{until}'`\n")
            rep.sql(q)
            rep.table(conn.execute(q, {"disease": disease, "since": since, "until": until}))

        rep.add("Contre-exemple : la même question pour le choléra en 2021, avec le champ `PublicationDate` "
                "lu dans le JSON brut au lieu de `published_at` (`PublicationDateAndTime`) :\n")
        q = """SELECT r.slug, r.title,
       substr(json_extract(p.body_text, '$.PublicationDate'), 1, 10) AS publication_date_brute,
       substr(r.published_at, 1, 10) AS published_at
FROM reports AS r JOIN raw_payloads AS p ON p.id = r.raw_payload_id
WHERE r.disease_code = 'cholera'
  AND json_extract(p.body_text, '$.PublicationDate') >= '2021-01-01'
  AND json_extract(p.body_text, '$.PublicationDate') <  '2022-01-01';"""
        rep.sql(q)
        rep.table(conn.execute(q))
        rep.add("Le bulletin de 1996 sortirait à tort dans une recherche sur 2021. "
                "Avec `published_at`, la même recherche ne renvoie rien.\n")

        rep.add("### 4.4 Doublons et contraintes\n")
        first = records[0]
        expect_error(
            rep, conn, "Doublon de DON (même Id OMS)",
            """INSERT INTO reports (source_code, external_id, slug, url, title, published_at, date_quality,
                     geo_scope, classification_status, raw_payload_id, first_seen_run_id, last_seen_run_id)
VALUES ('oms_don', ?, 'autre-slug', 'https://example.invalid', 'doublon', ?, 'ok',
        'inconnu', 'non_classe', 1, ?, ?);""",
            (first["Id"], first["PublicationDateAndTime"], run_oms, run_oms),
        )
        expect_error(
            rep, conn, "Doublon de version d'observation (S39, version 2)",
            """INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
                          value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (?, '2026-09-21', '2026-09-27', 2026, 39, 2, 99, ?, ?, ?, ?);""",
            (series_id, "2026-10-07T17:18:00Z", NOW, run_b, raw_b),
        )
        expect_error(
            rep, conn, "Deuxième version courante sans fermer la précédente (S40)",
            """INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
                          value, valid_from, run_id, raw_payload_id)
VALUES (?, '2026-09-28', '2026-10-04', 2026, 40, 2, 71, ?, ?, ?);""",
            (series_id, NOW, run_b, raw_b),
        )
        expect_error(
            rep, conn, "Chiffres extraits par LLM marqués « auto »",
            """INSERT INTO report_figures (report_id, raw_payload_id, measure, case_definition, precision,
                            value, method, status, evidence, extractor_version)
SELECT id, raw_payload_id, 'deces', 'total', 'exact', 1, 'llm', 'auto', 'confirmed the death', 'llm-0'
FROM reports WHERE slug = '2026-DON620';""",
            (),
        )
        expect_error(
            rep, conn, "Clé étrangère vers une série inexistante",
            """INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
                          value, valid_from, run_id, raw_payload_id)
VALUES (999, '2026-09-28', '2026-10-04', 2026, 40, 1, 1, ?, ?, ?);""",
            (NOW, run_b, raw_b),
        )
        body = canonical_json(first)
        expect_error(
            rep, conn, "Relance : même contenu brut réinséré (déduplication idempotente, pas une erreur)",
            """INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256,
                          byte_size, body_text, first_run_id, retrieved_at)
VALUES ('oms_don', ?, 'https://www.who.int/api/news/diseaseoutbreaknews', 'application/json', ?, ?, ?, ?, ?)
ON CONFLICT (source_code, resource_key, sha256) DO NOTHING;""",
            (first["Id"], hashlib.sha256(body.encode("utf-8")).hexdigest(), len(body.encode("utf-8")),
             body, run_oms, NOW),
        )
        count = conn.execute("SELECT count(*) FROM raw_payloads").fetchone()[0]
        rep.add(f"Après la relance : {count} lignes dans `raw_payloads` (5 attendues).\n")

        rep.add("### 4.5 Contrôle des invariants\n")
        rep.add("Vue qui doit être vide avant tout envoi de la base (voir `docs/01-invariants.md`) :\n")
        q = "SELECT invariant, table_name, row_id FROM controle_invariants;"
        rep.sql(q)
        rep.table(conn.execute(q))
        conn.close()


def measure_volume(rep: Report) -> None:
    """Remplit une base avec un volume proche de l'estimation v1 et mesure sa taille."""
    sentinel_series, sentinel_weeks = 4 * 14 * 2, 560      # 4 indicateurs × 14 zones × 2 mesures, depuis 2016
    odisse_series, odisse_weeks = 4 * 19 * 6 * 3, 300      # 4 jeux × 19 zones × 6 âges × 3 mesures, ~6 ans
    revision_rate = 0.05
    n_reports = 3199

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "volume.sqlite"
        conn = connect(db_path)
        apply_schema(conn)
        t0 = time.perf_counter()
        with conn:
            run_id = start_run(conn, "spf_odisse", "2026-10-13T00:00:00Z", NOW)
            run_oms = start_run(conn, "oms_don", "2026-10-13T00:00:00Z", NOW, expected=n_reports, seen=n_reports)
            conn.executemany(
                """INSERT INTO datasets (source_code, dataset, license_name, license_evidence, license_checked_at,
                                         is_publishable, publishable_since)
                   VALUES (?, ?, 'Licence Ouverte 2.0', 'verification_manuelle', ?, 1, ?)""",
                [(source, f"jeu-{j}", NOW, NOW) for source in ("sentinelles", "spf_odisse") for j in range(8)],
            )
            series_rows = []
            for i in range(sentinel_series + odisse_series):
                source = "sentinelles" if i < sentinel_series else "spf_odisse"
                series_rows.append((source, f"jeu-{i % 8}", f"mesure-{i}", "grippe", "region", f"{i:04d}",
                                    "zone", "tous", "semaine_iso", "taux", "unité", "syndromique",
                                    "passage_urgences"))
            conn.executemany(
                """INSERT INTO series (source_code, dataset, metric, disease_code, geo_level, geo_code,
                       geo_label, age_group, period_type, value_kind, unit, case_status, date_basis)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                series_rows,
            )
            raw_id = insert_raw(conn, "spf_odisse", "jeu-0", "export synthétique", run_id, NOW)
            obs = []
            for sid in range(1, sentinel_series + odisse_series + 1):
                weeks = sentinel_weeks if sid <= sentinel_series else odisse_weeks
                monday = date(2026, 9, 28) - timedelta(weeks=weeks)
                for w in range(weeks):
                    d = monday + timedelta(weeks=w)
                    y, wk, _ = d.isocalendar()
                    revised = (sid * 7919 + w) % 100 < revision_rate * 100
                    obs.append((sid, d.isoformat(), (d + timedelta(days=6)).isoformat(), y, wk, 1,
                                123.456789 + w, "v1", "2026-01-01T00:00:00Z",
                                "2026-02-01T00:00:00Z" if revised else None, run_id, raw_id))
                    if revised:
                        obs.append((sid, d.isoformat(), (d + timedelta(days=6)).isoformat(), y, wk, 2,
                                    124.5 + w, "v2", "2026-02-01T00:00:00Z", None, run_id, raw_id))
            conn.executemany(
                """INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
                       value, source_version, valid_from, valid_to, run_id, raw_payload_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                obs,
            )
            # Les DON de l'échantillon sont plus gros que la moyenne réelle (6 466 caractères,
            # mesurée sur les 3199 enregistrements en phase 0) : on tronque à cette taille.
            samples = [canonical_json(r) for r in json.loads(FIXTURE.read_text(encoding="utf-8"))["value"]]
            for i in range(n_reports):
                body = f"{i:06d}" + samples[i % len(samples)][:AVG_DON_JSON_CHARS - 6]
                raw_id = conn.execute(
                    """INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256,
                           byte_size, body_text, first_run_id, retrieved_at)
                       VALUES ('oms_don', ?, 'u', 'application/json', ?, ?, ?, ?, ?)""",
                    (f"id-{i}", hashlib.sha256(body.encode()).hexdigest(), len(body), body, run_oms, NOW),
                ).lastrowid
                report_id = conn.execute(
                    """INSERT INTO reports (source_code, external_id, slug, url, title, summary, published_at,
                           date_quality, geo_scope, classification_status, raw_payload_id,
                           first_seen_run_id, last_seen_run_id)
                       VALUES ('oms_don', ?, ?, 'u', 'titre', ?, ?, 'ok', 'inconnu', 'non_classe', ?, ?, ?)""",
                    (f"id-{i}", f"slug-{i}", "x" * 300, NOW, raw_id, run_oms, run_oms),
                ).lastrowid
                conn.execute(
                    """INSERT INTO report_versions (report_id, version, source_code, external_id, raw_payload_id,
                                                    run_id)
                       VALUES (?, 1, 'oms_don', ?, ?, ?)""",
                    (report_id, f"id-{i}", raw_id, run_oms),
                )
        conn.execute("VACUUM")
        elapsed = time.perf_counter() - t0
        n_obs = conn.execute("SELECT count(*) FROM observations").fetchone()[0]
        n_series = conn.execute("SELECT count(*) FROM series").fetchone()[0]
        raw_bytes = conn.execute("SELECT sum(byte_size) FROM raw_payloads").fetchone()[0]
        conn.close()
        size = db_path.stat().st_size
        gz = len(gzip.compress(db_path.read_bytes(), compresslevel=6))

    rep.add("## 5. Mesure de volume (base synthétique)\n")
    rep.add("Hypothèses (estimation, à confirmer en phase 2) : Sentinelles 4 indicateurs hebdomadaires × "
            "14 zones (national + 13 régions) × 2 mesures × 560 semaines ; Odissé 4 jeux SurSaUD × 19 zones × "
            "6 classes d'âge × 3 mesures × 300 semaines ; 5 % de points révisés une fois ; 3199 DON avec un "
            "JSON brut de 6 466 caractères (moyenne réelle mesurée en phase 0). Exports bruts Odissé non "
            "inclus (rétention à part).\n")
    rep.add("| Mesure | Valeur |")
    rep.add("|---|---|")
    rep.add(f"| Séries | {n_series:,} |".replace(",", " "))
    rep.add(f"| Lignes `observations` | {n_obs:,} |".replace(",", " "))
    rep.add(f"| JSON brut OMS | {raw_bytes / 1e6:.1f} Mo |")
    rep.add(f"| Taille du fichier SQLite (après VACUUM) | {size / 1e6:.1f} Mo |")
    rep.add(f"| Taille compressée (gzip -6) | {gz / 1e6:.1f} Mo |")
    rep.add(f"| Temps de remplissage | {elapsed:.1f} s |\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--volume", action="store_true")
    args = parser.parse_args()

    rep = Report()
    rep.add("# Phase 1 : validation du schéma")
    rep.add("")
    rep.add("Fichier généré par `python db/check_schema.py --out docs/01-validation.md --volume`. "
            "Ne pas modifier à la main.\n")
    validate(rep)
    if args.volume:
        measure_volume(rep)
    args.out.write_text(rep.text(), encoding="utf-8")


if __name__ == "__main__":
    main()
