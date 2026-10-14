"""Échantillon d'étiquetage (phase 3, étape 0) : format, reproductibilité, strates, isolation."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from fake_who import FakeWHO, fixture_records, make_record
from observatoire import gold_sample
from observatoire.cli import EXIT_OK, EXIT_USAGE, main
from observatoire.db import to_utc_z
from observatoire.gold_sample import (
    GOLD_COLUMNS, PRECISIONS, QUOTAS, SAMPLE_COLUMNS, load_candidates, select, split_for,
)
from observatoire.oms.ingest import RunSummary
from observatoire.oms.normalize import DON_URL, display_title
from observatoire.oms.models import DonRecord
from observatoire.oms.text import html_to_text, report_text

ROOT = Path(__file__).resolve().parents[1]
Ingest = Callable[[FakeWHO], RunSummary]

DISEASES = ["Cholera", "Mpox", "Ebola disease", "Measles", "Yellow fever", "Dengue", "Nipah virus",
            "Marburg virus disease", "Avian influenza", "Polio", "Anthrax", "Lassa fever", "Plague",
            "Zika virus", "MERS-CoV", "Diphtheria"]
OVERVIEWS = [
    "<p>No numeric information is available at this time.</p>",
    "<p>A cumulative number of 100 cases including 3 deaths has been reported to date.</p>",
    "<p>About 200 cases were reported, including 5 new cases this week.</p>",
    "<p>At least 40 confirmed cases and two deaths.</p>",
    "<p>Newly reported: 12 suspected cases since the last update.</p>",
    "<p>The ministry gave an update without figures.</p>",
]


def synthetic_records(count: int) -> list[dict[str, object]]:
    records = []
    for i in range(count):
        record = make_record(1000 + i)
        year = 2000 + (i * 7) % 27
        scope = "multi-country outbreak" if i % 5 == 0 else f"Country{i}"
        record["Title"] = f"{DISEASES[i % len(DISEASES)]} – {scope}"
        record["PublicationDateAndTime"] = f"{year}-03-01T12:00:00Z"
        record["DonId"] = f"{year}-DON{i}"
        record["Overview"] = OVERVIEWS[i % len(OVERVIEWS)]
        for name in ("Summary", "Epidemiology", "Assessment", "Advice", "Response", "FurtherInformation"):
            record[name] = ""
        records.append(record)
    return records


@pytest.fixture
def populated(conn: sqlite3.Connection, ingest: Ingest, settings: object) -> sqlite3.Connection:
    ingest(FakeWHO(synthetic_records(300)))
    return conn


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_gabarit_du_jeu_de_reference_entetes_seulement() -> None:
    lines = (ROOT / "tests" / "gold" / "don_gold.csv").read_text(encoding="utf-8").splitlines()
    assert lines == [",".join(GOLD_COLUMNS)]
    assert GOLD_COLUMNS == ("don_id", "split", "pays", "maladie", "type", "valeur", "qualificatif",
                            "precision", "cumule_ou_nouveau", "date_reference", "citation")
    assert GOLD_COLUMNS.index("precision") == GOLD_COLUMNS.index("qualificatif") + 1
    assert PRECISIONS == ("exact", "environ", "au_moins", "au_plus", "fourchette_basse",
                          "fourchette_haute")


def test_split_deterministe_et_equilibre() -> None:
    assert split_for("202f9f50-fdb1-4f07-b54b-007046fb5b59") == "holdout"  # valeur figée du hash
    assert split_for("a2e9b557-fa1d-4427-bc25-b80d6684b14e") == "dev"
    ids = [f"00000000-0000-4000-8000-{i:012d}" for i in range(2000)]
    share = sum(split_for(i) == "dev" for i in ids) / len(ids)
    assert 0.45 < share < 0.55
    assert [split_for(i) for i in ids[:50]] == [split_for(i) for i in ids[:50]]


def test_html_to_text_conserve_les_paragraphes() -> None:
    html = "<div><p>Un&nbsp;cas &amp; deux</p><ul><li>a</li><li>b</li></ul><table><tr><td>x</td><td>1</td></tr></table></div>"
    assert html_to_text(html) == "Un cas & deux\na\nb\n| x | 1"
    assert html_to_text(None) == "" and html_to_text("<p> </p>") == ""


def test_echantillon_sur_la_fixture(
    conn: sqlite3.Connection, ingest: Ingest, tmp_path: Path
) -> None:
    ingest(FakeWHO(fixture_records()))
    selection = select(load_candidates(conn, set()), 40)
    out = tmp_path / "a_etiqueter.csv"
    gold_sample.write_sample(selection, out, tmp_path / "textes")
    rows = read_csv(out)
    assert out.read_text(encoding="utf-8").splitlines()[0] == ",".join(SAMPLE_COLUMNS)
    assert len(rows) == 5  # moins de 40 DON en base : tous proposés
    by_url = {r["url"].rsplit("/", 1)[1]: r for r in rows}
    assert set(by_url) == {"2026-DON620", "2024-DON528", "2022-DON398_1", "2008_01_21-en",
                           "1996_01_22a-en"}
    for row in rows:
        assert row["split"] == split_for(row["don_id"])
        text = Path(row["chemin_texte"]).read_text(encoding="utf-8")
        assert text.startswith(f"TITRE : {row['titre']}\n")
        assert row["url"] in text
    assert {r["origine"] for r in rows} == {"aleatoire"}  # 5 DON < n_random : tous tirés au hasard
    somalia = Path(by_url["2022-DON398_1"]["chemin_texte"]).read_text(encoding="utf-8")
    assert "a cumulative number of 7796 cases of cholera including 37 associated deaths" in somalia
    assert "\n## Overview\n" in somalia and "<p>" not in somalia


def test_aucune_etiquette_prerempli(
    conn: sqlite3.Connection, ingest: Ingest, tmp_path: Path
) -> None:
    ingest(FakeWHO(fixture_records()))
    out = tmp_path / "a.csv"
    gold_sample.write_sample(select(load_candidates(conn, set())), out, tmp_path / "t")
    header = out.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header == list(SAMPLE_COLUMNS)
    assert not {"pays", "maladie", "type", "valeur", "qualificatif", "citation"} & set(header)


def test_echantillon_de_40_sur_base_factice_reproductible_et_stratifie(
    populated: sqlite3.Connection, tmp_path: Path
) -> None:
    candidates = load_candidates(populated, set())
    assert len(candidates) == 300
    first = select(candidates, 40, seed=7)
    again = select(list(reversed(candidates)), 40, seed=7)
    other = select(candidates, 40, seed=8)
    ids = [c.don_id for c in first.chosen]
    assert len(ids) == len(set(ids)) == 40
    assert ids == [c.don_id for c in again.chosen]  # indépendant de l'ordre d'entrée
    assert ids != [c.don_id for c in other.chosen]
    assert ids == sorted(ids)
    assert first.shortfalls == {}  # chaque strate a atteint son effectif
    assert all(first.reached[k] >= QUOTAS[k] for k in QUOTAS)
    strata_part = [c for c in first.chosen if c.don_id not in first.random_ids]
    per_disease = Counter(c.disease for c in strata_part)  # le tirage aléatoire, lui, est uniforme
    assert len(strata_part) == 30 and len(per_disease) == len(DISEASES)
    assert max(per_disease.values()) - min(per_disease.values()) <= 1  # réparties au plus égal
    assert max(per_disease.values()) <= -(-30 // len(DISEASES))  # le plafond cède quand il faut 30 DON
    years = [int(c.published_at[:4]) for c in first.chosen]
    assert min(years) < 2015 and max(years) >= 2022


def test_fichiers_identiques_a_chaque_execution(populated: sqlite3.Connection, tmp_path: Path) -> None:
    candidates = load_candidates(populated, set())
    outputs = []
    for name in ("un", "deux"):
        out = tmp_path / name / "a.csv"
        gold_sample.write_sample(select(candidates, 40), out, tmp_path / name / "textes",
                                 path_of=lambda c: f"textes/{c.don_id}.txt")
        outputs.append(out.read_bytes())
    assert outputs[0] == outputs[1]
    rows = read_csv(tmp_path / "un" / "a.csv")
    assert Counter(r["split"] for r in rows).keys() <= {"dev", "holdout"}
    assert len(list((tmp_path / "un" / "textes").glob("*.txt"))) == 40


def test_commande_exclut_la_fixture_et_protege_le_fichier(
    conn: sqlite3.Connection, ingest: Ingest, settings: object, tmp_path: Path,
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OBSERVATOIRE_DB", raising=False)
    ingest(FakeWHO(fixture_records() + synthetic_records(60)))
    db = str(conn.execute("PRAGMA database_list").fetchone()["file"])
    out, texts = tmp_path / "a_etiqueter.csv", tmp_path / "textes"
    args = ["gold-sample", "--db", db, "--out", str(out), "--texts-dir", str(texts)]

    assert main(args) == EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["eligible"] == 60 and report["selected"] == 40
    assert report["dev"] + report["holdout"] == 40
    fixture_ids = {r["Id"] for r in fixture_records()}
    assert fixture_ids.isdisjoint(r["don_id"] for r in read_csv(out))

    assert main(args) == EXIT_USAGE  # n'écrase pas sans --force
    assert "existe déjà" in capsys.readouterr().err
    assert main([*args, "--force", "--keep-fixture-dons"]) == EXIT_OK
    assert fixture_ids & {r["don_id"] for r in read_csv(out)} == fixture_ids


def test_commande_refuse_base_absente_ou_sans_don_eligible(
    conn: sqlite3.Connection, ingest: Ingest, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["gold-sample", "--db", str(tmp_path / "absente.sqlite"),
                 "--out", str(tmp_path / "a.csv")]) == EXIT_USAGE
    ingest(FakeWHO(fixture_records()))  # base qui ne contient que la fixture
    db = str(conn.execute("PRAGMA database_list").fetchone()["file"])
    assert main(["gold-sample", "--db", db, "--out", str(tmp_path / "a.csv")]) == EXIT_USAGE
    assert "aucun DON éligible" in capsys.readouterr().err
    assert not (tmp_path / "a.csv").exists()


def test_les_heuristiques_d_echantillonnage_ne_sont_jamais_reutilisees() -> None:
    """Point 4 : seuls le module lui-même et la commande `gold-sample` y touchent."""
    users = []
    for path in (ROOT / "src").rglob("*.py"):
        if path.name == "gold_sample.py":
            continue
        if re.search(r"\bgold_sample\b", path.read_text(encoding="utf-8")):
            users.append(path.name)
    assert users == ["cli.py"]
    imported = re.findall(r"from observatoire.gold_sample import \(([^)]*)\)",
                          (ROOT / "src/observatoire/cli.py").read_text(encoding="utf-8"))[0]
    assert not {"strata_flags", "year_bin", "disease_key", "Candidate"} & set(re.findall(r"\w+", imported))


def test_citations_du_guide_sont_des_extraits_exacts_des_textes_exportes(
    conn: sqlite3.Connection, ingest: Ingest
) -> None:
    """Chaque exemple du guide d'étiquetage est vérifié contre le texte exporté de la fixture."""
    ingest(FakeWHO(fixture_records()))
    texts = {c.don_id: c.text for c in load_candidates(conn, set())}
    guide = (ROOT / "docs" / "03-guide-etiquetage.md").read_text(encoding="utf-8")
    rows = [line for line in guide.splitlines() if re.match(r"\| `[0-9a-f-]{36}` \|", line)]
    assert len(rows) >= 7
    for line in rows:
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        don_id, split, citation = cells[0], cells[1], cells[-1]
        assert split == split_for(don_id)
        if citation != "aucun chiffre":
            assert citation in texts[don_id], citation
        assert "\n" not in citation
    for citation in re.findall(r"`((?:\(CFR[^`]*|more than 78 000[^`]*|2,027[^`]*|only two cases[^`]*))`", guide):
        assert any(citation in t for t in texts.values()), citation


def test_fichier_texte_egal_a_la_sortie_de_la_fonction_unique(
    conn: sqlite3.Connection, ingest: Ingest, tmp_path: Path
) -> None:
    """Le texte étiqueté est exactement `report_text` (la même fonction que l'extracteur importera)."""
    ingest(FakeWHO(fixture_records()))
    out = tmp_path / "a.csv"
    gold_sample.write_sample(select(load_candidates(conn, set()), 40), out, tmp_path / "textes")
    by_id = {r["Id"]: r for r in fixture_records()}
    rows = read_csv(out)
    assert {r["don_id"] for r in rows} == set(by_id)
    for row in rows:
        raw = by_id[row["don_id"]]
        expected = report_text(display_title(DonRecord.model_validate(raw)),
                               DON_URL.format(slug=raw["UrlName"]),
                               to_utc_z(raw["PublicationDateAndTime"]), raw)
        assert Path(row["chemin_texte"]).read_text(encoding="utf-8") == expected
    assert "gold_sample" not in (ROOT / "src/observatoire/oms/text.py").read_text(encoding="utf-8")


def test_n_random_tire_au_hasard_avec_la_meme_graine(populated: sqlite3.Connection) -> None:
    candidates = load_candidates(populated, set())
    sample = select(candidates, 40, seed=7, n_random=10)
    assert len(sample.chosen) == 40 and len(sample.random_ids) == 10
    assert sample.random_ids <= {c.don_id for c in sample.chosen}
    # Le tirage ne dépend que de la graine et de l'ensemble de DON : il est stable et reproductible.
    assert sample.random_ids == select(list(reversed(candidates)), 40, seed=7, n_random=10).random_ids
    assert sample.random_ids == select(candidates, 20, seed=7, n_random=10).random_ids
    assert sample.random_ids != select(candidates, 40, seed=8, n_random=10).random_ids
    # Sans stratification : tirage uniforme, pas de quotas visés ; la partie stratifiée, elle, les tient.
    strata_part = [c for c in sample.chosen if c.don_id not in sample.random_ids]
    assert len(strata_part) == 30 and sample.shortfalls == {}
    assert all(sum(k in c.flags for c in strata_part) >= QUOTAS[k] for k in QUOTAS)
    assert select(candidates, 40, seed=7, n_random=0).random_ids == frozenset()
    assert len(select(candidates, 40, seed=7, n_random=40).random_ids) == 40
    with pytest.raises(ValueError, match="n_random"):
        select(candidates, 40, n_random=41)


def test_origine_dans_le_csv_et_option_n_random_de_la_commande(
    populated: sqlite3.Connection, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OBSERVATOIRE_DB", raising=False)
    db = str(populated.execute("PRAGMA database_list").fetchone()["file"])
    base = ["gold-sample", "--db", db, "--texts-dir", str(tmp_path / "t")]

    assert main([*base, "--out", str(tmp_path / "defaut.csv")]) == EXIT_OK  # défaut : 10 au hasard
    report = json.loads(capsys.readouterr().out)
    rows = read_csv(tmp_path / "defaut.csv")
    assert report["selected"] == len(rows) == 40 and report["aleatoire"] == 10
    assert Counter(r["origine"] for r in rows) == {"aleatoire": 10, "strate": 30}
    assert (tmp_path / "defaut.csv").read_text(encoding="utf-8").splitlines()[0] == ",".join(SAMPLE_COLUMNS)

    assert main([*base, "--out", str(tmp_path / "c.csv"), "--n", "25", "--n-random", "5"]) == EXIT_OK
    capsys.readouterr()
    assert Counter(r["origine"] for r in read_csv(tmp_path / "c.csv")) == {"aleatoire": 5, "strate": 20}

    assert main([*base, "--out", str(tmp_path / "d.csv"), "--n", "10", "--n-random", "11"]) == EXIT_USAGE
    assert "--n-random" in capsys.readouterr().err
    assert not (tmp_path / "d.csv").exists()
