"""Points d'entrée en ligne de commande : codes de sortie et sortie JSON, sans réseau."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from fake_who import FakeWHO, make_record, make_records
from observatoire.cli import EXIT_FAILED, EXIT_OK, EXIT_PARTIAL, EXIT_USAGE, main


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OBSERVATOIRE_CONTACT", "OBSERVATOIRE_DB", "OBSERVATOIRE_TIMEOUT",
                 "OBSERVATOIRE_CI_RUN_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OBSERVATOIRE_CODE_VERSION", "test")


def run_cli(db: Path, fake: FakeWHO, *extra: str) -> int:
    return main(["ingest-oms", "--db", str(db), "--contact", "contact@example.org",
                 "--page-size", "10", "--max-retries", "0", *extra],
                transport=httpx.MockTransport(fake))


def test_ingest_oms_succes_puis_second_run_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "sous" / "dossier" / "obs.sqlite"  # le dossier est créé
    fake = FakeWHO(make_records(25))
    assert run_cli(db, fake) == EXIT_OK
    first = json.loads(capsys.readouterr().out)
    assert (first["status"], first["inserted_count"], first["seen_count"]) == ("succes", 25, 25)
    assert run_cli(db, fake) == EXIT_OK
    second = json.loads(capsys.readouterr().out)
    assert (second["status"], second["inserted_count"], second["updated_count"]) == ("inchange", 0, 0)
    assert second["run_id"] == first["run_id"] + 1


def test_contact_obligatoire(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["ingest-oms", "--db", str(tmp_path / "x.sqlite")],
                transport=httpx.MockTransport(FakeWHO([])))
    assert code == EXIT_USAGE
    assert "--contact" in capsys.readouterr().err
    assert not (tmp_path / "x.sqlite").exists()


def test_contact_et_base_depuis_l_environnement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OBSERVATOIRE_CONTACT", "env@example.org")
    monkeypatch.setenv("OBSERVATOIRE_DB", str(tmp_path / "env.sqlite"))
    fake = FakeWHO(make_records(3))
    assert main(["ingest-oms"], transport=httpx.MockTransport(fake)) == EXIT_OK
    assert "env@example.org" in fake.calls[0]["headers"]["user-agent"]
    assert (tmp_path / "env.sqlite").exists()
    capsys.readouterr()


def test_reglage_invalide_est_une_erreur_d_usage(tmp_path: Path) -> None:
    code = main(["ingest-oms", "--db", str(tmp_path / "x.sqlite"), "--contact", "a@b.c",
                 "--page-size", "101"], transport=httpx.MockTransport(FakeWHO([])))
    assert code == EXIT_USAGE


def test_code_de_sortie_non_nul_en_cas_d_echec(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeWHO(make_records(25))
    fake.fault(503, skip=10)
    assert run_cli(tmp_path / "obs.sqlite", fake) == EXIT_FAILED
    out = json.loads(capsys.readouterr().out)
    assert (out["status"], out["error_kind"]) == ("echec", "http")


def test_code_de_sortie_distinct_pour_un_run_partiel(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = make_record(50)
    broken["Title"] = None
    assert run_cli(tmp_path / "obs.sqlite", FakeWHO(make_records(4) + [broken])) == EXIT_PARTIAL
    assert json.loads(capsys.readouterr().out)["rejected_count"] == 1


def test_db_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "obs.sqlite"
    fake = FakeWHO(make_records(25))
    run_cli(db, fake)
    capsys.readouterr()

    assert main(["db-check", "--db", str(db)]) == EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["integrity_check"] == "ok" and report["controle_invariants"] == []
    assert (report["reports_total"], report["reports_distinct_external_id"],
            report["reports_active"]) == (25, 25, 25)
    assert report["presence"] == {"present": 25, "absent": 0, "retire": 0}
    assert report["last_run"]["status"] == "succes"

    connection = sqlite3.connect(db)  # violation volontaire : retrait trop tôt
    connection.execute("UPDATE reports SET removed_run_id = 99 WHERE slug = '2030-DON0'")
    connection.commit()
    connection.close()
    assert main(["db-check", "--db", str(db)]) == EXIT_FAILED


def test_db_check_base_introuvable(tmp_path: Path) -> None:
    assert main(["db-check", "--db", str(tmp_path / "absent.sqlite")]) == EXIT_USAGE
