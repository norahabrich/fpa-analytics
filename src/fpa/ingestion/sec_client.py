"""Client HTTP minimal pour les API publiques EDGAR de la SEC.

Règles d'accès de la SEC (https://www.sec.gov/os/accessing-edgar-data) :
- chaque requête doit porter un User-Agent qui identifie le demandeur (nom + e-mail) ;
- au plus 10 requêtes par seconde.

Le client renvoie les octets bruts reçus, sans les transformer, pour que la couche
Bronze archive exactement ce que la SEC a servi.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

DATA_HOST = "https://data.sec.gov"
COMPANY_FACTS_URL = DATA_HOST + "/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = DATA_HOST + "/submissions/CIK{cik}.json"

MIN_INTERVAL_S = 0.15  # marge sous la limite de 10 requêtes/s
RETRY_STATUSES = {429, 500, 502, 503, 504}


def normalize_cik(cik: str | int) -> str:
    """Renvoie le CIK sur 10 chiffres, complété par des zéros (format attendu par l'API)."""
    text = str(cik).strip().upper().removeprefix("CIK")
    if not text.isdigit():
        raise ValueError(f"CIK invalide : {cik!r}")
    value = int(text)
    if value <= 0 or value >= 10**10:
        raise ValueError(f"CIK hors limites : {cik!r}")
    return f"{value:010d}"


@dataclass(frozen=True)
class SecResponse:
    url: str
    status: int
    content: bytes


class SecClient:
    """Accès à data.sec.gov avec User-Agent obligatoire, cadence limitée et reprises."""

    def __init__(
        self,
        user_agent: str | None = None,
        session: requests.Session | None = None,
        max_retries: int = 4,
        backoff_s: float = 1.0,
        timeout_s: float = 30.0,
    ) -> None:
        ua = user_agent or os.environ.get("SEC_USER_AGENT", "")
        if "@" not in ua:
            raise ValueError(
                "La SEC exige un User-Agent avec un contact, par exemple "
                "SEC_USER_AGENT='Prénom Nom prenom.nom@exemple.com'."
            )
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.timeout_s = timeout_s
        self._last_call = 0.0

    def _throttle(self) -> None:
        wait = MIN_INTERVAL_S - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def get(self, url: str) -> SecResponse:
        """GET avec reprises exponentielles sur 429 et erreurs 5xx."""
        for attempt in range(self.max_retries + 1):
            self._throttle()
            resp = self.session.get(url, timeout=self.timeout_s)
            if resp.status_code in RETRY_STATUSES and attempt < self.max_retries:
                time.sleep(self.backoff_s * 2**attempt)
                continue
            resp.raise_for_status()
            return SecResponse(url=url, status=resp.status_code, content=resp.content)
        raise RuntimeError("unreachable")  # pragma: no cover

    def company_facts(self, cik: str | int) -> SecResponse:
        """Tous les faits XBRL publiés par l'entreprise (comptes, bilans, flux)."""
        return self.get(COMPANY_FACTS_URL.format(cik=normalize_cik(cik)))

    def submissions(self, cik: str | int) -> SecResponse:
        """Métadonnées de l'entreprise et liste de ses dépôts récents (10-K, 10-Q, 8-K…)."""
        return self.get(SUBMISSIONS_URL.format(cik=normalize_cik(cik)))
