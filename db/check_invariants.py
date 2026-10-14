"""Rejeu des contre-exemples de la revue du schéma (phase 1b).

Pour chaque contre-exemple, deux bases SQLite ':memory:' partent du même état
cohérent : l'une avec le schéma de la phase 1 (commit e8f65a6, lu par git show),
l'autre avec db/schema.sql. On y exécute les mêmes instructions fautives (adaptées
aux colonnes de chaque schéma) et on note :
  * si la base les rejette ;
  * sinon, si la vue controle_invariants ou PRAGMA foreign_key_check les détecte
    (contrôle avant envoi de la base) ;
  * sinon, quel test Python futur les couvre.
Le résultat obtenu sur le schéma corrigé est comparé au résultat attendu ; tout
écart est signalé dans le document et donne un code de sortie non nul.

Deux listes : CASES (contre-exemples construits pour l'arbitrage, état de départ
build_base) et REVIEW_CASES (preuves SQL du rapport du relecteur, rejouées telles
qu'écrites sur son état de départ : schéma, référentiel, 5 fixtures, série 1
Sentinelles, exécutions 1 OMS, 2 Sentinelles, 3 Odissé).

Ce script n'est pas le pipeline : les données sont des fixtures saisies à la main.

Usage :
    python db/check_invariants.py --out docs/01b-preuves.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "db"))
sys.dont_write_bytecode = True  # pas de db/__pycache__ dans le dépôt
import check_schema  # noqa: E402  (insert_observation, canonical_json)
SCHEMA = ROOT / "db" / "schema.sql"
SEED = ROOT / "db" / "seed.sql"
FIXTURE = ROOT / "fixtures" / "who_don_sample.json"
OLD_COMMIT = "e8f65a6"

# Débuts d'exécution de l'état de départ (05:47 UTC, horaire du workflow).
T_OMS1 = "2026-10-11T05:47:00Z"
T_SEN_A = "2026-09-30T05:47:00Z"
T_SEN_B = "2026-10-07T05:47:00Z"
T_SPF = "2026-10-08T05:47:00Z"
T_SEN_C = "2026-10-14T05:47:00Z"
DEDUP_A = "anomalie:sentinelles:inc-3-PAY-ds2:inc100:FR-MET:2026-09-21:v2:baseline_saisonniere@1"

# Libellés : catégorie de résultat -> texte du document.
LABELS = {
    "rejete": "rejeté par la base",
    "vue": "accepté, détecté par `controle_invariants`",
    "fk_check": "accepté, détecté par `PRAGMA foreign_key_check`",
    "test_seul": "accepté, **non détecté dans la base** : contrôle de relecture des bruts (phase 2, D31)",
    "coherent": "accepté, état cohérent (attendu)",
    "par_conception": "accepté **par conception** (risque documenté)",
    "hors_schema": "constat hors schéma : même résultat sur les deux schémas",
}
NO_VIOLATION = {"test_seul", "coherent", "par_conception", "hors_schema"}


def fin(started: str) -> str:
    """Fin d'exécution : 3 minutes après un début à hh:47."""
    return started[:14] + "50:00Z"


def oms_run(run_id: int, started: str, status: str, expected: int | None, seen: int | None,
            new: bool, absent: int | None = None, removed: int | None = None) -> str:
    error = "'controle'" if status in ("partiel", "echec") else "NULL"
    finished = "NULL" if status == "en_cours" else f"'{fin(started)}'"
    exp = "NULL" if expected is None else expected
    see = "NULL" if seen is None else seen
    if not new:
        return (f"INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,\n"
                f"    code_version, expected_count, seen_count, error_kind)\n"
                f"VALUES ({run_id}, 'oms_don', '{started}', {finished}, '{status}', 'planifie', 'ce', {exp}, {see}, {error});")
    ab = "NULL" if absent is None else absent
    rm = "NULL" if removed is None else removed
    return (f"INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,\n"
            f"    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)\n"
            f"VALUES ({run_id}, 'oms_don', '{started}', {finished}, '{status}', 'planifie', 'ce', {exp}, {see}, "
            f"{ab}, {rm}, {0 if absent is not None else 'NULL'}, {error});")


def source_run(run_id: int, source: str, started: str) -> str:
    return (f"INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by, code_version)\n"
            f"VALUES ({run_id}, '{source}', '{started}', '{fin(started)}', 'succes', 'planifie', 'ce');")


def obs(series_id: int, start: str, end: str, year: int, week: int | None, version: int, value: float,
        valid_from: str, run_id: int, valid_to: str | None = None, raw: int | None = None) -> str:
    """Observation de l'état de départ des CE ; brut par défaut : Sentinelles n° 5, Odissé n° 6 (I60)."""
    wk = "NULL" if week is None else week
    vt = "NULL" if valid_to is None else f"'{valid_to}'"
    raw = raw if raw is not None else (6 if series_id == 2 else 5)
    return (f"INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,\n"
            f"    value, valid_from, valid_to, run_id, raw_payload_id)\n"
            f"VALUES ({series_id}, '{start}', '{end}', {year}, {wk}, {version}, {value}, '{valid_from}', {vt}, "
            f"{run_id}, {raw});")


# -----------------------------------------------------------------------------
# État de départ cohérent (identique dans les deux schémas, sauf reports)
# -----------------------------------------------------------------------------

def fixture_records() -> dict[str, dict[str, Any]]:
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))["value"]
    return {r["UrlName"]: r for r in records}


def display_title(record: dict[str, Any]) -> str:
    override = (record.get("OverrideTitle") or "").strip()
    return override if record.get("UseOverrideTitle") and override else record["Title"]


# Trois DON réels de la fixture ; les Id (GUID) sont remplacés par des libellés courts.
DONS = [
    (1, "guid-a", "2026-DON620", "pneumonie_indeterminee", "pays", [("RUS", 1)]),
    (2, "guid-b", "2024-DON528", "mpox", "multi_pays", [("BDI", 0), ("KEN", 0), ("RWA", 0)]),
    (3, "guid-c", "2022-DON398_1", "cholera", "pays", [("SOM", 1)]),
]


def build_base(conn: sqlite3.Connection, new: bool) -> None:
    recs = fixture_records()
    conn.executescript(f"""
        INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
                                    code_version, expected_count, seen_count)
        VALUES (1, 'oms_don',     '{T_OMS1}',  '{fin(T_OMS1)}',  'succes', 'planifie', 'base', 3, 3),
               (2, 'sentinelles', '{T_SEN_A}', '{fin(T_SEN_A)}', 'succes', 'planifie', 'base', NULL, NULL),
               (3, 'sentinelles', '{T_SEN_B}', '{fin(T_SEN_B)}', 'succes', 'planifie', 'base', NULL, NULL),
               (4, 'spf_odisse',  '{T_SPF}',   '{fin(T_SPF)}',   'succes', 'planifie', 'base', NULL, NULL);
    """)
    payloads = [(1, "oms_don", "guid-a", 1), (2, "oms_don", "guid-b", 1), (3, "oms_don", "guid-c", 1),
                (4, "sentinelles", "inc-3-PAY-ds2", 2), (5, "sentinelles", "inc-3-PAY-ds2", 3),
                (6, "spf_odisse", "rougeole-donnees-declaration-obligatoire", 4)]
    for pid, source, key, run_id in payloads:
        body = f'{{"payload":{pid},"resource":"{key}"}}'
        conn.execute(
            """INSERT INTO raw_payloads (id, source_code, resource_key, request_url, content_type, sha256,
                                         byte_size, body_text, first_run_id, retrieved_at)
               VALUES (?, ?, ?, 'https://example.invalid', 'application/json', ?, ?, ?, ?, ?)""",
            (pid, source, key, hashlib.sha256(body.encode()).hexdigest(), len(body), body, run_id, T_OMS1),
        )
    for rid, guid, slug, disease, scope, countries in DONS:
        rec = recs[slug]
        common = (rid, guid, rec["DonId"] or None, slug,
                  f"https://www.who.int/emergencies/disease-outbreak-news/item/{slug}",
                  display_title(rec), rec["PublicationDateAndTime"], disease, scope, rid)
        if new:
            conn.execute(
                """INSERT INTO reports (id, source_code, external_id, external_ref, slug, url, title, published_at,
                                        date_quality, disease_code, geo_scope, classification_status,
                                        raw_payload_id, first_seen_run_id, last_seen_run_id)
                   VALUES (?, 'oms_don', ?, ?, ?, ?, ?, ?, 'ok', ?, ?, 'valide', ?, 1, 1)""", common)
            conn.execute("""INSERT INTO report_versions (report_id, version, source_code, external_id,
                                                         raw_payload_id, run_id)
                            VALUES (?, 1, 'oms_don', ?, ?, 1)""", (rid, guid, rid))
        else:
            conn.execute(
                """INSERT INTO reports (id, source_code, external_id, external_ref, slug, url, title, published_at,
                                        date_quality, disease_code, geo_scope, classification_status,
                                        raw_payload_id, first_seen_at, last_seen_at)
                   VALUES (?, 'oms_don', ?, ?, ?, ?, ?, ?, 'ok', ?, ?, 'valide', ?, ?, ?)""",
                common + (T_OMS1, T_OMS1))
        for iso3, primary in countries:
            conn.execute("INSERT INTO report_countries (report_id, country_iso3, is_primary) VALUES (?, ?, ?)",
                         (rid, iso3, primary))
    if new:
        conn.execute("UPDATE reports SET figures_payload_id = 2, figures_extractor_version = 'regle-0' WHERE id = 2")
        conn.executemany(
            """INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,
                                           precision, period_start, as_of, value, method, status, evidence,
                                           extractor_version)
               VALUES (2, 2, ?, 'cas', 'confirme', 'exact', NULL, ?, ?, 'regle', 'auto', ?, 'regle-0')""",
            [("BDI", "2024-08-17", 142, "Of 358 suspected cases tested, 142 (39.7%) tested positive for MPXV."),
             ("KEN", "2024-08-13", 1, "one case had tested positive for MPXV Clade Ib")],
        )
    conn.executescript(f"""
        INSERT INTO series (id, source_code, dataset, metric, disease_code, geo_level, geo_code, geo_label,
                            age_group, period_type, value_kind, unit, case_status, date_basis)
        VALUES (1, 'sentinelles', 'inc-3-PAY-ds2', 'inc100', 'grippe', 'pays', 'FR-MET', 'France métropolitaine',
                'tous', 'semaine_iso', 'taux_incidence', 'pour 100 000 habitants', 'syndromique', 'consultation'),
               (2, 'spf_odisse', 'rougeole-donnees-declaration-obligatoire', 'tx', 'rougeole', 'pays', 'FR',
                'France', 'tous', 'annee', 'taux', 'pour 100 000 habitants', 'non_precise', 'declaration');
        INSERT INTO observations (id, series_id, period_start, period_end, iso_year, iso_week, version, value,
                                  valid_from, valid_to, run_id, raw_payload_id)
        VALUES (1, 1, '2026-09-21', '2026-09-27', 2026, 39,   1, 60.0, '{T_SEN_A}', '{T_SEN_B}', 2, 4),
               (2, 1, '2026-09-21', '2026-09-27', 2026, 39,   2, 63.0, '{T_SEN_B}', NULL,        3, 5),
               (3, 1, '2026-09-28', '2026-10-04', 2026, 40,   1, 70.0, '{T_SEN_B}', NULL,        3, 5),
               (4, 2, '2025-01-01', '2025-12-31', 2025, NULL, 1, 1.2,  '{T_SPF}',   NULL,        4, 6);
        INSERT INTO anomalies (id, observation_id, method, method_version, parameters, observed_value,
                               expected_value, threshold_value, severity, status, detected_at, code_version)
        VALUES (1, 2, 'baseline_saisonniere', '1', '{{}}', 63.0, 40.0, 55.0, 'elevee', 'ouverte', '{T_SEN_B}', 'base');
        INSERT INTO alerts_log (id, alert_type, channel, dedup_key, anomaly_id, message, status, attempts,
                                created_at, sent_at)
        VALUES (1, 'anomalie', 'telegram', '{DEDUP_A}', 1, 'Grippe (Sentinelles) : hausse en semaine 39',
                'envoyee', 1, '{T_SEN_B}', '{T_SEN_B}');
    """)


REVIEW_T0 = "2026-10-01T00:00:00Z"  # début des exécutions 1 à 3 de l'état de départ du relecteur


def review_base(conn: sqlite3.Connection, new: bool) -> None:
    """État de départ du rapport : 5 fixtures, série Sentinelles 1, exécutions 1 OMS, 2 Sentinelles, 3 Odissé."""
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))["value"]
    for run_id, source, counts in ((1, "oms_don", (5, 5)), (2, "sentinelles", (None, None)),
                                   (3, "spf_odisse", (None, None))):
        conn.execute(
            """INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
                                           code_version, expected_count, seen_count)
               VALUES (?, ?, ?, '2026-10-01T00:05:00Z', 'succes', 'manuel', 'relecteur', ?, ?)""",
            (run_id, source, REVIEW_T0) + counts)
    for i, rec in enumerate(records, start=1):
        body = check_schema.canonical_json(rec)
        conn.execute(
            """INSERT INTO raw_payloads (id, source_code, resource_key, request_url, content_type, sha256,
                                         byte_size, body_text, source_modified_at, first_run_id, retrieved_at)
               VALUES (?, 'oms_don', ?, 'https://www.who.int/api/news/diseaseoutbreaknews', 'application/json',
                       ?, ?, ?, ?, 1, ?)""",
            (i, rec["Id"], hashlib.sha256(body.encode()).hexdigest(), len(body.encode()), body,
             rec["LastModified"], REVIEW_T0))
        common = (i, rec["Id"], rec["DonId"] or None, rec["UrlName"],
                  f"https://www.who.int/emergencies/disease-outbreak-news/item/{rec['UrlName']}",
                  display_title(rec), rec["PublicationDateAndTime"], i)
        if new:
            conn.execute(
                """INSERT INTO reports (id, source_code, external_id, external_ref, slug, url, title, published_at,
                                        date_quality, geo_scope, classification_status, raw_payload_id,
                                        first_seen_run_id, last_seen_run_id)
                   VALUES (?, 'oms_don', ?, ?, ?, ?, ?, ?, 'ok', 'inconnu', 'non_classe', ?, 1, 1)""", common)
            conn.execute("""INSERT INTO report_versions (report_id, version, source_code, external_id,
                                                         raw_payload_id, run_id)
                            VALUES (?, 1, 'oms_don', ?, ?, 1)""", (i, rec["Id"], i))
        else:
            conn.execute(
                """INSERT INTO reports (id, source_code, external_id, external_ref, slug, url, title, published_at,
                                        date_quality, geo_scope, classification_status, raw_payload_id,
                                        first_seen_at, last_seen_at)
                   VALUES (?, 'oms_don', ?, ?, ?, ?, ?, ?, 'ok', 'inconnu', 'non_classe', ?, ?, ?)""",
                common + (REVIEW_T0, REVIEW_T0))
    if new:  # bruts exigés par raw_payload_id obligatoire (I60) : 6 Sentinelles (exécution 2), 7 Odissé (exécution 3)
        check_schema.insert_raw(conn, "sentinelles", "inc-3-PAY-ds2", "week,inc100", 2, REVIEW_T0)
        check_schema.insert_raw(conn, "spf_odisse", "ira-virologie-renal", "semaine,valeur", 3, REVIEW_T0)
    conn.execute(
        """INSERT INTO series (id, source_code, dataset, metric, disease_code, geo_level, geo_code, geo_label,
                               period_type, value_kind, unit, case_status, date_basis)
           VALUES (1, 'sentinelles', 'inc-3-PAY-ds2', 'inc100', 'grippe', 'pays', 'FR-MET', 'France métropolitaine',
                   'semaine_iso', 'taux_incidence', 'pour 100 000 habitants', 'syndromique', 'consultation')""")


@dataclass
class Outcome:
    error: str | None = None
    violations: list[tuple[str, str, int]] = field(default_factory=list)
    fk: list[tuple[Any, ...]] = field(default_factory=list)
    shows: list[tuple[str, list[str], list[tuple[Any, ...]]]] = field(default_factory=list)

    def category(self) -> str:
        if self.error:
            return "rejete"
        if self.violations:
            return "vue"
        if self.fk:
            return "fk_check"
        return "aucune"


Hook = Callable[[sqlite3.Connection], None]


@dataclass
class Case:
    code: str
    point: str
    title: str
    invariants: str
    constat: str
    old: list[str] | None
    new: list[str] | None
    expected: str
    tests: str
    old_show: list[str] = field(default_factory=list)
    new_show: list[str] = field(default_factory=list)
    fk_off: bool = False
    old_py: Hook | None = None          # étape Python après les instructions SQL
    new_py: Hook | None = None
    py_desc: str = ""


@dataclass
class Schema:
    label: str
    sql: str
    seed: str
    new: bool


def open_db(schema: Schema, base: Callable[[sqlite3.Connection, bool], None]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema.sql)
    conn.executescript(schema.seed)
    conn.execute("PRAGMA foreign_keys = ON")
    base(conn, schema.new)
    conn.commit()
    return conn


def play(schema: Schema, base: Callable[[sqlite3.Connection, bool], None], statements: list[str],
         shows: list[str], fk_off: bool, hook: Hook | None) -> Outcome:
    conn = open_db(schema, base)
    out = Outcome()
    if fk_off:
        conn.execute("PRAGMA foreign_keys = OFF")  # connexion qui n'a pas exécuté le PRAGMA
    for stmt in statements:
        try:
            conn.execute(stmt)
        except sqlite3.DatabaseError as exc:
            out.error = f"{type(exc).__name__}: {exc}"
            conn.rollback()
            break
    conn.commit()
    if hook and not out.error:
        try:
            hook(conn)
        except sqlite3.DatabaseError as exc:
            out.error = f"{type(exc).__name__}: {exc}"
            conn.rollback()
        conn.commit()
    if schema.new:
        out.violations = [tuple(r) for r in conn.execute(
            "SELECT invariant, table_name, row_id FROM controle_invariants ORDER BY invariant, row_id")]
    out.fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if not out.error:
        for q in shows:
            cur = conn.execute(q)
            out.shows.append((q, [d[0] for d in cur.description], cur.fetchall()))
    conn.close()
    return out


# -----------------------------------------------------------------------------
# Contre-exemples
# -----------------------------------------------------------------------------

T5, T6, T7, T8 = ("2026-10-12T05:47:00Z", "2026-10-13T05:47:00Z", "2026-10-14T05:47:00Z", "2026-10-15T05:47:00Z")
SEEN_AB_OLD = "UPDATE reports SET last_seen_at = '{t}' WHERE external_id IN ('guid-a', 'guid-b');"
SEEN_AB_NEW = "UPDATE reports SET last_seen_run_id = {r} WHERE external_id IN ('guid-a', 'guid-b');"
PRESENCE = ("SELECT slug, last_seen_run_id, missing_runs, presence, removed_run_id, expected_removed_run_id\n"
            "FROM reports_presence ORDER BY report_id;")
ECART_OLD = ("SELECT (SELECT expected_count FROM ingestion_runs WHERE id = (SELECT max(id) FROM ingestion_runs\n"
             "        WHERE source_code = 'oms_don')) AS total_api,\n"
             "       (SELECT count(*) FROM reports_active) AS dons_actifs_en_base,\n"
             "       (SELECT count(*) FROM reports) AS dons_ingeres;")
ECART_NEW = ("SELECT g.id AS derniere_execution, g.expected_count AS total_api, g.seen_count,\n"
             "       (SELECT count(*) FROM reports AS r WHERE r.last_seen_run_id = g.id) AS presents_en_base,\n"
             "       g.absent_count, g.removed_count\n"
             "FROM ingestion_runs AS g WHERE g.id = (SELECT max(id) FROM ingestion_runs WHERE source_code = 'oms_don');")
FIG = ("INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,\n"
       "    precision, period_start, as_of, value, method, status, evidence, extractor_version)\nVALUES ({v});")
ALERT = ("INSERT INTO alerts_log (alert_type, channel, dedup_key, anomaly_id, report_id, run_id, message,\n"
         "    status, attempts, created_at, sent_at, last_error)\nVALUES ({v});")

CASES: list[Case] = [
    # --- Point A : écart 0 et retrait -------------------------------------------------
    Case("A1", "A", "Un DON disparaît de l'API : écart 0 et retrait", "I7, I9, I10",
         "Sur l'ancien schéma, la règle « seen_count = expected_count = nombre de reports_active » "
         "(architecture §3.2) échoue sur une exécution correcte dès qu'un DON disparaît ; le critère "
         "« DON ingérés = DON du site » ne redevient jamais vrai.",
         [oms_run(5, T5, "succes", 2, 2, False), SEEN_AB_OLD.format(t=T5)],
         [oms_run(5, T5, "succes", 2, 2, True, absent=1, removed=0), SEEN_AB_NEW.format(r=5),
          oms_run(6, T6, "partiel", 2, 1, True),
          "UPDATE reports SET last_seen_run_id = 6 WHERE external_id = 'guid-a';",
          oms_run(7, T7, "succes", 2, 2, True, absent=1, removed=0), SEEN_AB_NEW.format(r=7),
          oms_run(8, T8, "succes", 2, 2, True, absent=1, removed=1), SEEN_AB_NEW.format(r=8),
          "UPDATE reports SET removed_run_id = 8 WHERE external_id = 'guid-c';"],
         "coherent", "tests/test_oms.py::test_ecart_zero_sur_les_presents, ::test_retrait_a_la_troisieme_absence, "
         "::test_execution_partielle_ne_compte_pas",
         old_show=[ECART_OLD], new_show=[ECART_NEW, PRESENCE]),
    Case("A2", "A", "Retrait posé dès la première absence", "I10",
         "Rien ne relie le retrait aux exécutions : un retrait prématuré passe.",
         [oms_run(5, T5, "succes", 2, 2, False), SEEN_AB_OLD.format(t=T5),
          f"UPDATE reports SET removed_at = '{fin(T5)}' WHERE external_id = 'guid-c';"],
         [oms_run(5, T5, "succes", 2, 2, True, absent=1, removed=1), SEEN_AB_NEW.format(r=5),
          "UPDATE reports SET removed_run_id = 5 WHERE external_id = 'guid-c';"],
         "vue", "tests/test_oms.py::test_retrait_a_la_troisieme_absence", new_show=[PRESENCE]),
    Case("A3", "A", "Retrait antérieur à la dernière présence", "I10",
         "Un DON peut être marqué retiré avant d'avoir été vu pour la dernière fois.",
         [f"UPDATE reports SET removed_at = '2026-10-01T00:00:00Z' WHERE external_id = 'guid-c';"],
         ["UPDATE reports SET removed_run_id = 1 WHERE external_id = 'guid-c';"],
         "rejete", "(contrainte SQL)"),
    Case("A4", "A", "Exécution « succes » avec un comptage incomplet", "I7",
         "Une exécution peut être marquée réussie alors qu'il manque des enregistrements.",
         [oms_run(5, T5, "succes", 3, 2, False)],
         [oms_run(5, T5, "succes", 3, 2, True, absent=0, removed=0)],
         "rejete", "(contrainte SQL)"),
    Case("A5", "A", "DON reçu mais non écrit en base", "I9",
         "L'ancien contrôle compare des totaux : un DON reçu mais non mis à jour reste compté comme présent.",
         [oms_run(5, T5, "succes", 3, 3, False), SEEN_AB_OLD.format(t=T5)],
         [oms_run(5, T5, "succes", 3, 3, True, absent=0, removed=0), SEEN_AB_NEW.format(r=5)],
         "vue", "tests/test_oms.py::test_ecart_zero_sur_les_presents",
         old_show=[ECART_OLD], new_show=[ECART_NEW]),
    Case("A6", "A", "Exécution OMS complète sans comptages", "I8",
         "Une exécution OMS réussie peut n'avoir ni total annoncé ni total reçu : l'écart n'est pas mesurable.",
         [oms_run(5, T5, "succes", None, None, False)],
         [oms_run(5, T5, "succes", None, None, True)],
         "rejete", "(contrainte SQL) ; Id distincts : tests/test_oms.py::test_pagination_complete_sans_doublon"),
    Case("A7", "A", "Deux exécutions en cours pour une même source", "I5",
         "Rien n'empêche deux exécutions simultanées de la même source.",
         [oms_run(5, T5, "en_cours", None, None, False), oms_run(6, T5, "en_cours", None, None, False)],
         [oms_run(5, T5, "en_cours", None, None, True), oms_run(6, T5, "en_cours", None, None, True)],
         "rejete", "(contrainte SQL)"),
    Case("A8", "A", "Exécution restée « en cours » dans la base envoyée", "I6",
         "Une exécution interrompue sans être fermée reste en_cours.",
         [oms_run(5, T5, "en_cours", None, None, False)],
         [oms_run(5, T5, "en_cours", None, None, True)],
         "vue", "tests/test_pipeline.py::test_echec_de_source_ferme_l_execution"),

    # --- Point B : révisions ---------------------------------------------------------
    Case("R1", "B-révisions", "Versions qui se chevauchent", "I22",
         "La version 1 reste valide après l'ouverture de la version 2 : deux valeurs connues à la même date.",
         ["UPDATE observations SET valid_to = '2026-10-09T05:47:00Z' WHERE id = 1;"],
         ["UPDATE observations SET valid_to = '2026-10-09T05:47:00Z' WHERE id = 1;"],
         "vue", "tests/test_observations.py::test_fermeture_egale_ouverture_suivante"),
    Case("R2", "B-révisions", "Trou dans la numérotation des versions", "I21",
         "Une version 3 sans version 2.",
         [source_run(5, "sentinelles", T_SEN_C), f"UPDATE observations SET valid_to = '{T_SEN_C}' WHERE id = 3;",
          obs(1, "2026-09-28", "2026-10-04", 2026, 40, 3, 72.0, T_SEN_C, 5)],
         [source_run(5, "sentinelles", T_SEN_C), f"UPDATE observations SET valid_to = '{T_SEN_C}' WHERE id = 3;",
          obs(1, "2026-09-28", "2026-10-04", 2026, 40, 3, 72.0, T_SEN_C, 5)],
         "vue", "tests/test_observations.py::test_versions_numerotees_sans_trou"),
    Case("R3", "B-révisions", "Point sans version courante", "I22",
         "La seule version d'un point est fermée sans successeur : le point disparaît de la série courante.",
         [f"UPDATE observations SET valid_to = '{T_SEN_C}' WHERE id = 3;"],
         [f"UPDATE observations SET valid_to = '{T_SEN_C}' WHERE id = 3;"],
         "vue", "tests/test_observations.py::test_retrait_cree_une_version_nulle"),
    Case("R4", "B-révisions", "Version de durée nulle", "I23",
         "valid_to = valid_from : la version n'est visible à aucune date (requête « as-of »).",
         ["UPDATE observations SET valid_to = valid_from WHERE id = 1;"],
         ["UPDATE observations SET valid_to = valid_from WHERE id = 1;"],
         "rejete", "(contrainte SQL)"),
    Case("R5", "B-révisions", "Nouvelle version identique à la précédente", "I25",
         "Une révision sans changement de valeur fausse le décompte des révisions.",
         [source_run(5, "sentinelles", T_SEN_C), f"UPDATE observations SET valid_to = '{T_SEN_C}' WHERE id = 3;",
          obs(1, "2026-09-28", "2026-10-04", 2026, 40, 2, 70.0, T_SEN_C, 5)],
         [source_run(5, "sentinelles", T_SEN_C), f"UPDATE observations SET valid_to = '{T_SEN_C}' WHERE id = 3;",
          obs(1, "2026-09-28", "2026-10-04", 2026, 40, 2, 70.0, T_SEN_C, 5)],
         "vue", "tests/test_observations.py::test_valeur_inchangee_ne_cree_pas_de_version"),
    Case("R6", "B-révisions", "Valeur hors de son intervalle", "I27",
         "value = 70 avec un intervalle [75, 80].",
         ["UPDATE observations SET value_low = 75, value_up = 80 WHERE id = 3;"],
         ["UPDATE observations SET value_low = 75, value_up = 80 WHERE id = 3;"],
         "rejete", "(contrainte SQL)"),
    Case("R7", "B-révisions", "Anomalie ouverte sur une version révisée", "I28",
         "Une alerte peut porter sur une valeur que la source a déjà corrigée.",
         ["INSERT INTO anomalies (observation_id, method, method_version, parameters, observed_value,\n"
          "    expected_value, threshold_value, severity, status, detected_at, code_version)\n"
          f"VALUES (1, 'baseline_saisonniere', '1', '{{}}', 60.0, 40.0, 55.0, 'elevee', 'ouverte', '{T_SEN_B}', 'ce');"],
         ["INSERT INTO anomalies (observation_id, method, method_version, parameters, observed_value,\n"
          "    expected_value, threshold_value, severity, status, detected_at, code_version)\n"
          f"VALUES (1, 'baseline_saisonniere', '1', '{{}}', 60.0, 40.0, 55.0, 'elevee', 'ouverte', '{T_SEN_B}', 'ce');"],
         "vue", "tests/test_detection.py::test_revision_remplace_l_anomalie"),
    Case("R8", "B-révisions", "Version fermée réécrite", "I26",
         "La valeur d'une version déjà fermée est modifiée : l'historique est falsifié sans trace.",
         ["UPDATE observations SET value = 99 WHERE id = 1;"],
         ["UPDATE observations SET value = 99 WHERE id = 1;"],
         "test_seul", "tests/test_observations.py::test_ecriture_par_ajout_seul, tests/test_controle.py::test_relecture_detecte_valeur_reecrite"),
    Case("R9", "B-révisions", "valid_from différent du début d'exécution", "I24",
         "La date de validité ne correspond à aucune exécution : le « vintage » n'est pas reproductible.",
         [obs(1, "2026-10-05", "2026-10-11", 2026, 41, 1, 75.0, "2026-10-07T17:18:00Z", 3)],
         [obs(1, "2026-10-05", "2026-10-11", 2026, 41, 1, 75.0, "2026-10-07T17:18:00Z", 3)],
         "vue", "tests/test_observations.py::test_valid_from_egale_debut_d_execution"),
    Case("R10", "B-révisions", "Anomalie qui ne reprend pas la valeur évaluée", "I29",
         "La valeur affichée dans l'alerte diffère de la valeur en base.",
         ["UPDATE anomalies SET observed_value = 64 WHERE id = 1;"],
         ["UPDATE anomalies SET observed_value = 64 WHERE id = 1;"],
         "vue", "tests/test_detection.py::test_anomalie_reprend_la_valeur_observee"),

    # --- Point B : semaines ISO ------------------------------------------------------
    Case("W1", "B-semaines", "Année au format YYYYWW", "I30",
         "La semaine Sentiweb '202641' rangée telle quelle dans iso_year.",
         [obs(1, "2026-10-05", "2026-10-11", 202641, 41, 1, 75.0, T_SEN_B, 3)],
         [obs(1, "2026-10-05", "2026-10-11", 202641, 41, 1, 75.0, T_SEN_B, 3)],
         "rejete", "(contrainte SQL)"),
    Case("W2", "B-semaines", "Point annuel dans une série hebdomadaire", "I31",
         "iso_week NULL dans une série semaine_iso.",
         [obs(1, "2026-01-01", "2026-12-31", 2026, None, 1, 75.0, T_SEN_B, 3)],
         [obs(1, "2026-01-01", "2026-12-31", 2026, None, 1, 75.0, T_SEN_B, 3)],
         "vue", "tests/test_semaines.py::test_type_de_periode_coherent"),
    Case("W3", "B-semaines", "Semaine dans une série annuelle", "I31",
         "iso_week renseignée dans une série annee.",
         [obs(2, "2026-09-28", "2026-10-04", 2026, 40, 1, 1.0, T_SPF, 4)],
         [obs(2, "2026-09-28", "2026-10-04", 2026, 40, 1, 1.0, T_SPF, 4)],
         "vue", "tests/test_semaines.py::test_type_de_periode_coherent"),
    Case("W4", "B-semaines", "Point annuel qui ne couvre pas l'année", "I32",
         "Période 2024-03-01 → 2024-12-31 pour l'année 2024.",
         [obs(2, "2024-03-01", "2024-12-31", 2024, None, 1, 1.0, T_SPF, 4)],
         [obs(2, "2024-03-01", "2024-12-31", 2024, None, 1, 1.0, T_SPF, 4)],
         "rejete", "(contrainte SQL)"),
    Case("W5", "B-semaines", "Début de semaine qui n'est pas un lundi", "I33",
         "Semaine 41 de 2026 rangée au mardi 2026-10-06.",
         [obs(1, "2026-10-06", "2026-10-12", 2026, 41, 1, 75.0, T_SEN_B, 3)],
         [obs(1, "2026-10-06", "2026-10-12", 2026, 41, 1, 75.0, T_SEN_B, 3)],
         "rejete", "(contrainte SQL) ; tests/test_semaines.py::test_lundi_de_la_semaine_iso"),
    Case("W6", "B-semaines", "Semaine 53 d'une année qui n'en a que 52", "I33",
         "2025-W53 n'existe pas (2025 commence un mercredi).",
         [obs(1, "2025-12-29", "2026-01-04", 2025, 53, 1, 75.0, T_SEN_B, 3)],
         [obs(1, "2025-12-29", "2026-01-04", 2025, 53, 1, 75.0, T_SEN_B, 3)],
         "rejete", "(contrainte SQL) ; tests/test_semaines.py::test_semaine_53_refusee_si_annee_a_52_semaines"),
    Case("W7", "B-semaines", "Année civile au lieu de l'année ISO", "I33",
         "La semaine du lundi 2025-12-29 est 2026-W01 ; elle est rangée en 2025-W01.",
         [obs(1, "2025-12-29", "2026-01-04", 2025, 1, 1, 75.0, T_SEN_B, 3)],
         [obs(1, "2025-12-29", "2026-01-04", 2025, 1, 1, 75.0, T_SEN_B, 3)],
         "rejete", "(contrainte SQL) ; tests/test_semaines.py::test_annee_iso_differente_de_l_annee_civile"),
    Case("W8", "B-semaines", "Fin de semaine fausse", "I33",
         "Semaine 41 fermée le samedi 2026-10-10.",
         [obs(1, "2026-10-05", "2026-10-10", 2026, 41, 1, 75.0, T_SEN_B, 3)],
         [obs(1, "2026-10-05", "2026-10-10", 2026, 41, 1, 75.0, T_SEN_B, 3)],
         "rejete", "(contrainte SQL) ; tests/test_semaines.py::test_lundi_de_la_semaine_iso"),

    # --- Point B : références entre sources --------------------------------------------
    Case("X1", "B-références", "DON rattaché à un brut Sentinelles", "I13",
         "reports.raw_payload_id pointe vers un brut d'une autre source.",
         ["UPDATE reports SET raw_payload_id = 4 WHERE external_id = 'guid-a';"],
         ["UPDATE reports SET raw_payload_id = 4 WHERE external_id = 'guid-a';"],
         "rejete", "(contrainte SQL)"),
    Case("X2", "B-références", "DON rattaché au brut d'un autre DON", "I13",
         "Le DON a pointe vers la version brute du DON b.",
         ["UPDATE reports SET raw_payload_id = 2 WHERE external_id = 'guid-a';"],
         ["UPDATE reports SET raw_payload_id = 2 WHERE external_id = 'guid-a';"],
         "rejete", "(contrainte SQL)"),
    Case("X3", "B-références", "Brut OMS attribué à une exécution Sentinelles", "I12",
         "raw_payloads.first_run_id désigne une exécution d'une autre source.",
         ["INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,\n"
          f"    body_text, first_run_id, retrieved_at)\nVALUES ('oms_don', 'guid-d', 'u', 'application/json', "
          f"'{'0' * 64}', 2, '{{}}', 2, '{T_OMS1}');"],
         ["INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,\n"
          f"    body_text, first_run_id, retrieved_at)\nVALUES ('oms_don', 'guid-d', 'u', 'application/json', "
          f"'{'0' * 64}', 2, '{{}}', 2, '{T_OMS1}');"],
         "rejete", "(contrainte SQL)"),
    Case("X4", "B-références", "Observation Sentinelles attribuée à une exécution OMS", "I15",
         "observations.run_id désigne une exécution d'une autre source que la série.",
         [obs(1, "2026-10-05", "2026-10-11", 2026, 41, 1, 75.0, T_OMS1, 1)],
         [obs(1, "2026-10-05", "2026-10-11", 2026, 41, 1, 75.0, T_OMS1, 1)],
         "vue", "tests/test_observations.py::test_observation_rattachee_a_la_source_de_sa_serie"),
    Case("X5", "B-références", "Observation Sentinelles rattachée à un brut OMS", "I15",
         "observations.raw_payload_id désigne un brut d'une autre source que la série.",
         ["UPDATE observations SET raw_payload_id = 1 WHERE id = 3;"],
         ["UPDATE observations SET raw_payload_id = 1 WHERE id = 3;"],
         "vue", "tests/test_observations.py::test_observation_rattachee_a_la_source_de_sa_serie"),
    Case("X6", "B-références", "DON « vu » par une exécution Sentinelles", "I14",
         "Sans objet dans l'ancien schéma (le DON n'était pas relié à une exécution).",
         None,
         ["UPDATE reports SET last_seen_run_id = 2 WHERE external_id = 'guid-a';"],
         "rejete", "(contrainte SQL)"),
    Case("X7", "B-références", "Chiffre lu dans la version d'un autre DON", "I16",
         "Sans objet dans l'ancien schéma (pas de lien chiffre → version brute).",
         None,
         [FIG.format(v="2, 1, 'BDI', 'deces', 'confirme', 'exact', NULL, '2024-08-17', 0, 'regle', 'auto', "
                       "'No deaths were reported as of 17 August.', 'regle-0'")],
         "vue", "tests/test_chiffres.py::test_chiffre_rattache_a_une_version_de_son_don"),
    Case("X8", "B-références", "Chiffre pour un pays que le DON ne cite pas", "I17",
         "Sans objet dans l'ancien schéma (pas de chiffre par pays).",
         None,
         [FIG.format(v="2, 2, 'UGA', 'cas', 'confirme', 'exact', NULL, '2024-08-12', 2, 'regle', 'auto', "
                       "'two of which tested positive for MPXV Clade Ib', 'regle-0'")],
         "rejete", "(contrainte SQL)"),

    # --- Point C : alertes -------------------------------------------------------------
    Case("C1", "C", "Relance dans la même base : même clé de déduplication", "I44",
         "La déduplication fonctionne quand la base de départ connaît l'envoi.",
         [ALERT.format(v=f"'anomalie', 'telegram', '{DEDUP_A}', 1, NULL, NULL, 'Grippe : hausse S39', "
                         f"'a_envoyer', 0, '{T_SEN_C}', NULL, NULL")],
         [ALERT.format(v=f"'anomalie', 'telegram', '{DEDUP_A}', 1, NULL, NULL, 'Grippe : hausse S39', "
                         f"'a_envoyer', 0, '{T_SEN_C}', NULL, NULL")],
         "rejete", "(contrainte SQL)"),
    Case("C2", "C", "Relance après échec de l'envoi de la base", "D19, R14",
         "L'alerte a été envoyée à Telegram mais la base qui le note n'a pas été publiée : la relance "
         "repart de la base de la veille, qui ne connaît pas l'envoi. La même alerte est réécrite et renvoyée.",
         [ALERT.format(v=f"'nouveau_rapport', 'telegram', 'nouveau_rapport:oms_don:guid-a', NULL, 1, NULL, "
                         f"'Nouveau DON : 2026-DON620', 'a_envoyer', 0, '{T_OMS1}', NULL, NULL")],
         [ALERT.format(v=f"'nouveau_rapport', 'telegram', 'nouveau_rapport:oms_don:guid-a', NULL, 1, NULL, "
                         f"'Nouveau DON : 2026-DON620', 'a_envoyer', 0, '{T_OMS1}', NULL, NULL")],
         "par_conception", "tests/test_alertes.py::test_alerte_journalisee_avant_envoi"),
    Case("C3", "C", "Échec d'envoi sans tentative ni erreur", "I47",
         "Une alerte en echec sans message d'erreur ni tentative.",
         [ALERT.format(v=f"'source_en_echec', 'telegram', 'source_en_echec:sentinelles:2026-10-14', NULL, NULL, 2, "
                         f"'Sentinelles en échec', 'echec', 0, '{T_SEN_C}', NULL, NULL")],
         [ALERT.format(v=f"'source_en_echec', 'telegram', 'source_en_echec:sentinelles:2026-10-14', NULL, NULL, 2, "
                         f"'Sentinelles en échec', 'echec', 0, '{T_SEN_C}', NULL, NULL")],
         "rejete", "(contrainte SQL)"),
    Case("C4", "C", "Alerte envoyée sans tentative", "I47",
         "status envoyee avec attempts = 0.",
         ["UPDATE alerts_log SET attempts = 0 WHERE id = 1;"],
         ["UPDATE alerts_log SET attempts = 0 WHERE id = 1;"],
         "rejete", "(contrainte SQL)"),
    Case("C5", "C", "Alerte envoyée avant d'être créée", "I47",
         "sent_at antérieur à created_at.",
         ["UPDATE alerts_log SET sent_at = '2026-10-01T00:00:00Z' WHERE id = 1;"],
         ["UPDATE alerts_log SET sent_at = '2026-10-01T00:00:00Z' WHERE id = 1;"],
         "rejete", "(contrainte SQL)"),

    # --- Point D : chiffres ------------------------------------------------------------
    Case("D1", "D", "DON multi-pays (2024-DON528) : un chiffre par pays", "D23",
         "Constat 1 : un seul couple cas/décès par DON. Trois pays écrits, un seul conservé.",
         ["UPDATE reports SET cases = 142, deaths = NULL, figures_as_of = '2024-08-17', figures_method = 'regle',\n"
          "    figures_status = 'auto', figures_evidence = 'Burundi' WHERE slug = '2024-DON528';",
          "UPDATE reports SET cases = 1, deaths = NULL, figures_as_of = '2024-08-13', figures_method = 'regle',\n"
          "    figures_status = 'auto', figures_evidence = 'Kenya' WHERE slug = '2024-DON528';",
          "UPDATE reports SET cases = 4, deaths = 0, figures_as_of = '2024-08-07', figures_method = 'regle',\n"
          "    figures_status = 'auto', figures_evidence = 'Rwanda' WHERE slug = '2024-DON528';"],
         [FIG.format(v="2, 2, 'RWA', 'cas', 'confirme', 'exact', NULL, '2024-08-07', 4, 'regle', 'auto', "
                       "'four confirmed mpox cases and zero deaths', 'regle-0'"),
          FIG.format(v="2, 2, 'RWA', 'deces', 'confirme', 'exact', NULL, '2024-08-07', 0, 'regle', 'auto', "
                       "'four confirmed mpox cases and zero deaths', 'regle-0'")],
         "coherent", "tests/test_chiffres.py::test_un_chiffre_par_pays_et_par_mesure",
         old_show=["SELECT slug, cases, deaths, figures_as_of, figures_evidence FROM reports WHERE slug = '2024-DON528';"],
         new_show=["SELECT country_iso3, measure, case_definition, as_of, value\n"
                   "FROM report_figures_current WHERE report_id = 2 ORDER BY country_iso3, measure;"]),
    Case("D2", "D", "Coût d'un passage tardif à une table de chiffres", "D23",
         "SQLite ne peut pas supprimer une colonne citée par une contrainte CHECK de table : passer à "
         "report_figures après la phase 3 imposerait de reconstruire reports.",
         ["ALTER TABLE reports DROP COLUMN cases;"],
         None,
         "rejete", "(sans objet)"),
    Case("D3", "D", "Chiffre extrait par LLM marqué « auto »", "I35",
         "Règle de CONTEXTE ; déjà appliquée par l'ancien schéma, conservée.",
         ["UPDATE reports SET cases = 10, figures_method = 'llm', figures_status = 'auto',\n"
          "    figures_evidence = 'x' WHERE slug = '2026-DON620';"],
         [FIG.format(v="1, 1, 'RUS', 'deces', 'total', 'exact', NULL, '2026-10-02', 1, 'llm', 'auto', "
                       "'confirmed the death', 'llm-0'")],
         "rejete", "(contrainte SQL)"),
    Case("D4", "D", "Chiffre « ensemble du rapport » en double", "I36",
         "Sans objet dans l'ancien schéma. Montre l'utilité du COALESCE dans l'index unique (NULL ≠ NULL).",
         None,
         [FIG.format(v="3, 3, NULL, 'cas', 'total', 'exact', '2022-01-01', '2022-07-10', 7796, 'regle', 'auto', "
                       "'a cumulative number of 7796 cases of cholera', 'regle-0'"),
          FIG.format(v="3, 3, NULL, 'cas', 'total', 'exact', '2022-01-01', '2022-07-10', 7796, 'regle', 'auto', "
                       "'a cumulative number of 7796 cases of cholera', 'regle-0'")],
         "rejete", "(contrainte SQL)"),

    # --- Bruts et chronologie des DON (constat 5 du relecteur) ---------------------------
    Case("P1", "bruts", "Purge du JSON brut d'un DON", "I53",
         "Le JSON brut OMS doit être conservé ; la purge est réservée aux exports volumineux.",
         ["UPDATE raw_payloads SET body_text = NULL, purged_at = '2026-10-12T00:00:00Z' WHERE id = 1;"],
         ["UPDATE raw_payloads SET body_text = NULL, purged_at = '2026-10-12T00:00:00Z' WHERE id = 1;"],
         "rejete", "(contrainte SQL)"),
    Case("V1", "bruts", "Contenu courant changé sans nouvelle version", "I51",
         "reports.raw_payload_id change sans ligne dans la chronologie : le changement n'est pas daté.",
         ["INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,\n"
          f"    body_text, first_run_id, retrieved_at)\nVALUES ('oms_don', 'guid-a', 'u', 'application/json', "
          f"'{'1' * 64}', 2, '{{}}', 1, '{T_OMS1}');",
          "UPDATE reports SET raw_payload_id = (SELECT max(id) FROM raw_payloads) WHERE external_id = 'guid-a';"],
         ["INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,\n"
          f"    body_text, first_run_id, retrieved_at)\nVALUES ('oms_don', 'guid-a', 'u', 'application/json', "
          f"'{'1' * 64}', 2, '{{}}', 1, '{T_OMS1}');",
          "UPDATE reports SET raw_payload_id = (SELECT max(id) FROM raw_payloads) WHERE external_id = 'guid-a';"],
         "vue", "tests/test_oms.py::test_changement_de_contenu_cree_une_version"),

    # --- Licence d'un jeu retirée après collecte (D30) ----------------------------------
    Case("L1", "licences", "Licence retirée après collecte : données antérieures gardées", "D30, I54",
         "La Licence Ouverte 2.0 accorde un droit sans limite de durée : les observations collectées avant le "
         "changement restent publiables.",
         None, ["UPDATE datasets SET is_publishable = 0, not_publishable_since = '2026-10-14T00:00:00Z',\n    license_note = 'Licence retirée du catalogue le 2026-10-14.'\nWHERE dataset = 'rougeole-donnees-declaration-obligatoire';"],
         "coherent", "tests/test_sources.py::test_licence_retiree_garde_les_donnees_anterieures"),
    Case("L2", "licences", "Observation collectée après le retrait de licence", "D30, I54",
         "La collecte doit s'arrêter à not_publishable_since.",
         None, ["UPDATE datasets SET is_publishable = 0, not_publishable_since = '2026-10-14T00:00:00Z',\n    license_note = 'Licence retirée du catalogue le 2026-10-14.'\nWHERE dataset = 'rougeole-donnees-declaration-obligatoire';", source_run(5, "spf_odisse", "2026-10-15T05:47:00Z"),
                obs(2, "2026-01-01", "2026-12-31", 2026, None, 1, 2.0, "2026-10-15T05:47:00Z", 5)],
         "vue", "tests/test_sources.py::test_jeu_non_publiable_non_ingere"),

    # --- Séries ----------------------------------------------------------------------
    Case("S1", "séries", "Série Sentinelles en France entière", "I49",
         "Sentinelles ne couvre que la métropole (D22) ; une série 'FR' mélangerait deux périmètres.",
         ["INSERT INTO series (source_code, dataset, metric, disease_code, geo_level, geo_code, geo_label,\n"
          "    period_type, value_kind, unit, case_status, date_basis)\n"
          "VALUES ('sentinelles', 'inc-3-PAY-ds2', 'inc', 'grippe', 'pays', 'FR', 'France', 'semaine_iso',\n"
          "    'incidence', 'cas', 'syndromique', 'consultation');"],
         ["INSERT INTO series (source_code, dataset, metric, disease_code, geo_level, geo_code, geo_label,\n"
          "    period_type, value_kind, unit, case_status, date_basis)\n"
          "VALUES ('sentinelles', 'inc-3-PAY-ds2', 'inc', 'grippe', 'pays', 'FR', 'France', 'semaine_iso',\n"
          "    'incidence', 'cas', 'syndromique', 'consultation');"],
         "rejete", "(contrainte SQL)"),

    # --- Général ---------------------------------------------------------------------
    Case("G1", "général", "Connexion sans PRAGMA foreign_keys", "I1",
         "Toutes les clés étrangères (dont les clés composites I12-I17) sont inertes sur une connexion "
         "qui n'a pas exécuté le PRAGMA.",
         [obs(999, "2026-10-05", "2026-10-11", 2026, 41, 1, 75.0, T_SEN_B, 3)],
         [obs(999, "2026-10-05", "2026-10-11", 2026, 41, 1, 75.0, T_SEN_B, 3)],
         "fk_check", "tests/test_db.py::test_connexion_active_les_cles_etrangeres", fk_off=True),
]


# -----------------------------------------------------------------------------
# Preuves du rapport du relecteur (Codex GPT-5.5), rejouées telles qu'écrites
# -----------------------------------------------------------------------------
# Numérotation K<n> = constat n du rapport. Les compléments (marqués « complément »)
# sont des instructions ajoutées pour montrer la correction retenue.

T_R4 = "2026-10-02T00:00:00Z"
T_R5 = "2026-10-03T00:00:00Z"
T_R8 = "2026-10-08T00:00:00Z"
DON528 = "(SELECT id FROM reports WHERE slug = '2024-DON528')"
K1_QUERY = ("SELECT 4 AS expected_count, 4 AS seen_count,\n"
            "       (SELECT count(*) FROM reports_active) AS actifs;")
K1B_QUERY = ("WITH received(id) AS (VALUES(1),(2),(3),(4),(4))\n"
             "SELECT count(*), count(DISTINCT id),\n"
             "       (SELECT count(*) FROM reports_active)\nFROM received;")
K3_INSERT = ("INSERT INTO observations\n(series_id,period_start,period_end,iso_year,iso_week,version,\n"
             " value,valid_from,valid_to,run_id)\nVALUES\n(1,'2026-09-21','2026-09-27',2026,39,1,60,\n"
             " '2026-10-01T00:00:00Z','2026-10-10T00:00:00Z',2),\n(1,'2026-09-21','2026-09-27',2026,39,2,63,\n"
             " '2026-10-05T00:00:00Z',NULL,2);")
K3_ASOF = ("SELECT version,value FROM observations\nWHERE series_id=1 AND period_start='2026-09-21'\n"
           "  AND valid_from<='2026-10-07T00:00:00Z'\n  AND (valid_to IS NULL OR valid_to>'2026-10-07T00:00:00Z');")
K4_SHOW = ("SELECT version, value, value_low, value_up, source_version, valid_from, valid_to\n"
           "FROM observations WHERE series_id = 1 ORDER BY version;")
K4_V1 = ("INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,\n"
         "    value, value_low, value_up, source_version, valid_from, run_id)\n"
         f"VALUES (1, '2026-09-21', '2026-09-27', 2026, 39, 1, 60, 50, 70, 'v1', '{REVIEW_T0}', 2);")
K4_RUN = source_run(4, "sentinelles", T_R8)
K4_RAW2 = ("INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,\n"
           f"    body_text, first_run_id, retrieved_at)\nVALUES ('sentinelles', 'inc-3-PAY-ds2', 'u', 'text/csv', "
           f"printf('%064d', 8), 2, 'v2', 4, '{T_R8}');")
K5_RAW = ("INSERT INTO raw_payloads\n(source_code,resource_key,request_url,content_type,sha256,\n"
          " byte_size,body_text,first_run_id,retrieved_at)\nVALUES\n('oms_don','test','u','application/json',"
          "printf('%064d',{n}),\n 7,'{{\"v\":{n}}}',1,'{t}')\nON CONFLICT(source_code,resource_key,sha256) DO NOTHING;")
K5_SHOW = "SELECT body_text,retrieved_at FROM raw_payloads\nWHERE resource_key='test' ORDER BY retrieved_at;"
K5_PAYLOAD = "(SELECT id FROM raw_payloads WHERE resource_key = 'test' AND sha256 = printf('%064d', {n}))"
K5_CHRONO = ("SELECT v.version, p.body_text, g.started_at AS depuis\nFROM report_versions AS v\n"
             "JOIN raw_payloads AS p ON p.id = v.raw_payload_id\nJOIN ingestion_runs AS g ON g.id = v.run_id\n"
             "WHERE v.report_id = (SELECT id FROM reports WHERE external_id = 'test') ORDER BY v.version;")
K6_INSERT = ("INSERT INTO observations\n(series_id,period_start,period_end,iso_year,iso_week,\n"
             " version,value,valid_from,run_id)\nVALUES\n(1,'2020-12-28','2021-01-03',2020,53,1,10,\n"
             " '2026-10-01T00:00:00Z',2),\n(1,'2020-12-29','2021-01-04',2020,53,1,20,\n '2026-10-01T00:00:00Z',2);")
K6_GROUP = "SELECT iso_year,iso_week,count(*) FROM observations_current\nGROUP BY iso_year,iso_week;"
K6_2021 = ("INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,\n"
           f"    value, valid_from, run_id)\nVALUES (1, '2021-01-01', '2021-01-07', 2021, 53, 1, 10, '{REVIEW_T0}', 2);")
K6_BASELINE = ("WITH reference(iso_year,iso_week,value) AS\n(VALUES(2016,52,10),(2017,52,11),(2018,52,12),\n"
               "       (2019,52,13),(2020,53,14))\nSELECT count(*),avg(value) FROM reference\n"
               "WHERE iso_year BETWEEN 2016 AND 2020 AND iso_week=53;")
K7_OBS = ("INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,\n"
          f"    value, valid_from, run_id)\nVALUES (1, '2026-09-21', '2026-09-27', 2026, 39, 1, 60, '{REVIEW_T0}', 1);")
K7_JOIN = ("SELECT s.source_code,i.source_code,r.source_code\nFROM observations o\n"
           "JOIN series s ON s.id=o.series_id\nJOIN ingestion_runs i ON i.id=o.run_id\n"
           "JOIN raw_payloads r ON r.id=o.raw_payload_id;")
K7B_SHOW = ("SELECT r.external_id=p.resource_key\nFROM reports r JOIN raw_payloads p ON p.id=r.raw_payload_id\n"
            "WHERE r.id=1;")
K8_SHOW = ("SELECT\n instr(json_extract(p.body_text,'$.Title'),'Burundi') AS titre,\n"
           " instr(json_extract(p.body_text,'$.Overview'),'Burundi')>0 AS texte\n"
           "FROM reports r JOIN raw_payloads p ON p.id=r.raw_payload_id\nWHERE r.slug='2024-DON528';")
K8_ALTER = ("ALTER TABLE report_countries ADD COLUMN role TEXT NOT NULL DEFAULT 'concerne'\n"
            "    CHECK (role IN ('concerne', 'mentionne', 'voyage'));")
K9_PRAGMA = "SELECT name FROM pragma_table_info('series')\nWHERE name LIKE '%license%';"
K9_SERIES = ("INSERT INTO series\n(source_code,dataset,metric,disease_code,geo_level,geo_code,\n"
             " geo_label,period_type,value_kind,unit,case_status,date_basis)\nVALUES\n"
             "('spf_odisse','ira-virologie-renal','test','ira','pays','FR',\n"
             " 'France','semaine_iso','incidence','cas','confirme','declaration');")
K9_OBS = ("INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,\n"
          "    value, valid_from, run_id)\nVALUES ((SELECT id FROM series WHERE dataset = 'ira-virologie-renal'),\n"
          f"    '2026-09-21', '2026-09-27', 2026, 39, 1, 5, '{REVIEW_T0}', 3);")
K9_OLD_JOIN = ("SELECT s.dataset,src.license_name\nFROM series s JOIN sources src ON src.code=s.source_code\n"
               "WHERE s.dataset='ira-virologie-renal';")
K9_NEW_JOIN = ("SELECT s.dataset, d.license_name, d.is_publishable, d.publishable_since, d.license_note\n"
               "FROM series s\n"
               "JOIN datasets d ON d.source_code = s.source_code AND d.dataset = s.dataset\n"
               "WHERE s.dataset='ira-virologie-renal';")
K10_INSERT = ("INSERT INTO observations\n(series_id,period_start,period_end,iso_year,iso_week,version,\n"
              " value,value_low,value_up,valid_from,run_id)\nVALUES\n(1,'2026-09-21','2026-09-27',2026,39,1,-5,0,10,\n"
              " '2026-10-01T00:00:00Z',2),\n(1,'2026-09-28','2026-10-04',2026,40,1,NULL,NULL,NULL,\n"
              " '2026-10-01T00:00:00Z',2),\n(1,'2026-10-05','2026-10-11',2026,41,1,0,NULL,NULL,\n"
              " '2026-10-01T00:00:00Z',2);")
K10_SHOW = "SELECT iso_week,value,value_low,value_up\nFROM observations_current ORDER BY iso_week;"
K10_NULL = ("INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,\n"
            f"    value, valid_from, run_id)\nVALUES (1, '2026-09-28', '2026-10-04', 2026, 40, 1, NULL, '{REVIEW_T0}', 2);")
K10_NEG = ("INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,\n"
           f"    value, valid_from, run_id)\nVALUES (1, '2026-09-21', '2026-09-27', 2026, 39, 1, -5, '{REVIEW_T0}', 2);")
K11_BAD = ("UPDATE ingestion_runs\nSET started_at='2026-99-99t99:99:99z',\n"
           "    finished_at='2026-99-99t99:99:99z'\nWHERE id=1;")
K11_TZ = "UPDATE ingestion_runs\nSET started_at='2026-10-01T02:00:00+02:00' WHERE id=1;"
K12_SHOW = "SELECT dedup_key,status FROM alerts_log\nWHERE status IN ('a_envoyer','echec');"
K14_ANOMALY = ("INSERT INTO anomalies (observation_id, method, method_version, parameters, observed_value,\n"
               "    expected_value, threshold_value, severity, detected_at, code_version)\n"
               "VALUES ((SELECT max(id) FROM observations), 'baseline_saisonniere', '1', 'pas du JSON',\n"
               f"    60, 40, 50, 'elevee', '{REVIEW_T0}', 'relecteur');")


def git_show(path: str) -> str:
    return subprocess.run(["git", "show", f"{OLD_COMMIT}:{path}"], cwd=ROOT, check=True,
                          capture_output=True, encoding="utf-8").stdout


def old_insert_observation() -> Callable[..., None]:
    """insert_observation de la phase 1 (commit e8f65a6), celle que le relecteur a appelée."""
    namespace: dict[str, Any] = {"__name__": "check_schema_e8f65a6", "__file__": str(ROOT / "db" / "check_schema.py")}
    exec(compile(git_show("db/check_schema.py"), f"check_schema.py@{OLD_COMMIT}", "exec"), namespace)
    return namespace["insert_observation"]


def k4_old(conn: sqlite3.Connection) -> None:
    # Signature de la phase 1 : aucune borne ne peut être transmise, seule la valeur est comparée.
    old_insert_observation()(conn, 1, 2026, 39, 60.0, T_R8, 4, "v2")


def k4_new(conn: sqlite3.Connection) -> None:
    raw = conn.execute("SELECT max(id) FROM raw_payloads WHERE source_code = 'sentinelles'").fetchone()[0]
    check_schema.insert_observation(conn, 1, 2026, 39, 60.0, T_R8, 4, "v2", raw, value_low=40.0, value_up=80.0)


def add_raw(sql: str, raw: int) -> str:
    """Adapte une insertion du relecteur au schéma corrigé, où raw_payload_id est obligatoire (I60).

    Seul changement : la colonne raw_payload_id et sa valeur en fin de chaque ligne.
    """
    head, values = sql.split("VALUES", 1)
    head = head.replace("run_id)", "run_id, raw_payload_id)", 1)
    values = re.sub(r"(,\s*\d+)\)(?=[,;])", rf"\1, {raw})", values)
    return f"-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)\n{head}VALUES{values}"


def k12(conn: sqlite3.Connection) -> None:
    conn.execute("""INSERT INTO alerts_log (alert_type, channel, dedup_key, report_id, message, status, attempts,
                                            created_at)
                    VALUES ('nouveau_rapport', 'telegram', 'rapport:1', 1, 'Nouveau DON', 'a_envoyer', 0,
                            '2026-10-01T00:00:00Z')""")
    conn.commit()
    image = conn.serialize()               # base telle qu'envoyée la veille
    conn.execute("""UPDATE alerts_log SET status='envoyee',
                    sent_at='2026-10-01T01:00:00Z', attempts=1 WHERE id=1""")
    conn.commit()                          # Telegram a reçu le message, la base n'est pas envoyée
    conn.deserialize(image)                # la relance repart de l'image précédente


REVIEW_CASES: list[Case] = [
    Case("K1a", "constat 1", "Comptage OMS contre retrait après trois absences", "D24, I9, I10",
         "Règle de la phase 1 : seen = expected = nombre de reports_active. Un DON sur 5 disparaît de l'API.",
         [oms_run(4, T_R4, "succes", 4, 4, False),
          f"UPDATE reports SET last_seen_at = '{T_R4}' WHERE id <> 5;"],
         [oms_run(4, T_R4, "succes", 4, 4, True, absent=1, removed=0),
          "UPDATE reports SET last_seen_run_id = 4 WHERE id <> 5;"],
         "coherent", "tests/test_oms.py::test_ecart_zero_sur_les_presents",
         old_show=[K1_QUERY], new_show=[K1_QUERY, ECART_NEW, PRESENCE]),
    Case("K1b", "constat 1", "Comptes égaux, ensembles différents", "I8, I9",
         "5 enregistrements reçus dont un doublon, le 5e DON manque : seen_count = expected_count = 5.",
         [oms_run(4, T_R4, "succes", 5, 5, False),
          f"UPDATE reports SET last_seen_at = '{T_R4}' WHERE id IN (1, 2, 3, 4);"],
         [oms_run(4, T_R4, "succes", 5, 5, True, absent=1, removed=0),
          "UPDATE reports SET last_seen_run_id = 4 WHERE id IN (1, 2, 3, 4);"],
         "vue", "tests/test_oms.py::test_pagination_complete_sans_doublon",
         old_show=[K1B_QUERY], new_show=[K1B_QUERY]),
    Case("K2", "constat 2", "Chiffres d'un DON sans définition", "D23",
         "Le DON mpox contient 474 suspects, 142 confirmés, des cumuls et plusieurs pays.",
         [],
         [f"INSERT INTO report_countries (report_id, country_iso3) VALUES ({DON528}, 'BDI');",
          f"UPDATE reports SET figures_payload_id = raw_payload_id, figures_extractor_version = 'regle-0'\n"
          f"WHERE id = {DON528};",
          "INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,\n"
          "    precision, as_of, value, method, status, evidence, extractor_version)\n"
          "SELECT id, raw_payload_id, 'BDI', 'cas', 'suspect', 'exact', '2024-08-17', 474, 'regle', 'auto',\n"
          "    '474 suspected cases (86.9%) had been investigated and validated', 'regle-0'\n"
          "FROM reports WHERE slug = '2024-DON528';",
          "INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,\n"
          "    precision, as_of, value, method, status, evidence, extractor_version)\n"
          "SELECT id, raw_payload_id, 'BDI', 'cas', 'confirme', 'exact', '2024-08-17', 142, 'regle', 'auto',\n"
          "    'Of 358 suspected cases tested, 142 (39.7%) tested positive for MPXV.', 'regle-0'\n"
          "FROM reports WHERE slug = '2024-DON528';"],
         "coherent", "tests/test_chiffres.py::test_un_chiffre_par_pays_et_par_mesure",
         old_show=["SELECT name FROM pragma_table_info('reports')\nWHERE name IN\n"
                   " ('case_status','value_kind','period_start','period_end','date_basis');",
                   "SELECT\n instr(json_extract(p.body_text,'$.Overview'),'474 suspected')>0,\n"
                   " instr(json_extract(p.body_text,'$.Overview'),'142 (39.7%)')>0,\n"
                   " instr(json_extract(p.body_text,'$.Overview'),'cumulatively')>0\n"
                   "FROM reports r JOIN raw_payloads p ON p.id=r.raw_payload_id\nWHERE r.slug='2024-DON528';"],
         new_show=["SELECT country_iso3, measure, case_definition, period_start, as_of, value\n"
                   "FROM report_figures_current ORDER BY value DESC;"]),
    Case("K3", "constat 3", "Versions historiques qui se chevauchent", "I22, I24",
         "Deux versions connues le 2026-10-07.",
         [K3_INSERT], [add_raw(K3_INSERT, 6)], "vue", "tests/test_observations.py::test_fermeture_egale_ouverture_suivante",
         old_show=[K3_ASOF], new_show=[K3_ASOF]),
    Case("K4", "constat 4", "Révision des bornes perdue", "I50",
         "Point initial 60 [50, 70] ; nouvelle publication 60 [40, 80], source_version 'v2'.",
         [K4_RUN, K4_V1], [K4_RUN, add_raw(K4_V1, 6), K4_RAW2], "coherent",
         "tests/test_observations.py::test_revision_des_bornes_cree_une_version",
         old_show=[K4_SHOW], new_show=[K4_SHOW], old_py=k4_old, new_py=k4_new,
         py_desc="Python : relance de `insert_observation` avec la valeur 60 et `source_version = 'v2'`. Phase 1 : "
                 "fonction du commit e8f65a6, qui ne reçoit pas les bornes et ne compare que la valeur. Corrigé : "
                 "fonction actuelle, appelée avec les bornes 40 et 80."),
    Case("K5", "constat 5", "Suite de contenus A → B → A", "D26, I51, I52",
         "La déduplication par hash garde 2 contenus et perd la date du retour à A.",
         [K5_RAW.format(n=1, t="2026-10-01T00:00:00Z"), K5_RAW.format(n=2, t="2026-10-02T00:00:00Z"),
          K5_RAW.format(n=1, t="2026-10-03T00:00:00Z")],
         [K5_RAW.format(n=1, t="2026-10-01T00:00:00Z"), K5_RAW.format(n=2, t="2026-10-02T00:00:00Z"),
          K5_RAW.format(n=1, t="2026-10-03T00:00:00Z"),
          "-- complément : chronologie du DON 'test' dans report_versions",
          oms_run(4, T_R4, "partiel", None, None, True), oms_run(5, T_R5, "partiel", None, None, True),
          "INSERT INTO reports (source_code, external_id, slug, url, title, published_at, date_quality,\n"
          "    geo_scope, classification_status, raw_payload_id, first_seen_run_id, last_seen_run_id)\n"
          f"VALUES ('oms_don', 'test', 'test', 'u', 'test', '{REVIEW_T0}', 'ok', 'inconnu', 'non_classe',\n"
          f"    {K5_PAYLOAD.format(n=1)}, 1, 5);",
          "INSERT INTO report_versions (report_id, version, source_code, external_id, raw_payload_id, run_id)\n"
          f"SELECT id, 1, 'oms_don', 'test', {K5_PAYLOAD.format(n=1)}, 1 FROM reports WHERE external_id = 'test';",
          "INSERT INTO report_versions (report_id, version, source_code, external_id, raw_payload_id, run_id)\n"
          f"SELECT id, 2, 'oms_don', 'test', {K5_PAYLOAD.format(n=2)}, 4 FROM reports WHERE external_id = 'test';",
          "INSERT INTO report_versions (report_id, version, source_code, external_id, raw_payload_id, run_id)\n"
          f"SELECT id, 3, 'oms_don', 'test', {K5_PAYLOAD.format(n=1)}, 5 FROM reports WHERE external_id = 'test';"],
         "coherent", "tests/test_oms.py::test_retour_a_un_contenu_anterieur_cree_une_version",
         old_show=[K5_SHOW], new_show=[K5_SHOW, K5_CHRONO]),
    Case("K6a", "constat 6", "Semaine commençant un mardi, deux semaines 2020-W53 courantes", "I33",
         "Deux points courants pour la même année et la même semaine ISO.",
         [K6_INSERT], [add_raw(K6_INSERT, 6)], "rejete", "(contrainte SQL)",
         old_show=[K6_GROUP]),
    Case("K6b", "constat 6", "2021-01-01 rangé en 2021-W53", "I33",
         "Cette date appartient à 2020-W53 ; 2021 n'a que 52 semaines ISO.",
         [K6_2021], [add_raw(K6_2021, 6)], "rejete", "(contrainte SQL)"),
    Case("K6c", "constat 6", "Baseline W53 avec une seule référence", "Q9",
         "Hors schéma : règle de la baseline à définir avant la phase de détection.",
         [], [], "hors_schema", "tests/test_detection.py::test_semaine_53_regle_de_reference",
         old_show=[K6_BASELINE], new_show=[K6_BASELINE]),
    Case("K7a", "constat 7", "Observation Sentinelles avec exécution et brut OMS", "I15",
         "Clés étrangères valides, provenance fausse.",
         [K7_OBS, "UPDATE observations SET raw_payload_id=1;"],
         [add_raw(K7_OBS, 6), "UPDATE observations SET raw_payload_id=1;"],
         "vue", "tests/test_observations.py::test_observation_rattachee_a_la_source_de_sa_serie",
         old_show=[K7_JOIN, "PRAGMA foreign_key_check;"], new_show=[K7_JOIN]),
    Case("K7b", "constat 7", "DON pointant le brut d'un autre DON", "I13",
         "Modification acceptée en phase 1.",
         ["UPDATE reports SET raw_payload_id=2 WHERE id=1;"], ["UPDATE reports SET raw_payload_id=2 WHERE id=1;"],
         "rejete", "(contrainte SQL)", old_show=[K7B_SHOW]),
    Case("K8", "constat 8", "Pays absents du titre", "R11",
         "Hors schéma : méthode de classification (phase 3). Complément : ajouter plus tard un rôle par pays "
         "ne coûte qu'un ALTER TABLE.",
         [K8_ALTER], [K8_ALTER], "hors_schema", "tests/test_classification.py::test_pays_lus_dans_le_texte_regional",
         old_show=[K8_SHOW], new_show=[K8_SHOW]),
    Case("K9", "constat 9", "Licence par jeu de données", "D27, I54",
         "Série créée sur un jeu exclu faute de licence ; la licence affichée est celle du fournisseur.",
         [K9_SERIES, K9_OBS], [K9_SERIES, add_raw(K9_OBS, 7)], "vue", "tests/test_sources.py::test_jeu_sans_licence_non_ingere",
         old_show=[K9_PRAGMA, K9_OLD_JOIN], new_show=[K9_PRAGMA, K9_NEW_JOIN]),
    Case("K10a", "constat 10", "Valeur négative hors de ses bornes", "I27",
         "-5 avec l'intervalle [0, 10] ; absence sans motif ; zéro.",
         [K10_INSERT], [add_raw(K10_INSERT, 6)], "rejete", "(contrainte SQL)", old_show=[K10_SHOW]),
    Case("K10b", "constat 10", "Complément : valeur absente sans motif", "I55",
         "Une valeur NULL doit porter son motif (value_status).",
         [K10_NULL], [add_raw(K10_NULL, 6)], "rejete", "(contrainte SQL)"),
    Case("K10c", "constat 10", "Complément : valeur sous le domaine de la série", "I56",
         "-5 sans bornes, pour une série dont la plus petite valeur admissible est 0.",
         None, ["UPDATE series SET value_min = 0 WHERE id = 1;", add_raw(K10_NEG, 6)],
         "vue", "tests/test_observations.py::test_valeur_dans_le_domaine_de_la_serie"),
    Case("K11a", "constat 11", "Horodatage impossible en minuscules", "I2",
         "LIKE est insensible à la casse et '_' accepte tout caractère.",
         [K11_BAD], [K11_BAD], "rejete", "(contrainte SQL)",
         old_show=["SELECT started_at,finished_at FROM ingestion_runs WHERE id=1;"]),
    Case("K11b", "constat 11", "Horodatage avec décalage +02:00", "I2",
         "Rejeté dans les deux schémas : la normalisation en UTC se fait en Python avant insertion.",
         [K11_TZ], [K11_TZ], "rejete", "(contrainte SQL)"),
    Case("K12", "constat 12", "Alerte envoyée, base non persistée", "D19, R14",
         "Restauration de l'image précédente par deserialize().",
         [], [], "par_conception", "tests/test_alertes.py::test_alerte_journalisee_avant_envoi",
         old_show=[K12_SHOW], new_show=[K12_SHOW], old_py=k12, new_py=k12,
         py_desc="Python : alerte `rapport:1` écrite `a_envoyer`, image de la base (`serialize`), passage à "
                 "`envoyee`, puis restauration de l'image (`deserialize`)."),
    Case("K13", "constat 13", "Croissance des exports bruts", "R16, I58",
         "Hors schéma : arithmétique de dimensionnement du relecteur.",
         [], [], "hors_schema", "tests/test_pipeline.py::test_taille_de_l_asset_bornee",
         old_show=["SELECT 26*10.0,52*10.0,260*10.0;"], new_show=["SELECT 26*10.0,52*10.0,260*10.0;"]),
    Case("K14a", "constat 14", "Précision de REAL", "architecture §6",
         "Hors schéma : REAL SQLite = double précision ; à migrer en DOUBLE PRECISION.",
         [], [], "hors_schema", "(migration)",
         old_show=["SELECT CAST(1.2345678901234567 AS REAL);"], new_show=["SELECT CAST(1.2345678901234567 AS REAL);"]),
    Case("K14b", "constat 14", "Paramètres d'anomalie qui ne sont pas du JSON", "I59",
         "parameters = 'pas du JSON' accepté en phase 1.",
         [K7_OBS.replace(", 1);", ", 2);"), K14_ANOMALY],
         [add_raw(K7_OBS.replace(", 1);", ", 2);"), 6), K14_ANOMALY],
         "rejete", "(contrainte SQL)",
         old_show=["SELECT parameters,json_valid(parameters) FROM anomalies;"]),
]


# -----------------------------------------------------------------------------
# Rendu
# -----------------------------------------------------------------------------

def md_table(headers: list[str], rows: list[tuple[Any, ...]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append("| " + " | ".join("NULL" if v is None else str(v) for v in row) + " |")
    return lines


def describe(out: Outcome, new: bool) -> str:
    cat = out.category()
    if cat == "rejete":
        return f"rejeté : `{' '.join(out.error.split())}`"
    parts = []
    if out.violations:
        parts.append("`controle_invariants` : " + ", ".join(f"{i} ({t} #{r})" for i, t, r in out.violations))
    if out.fk:
        parts.append(f"`PRAGMA foreign_key_check` : {len(out.fk)} violation(s)")
    if parts:
        return "accepté ; détecté par " + " ; ".join(parts)
    return "accepté ; aucune violation détectée" if new else "accepté ; aucun contrôle ne le détecte"


def short(out: Outcome | None, new: bool) -> str:
    if out is None:
        return "sans objet"
    cat = out.category()
    if cat == "rejete":
        return "rejeté"
    if cat == "aucune":
        return "accepté" if not new else "accepté, aucune violation"
    if cat == "vue":
        return "accepté, vue : " + ", ".join(sorted({v[0] for v in out.violations}))
    return "accepté, foreign_key_check"


def matches(case: Case, out: Outcome | None) -> bool:
    if out is None:
        return case.expected == "rejete" and case.new is None  # D2 : sans objet côté nouveau schéma
    cat = out.category()
    if case.expected in NO_VIOLATION:
        return cat == "aucune"
    return cat == case.expected


Result = tuple[Case, Outcome | None, Outcome | None, bool]


def run_all(cases: list[Case], old: Schema, new: Schema,
            base: Callable[[sqlite3.Connection, bool], None]) -> list[Result]:
    results = []
    for case in cases:
        old_out = (play(old, base, case.old, case.old_show, case.fk_off, case.old_py)
                   if case.old is not None else None)
        new_out = (play(new, base, case.new, case.new_show, case.fk_off, case.new_py)
                   if case.new is not None else None)
        results.append((case, old_out, new_out, matches(case, new_out)))
    return results


def render_summary(add: Callable[[str], None], results: list[Result], label: str) -> list[str]:
    mismatches = [c.code for c, _, _, ok in results if not ok]
    tally: dict[str, int] = {}
    for case, _, new_out, _ in results:
        if new_out is not None:
            tally[case.expected] = tally.get(case.expected, 0) + 1
    old_accepted = sum(1 for _, o, _, _ in results if o is not None and o.category() != "rejete")
    old_total = sum(1 for _, o, _, _ in results if o is not None)
    add(f"{len(results)} {label}. Phase 1 : **{old_accepted} acceptés sur {old_total}** applicables. "
        f"Schéma corrigé ({sum(tally.values())} applicables) :")
    add("")
    for key in ("rejete", "vue", "fk_check", "test_seul", "par_conception", "coherent", "hors_schema"):
        if tally.get(key):
            add(f"- {LABELS[key]} : **{tally[key]}**")
    add("")
    add("Écarts entre résultat attendu et résultat obtenu : "
        + ("**aucun**." if not mismatches else "**" + ", ".join(mismatches) + "**."))
    add("")
    add("| Code | Point | Invariant | Phase 1 (`" + OLD_COMMIT + "`) | Schéma corrigé | Couverture Python |")
    add("|---|---|---|---|---|---|")
    for case, old_out, new_out, ok in results:
        flag = "" if ok else " **ÉCART**"
        add(f"| {case.code} | {case.point} | {case.invariants} | {short(old_out, False)} | "
            f"{short(new_out, True)}{flag} | `{case.tests}` |")
    add("")
    return mismatches


def render_details(add: Callable[[str], None], lines: list[str], results: list[Result], prefix: str) -> None:
    for case, old_out, new_out, ok in results:
        add(f"### {prefix}{case.code} · {case.title}")
        add("")
        add(f"Point {case.point} · invariant(s) {case.invariants} · résultat attendu : {LABELS[case.expected]}"
            + ("" if ok else " · **ÉCART**"))
        add("")
        add(case.constat)
        add("")
        for label, stmts, out, new in (("Phase 1", case.old, old_out, False), ("Schéma corrigé", case.new, new_out, True)):
            if stmts is None:
                add(f"**{label}** : sans objet.")
                add("")
                continue
            add(f"**{label}**")
            add("")
            if stmts:
                add("```sql")
                add("\n".join(stmts))
                add("```")
                add("")
            if case.py_desc and (case.old_py if not new else case.new_py):
                add(case.py_desc)
                add("")
            add("→ " + describe(out, new))
            add("")
            for q, headers, rows in out.shows:
                add("```sql")
                add(q)
                add("```")
                lines.extend(md_table(headers, rows))
                add("")
        add(f"Test Python futur : `{case.tests}`")
        add("")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    new = Schema("Corrigé (`db/schema.sql`)", SCHEMA.read_text(encoding="utf-8"), SEED.read_text(encoding="utf-8"), True)
    old = Schema(f"Phase 1 (`{OLD_COMMIT}`)", git_show("db/schema.sql"), git_show("db/seed.sql"), False)

    lines: list[str] = []
    add = lines.append
    add("# Phase 1b : rejeu des contre-exemples et des preuves du relecteur")
    add("")
    add("Fichier généré par `python db/check_invariants.py --out docs/01b-preuves.md`. Ne pas modifier à la main.")
    add("")
    add(f"Moteur : SQLite {sqlite3.sqlite_version}, bases `:memory:` ouvertes par le module `sqlite3` de Python "
        "(l'outil en ligne de commande `sqlite3` n'est pas installé sur ce poste). Chaque cas part d'une base neuve. "
        f"Phase 1 = schéma et référentiel du commit `{OLD_COMMIT}` (lus par `git show`).")
    add("")
    add("Deux séries de cas :")
    add("- **§2-3, contre-exemples de l'arbitrage** (CE-…), construits à partir des points A à D de la demande ;")
    add("- **§4-5, preuves du rapport du relecteur** (K…, K*n* = constat *n*), rejouées telles qu'écrites, "
        "sur son état de départ (5 fixtures, série Sentinelles 1, exécutions 1 OMS, 2 Sentinelles, 3 Odissé). "
        "Les instructions marquées « complément » montrent la correction retenue.")
    add("")

    add("## 1. Application des schémas")
    add("")
    for schema in (old, new):
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(schema.sql)
        conn.executescript(schema.seed)
        counts = dict(conn.execute("SELECT type, count(*) FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' GROUP BY type"))
        empty_ctrl = conn.execute("SELECT count(*) FROM controle_invariants").fetchone()[0] if schema.new else None
        add(f"**{schema.label}** : schéma puis référentiel exécutés sans erreur ; "
            f"{counts.get('table', 0)} tables, {counts.get('index', 0)} index, {counts.get('view', 0)} vues ; "
            f"`integrity_check` = {conn.execute('PRAGMA integrity_check').fetchone()[0]}.")
        conn.close()
        if schema.new:
            ctrl = []
            for base in (build_base, review_base):
                c = open_db(schema, base)
                ctrl.append((c.execute("SELECT count(*) FROM controle_invariants").fetchone()[0],
                             len(c.execute("PRAGMA foreign_key_check").fetchall())))
                c.close()
            add(f"`controle_invariants` : {empty_ctrl} ligne(s) sur la base vide, {ctrl[0][0]} sur l'état de départ "
                f"des CE, {ctrl[1][0]} sur celui du relecteur ; `foreign_key_check` : {ctrl[0][1]} et {ctrl[1][1]} "
                "violation(s). La vue ne produit pas de fausse alerte sur un état cohérent.")
        add("")
    add("État de départ des CE : 3 DON réels de la fixture (`2026-DON620`, `2024-DON528`, `2022-DON398_1`) vus par "
        "l'exécution OMS n° 1 ; une série Sentinelles hebdomadaire (S39 révisée de 60 à 63, S40 = 70) ; une série "
        "Odissé annuelle ; une anomalie ouverte sur S39 v2 ; une alerte envoyée. Schéma corrigé seulement : deux "
        "chiffres de `2024-DON528` (Burundi, Kenya). Valeurs des séries fictives.")
    add("")

    ce_results = run_all(CASES, old, new, build_base)
    review_results = run_all(REVIEW_CASES, old, new, review_base)

    add("## 2. Contre-exemples de l'arbitrage : synthèse")
    add("")
    mismatches = render_summary(add, ce_results, "contre-exemples")
    add("## 3. Contre-exemples de l'arbitrage : détail")
    add("")
    render_details(add, lines, ce_results, "CE-")
    add("## 4. Preuves du relecteur : synthèse")
    add("")
    mismatches += render_summary(add, review_results, "preuves rejouées")
    add("## 5. Preuves du relecteur : détail")
    add("")
    render_details(add, lines, review_results, "")

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(CASES)} contre-exemples, {len(REVIEW_CASES)} preuves du relecteur ; écarts : {mismatches or 'aucun'}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
