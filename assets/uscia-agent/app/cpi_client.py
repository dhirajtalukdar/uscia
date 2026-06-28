"""SAP Integration Suite (CPI) client stub.

Activated when CPI_BASE_URL, CPI_CLIENT_ID, and CPI_CLIENT_KEY are set.
Until those env vars are set, all calls return a MISSING_DATA dict — the
same behaviour as the original tools/cpi_messages.py stub.

This client provides the same async interface as S4Client and IBPClient so
the tool layer is consistent.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MESSAGE_PROCESSING_ROOT = "/api/v1/MessageProcessingLogs"
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("CPI_TIMEOUT_SECONDS", "20.0"))
_TOKEN_TTL_MARGIN = 30


def _cpi_configured() -> bool:
    return bool(
        os.environ.get("CPI_BASE_URL")
        and os.environ.get("CPI_CLIENT_ID")
        and os.environ.get("CPI_CLIENT_KEY")
    )


class CPIClient:
    """Async HTTP client for SAP Integration Suite message logs."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _token_is_fresh(self) -> bool:
        return bool(self._token) and time.monotonic() < self._token_expires_at

    async def _fetch_token(self) -> str:
        token_url = os.environ.get("CPI_TOKEN_URL", "")
        if not token_url:
            raise EnvironmentError("CPIClient: CPI_TOKEN_URL is not set.")
        cid = os.environ.get("CPI_CLIENT_ID", "")
        ckey = os.environ.get("CPI_CLIENT_KEY", "")
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            r = await http.post(
                token_url,
                data={"grant_type": "client_credentials"},
                auth=(cid, ckey),
                headers={"Accept": "application/json"},
            )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._token_expires_at = time.monotonic() + int(data.get("expires_in", 3600)) - _TOKEN_TTL_MARGIN
        return self._token

    async def _bearer(self) -> str:
        if not self._token_is_fresh():
            await self._fetch_token()
        return self._token  # type: ignore[return-value]

    def _build_url(self, service_path: str) -> str:
        base = (os.environ.get("CPI_BASE_URL") or "").rstrip("/")
        if not service_path.startswith("/"):
            service_path = "/" + service_path
        return f"{base}{service_path}"

    async def get(
        self,
        service_path: str,
        params: dict[str, Any] | None = None,
        user_identity: str | None = None,
    ) -> dict[str, Any]:
        if not _cpi_configured():
            return {
                "error": True,
                "status_code": 503,
                "message": "CPI not configured — set CPI_BASE_URL, CPI_CLIENT_ID, CPI_CLIENT_KEY",
            }
        bearer = await self._bearer()
        headers: dict[str, str] = {
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json",
        }
        if user_identity:
            headers["X-User-Identity"] = user_identity
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            r = await http.get(self._build_url(service_path), headers=headers, params=params or {})
        if r.status_code >= 400:
            return {"error": True, "status_code": r.status_code, "message": r.text}
        try:
            return r.json()
        except Exception:
            return {"error": True, "status_code": r.status_code, "message": r.text}


__all__ = ["CPIClient", "MESSAGE_PROCESSING_ROOT"]
