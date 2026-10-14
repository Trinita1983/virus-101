"""Ingestion OMS de bout en bout : pagination, idempotence, révisions, présence des DON."""

from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest

from conftest import assert_base_coherente, row_counts
from fake_who import FakeWHO, fixture_records, make_record, make_records
from observatoire.config import Settings
from observatoire.oms.client import WhoClient
from observatoire.oms.ingest import RunSummary, run_oms_ingestion

Ingest = Callable[[FakeWHO], RunSummary]


def presence(conn: sqlite3.Connection, slug: str) -> sqlite3.Row:
    row: sqlite3.Row = conn.execute("SELECT * FROM reports_presence WHERE slug = ?", (slug,)).fetchone()
    return row


# --- Pagination (I8) ---------------------------------------------------------------------------


@pytest.mark.parametrize("pages, missing", [(5, 0), (5, 1), (5, 3), (5, 9), (1, 4), (2, 0)])
def test_pagination_complete_sans_doublon(
    conn: sqlite3.Connection, settings: Settings, ingest: Ingest, pages: int, missing: int
) -> None:
    """I8 : N pages de `taille` moins les manquants donnent exactement ces DON, sans doublon ni perte."""
    size = settings.page_size
    total = pages * size - missing
    fake = FakeWHO(make_records(total))
    summary = ingest(fake)

    stored = [r[0] for r in conn.execute("SELECT external_id FROM reports")]
    assert len(stored) == total == pages * size - missing
    assert len(set(stored)) == len(stored)  # aucun doublon
    assert set(stored) == {r["Id"] for r in fake.records}  # aucune perte
    assert (summary.status, summary.expected_count, summary.seen_count) == ("succes", total, total)
    # La dernière page est partielle ; si le total est un multiple de la taille, une page vide la suit.
    expected_pages = pages if missing else pages + 1
    assert fake.page_skips == [i * size for i in range(expected_pages)]
    assert_base_coherente(conn)


def test_pagination_a_l_echelle_de_la_phase_0(conn: sqlite3.Connection, settings: Settings) -> None:
    """3199 enregistrements, pages de 100 : 1 appel de décompte + 32 pages (architecture §3.2)."""
    fake = FakeWHO(make_records(3199))
    client = WhoClient(replace(settings, page_size=100), transport=httpx.MockTransport(fake))
    summary = run_oms_ingestion(conn, client)
    client.close()
    assert (summary.status, summary.expected_count, summary.seen_count) == ("succes", 3199, 3199)
    assert [c["kind"] for c in fake.calls] == ["count"] + ["page"] * 32
    assert fake.page_skips == [i * 100 for i in range(32)]
    assert conn.execute("SELECT count(DISTINCT external_id) FROM reports").fetchone()[0] == 3199
    assert_base_coherente(conn)


def test_pagination_reponse_vide(conn: sqlite3.Connection, ingest: Ingest) -> None:
    fake = FakeWHO([])
    summary = ingest(fake)
    assert (summary.status, summary.expected_count, summary.seen_count) == ("inchange", 0, 0)
    assert fake.page_skips == [0]
    assert row_counts(conn)["reports"] == 0
    assert_base_coherente(conn)


def test_ids_en_double_rendent_l_execution_partielle(
    conn: sqlite3.Connection, ingest: Ingest
) -> None:
    """I8 : des `Id` reçus en double ne sont pas écrits deux fois ; l'exécution est `partiel`."""
    records = make_records(20)
    fake = FakeWHO(records + [copy.deepcopy(records[4])])
    summary = ingest(fake)
    assert summary.status == "partiel" and summary.error_kind == "controle"
    assert "en double" in (summary.error_message or "")
    assert row_counts(conn)["reports"] == 20
    assert_base_coherente(conn)


def test_total_annonce_different_du_recu_rend_l_execution_partielle(
    conn: sqlite3.Connection, ingest: Ingest
) -> None:
    fake = FakeWHO(make_records(25))
    fake.fault(lambda: httpx.Response(200, json={"@odata.count": 99, "value": []}), skip=None)
    summary = ingest(fake)
    assert summary.status == "partiel" and summary.error_kind == "controle"
    assert summary.seen_count == 25 and summary.expected_count == 99
    assert row_counts(conn)["reports"] == 25  # les DON reçus sont écrits (architecture §7)
    assert_base_coherente(conn)


def test_baisse_de_plus_de_1_pourcent_rend_l_execution_partielle(
    conn: sqlite3.Connection, ingest: Ingest
) -> None:
    fake = FakeWHO(make_records(100))
    assert ingest(fake).status == "succes"
    del fake.records[:10]
    summary = ingest(fake)
    assert summary.status == "partiel" and "baisse de plus de 1 %" in (summary.error_message or "")
    assert presence(conn, "2030-DON0")["presence"] == "present"  # une exécution partielle ne compte pas
    assert_base_coherente(conn)


# --- Idempotence -------------------------------------------------------------------------------


def test_idempotence_second_run_sans_ajout(conn: sqlite3.Connection, ingest: Ingest) -> None:
    fake = FakeWHO(make_records(47) + fixture_records())
    first = ingest(fake)
    assert (first.status, first.inserted_count) == ("succes", 52)
    before = row_counts(conn)

    second = ingest(fake)

    assert (second.status, second.inserted_count, second.updated_count) == ("inchange", 0, 0)
    after = row_counts(conn)
    assert {t: after[t] - before[t] for t in before} == {
        "reports": 0, "raw_payloads": 0, "report_versions": 0, "ingestion_runs": 1}
    assert conn.execute("SELECT count(DISTINCT external_id) FROM reports").fetchone()[0] == 52
    assert_base_coherente(conn)


# --- Correspondance avec la fixture réelle -----------------------------------------------------


def test_champs_de_reports_depuis_les_5_enregistrements_de_la_fixture(
    conn: sqlite3.Connection, ingest: Ingest
) -> None:
    summary = ingest(FakeWHO(fixture_records()))
    assert (summary.status, summary.inserted_count, summary.seen_count) == ("succes", 5, 5)
    rows = {r["slug"]: r for r in conn.execute("SELECT * FROM reports")}
    assert set(rows) == {"2026-DON620", "2024-DON528", "2022-DON398_1", "2008_01_21-en",
                         "1996_01_22a-en"}
    cholera = rows["2022-DON398_1"]
    assert cholera["title"] == "Cholera – Somalia"  # UseOverrideTitle vrai mais OverrideTitle vide
    assert cholera["external_ref"] == "2022-DON398"  # DonId partagé avec 2022-DON398
    assert cholera["published_at"] == "2022-07-20T15:25:53Z"
    assert rows["2024-DON528"]["title"] == "Mpox – African Region"
    assert rows["2008_01_21-en"]["external_ref"] is None
    assert rows["1996_01_22a-en"]["published_at"] == "1996-01-22T00:00:00Z"
    assert all(r["date_quality"] == "ok" for r in rows.values())
    assert rows["2026-DON620"]["summary"].startswith("On 2 October 2026, WHO became aware")
    # Phase 3 : ni classification ni chiffres.
    for r in rows.values():
        assert (r["classification_status"], r["disease_code"], r["geo_scope"]) == (
            "non_classe", None, "inconnu")
        assert r["figures_payload_id"] is None and r["figures_extractor_version"] is None
    assert conn.execute("SELECT count(*) FROM report_figures").fetchone()[0] == 0
    assert_base_coherente(conn)


# --- Enregistrements invalides (test obligatoire 7) -------------------------------------------


def test_enregistrements_invalides_rejetes_sans_arreter_le_run(
    conn: sqlite3.Connection, ingest: Ingest, caplog: pytest.LogCaptureFixture
) -> None:
    good = make_records(8)
    missing_title = make_record(100)
    del missing_title["Title"]
    mistyped = make_record(101)
    mistyped["UseOverrideTitle"] = "oui"
    bad_date = make_record(102)
    bad_date["PublicationDateAndTime"] = "pas une date"
    no_id = make_record(103)
    del no_id["Id"]
    fake = FakeWHO(good + [missing_title, mistyped, bad_date, no_id, "pas un objet"])  # type: ignore[list-item]

    with caplog.at_level("WARNING"):
        summary = ingest(fake)

    assert summary.status == "partiel" and summary.error_kind == "validation"
    assert summary.rejected_count == 5 and summary.seen_count == 13 == summary.expected_count
    assert summary.inserted_count == 8  # le reste du run continue
    ids = {r[0] for r in conn.execute("SELECT external_id FROM reports")}
    assert ids == {r["Id"] for r in good}
    run = conn.execute("SELECT * FROM ingestion_runs WHERE id = ?", (summary.run_id,)).fetchone()
    assert run["status"] == "partiel" and run["error_kind"] == "validation"
    for fragment in (missing_title["Id"], "Title", mistyped["Id"], "UseOverrideTitle",
                     bad_date["Id"], "PublicationDateAndTime", "Id : Field required"):
        assert fragment in run["error_message"]
    assert sum("enregistrement rejeté" in r.message for r in caplog.records) == 5
    assert_base_coherente(conn)


def test_enregistrement_corrige_est_repris_au_run_suivant(
    conn: sqlite3.Connection, ingest: Ingest
) -> None:
    broken = make_record(7)
    broken["UseOverrideTitle"] = "oui"
    fake = FakeWHO([make_record(1), broken])
    assert ingest(fake).status == "partiel"
    fake.records[1] = make_record(7)
    fixed = ingest(fake)
    assert (fixed.status, fixed.inserted_count) == ("succes", 1)
    assert row_counts(conn)["reports"] == 2
    assert_base_coherente(conn)


def test_rejet_d_un_don_connu_ne_modifie_pas_la_base(
    conn: sqlite3.Connection, ingest: Ingest
) -> None:
    fake = FakeWHO(make_records(5))
    ingest(fake)
    title_before = conn.execute("SELECT title FROM reports WHERE slug = '2030-DON2'").fetchone()[0]
    fake.records[2]["Title"] = None
    summary = ingest(fake)
    assert summary.status == "partiel" and summary.updated_count == 0
    assert conn.execute("SELECT title FROM reports WHERE slug = '2030-DON2'").fetchone()[0] == title_before
    assert_base_coherente(conn)


def test_champs_de_l_api_ajoutes_ne_font_pas_echouer(
    conn: sqlite3.Connection, ingest: Ingest
) -> None:
    fake = FakeWHO(make_records(5))
    ingest(fake)
    first = conn.execute("SELECT field_fingerprint FROM ingestion_runs ORDER BY id DESC").fetchone()[0]
    for record in fake.records:
        record["NouveauChamp"] = "x"
    summary = ingest(fake)
    second = conn.execute("SELECT field_fingerprint FROM ingestion_runs ORDER BY id DESC").fetchone()[0]
    assert summary.status == "succes" and summary.updated_count == 5  # le contenu brut a changé
    assert first != second and len(first) == 64


# --- Modification d'un DON (test obligatoire 3 ; I51, I52) ------------------------------------


def test_changement_de_contenu_cree_une_version(conn: sqlite3.Connection, ingest: Ingest) -> None:
    """I51 : un DON modifié met `reports` à jour et ajoute une version ; l'ancien brut reste."""
    fake = FakeWHO(make_records(30))
    ingest(fake)
    target = fake.records[12]
    original = copy.deepcopy(target)
    target["Summary"] = "<p>Texte <b>révisé</b> par l'OMS.</p>"
    target["LastModified"] = "2030-02-01T08:00:00Z"
    before = row_counts(conn)

    summary = ingest(fake)

    assert (summary.status, summary.inserted_count, summary.updated_count) == ("succes", 0, 1)
    report = conn.execute("SELECT * FROM reports WHERE external_id = ?", (target["Id"],)).fetchone()
    assert report["summary"] == "Texte révisé par l'OMS."
    raws = conn.execute("SELECT * FROM raw_payloads WHERE resource_key = ? ORDER BY id",
                        (target["Id"],)).fetchall()
    assert len(raws) == 2 and raws[0]["sha256"] != raws[1]["sha256"]
    assert json.loads(raws[0]["body_text"]) == original  # historisé, jamais écrasé
    assert json.loads(raws[1]["body_text"]) == target
    assert raws[1]["source_modified_at"] == "2030-02-01T08:00:00Z"
    versions = conn.execute("SELECT version, raw_payload_id, run_id FROM report_versions "
                            "WHERE report_id = ? ORDER BY version", (report["id"],)).fetchall()
    assert [tuple(v) for v in versions] == [(1, raws[0]["id"], raws[0]["first_run_id"]),
                                            (2, raws[1]["id"], summary.run_id)]
    assert report["raw_payload_id"] == raws[1]["id"]
    after = row_counts(conn)
    assert (after["reports"] - before["reports"], after["raw_payloads"] - before["raw_payloads"],
            after["report_versions"] - before["report_versions"]) == (0, 1, 1)
    assert_base_coherente(conn)


def test_retour_a_un_contenu_anterieur_cree_une_version(
    conn: sqlite3.Connection, ingest: Ingest
) -> None:
    """I52 : A -> B -> A donne 3 versions et 2 bruts ; la version 3 pointe vers le brut de A."""
    fake = FakeWHO(make_records(5))
    version_a = copy.deepcopy(fake.records[1])
    ingest(fake)
    fake.records[1]["Title"] = "Titre B"
    assert ingest(fake).updated_count == 1
    fake.records[1].update(version_a)
    summary = ingest(fake)

    assert (summary.status, summary.updated_count) == ("succes", 1)
    report = conn.execute("SELECT * FROM reports WHERE external_id = ?", (version_a["Id"],)).fetchone()
    versions = conn.execute("SELECT version, raw_payload_id FROM report_versions "
                            "WHERE report_id = ? ORDER BY version", (report["id"],)).fetchall()
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert versions[2]["raw_payload_id"] == versions[0]["raw_payload_id"] != versions[1]["raw_payload_id"]
    assert report["raw_payload_id"] == versions[2]["raw_payload_id"]
    assert report["title"] == version_a["Title"]
    assert conn.execute("SELECT count(*) FROM raw_payloads WHERE resource_key = ?",
                        (version_a["Id"],)).fetchone()[0] == 2
    assert_base_coherente(conn)


# --- Présence des DON (test obligatoire 4 ; I9, I10, I11) -------------------------------------


def test_ecart_zero_sur_les_presents(conn: sqlite3.Connection, ingest: Ingest) -> None:
    """I9 : seen_count = expected_count = DON de la base vus par ce run ; les absents sont hors écart."""
    fake = FakeWHO(make_records(300))
    ingest(fake)
    fake.records.pop(40)
    summary = ingest(fake)
    seen_in_base = conn.execute("SELECT count(*) FROM reports WHERE last_seen_run_id = ?",
                                (summary.run_id,)).fetchone()[0]
    assert summary.expected_count == summary.seen_count == seen_in_base == 299
    assert row_counts(conn)["reports"] == 300  # le DON absent reste en base
    assert_base_coherente(conn)  # la vue ne signale ni I9 ni I10


def test_retrait_a_la_troisieme_absence(conn: sqlite3.Connection, ingest: Ingest) -> None:
    """I10 : « absent » après 1 et 2 exécutions complètes sans le DON, « retiré » à la 3e."""
    fake = FakeWHO(make_records(300))
    ingest(fake)
    gone = fake.records.pop(10)
    slug = gone["UrlName"]
    assert presence(conn, slug)["presence"] == "present"

    for missing_runs in (1, 2):
        summary = ingest(fake)
        assert summary.status == "inchange"  # complète, rien n'a changé dans les données
        row = presence(conn, slug)
        assert (row["presence"], row["missing_runs"], row["removed_run_id"]) == (
            "absent", missing_runs, None)
        assert conn.execute("SELECT count(*) FROM reports_active").fetchone()[0] == 300
        assert_base_coherente(conn)

    third = ingest(fake)
    row = presence(conn, slug)
    assert (row["presence"], row["removed_run_id"]) == ("retire", third.run_id)
    assert conn.execute("SELECT count(*) FROM reports_active").fetchone()[0] == 299
    assert third.status == "succes" and third.removed_count == 1
    assert_base_coherente(conn)

    fourth = ingest(fake)  # une exécution de plus ne déplace pas le retrait
    assert presence(conn, slug)["removed_run_id"] == third.run_id
    assert fourth.removed_count == 0
    assert row_counts(conn)["reports"] == 300  # jamais supprimé (I3)
    assert_base_coherente(conn)


def test_execution_partielle_ne_compte_pas(conn: sqlite3.Connection, ingest: Ingest) -> None:
    """I10 : seules les exécutions complètes comptent ; une partielle ne peut pas être la 3e absence."""
    fake = FakeWHO(make_records(300))
    ingest(fake)
    slug = fake.records.pop(10)["UrlName"]
    for missing in (1, 2):
        assert ingest(fake).status == "inchange"
        assert presence(conn, slug)["missing_runs"] == missing

    broken = make_record(999)
    broken["Title"] = None
    fake.records.append(broken)  # run partiel : un enregistrement rejeté, qui tombe en 3e position
    partial = ingest(fake)
    assert partial.status == "partiel"
    row = presence(conn, slug)
    assert (row["presence"], row["missing_runs"], row["removed_run_id"]) == ("absent", 2, None)
    assert partial.removed_count == 0
    assert_base_coherente(conn)
    fake.records.pop()

    last = ingest(fake)  # la 3e exécution complète sans le DON
    row = presence(conn, slug)
    assert (row["presence"], row["removed_run_id"], row["missing_runs"]) == ("retire", last.run_id, 3)
    assert_base_coherente(conn)


def test_echec_ne_compte_pas_pour_le_retrait(conn: sqlite3.Connection, ingest: Ingest) -> None:
    fake = FakeWHO(make_records(300))
    ingest(fake)
    slug = fake.records.pop(10)["UrlName"]
    ingest(fake)
    fake.fault(503, skip=0)
    assert ingest(fake).status == "echec"
    fake.clear_faults()
    ingest(fake)
    assert presence(conn, slug)["missing_runs"] == 2
    assert_base_coherente(conn)


@pytest.mark.parametrize("absences", [1, 2, 3, 5])
def test_reapparition_annule_le_retrait(conn: sqlite3.Connection, ingest: Ingest,
                                        absences: int) -> None:
    """I10 : un DON qui réapparaît redevient présent, sans nouvelle ligne ni nouvelle version."""
    fake = FakeWHO(make_records(300))
    ingest(fake)
    gone = fake.records.pop(10)
    for _ in range(absences):
        ingest(fake)
    retired = absences >= 3
    assert presence(conn, gone["UrlName"])["presence"] == ("retire" if retired else "absent")
    versions_before = row_counts(conn)["report_versions"]

    fake.records.insert(10, gone)
    summary = ingest(fake)

    row = presence(conn, gone["UrlName"])
    assert (row["presence"], row["removed_run_id"], row["last_seen_run_id"]) == (
        "present", None, summary.run_id)
    assert summary.reappeared_count == 1 and summary.status == "succes"
    assert (summary.inserted_count, summary.updated_count) == (0, 0)
    counts = row_counts(conn)
    assert counts["reports"] == 300 and counts["report_versions"] == versions_before
    assert conn.execute("SELECT count(*) FROM reports_active").fetchone()[0] == 300
    assert_base_coherente(conn)


def test_compteurs_d_absence_journalises(conn: sqlite3.Connection, ingest: Ingest) -> None:
    """I11 : absent_count, removed_count, reappeared_count décrivent reports_presence en fin de run."""
    fake = FakeWHO(make_records(300))
    first = ingest(fake)
    assert (first.absent_count, first.removed_count, first.reappeared_count) == (0, 0, 0)
    gone_a, gone_b = fake.records.pop(5), fake.records.pop(20)

    def logged(run_id: int) -> tuple[int, int, int]:
        row = conn.execute("SELECT absent_count, removed_count, reappeared_count "
                           "FROM ingestion_runs WHERE id = ?", (run_id,)).fetchone()
        return (row[0], row[1], row[2])

    def view_absent() -> int:
        return int(conn.execute("SELECT count(*) FROM reports_presence "
                                "WHERE presence = 'absent'").fetchone()[0])

    expected = [(2, 0, 0), (2, 0, 0), (0, 2, 0)]  # 1re, 2e, 3e absence
    for counts in expected:
        run = ingest(fake)
        assert logged(run.run_id) == counts == (run.absent_count, run.removed_count,
                                                run.reappeared_count)
        assert view_absent() == run.absent_count
        assert conn.execute("SELECT count(*) FROM reports WHERE removed_run_id = ?",
                            (run.run_id,)).fetchone()[0] == run.removed_count

    fake.records.insert(5, gone_a)
    back = ingest(fake)
    assert logged(back.run_id) == (0, 0, 1) and view_absent() == 0
    assert conn.execute("SELECT count(*) FROM reports_presence WHERE presence = 'retire'"
                        ).fetchone()[0] == 1  # gone_b reste retiré
    assert gone_b["Id"]
    assert_base_coherente(conn)


def test_run_sans_changement_apres_retrait_reste_inchange(
    conn: sqlite3.Connection, ingest: Ingest
) -> None:
    fake = FakeWHO(make_records(300))
    ingest(fake)
    fake.records.pop(0)
    for _ in range(3):
        ingest(fake)
    again: Any = ingest(fake)
    assert again.status == "inchange"
    assert_base_coherente(conn)
