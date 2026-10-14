"""Normalisation d'un enregistrement : titre affiché, dates, HTML retiré, JSON canonique."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError

from fake_who import fixture_records, make_record
from observatoire.oms.models import DonRecord
from observatoire.oms.normalize import (
    DON_URL, build_row, canonical_json, display_title, prepare_record, strip_html,
)


def _record(**changes: Any) -> DonRecord:
    return DonRecord.model_validate({**make_record(1), **changes})


@pytest.mark.parametrize("use_override, override, title, expected", [
    (True, "Titre affiché", "Titre de base", "Titre affiché"),
    (True, "", "Titre de base", "Titre de base"),  # 2022-DON398_1 dans la fixture
    (True, "   ", "Titre de base", "Titre de base"),
    (True, None, "Titre de base", "Titre de base"),
    (False, "Titre affiché", "Titre de base", "Titre de base"),
])
def test_titre_affiche_regle_d8(use_override: bool, override: str | None, title: str,
                                expected: str) -> None:
    record = _record(UseOverrideTitle=use_override, OverrideTitle=override, Title=title)
    assert display_title(record) == expected


def test_strip_html() -> None:
    assert strip_html("<p>Un <b>cas</b> &amp; deux&nbsp;décès</p>\r\n<p>fin</p>") == "Un cas & deux décès fin"
    assert strip_html("") is None
    assert strip_html(None) is None
    assert strip_html("<p> </p>") is None


@pytest.mark.parametrize("don_id, title, published, expected", [
    ("2026-DON620", "Pneumonia", "2026-10-10T15:00:00Z", "ok"),
    ("2019DON", "Autre", "2019-05-01T00:00:00Z", "ok"),
    ("1997", "Autre", "1997-05-01T00:00:00Z", "ok"),
    ("", "1996 - Global Cholera Update", "1996-01-22T00:00:00Z", "ok"),
    (None, "Avian influenza", "2008-01-21T00:00:00Z", "ok"),
    ("2020-DON286", "Autre", "2021-04-01T00:00:00Z", "a_verifier"),  # année du DonId différente
    ("", "1996 - Global Cholera Update", "2021-06-08T00:00:00Z", "a_verifier"),  # titre
    ("DON588", "Sans année", "2013-01-01T00:00:00Z", "ok"),
])
def test_date_quality(don_id: str | None, title: str, published: str, expected: str) -> None:
    row = build_row(_record(DonId=don_id, Title=title, OverrideTitle="", PublicationDateAndTime=published))
    assert row.date_quality == expected


def test_champs_de_reports_depuis_la_fixture() -> None:
    by_slug = {r["UrlName"]: build_row(DonRecord.model_validate(r)) for r in fixture_records()}
    recent = by_slug["2026-DON620"]
    assert recent.external_ref == "2026-DON620"
    assert recent.url == DON_URL.format(slug="2026-DON620")
    assert recent.published_at == "2026-10-10T15:00:00Z"  # PublicationDateAndTime, pas 15:53:19
    assert recent.source_modified_at == "2026-10-13T09:22:55Z"
    assert by_slug["2008_01_21-en"].external_ref is None  # DonId '' -> NULL
    assert by_slug["2008_01_21-en"].summary is None
    archive = by_slug["1996_01_22a-en"]
    assert archive.published_at == "1996-01-22T00:00:00Z"  # et non 2021-06-08 (PublicationDate)
    assert archive.date_quality == "ok"


def test_url_publique_encode_le_slug() -> None:
    assert build_row(_record(UrlName="a b/c")).url == DON_URL.format(slug="a%20b%2Fc")


def test_json_canonique_independant_de_l_ordre_des_cles() -> None:
    record = make_record(1)
    shuffled = dict(reversed(list(record.items())))
    assert canonical_json(record) == canonical_json(shuffled)
    assert json.loads(canonical_json(record)) == record
    assert prepare_record(record, "u").sha256 == prepare_record(shuffled, "u").sha256


@pytest.mark.parametrize("field, value", [
    ("Id", None), ("Id", ""), ("Id", 12), ("UrlName", None), ("Title", None), ("Title", 3),
    ("UseOverrideTitle", "true"), ("UseOverrideTitle", 1), ("UseOverrideTitle", None),
    ("PublicationDateAndTime", "hier"), ("PublicationDateAndTime", "2026-10-10T15:00:00"),
    ("PublicationDateAndTime", 20261010), ("LastModified", None), ("DonId", 42),
])
def test_champ_mal_type_ou_invalide_rejete(field: str, value: Any) -> None:
    record = make_record(1)
    record[field] = value
    with pytest.raises(ValidationError):
        prepare_record(record, "u")


@pytest.mark.parametrize("field", ["Id", "UrlName", "Title", "UseOverrideTitle",
                                   "PublicationDateAndTime", "LastModified"])
def test_champ_obligatoire_manquant_rejete(field: str) -> None:
    record = copy.deepcopy(make_record(1))
    del record[field]
    with pytest.raises(ValidationError, match=field):
        prepare_record(record, "u")


def test_champs_inutilises_acceptes_et_archives() -> None:
    record = make_record(1)
    record["Epidemiology"] = None  # null observé sur les enregistrements anciens
    record["ChampInconnu"] = {"x": 1}
    prepared = prepare_record(record, "u")
    assert json.loads(prepared.body) == record
