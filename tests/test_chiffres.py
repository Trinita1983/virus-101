"""Table `report_figures` : précision des chiffres (D33), unicité (I36), fourchettes (I61, I62)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

import pytest

from conftest import assert_base_coherente
from fake_who import FakeWHO, fixture_records
from observatoire.db import SQL_DIR, connect, init_db
from observatoire.oms.ingest import RunSummary

Ingest = Callable[[FakeWHO], RunSummary]
PRECISIONS = ("exact", "environ", "au_moins", "au_plus", "fourchette_basse", "fourchette_haute")


@pytest.fixture
def figures(conn: sqlite3.Connection, ingest: Ingest) -> sqlite3.Connection:
    """Base avec les 5 DON de la fixture ; le DON Mpox a ses pays listés (I17)."""
    ingest(FakeWHO(fixture_records()))
    report_id = conn.execute("SELECT id FROM reports WHERE slug = '2024-DON528'").fetchone()[0]
    conn.executemany("INSERT INTO report_countries (report_id, country_iso3) VALUES (?, ?)",
                     [(report_id, "BDI"), (report_id, "RWA")])
    return conn


def add_figure(conn: sqlite3.Connection, **changes: Any) -> int:
    """Insère un chiffre du DON Mpox ; `changes` remplace les valeurs par défaut (None les retire)."""
    row = conn.execute("SELECT id, raw_payload_id FROM reports WHERE slug = '2024-DON528'").fetchone()
    values: dict[str, Any] = {
        "report_id": row["id"], "raw_payload_id": row["raw_payload_id"], "country_iso3": "BDI",
        "measure": "cas", "case_definition": "suspect", "precision": "exact", "period_start": None,
        "as_of": "2024-08-17", "value": 150, "method": "regle", "status": "auto",
        "evidence": "texte source", "extractor_version": "regle-0"}
    values.update(changes)
    values = {k: v for k, v in values.items() if v is not None or k in ("country_iso3", "period_start")}
    columns = ", ".join(values)
    marks = ", ".join(f":{k}" for k in values)
    return int(conn.execute(f"INSERT INTO report_figures ({columns}) VALUES ({marks}) RETURNING id",
                            values).fetchone()[0])


def range_bounds(conn: sqlite3.Connection, low: int, high: int, **key: Any) -> tuple[int, int]:
    return (add_figure(conn, precision="fourchette_basse", value=low, **key),
            add_figure(conn, precision="fourchette_haute", value=high, **key))


def i61(conn: sqlite3.Connection) -> list[tuple[str, str, int]]:
    return [tuple(r) for r in conn.execute("SELECT * FROM controle_invariants WHERE invariant = 'I61'")]


def test_le_schema_s_execute_sans_erreur_et_precision_est_obligatoire(tmp_path: Any) -> None:
    connection = connect(tmp_path / "neuve.sqlite")
    assert init_db(connection) is True  # db/schema.sql puis db/seed.sql, sans erreur
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    column = next(r for r in connection.execute("PRAGMA table_info(report_figures)")
                  if r["name"] == "precision")
    assert (column["type"], column["notnull"], column["dflt_value"]) == ("TEXT", 1, None)
    assert [tuple(r) for r in connection.execute("SELECT * FROM controle_invariants")] == []
    connection.close()
    assert "precision" in (SQL_DIR / "schema.sql").read_text(encoding="utf-8")


def test_precision_sans_valeur_par_defaut(figures: sqlite3.Connection) -> None:
    row = figures.execute("SELECT id, raw_payload_id FROM reports WHERE slug = '2024-DON528'").fetchone()
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL constraint failed: report_figures.precision"):
        figures.execute(
            """INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure,
                      case_definition, as_of, value, method, status, evidence, extractor_version)
               VALUES (?, ?, 'BDI', 'cas', 'suspect', '2024-08-17', 1, 'regle', 'auto', 'x', 'r')""",
            (row["id"], row["raw_payload_id"]))


@pytest.mark.parametrize("bad", ["approx", "", "Exact", "fourchette", "environ ", "about", "au moins"])
def test_precision_hors_liste_rejetee(figures: sqlite3.Connection, bad: str) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_figure(figures, precision=bad)


def test_les_six_precisions_sont_acceptees(figures: sqlite3.Connection) -> None:
    for i, precision in enumerate(PRECISIONS):
        add_figure(figures, precision=precision, country_iso3="RWA", as_of=f"2024-08-{10 + i:02d}")
    assert figures.execute("SELECT count(DISTINCT precision) FROM report_figures").fetchone()[0] == 6


def test_deux_bornes_d_une_fourchette_coexistent(figures: sqlite3.Connection) -> None:
    low, high = range_bounds(figures, 120, 150)
    rows = figures.execute("SELECT precision, value FROM report_figures ORDER BY value").fetchall()
    assert [tuple(r) for r in rows] == [("fourchette_basse", 120), ("fourchette_haute", 150)]
    assert low != high
    # idem pour l'ensemble du rapport (pays NULL) : COALESCE les fait se heurter, pas se confondre
    range_bounds(figures, 10, 20, country_iso3=None, measure="deces")
    assert figures.execute("SELECT count(*) FROM report_figures").fetchone()[0] == 4


@pytest.mark.parametrize("country", ["BDI", None])
@pytest.mark.parametrize("precision", PRECISIONS)
def test_doublon_exact_rejete(figures: sqlite3.Connection, precision: str,
                              country: str | None) -> None:
    add_figure(figures, precision=precision, country_iso3=country)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        add_figure(figures, precision=precision, country_iso3=country, value=999)


@pytest.mark.parametrize("second", ["environ", "au_moins", "au_plus", "exact"])
def test_un_meme_chiffre_n_a_qu_une_lecture_ponctuelle(figures: sqlite3.Connection,
                                                       second: str) -> None:
    add_figure(figures, precision="exact")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        add_figure(figures, precision=second)
    add_figure(figures, precision=second, as_of="2024-08-18")  # autre date : autre chiffre
    add_figure(figures, precision=second, case_definition="confirme")  # autre définition


def test_une_borne_ne_remplace_pas_une_valeur_ponctuelle_mais_cohabite(figures: sqlite3.Connection) -> None:
    add_figure(figures, precision="fourchette_basse", value=120)
    add_figure(figures, precision="exact", value=130)  # rôles distincts : 'fourchette_basse' / 'point'
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        add_figure(figures, precision="fourchette_basse", value=121)


def test_fourchette_borne_basse_inferieure_ou_egale(figures: sqlite3.Connection) -> None:
    """I61 : la vue de contrôle signale une borne basse supérieure à la borne haute."""
    range_bounds(figures, 120, 150)
    range_bounds(figures, 100, 100, country_iso3="RWA")  # bornes égales : permis
    range_bounds(figures, 5, 9, country_iso3=None, measure="deces")
    assert i61(figures) == []
    assert_base_coherente(figures)

    low, _ = range_bounds(figures, 150, 120, as_of="2024-08-20")  # inversée : non rejetée par SQL
    assert i61(figures) == [("I61", "report_figures", low)]
    # une autre fourchette (autre date, autre pays) n'est pas rapprochée de celle-ci
    range_bounds(figures, 1, 2, as_of="2024-08-21")
    range_bounds(figures, 300, 400, country_iso3="RWA", as_of="2024-08-20")
    assert i61(figures) == [("I61", "report_figures", low)]
