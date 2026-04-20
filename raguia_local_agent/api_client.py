"""Client HTTP vers l'API portail (JWT agent)."""

from __future__ import annotations

import contextlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0  # secondes (x2 a chaque tentative)


def _request_with_retry(method: str, url: str, *, retries: int = _MAX_RETRIES, **kwargs) -> httpx.Response:
    """Effectue une requete HTTP avec retry exponentiel sur erreurs transitoires."""
    last_exc: Exception | None = None
    delay = _RETRY_BACKOFF
    for attempt in range(retries + 1):
        try:
            r = httpx.request(method, url, **kwargs)
            if r.status_code in _RETRYABLE_STATUS and attempt < retries:
                log.warning("HTTP %s depuis %s (tentative %d/%d), retry dans %.1fs...",
                            r.status_code, url, attempt + 1, retries, delay)
                time.sleep(delay)
                delay *= 2
                continue
            return r
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
            last_exc = e
            if attempt < retries:
                log.warning("Erreur reseau %s (tentative %d/%d), retry dans %.1fs: %s",
                            url, attempt + 1, retries, delay, e)
                time.sleep(delay)
                delay *= 2
            else:
                raise
    raise last_exc  # type: ignore[misc]


class PortalApiClient:
    def __init__(self, api_base: str, agent_token: str):
        self.api_base = api_base.rstrip("/")
        self.agent_token = agent_token
        self._headers = {"Authorization": f"Bearer {agent_token}"}
        
        # Securite : Bloquer HTTP si ce n'est pas localhost (evite MitM / vol de JWT)
        if self.api_base.startswith("http://"):
            import urllib.parse
            hostname = urllib.parse.urlparse(self.api_base).hostname
            if hostname not in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                log.error("SECURITE CRITIQUE : api_base (%s) utilise HTTP au lieu de HTTPS !", self.api_base)
                log.error("Le jeton agent serait envoye en clair sur le reseau.")
                raise ValueError("L'URL du portail DOIT utiliser 'https://' pour des raisons de securite.")

    def sync_status(self) -> dict[str, Any]:
        r = _request_with_retry(
            "GET",
            f"{self.api_base}/api/portal/agent/sync-status",
            headers=self._headers,
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()

    def sync_complete(
        self, metrics: Optional[dict[str, Any]] = None, error: Optional[str] = None
    ) -> None:
        r = _request_with_retry(
            "POST",
            f"{self.api_base}/api/portal/agent/sync-complete",
            headers={**self._headers, "Content-Type": "application/json"},
            json={"metrics": metrics or {}, "error": error},
            timeout=120.0,
        )
        r.raise_for_status()

    def upload_files(
        self,
        paths: list[Path],
        metadata: list[dict[str, Any]],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if len(paths) != len(metadata):
            raise ValueError("paths et metadata doivent avoir la meme longueur")

        data = {
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
            "dry_run": str(dry_run).lower(),
        }
        with contextlib.ExitStack() as stack:
            file_tuples = []
            for p in paths:
                fh = stack.enter_context(open(p, "rb"))
                file_tuples.append(
                    ("files", (p.name, fh, "application/octet-stream")),
                )
            # Upload sans retry (fichiers ouverts, non re-openable dans ExitStack)
            r = httpx.post(
                f"{self.api_base}/api/portal/agent/upload",
                headers=self._headers,
                data=data,
                files=file_tuples,
                timeout=600.0,
            )
        r.raise_for_status()
        return r.json()
