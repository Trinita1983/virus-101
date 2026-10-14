"""Faux serveur OData de l'OMS pour `httpx.MockTransport` : aucun appel réseau.

Comportements reproduits d'après docs/00-sources.md §2.3 : `$top`, `$skip`, `$count=true`
(`@odata.count`), `$top=0&$count=true` renvoie le total seul, `$top` > 100 donne HTTP 400.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "who_don_sample.json"


def fixture_records() -> list[dict[str, Any]]:
    """Les 5 enregistrements bruts de la fixture de la phase 0."""
    data: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))["value"]
    return data


def make_record(i: int) -> dict[str, Any]:
    """Un enregistrement synthétique valide, dérivé d'un enregistrement réel de la fixture."""
    record = copy.deepcopy(fixture_records()[2])  # 2022-DON398_1 : le plus petit DON moderne
    record["Id"] = f"00000000-0000-4000-8000-{i:012d}"
    record["UrlName"] = f"2030-DON{i}"
    record["DonId"] = f"2030-DON{i}"
    record["Title"] = f"Maladie fictive {i}"
    record["OverrideTitle"] = ""
    record["PublicationDateAndTime"] = "2030-01-01T12:00:00Z"
    record["LastModified"] = "2030-01-02T12:00:00Z"
    return record


def make_records(count: int, start: int = 0) -> list[dict[str, Any]]:
    return [make_record(i) for i in range(start, start + count)]


Outcome = Exception | int | Callable[[], httpx.Response]


@dataclass
class _Fault:
    skip: int | None  # None : l'appel de décompte (`$top=0`)
    outcome: Outcome
    remaining: int | None  # None : à chaque appel


class FakeWHO:
    """Serveur simulé. `records` est modifiable entre deux exécutions."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.calls: list[dict[str, Any]] = []
        self._faults: list[_Fault] = []

    def fault(self, outcome: Outcome, *, skip: int | None, times: int | None = None) -> None:
        """Fait échouer les appels pour `skip` (page) ou pour le décompte (`skip=None`)."""
        self._faults.append(_Fault(skip, outcome, times))

    def clear_faults(self) -> None:
        self._faults.clear()

    @property
    def page_skips(self) -> list[int]:
        """Valeurs de `$skip` des pages demandées, dans l'ordre (tentatives comprises)."""
        return [c["skip"] for c in self.calls if c["kind"] == "page"]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        top, skip = int(params["$top"]), int(params.get("$skip", "0"))
        kind = "count" if top == 0 else "page"
        self.calls.append({"kind": kind, "skip": skip, "top": top, "url": str(request.url),
                           "headers": dict(request.headers), "orderby": params.get("$orderby")})
        for fault in self._faults:
            if fault.skip == (None if kind == "count" else skip) and fault.remaining != 0:
                if fault.remaining is not None:
                    fault.remaining -= 1
                return self._apply(fault.outcome, request)
        if top > 100:
            return httpx.Response(400, json={"error": "top trop grand"})
        body: dict[str, Any] = {"@odata.context": "https://www.who.int/api/news/$metadata",
                                "value": [] if kind == "count" else self.records[skip:skip + top]}
        if params.get("$count") == "true":
            body["@odata.count"] = len(self.records)
        return httpx.Response(200, json=body)

    @staticmethod
    def _apply(outcome: Outcome, request: httpx.Request) -> httpx.Response:
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, int):
            return httpx.Response(outcome, json={"error": f"HTTP {outcome} simulé"})
        return outcome()
