"""
Tests directory conftest — adds app/ to sys.path so all imports work.
Also provides FakeClient / FakeS4Client / FakeIBPClient fixtures used
across domain-tool tests after the MCP -> direct-API migration.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Add app/ to sys.path so test imports resolve the same way as at runtime
_APP_PATH = str(Path(__file__).parent.parent / "app")
if _APP_PATH not in sys.path:
    sys.path.insert(0, _APP_PATH)

# Add tests/ to sys.path so helpers.py is importable
_TESTS_PATH = str(Path(__file__).parent)
if _TESTS_PATH not in sys.path:
    sys.path.insert(0, _TESTS_PATH)


# ── Fake client helpers ────────────────────────────────────────────────────────

@dataclass
class FakeCall:
    method: str
    path: str
    params: dict
    user_identity: str | None
    body: dict | None = None
    service_root: str | None = None


@dataclass
class FakeClient:
    """Generic fake for S4Client / IBPClient / CPIClient / CloudALMClient."""
    responses: dict[str, Any] = field(default_factory=dict)
    calls: list[FakeCall] = field(default_factory=list)

    def _resolve(self, call: FakeCall) -> dict:
        for needle, payload in self.responses.items():
            if needle in call.path:
                if callable(payload):
                    return payload(call)
                return dict(payload) if isinstance(payload, dict) else payload
        return {"results": []}

    async def get(
        self,
        service_path: str,
        params: dict | None = None,
        user_identity: str | None = None,
    ) -> dict:
        call = FakeCall("GET", service_path, dict(params or {}), user_identity)
        self.calls.append(call)
        return self._resolve(call)

    async def post(
        self,
        service_path: str,
        body: dict,
        service_root: str,
        user_identity: str | None = None,
    ) -> dict:
        call = FakeCall("POST", service_path, {}, user_identity, body, service_root)
        self.calls.append(call)
        return self._resolve(call)


# Typed aliases (optional — test code may import these directly)
FakeS4Client = FakeClient
FakeIBPClient = FakeClient


def make_fake(responses: dict[str, Any] | None = None) -> FakeClient:
    """Factory: create a FakeClient pre-loaded with response stubs.

    Example::

        fake = make_fake({"A_PlannedOrder": {"results": [{"PlannedOrder": "1000001"}]}})
        result = await get_planned_orders("MAT", "1000", "2024-01-01", "2024-12-31", s4=fake)
        assert result["status"] == "AVAILABLE"
        assert fake.calls[0].params["$filter"].startswith("Material eq 'MAT'")
    """
    return FakeClient(responses=dict(responses or {}))
