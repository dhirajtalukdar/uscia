"""Unit tests for s4hana_client.py — covers destination resolver and S4Client."""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Any


# ── Stub HTTP client helpers ─────────────────────────────────────────────────

@dataclass
class _StubResponse:
    status_code: int
    _body: Any
    _headers: dict = field(default_factory=dict)

    def json(self):
        return self._body

    @property
    def text(self):
        return json.dumps(self._body)

    @property
    def headers(self):
        return self._headers

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class _StubAsyncClient:
    """Minimal stub for httpx.AsyncClient used in tests."""
    def __init__(self, responses: list[_StubResponse]):
        self._responses = list(responses)
        self._idx = 0
        self.requests: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def _next(self) -> _StubResponse:
        r = self._responses[self._idx % len(self._responses)]
        self._idx += 1
        return r

    async def get(self, url, **kwargs) -> _StubResponse:
        self.requests.append({"method": "GET", "url": url, **kwargs})
        return self._next()

    async def post(self, url, **kwargs) -> _StubResponse:
        self.requests.append({"method": "POST", "url": url, **kwargs})
        return self._next()


# ── _first_binding ────────────────────────────────────────────────────────────

def test_first_binding_returns_none_when_vcap_empty(monkeypatch):
    monkeypatch.delenv("VCAP_SERVICES", raising=False)
    from s4hana_client import _first_binding
    assert _first_binding("destination") is None


def test_first_binding_returns_none_on_invalid_json(monkeypatch):
    monkeypatch.setenv("VCAP_SERVICES", "not-json")
    from s4hana_client import _first_binding
    assert _first_binding("destination") is None


def test_first_binding_returns_credentials(monkeypatch):
    vcap = {"destination": [{"credentials": {"uri": "https://dest.example.com", "clientid": "cid", "clientsecret": "csec", "url": "https://oauth.example.com"}}]}
    monkeypatch.setenv("VCAP_SERVICES", json.dumps(vcap))
    from s4hana_client import _first_binding
    creds = _first_binding("destination")
    assert creds["uri"] == "https://dest.example.com"


# ── URL building ──────────────────────────────────────────────────────────────

def test_build_url_with_leading_slash():
    from s4hana_client import S4Client, Destination
    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication")
    client = S4Client(destination=dest)
    assert client._build_url("https://s4.example.com", "/sap/opu/odata/sap/FOO") == "https://s4.example.com/sap/opu/odata/sap/FOO"


def test_build_url_without_leading_slash():
    from s4hana_client import S4Client, Destination
    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication")
    client = S4Client(destination=dest)
    assert client._build_url("https://s4.example.com", "sap/opu/odata/sap/FOO") == "https://s4.example.com/sap/opu/odata/sap/FOO"


# ── X-User-Identity header ────────────────────────────────────────────────────

def test_base_headers_with_user_identity():
    from s4hana_client import S4Client, Destination
    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication")
    client = S4Client(destination=dest)
    h = client._base_headers("alice@example.com")
    assert h["X-User-Identity"] == "alice@example.com"


def test_base_headers_no_user_identity():
    from s4hana_client import S4Client, Destination
    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication")
    client = S4Client(destination=dest)
    h = client._base_headers(None)
    assert "X-User-Identity" not in h


# ── _auth for BasicAuthentication ────────────────────────────────────────────

def test_auth_returns_basic_for_basic_authentication():
    import httpx
    from s4hana_client import S4Client, Destination
    dest = Destination(
        url="https://s4.example.com",
        auth_type="BasicAuthentication",
        user="admin",
        pw="pass123",
    )
    client = S4Client(destination=dest)
    result = client._auth(dest)
    assert isinstance(result, httpx.BasicAuth)


def test_auth_returns_none_for_no_authentication():
    from s4hana_client import S4Client, Destination
    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication")
    client = S4Client(destination=dest)
    assert client._auth(dest) is None


# ── _enforce_page_size ────────────────────────────────────────────────────────

def test_enforce_page_size_caps_at_100():
    from s4hana_client import S4Client
    params = {"$top": 500}
    S4Client._enforce_page_size(params)
    assert params["$top"] == 100


def test_enforce_page_size_sets_default_when_missing():
    from s4hana_client import S4Client
    params = {}
    S4Client._enforce_page_size(params)
    assert params["$top"] == 100


def test_enforce_page_size_keeps_small_value():
    from s4hana_client import S4Client
    params = {"$top": 10}
    S4Client._enforce_page_size(params)
    assert params["$top"] == 10


# ── sap-client injection ──────────────────────────────────────────────────────

def test_inject_mandatory_params_adds_sap_client():
    from s4hana_client import S4Client, Destination
    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication", sap_client="910")
    client = S4Client(destination=dest)
    params: dict = {}
    client._inject_mandatory_params(dest, params)
    assert params["sap-client"] == "910"
    assert params["$format"] == "json"


def test_inject_mandatory_params_skips_if_already_set():
    from s4hana_client import S4Client, Destination
    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication", sap_client="910")
    client = S4Client(destination=dest)
    params: dict = {"sap-client": "800"}
    client._inject_mandatory_params(dest, params)
    assert params["sap-client"] == "800"  # not overwritten


# ── OData v2 envelope unwrap ──────────────────────────────────────────────────

def test_unwrap_odata_v2_envelope():
    from s4hana_client import S4Client, Destination
    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication")
    client = S4Client(destination=dest)
    body = {"d": {"results": [{"PlannedOrder": "1000001"}]}}
    assert client._unwrap(body) == {"results": [{"PlannedOrder": "1000001"}]}


def test_unwrap_passthrough_when_no_d_key():
    from s4hana_client import S4Client, Destination
    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication")
    client = S4Client(destination=dest)
    body = {"value": []}
    assert client._unwrap(body) == {"value": []}


# ── get returns error dict on 4xx/5xx ────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_returns_error_on_4xx(monkeypatch):
    from s4hana_client import S4Client, Destination
    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication")
    client = S4Client(destination=dest)
    stub = _StubAsyncClient([_StubResponse(404, {"error": {"message": "Not found"}})])
    monkeypatch.setattr("s4hana_client.httpx.AsyncClient", lambda **kw: stub)
    result = await client.get("/sap/opu/odata/sap/FOO/A_Entity")
    assert result["error"] is True
    assert result["status_code"] == 404


# ── get handles non-JSON 2xx ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_handles_non_json_2xx(monkeypatch):
    from s4hana_client import S4Client, Destination

    class _NonJsonResponse:
        status_code = 200
        text = "OK plain text"
        def json(self): raise ValueError("not json")
        @property
        def headers(self): return {}

    dest = Destination(url="https://s4.example.com", auth_type="NoAuthentication")
    client = S4Client(destination=dest)

    class _StubNonJson:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, *a, **kw): return _NonJsonResponse()

    monkeypatch.setattr("s4hana_client.httpx.AsyncClient", lambda **kw: _StubNonJson())
    result = await client.get("/foo")
    assert result["error"] is True
    assert result["status_code"] == 200


# ── OnPremise wires connectivity proxy ────────────────────────────────────────

@pytest.mark.asyncio
async def test_client_kwargs_adds_proxy_for_onpremise(monkeypatch):
    from s4hana_client import S4Client, Destination, _DestinationResolver

    dest = Destination(
        url="https://s4.example.com",
        auth_type="NoAuthentication",
        proxy_type="OnPremise",
    )
    mock_resolver = AsyncMock(spec=_DestinationResolver)
    mock_resolver.proxy_settings = AsyncMock(
        return_value=("http://proxy.example.com:20003", {"Proxy-Authorization": "Bearer tok"})
    )
    client = S4Client(destination=dest, resolver=mock_resolver)
    kwargs, extra = await client._client_kwargs(dest)
    assert kwargs["proxy"] == "http://proxy.example.com:20003"
    assert extra["Proxy-Authorization"] == "Bearer tok"


# ── Lazy destination resolution resolves only once ───────────────────────────

@pytest.mark.asyncio
async def test_lazy_destination_resolves_once():
    from s4hana_client import S4Client, Destination, _DestinationResolver

    resolved_dest = Destination(
        url="https://s4.example.com",
        auth_type="NoAuthentication",
        sap_client="910",
    )
    mock_resolver = AsyncMock(spec=_DestinationResolver)
    mock_resolver.resolve = AsyncMock(return_value=resolved_dest)
    mock_resolver.proxy_settings = AsyncMock(return_value=("http://proxy:20003", {}))

    client = S4Client(destination=None, destination_name="S4HANA", resolver=mock_resolver)

    class _DummyResp:
        status_code = 200
        def json(self): return {"d": {"results": []}}
        @property
        def headers(self): return {}

    class _StubHttp:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, *a, **kw): return _DummyResp()

    import s4hana_client
    original = s4hana_client.httpx.AsyncClient

    with patch("s4hana_client.httpx.AsyncClient", return_value=_StubHttp()):
        await client.get("/sap/opu/odata/sap/FOO/A_Entity")
        await client.get("/sap/opu/odata/sap/FOO/A_Entity")

    # Resolver.resolve should have been called exactly once (result cached on _destination)
    assert mock_resolver.resolve.call_count == 1
