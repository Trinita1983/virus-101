"""Client HTTP de l'API OMS : pagination OData, retries avec backoff, User-Agent explicite."""

from __future__ import annotations

import logging
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from observatoire.config import Settings
from observatoire.oms.errors import IngestionError

logger = logging.getLogger(__name__)

# Pages supplémentaires tolérées au-delà du total annoncé (DON publiés pendant le parcours).
_EXTRA_PAGES = 10


class _CountPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    count: int = Field(alias="@odata.count", ge=0, strict=True)


class _PagePayload(BaseModel):
    value: list[Any]


@dataclass(frozen=True)
class FetchedRecord:
    """Un enregistrement tel que reçu, avec l'URL de la page qui l'a renvoyé."""

    raw: Any
    request_url: str


@dataclass
class Fetched:
    """Résultat d'un parcours complet de l'API."""

    expected_count: int
    records: list[FetchedRecord] = field(default_factory=list)


def default_jitter(delay: float) -> float:
    """Part aléatoire ajoutée à l'attente (jusqu'à 25 %), pour ne pas synchroniser les relances."""
    return random.uniform(0.0, delay * 0.25)


class WhoClient:
    """Client de `diseaseoutbreaknews`. Une instance par exécution : les compteurs sont cumulatifs.

    `sleep` et `jitter` sont injectables pour les tests (aucune attente réelle).
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float], float] = default_jitter,
    ) -> None:
        self.settings = settings
        self.requests = 0
        self.retries = 0
        self._sleep = sleep
        self._jitter = jitter
        self._http = httpx.Client(
            transport=transport,
            timeout=settings.timeout,
            headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
        )

    def close(self) -> None:
        self._http.close()

    def _url(self, params: dict[str, str | int]) -> str:
        """URL avec `$` littéral dans les noms OData (forme vérifiée en phase 0)."""
        query = urlencode(params, safe="$", quote_via=quote)
        return f"{self.settings.base_url}?{query}"

    def _delay(self, attempt: int) -> float:
        s = self.settings
        return min(s.backoff_max, s.backoff_base * s.backoff_factor**attempt)

    def _get_json(self, url: str) -> Any:
        """GET avec retries sur erreur réseau et 5xx ; jamais sur 4xx. Renvoie le JSON décodé."""
        failure: IngestionError | None = None
        for attempt in range(self.settings.max_retries + 1):
            if attempt:
                delay = self._delay(attempt - 1)
                delay += self._jitter(delay)
                logger.warning("nouvel essai %d/%d dans %.1f s : %s", attempt,
                               self.settings.max_retries, delay, failure)
                self.retries += 1
                self._sleep(delay)
            self.requests += 1
            try:
                response = self._http.get(url)
            except httpx.TransportError as exc:
                failure = IngestionError("reseau", f"{type(exc).__name__} : {exc} ({url})")
                continue
            if response.status_code >= 500:
                failure = IngestionError("http", f"HTTP {response.status_code} ({url})")
                continue
            return self._decode(response, url)
        assert failure is not None
        raise failure

    @staticmethod
    def _decode(response: httpx.Response, url: str) -> Any:
        """Refuse tout statut hors 2xx (sans retry) puis décode le JSON."""
        status = response.status_code
        if status == 429:
            raise IngestionError("quota", f"HTTP 429, quota atteint ({url})")
        if not 200 <= status < 300:
            raise IngestionError("http", f"HTTP {status} ({url})")
        try:
            return response.json()
        except ValueError as exc:
            raise IngestionError("format", f"réponse non JSON ({url}) : {exc}") from exc

    def total_count(self) -> int:
        """Total annoncé par l'API : `$top=0&$count=true` ne renvoie que le décompte."""
        url = self._url({"$top": 0, "$count": "true"})
        try:
            return _CountPayload.model_validate(self._get_json(url)).count
        except ValidationError as exc:
            raise IngestionError("format", f"@odata.count absent ou invalide ({url})") from exc

    def fetch_page(self, skip: int) -> tuple[list[Any], str]:
        """Une page de `page_size` enregistrements à partir de `skip`. Renvoie (enregistrements, URL)."""
        s = self.settings
        url = self._url({"$top": s.page_size, "$skip": skip, "$orderby": s.order_by})
        try:
            return _PagePayload.model_validate(self._get_json(url)).value, url
        except ValidationError as exc:
            raise IngestionError("format", f"champ `value` absent ou invalide ({url})") from exc

    def fetch_all(self) -> Fetched:
        """Parcourt toutes les pages. S'arrête sur la première page incomplète ou vide.

        La page de fin peut être partielle (total non multiple de la taille de page) ou vide
        (total multiple, ou aucun DON). Un garde-fou borne le nombre de pages si l'API ignorait
        `$skip` : il lève une erreur de contrôle plutôt que de boucler.
        """
        size = self.settings.page_size
        result = Fetched(expected_count=self.total_count())
        max_pages = math.ceil(result.expected_count / size) + _EXTRA_PAGES
        for page in range(max_pages):
            records, url = self.fetch_page(page * size)
            result.records.extend(FetchedRecord(raw, url) for raw in records)
            if len(records) < size:
                return result
        raise IngestionError("controle", f"pagination sans fin : {max_pages} pages lues")
