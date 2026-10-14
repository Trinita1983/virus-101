"""Normalisation d'un enregistrement OMS : champs de `reports` et JSON brut canonique."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote

from observatoire.oms.models import DonRecord

# URL publique d'un DON (docs/00-sources.md §2.2).
DON_URL = "https://www.who.int/emergencies/disease-outbreak-news/item/{slug}"

# Année en tête d'un DonId ou d'un titre : « 2026-DON620 », « 2019DON », « 1997 », « 1996 - ... ».
_LEADING_YEAR = re.compile(r"^(\d{4})(?!\d)")


@dataclass(frozen=True)
class ReportRow:
    """Les champs de `reports` tirés de l'enregistrement (hors identifiants d'exécution)."""

    external_id: str
    external_ref: str | None
    slug: str
    url: str
    title: str
    summary: str | None
    published_at: str
    date_quality: str
    source_modified_at: str


@dataclass(frozen=True)
class Prepared:
    """Un enregistrement validé, avec son JSON brut canonique, prêt à être écrit."""

    row: ReportRow
    body: str
    sha256: str
    byte_size: int
    request_url: str


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def strip_html(text: str | None) -> str | None:
    """Texte brut d'un fragment HTML, espaces réduits. None si rien ne reste."""
    if not text:
        return None
    parser = _TextExtractor()
    parser.feed(text)
    parser.close()
    return " ".join("".join(parser.parts).split()) or None


def display_title(record: DonRecord) -> str:
    """Titre affiché sur who.int (D8) : `OverrideTitle` si `UseOverrideTitle` et non vide, sinon `Title`."""
    if record.UseOverrideTitle and record.OverrideTitle and record.OverrideTitle.strip():
        return record.OverrideTitle
    return record.Title


def date_quality(record: DonRecord, title: str) -> str:
    """'a_verifier' si l'année du DonId ou du titre diffère de celle de `PublicationDateAndTime`.

    Interprétation de docs/01-architecture.md §3.4 (13 cas mesurés : 11 sur le DonId, 2 sur le
    titre). La règle exacte de la mesure n'est pas écrite dans les documents.
    """
    published_year = int(record.PublicationDateAndTime[:4])
    for text in (record.DonId, title):
        match = _LEADING_YEAR.match(text or "")
        if match and int(match.group(1)) != published_year:
            return "a_verifier"
    return "ok"


def canonical_json(raw: dict[str, Any]) -> str:
    """JSON canonique de l'enregistrement reçu : clés triées, UTF-8, sans espaces superflus."""
    return json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def build_row(record: DonRecord) -> ReportRow:
    """Champs de `reports` d'un enregistrement validé (correspondance : commentaire de schema.sql)."""
    title = display_title(record)
    return ReportRow(
        external_id=record.Id,
        external_ref=record.DonId or None,  # '' -> NULL (CHECK external_ref <> '')
        slug=record.UrlName,
        url=DON_URL.format(slug=quote(record.UrlName, safe="")),
        title=title,
        summary=strip_html(record.Summary),
        published_at=record.PublicationDateAndTime,
        date_quality=date_quality(record, title),
        source_modified_at=record.LastModified,
    )


def prepare_record(raw: Any, request_url: str) -> Prepared:
    """Valide un enregistrement reçu et prépare son écriture.

    Lève `pydantic.ValidationError` (champ manquant ou mal typé) ou `ValueError`.
    L'empreinte porte sur le contenu non compressé (I43).
    """
    record = DonRecord.model_validate(raw)
    body = canonical_json(raw)
    encoded = body.encode("utf-8")
    return Prepared(
        row=build_row(record),
        body=body,
        sha256=hashlib.sha256(encoded).hexdigest(),
        byte_size=len(encoded),
        request_url=request_url,
    )
