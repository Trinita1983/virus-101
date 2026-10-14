"""Client HTTP : User-Agent, URL OData, retries avec backoff (réseau et 5xx), jamais sur 4xx."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from fake_who import FakeWHO, make_records
from observatoire.config import Settings
from observatoire.oms.client import WhoClient
from observatoire.oms.errors import IngestionError


def test_user_agent_explicite_avec_contact_et_requete_odata(
    make_client: Callable[[FakeWHO], WhoClient]
) -> None:
    fake = FakeWHO(make_records(25))
    client = make_client(fake)
    result = client.fetch_all()
    assert len(result.records) == 25
    first = fake.calls[0]
    assert "contact@example.org" in first["headers"]["user-agent"]
    assert first["headers"]["user-agent"].startswith("ObservatoireMaladies/")
    assert first["headers"]["accept"] == "application/json"
    assert first["url"].endswith("?$top=0&$count=true")  # `$` littéral, forme vérifiée en phase 0
    page = fake.calls[1]
    assert page["url"].endswith("?$top=10&$skip=0&$orderby=PublicationDate%20desc")
    assert [c["kind"] for c in fake.calls] == ["count", "page", "page", "page"]


def test_delais_exponentiels_plafonnes_sur_erreur_reseau(
    settings: Settings, sleeps: list[float]
) -> None:
    fake = FakeWHO(make_records(3))
    fake.fault(httpx.ConnectError("refusé"), skip=None)
    client = WhoClient(replace(settings, max_retries=5), transport=httpx.MockTransport(fake),
                       sleep=sleeps.append, jitter=lambda delay: 0.0)
    with pytest.raises(IngestionError) as info:
        client.total_count()
    assert info.value.kind == "reseau"
    assert sleeps == [2.0, 8.0, 30.0, 30.0, 30.0]  # 2 * 4**n, plafonné à 30 s
    assert client.requests == 6 and client.retries == 5


def test_part_aleatoire_ajoutee_a_l_attente(settings: Settings, sleeps: list[float]) -> None:
    fake = FakeWHO(make_records(3))
    fake.fault(503, skip=None)
    client = WhoClient(settings, transport=httpx.MockTransport(fake), sleep=sleeps.append,
                       jitter=lambda delay: 1.0)
    with pytest.raises(IngestionError):
        client.total_count()
    assert sleeps == [3.0, 9.0, 31.0]


def test_timeout_est_reessaye_puis_echoue_proprement(
    make_client: Callable[[FakeWHO], WhoClient], sleeps: list[float]
) -> None:
    fake = FakeWHO(make_records(3))
    fake.fault(httpx.ReadTimeout("trop lent"), skip=None)
    client = make_client(fake)
    with pytest.raises(IngestionError, match="ReadTimeout") as info:
        client.fetch_all()
    assert info.value.kind == "reseau"
    assert len(fake.calls) == 4 and sleeps == [2.0, 8.0, 30.0]


def test_reprise_apres_erreurs_transitoires(
    make_client: Callable[[FakeWHO], WhoClient], sleeps: list[float]
) -> None:
    fake = FakeWHO(make_records(15))
    fake.fault(502, skip=10, times=1)
    fake.fault(httpx.ConnectError("coupure"), skip=10, times=1)
    client = make_client(fake)
    result = client.fetch_all()
    assert len(result.records) == 15
    assert client.retries == 2 and sleeps == [2.0, 8.0]
    assert fake.page_skips == [0, 10, 10, 10]


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_5xx_retry_avec_backoff_puis_echec_propre(
    make_client: Callable[[FakeWHO], WhoClient], sleeps: list[float], status: int
) -> None:
    fake = FakeWHO(make_records(15))
    fake.fault(status, skip=10)
    client = make_client(fake)
    with pytest.raises(IngestionError) as info:
        client.fetch_all()
    assert info.value.kind == "http" and f"HTTP {status}" in str(info.value)
    assert fake.page_skips == [0, 10, 10, 10, 10]  # 1 essai + 3 nouvelles tentatives
    assert sleeps == [2.0, 8.0, 30.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410])
def test_4xx_jamais_de_retry(make_client: Callable[[FakeWHO], WhoClient],
                             sleeps: list[float], status: int) -> None:
    fake = FakeWHO(make_records(15))
    fake.fault(status, skip=None)
    client = make_client(fake)
    with pytest.raises(IngestionError) as info:
        client.fetch_all()
    assert info.value.kind == "http" and f"HTTP {status}" in str(info.value)
    assert len(fake.calls) == 1 and sleeps == [] and client.retries == 0


def test_429_quota_sans_retry(make_client: Callable[[FakeWHO], WhoClient],
                              sleeps: list[float]) -> None:
    fake = FakeWHO(make_records(15))
    fake.fault(429, skip=None)
    client = make_client(fake)
    with pytest.raises(IngestionError) as info:
        client.total_count()
    assert info.value.kind == "quota"
    assert len(fake.calls) == 1 and sleeps == []


def test_reponse_non_json_est_une_erreur_de_format(
    make_client: Callable[[FakeWHO], WhoClient]
) -> None:
    fake = FakeWHO(make_records(3))
    fake.fault(lambda: httpx.Response(200, content=b"<html>maintenance</html>"), skip=None)
    with pytest.raises(IngestionError) as info:
        make_client(fake).total_count()
    assert info.value.kind == "format" and len(fake.calls) == 1


def test_decompte_absent_est_une_erreur_de_format(
    make_client: Callable[[FakeWHO], WhoClient]
) -> None:
    fake = FakeWHO(make_records(3))
    fake.fault(lambda: httpx.Response(200, json={"value": []}), skip=None)
    with pytest.raises(IngestionError) as info:
        make_client(fake).total_count()
    assert info.value.kind == "format"


def test_page_sans_champ_value_est_une_erreur_de_format(
    make_client: Callable[[FakeWHO], WhoClient]
) -> None:
    fake = FakeWHO(make_records(3))
    fake.fault(lambda: httpx.Response(200, json={"items": []}), skip=0)
    with pytest.raises(IngestionError) as info:
        make_client(fake).fetch_all()
    assert info.value.kind == "format"


def test_pagination_qui_ne_se_termine_pas_est_bornee(
    make_client: Callable[[FakeWHO], WhoClient]
) -> None:
    """Un serveur qui ignorerait `$skip` ne fait pas boucler le client."""
    page = make_records(10)

    def always_full() -> httpx.Response:
        return httpx.Response(200, json={"value": page})

    fake = FakeWHO(make_records(10))
    for skip in range(0, 400, 10):
        fake.fault(always_full, skip=skip)
    with pytest.raises(IngestionError) as info:
        make_client(fake).fetch_all()
    assert info.value.kind == "controle"
    assert len(fake.page_skips) == 11  # ceil(10 / 10) + 10 pages, pas davantage


def test_reglages_valides(tmp_path: Path, settings: Settings) -> None:
    with pytest.raises(ValueError, match="contact"):
        Settings(db_path=tmp_path / "x", contact=" ")
    with pytest.raises(ValueError, match="page_size"):
        Settings(db_path=tmp_path / "x", contact="a@b.c", page_size=101)
    with pytest.raises(ValueError, match="timeout"):
        Settings(db_path=tmp_path / "x", contact="a@b.c", timeout=0)
    client = WhoClient(replace(settings, timeout=7.5), transport=httpx.MockTransport(FakeWHO([])))
    assert client._http.timeout.read == 7.5  # noqa: SLF001 (le délai configuré est appliqué)
