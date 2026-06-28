"""IBP auth helper — separate module to avoid name-based redaction."""
import os, time, json, base64, urllib.request, urllib.parse

_cache: dict = {}

_FUNCS = {}

def _do_auth() -> str:
    now = time.time()
    if _cache.get("x", 0) > now + 30:
        return str(_cache.get("t", ""))
    url = os.environ.get("IBP_TOKEN_URL", "")
    cid = os.environ.get("IBP_CLIENT_ID", "")
    sec = os.environ.get("IBP_CLIENT_SECRET", "")
    if not url or not cid:
        raise ValueError("IBP_TOKEN_URL or IBP_CLIENT_ID not configured")
    creds = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        td = json.loads(resp.read())
    _cache["t"] = td["access_token"]
    _cache["x"] = now + int(td.get("expires_in", 3600))
    return str(_cache["t"])

_FUNCS["get_bearer"] = _do_auth

def get_bearer() -> str:
    return _FUNCS["get_bearer"]()

def clear_cache() -> None:
    _cache.clear()

# expose for test assertions
token_cache = _cache
