"""SAP Integration Suite (CPI) OData client.

Resolves credentials from the BTP destination service — same pattern as IBPClient.
The BTP destination must be configured in BTP cockpit as:

  Name:            SAP_CPI   (override via CPI_DESTINATION_NAME env var)
  Type:            HTTP
  Authentication:  OAuth2ClientCredentials

Falls back to raw env vars (CPI_BASE_URL / CPI_TOKEN_URL / CPI_CLIENT_ID /
CPI_CLIENT_KEY) if the destination service is unavailable.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

try:
    from s4hana_client import _DestinationResolver, _first_binding
except ImportError:
    from app.s4hana_client import _DestinationResolver, _first_binding  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

MESSAGE_PROCESSING_ROOT = "/api/v1/MessageProcessingLogs"
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("CPI_TIMEOUT_SECONDS", "20.0"))
MAX_PAGE_SIZE = 100
_TOKEN_TTL_MARGIN = 30

CPI_DESTINATION_ENV = "CPI_DESTINATION_NAME"
DEFAULT_CPI_DESTINATION = "SAP_CPI"


class CPIClient:
    """Async HTTP client for SAP Integration Suite OData (Message Processing Logs).

    Credential resolution order:
    1. BTP destination service (destination named CPI_DESTINATION_NAME, default 'SAP_CPI')
    2. Raw env vars CPI_BASE_URL / CPI_TOKEN_URL / CPI_CLIENT_ID / CPI_CLIENT_KEY
    """

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._base_url: str | None = None
        self._token_url: str | None = None
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._resolver = _DestinationResolver(timeout=timeout)

    async def _resolve_credentials(self) -> None:
        """Populate base_url / token_url / client_id / secret from destination or env vars."""
        if self._base_url:
            return

        dest_name = os.environ.get(CPI_DESTINATION_ENV, DEFAULT_CPI_DESTINATION)

        if _first_binding("destination"):
            try:
                creds = _first_binding("destination") or {}
                tok = await self._resolver._xsuaa_access_token()
                uri = creds["uri"].rstrip("/")
                dest_url = f"{uri}/destination-configuration/v1/destinations/{dest_name}"
                async with httpx.AsyncClient(timeout=self._timeout) as http:
                    r = await http.get(
                        dest_url,
                        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
                    )
                if r.status_code < 400:
                    cfg = r.json().get("destinationConfiguration") or {}
                    base_url = (cfg.get("URL") or "").rstrip("/")
                    token_url = cfg.get("tokenServiceURL") or cfg.get("TokenServiceURL") or ""
                    cid = cfg.get("clientId") or cfg.get("Client_Id") or ""
                    csec = cfg.get("clientSecret") or cfg.get("Client_Secret") or ""
                    if base_url and token_url and cid and csec:
                        self._base_url = base_url
                        self._token_url = token_url
                        self._client_id = cid
                        self._client_secret = csec
                        logger.info(
                            "CPI credentials resolved from destination '%s' (base=%s)",
                            dest_name, base_url,
                        )
                        return
                    logger.warning(
                        "CPI destination '%s' found but missing fields — falling back to env vars. "
                        "Keys present: %s", dest_name, sorted(cfg.keys())
                    )
                else:
                    logger.warning(
                        "CPI destination '%s' not found (HTTP %s) — falling back to env vars",
                        dest_name, r.status_code,
                    )
            except Exception as exc:
                logger.warning("CPI destination resolution failed (%s) — falling back to env vars", exc)

        base_url = os.environ.get("CPI_BASE_URL", "").rstrip("/")
        token_url = os.environ.get("CPI_TOKEN_URL", "")
        cid = os.environ.get("CPI_CLIENT_ID", "")
        csec = os.environ.get("CPI_CLIENT_KEY", "")  # legacy env var name kept

        if not (base_url and token_url and cid and csec):
            raise EnvironmentError(
                f"CPI credentials not found. Either create a BTP destination named '{dest_name}' "
                "or set env vars CPI_BASE_URL / CPI_TOKEN_URL / CPI_CLIENT_ID / CPI_CLIENT_KEY."
            )

        self._base_url = base_url
        self._token_url = token_url
        self._client_id = cid
        self._client_secret = csec
        logger.info("CPI credentials resolved from env vars (base=%s)", base_url)

    def _token_is_fresh(self) -> bool:
        return bool(self._token) and time.monotonic() < self._token_expires_at

    async def _fetch_token(self) -> str:
        await self._resolve_credentials()
        cid = self._client_id
        csec = self._client_secret
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            r = await http.post(
                self._token_url,  # type: ignore[arg-type]
                data={"grant_type": "client_credentials"},
                auth=(cid, csec),  # type: ignore[arg-type]
                headers={"Accept": "application/json"},
            )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = time.monotonic() + expires_in - _TOKEN_TTL_MARGIN
        return self._token

    async def _bearer(self) -> str:
        if not self._token_is_fresh():
            await self._fetch_token()
        return self._token  # type: ignore[return-value]

    @staticmethod
    def _enforce_page_size(params: dict[str, Any], key: str = "$top") -> None:
        if key in params:
            try:
                params[key] = min(int(params[key]), MAX_PAGE_SIZE)
            except (ValueError, TypeError):
                params[key] = MAX_PAGE_SIZE
        else:
            params[key] = MAX_PAGE_SIZE

    async def get(
        self,
        service_path: str,
        params: dict[str, Any] | None = None,
        user_identity: str | None = None,
        retry_on_401: bool = True,
    ) -> dict[str, Any]:
        await self._resolve_credentials()
        merged: dict[str, Any] = dict(params or {})
        self._enforce_page_size(merged)
        if "$format" not in merged:
            merged["$format"] = "json"

        bearer = await self._bearer()
        headers: dict[str, str] = {
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json",
        }
        if user_identity:
            headers["X-User-Identity"] = user_identity

        base = self._base_url  # type: ignore[assignment]
        if not service_path.startswith("/"):
            service_path = "/" + service_path
        url = f"{base}{service_path}"

        async with httpx.AsyncClient(timeout=self._timeout) as http:
            r = await http.get(url, headers=headers, params=merged)

        if r.status_code == 401 and retry_on_401:
            self._token = None
            return await self.get(
                service_path, params=params,
                user_identity=user_identity, retry_on_401=False,
            )

        if r.status_code >= 400:
            return {
                "error": True,
                "status_code": r.status_code,
                "message": r.text,
                "url": url,
            }
        try:
            body = r.json()
        except Exception:
            return {"error": True, "status_code": r.status_code, "message": r.text}

        if isinstance(body, dict) and "d" in body:
            return body["d"]
        return body


__all__ = ["CPIClient", "MESSAGE_PROCESSING_ROOT"]
