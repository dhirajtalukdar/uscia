"""SAP IBP Supply Planning OData client.

Resolves credentials from the BTP destination service — same pattern as S4HANA and AI Core.
The destination must be configured in BTP cockpit as:

  Name:            IBP   (override via IBP_DESTINATION_NAME env var)
  Type:            HTTP
  URL:             https://<tenant>.ibp.cloud.sap
  Authentication:  OAuth2ClientCredentials
  Client ID:       <from IBP service key uaa.clientid>
  Client Secret:   <from IBP service key uaa.clientsecret>
  Token URL:       <from IBP service key uaa.url>/oauth/token

Falls back to raw env vars (IBP_BASE_URL / IBP_TOKEN_URL / IBP_CLIENT_ID /
IBP_CLIENT_SECRET) if the destination service is unavailable or the destination
name is not set — preserves backward compatibility.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from s4hana_client import _DestinationResolver, _first_binding

logger = logging.getLogger(__name__)

SUPPLY_PLANNING_ROOT = "/sap/opu/odata/IBP/SUPPLY_PLANNING_SRV"

MAX_PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("IBP_TIMEOUT_SECONDS", "30.0"))
_TOKEN_TTL_MARGIN = 30

IBP_DESTINATION_ENV = "IBP_DESTINATION_NAME"
DEFAULT_IBP_DESTINATION = "IBP"


class IBPClient:
    """Async HTTP client for SAP IBP OData.

    Credential resolution order:
    1. BTP destination service (destination named IBP_DESTINATION_NAME, default 'IBP')
    2. Raw env vars IBP_BASE_URL / IBP_TOKEN_URL / IBP_CLIENT_ID / IBP_CLIENT_SECRET
       (legacy — kept for backward compatibility and local testing)
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
            return  # already resolved

        dest_name = os.environ.get(IBP_DESTINATION_ENV, DEFAULT_IBP_DESTINATION)

        # Try BTP destination service first (same as S4HANA / AI Core)
        if _first_binding("destination"):
            try:
                from s4hana_client import _DestinationResolver as DR
                import httpx as _httpx
                creds = _first_binding("destination") or {}
                tok = await self._resolver._xsuaa_access_token()
                uri = creds["uri"].rstrip("/")
                url = f"{uri}/destination-configuration/v1/destinations/{dest_name}"
                async with _httpx.AsyncClient(timeout=self._timeout) as http:
                    r = await http.get(
                        url,
                        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
                    )
                if r.status_code < 400:
                    cfg = r.json().get("destinationConfiguration") or {}
                    base_url = (cfg.get("URL") or "").rstrip("/")
                    token_url = cfg.get("tokenServiceURL") or cfg.get("TokenServiceURL") or ""
                    client_id = cfg.get("clientId") or cfg.get("Client_Id") or ""
                    client_secret = cfg.get("clientSecret") or cfg.get("Client_Secret") or ""
                    if base_url and token_url and client_id and client_secret:
                        self._base_url = base_url
                        self._token_url = token_url
                        self._client_id = client_id
                        self._client_secret = client_secret
                        logger.info(
                            "IBP credentials resolved from destination '%s' (base=%s)",
                            dest_name, base_url,
                        )
                        return
                    logger.warning(
                        "IBP destination '%s' found but missing fields — falling back to env vars. "
                        "Keys present: %s", dest_name, sorted(cfg.keys())
                    )
                else:
                    logger.warning(
                        "IBP destination '%s' not found in destination service (HTTP %s) — "
                        "falling back to env vars", dest_name, r.status_code
                    )
            except Exception as exc:
                logger.warning("IBP destination resolution failed (%s) — falling back to env vars", exc)

        # Fall back to raw env vars
        base_url = os.environ.get("IBP_BASE_URL", "").rstrip("/")
        token_url = os.environ.get("IBP_TOKEN_URL", "")
        client_id = os.environ.get("IBP_CLIENT_ID", "")
        client_secret = os.environ.get("IBP_CLIENT_SECRET", "")

        if not (base_url and token_url and client_id and client_secret):
            raise EnvironmentError(
                f"IBP credentials not found. Either create a BTP destination named '{dest_name}' "
                "or set env vars IBP_BASE_URL / IBP_TOKEN_URL / IBP_CLIENT_ID / IBP_CLIENT_SECRET."
            )

        self._base_url = base_url
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        logger.info("IBP credentials resolved from env vars (base=%s)", base_url)

    def _token_is_fresh(self) -> bool:
        return bool(self._token) and time.monotonic() < self._token_expires_at

    async def _fetch_token(self) -> str:
        await self._resolve_credentials()
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            r = await http.post(
                self._token_url,  # type: ignore[arg-type]
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),  # type: ignore[arg-type]
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


__all__ = ["IBPClient", "SUPPLY_PLANNING_ROOT"]

