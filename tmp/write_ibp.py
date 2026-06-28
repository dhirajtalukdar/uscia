ibp_content = """\
\"\"\"
SAP IBP Supply Data tool wrapper.
OAuth 2.0 with tenant-specific endpoint. Reads credentials from environment.
Token is cached and refreshed on 401.
\"\"\"
from __future__ import annotations
import os
import time
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import base64

logger = logging.getLogger(__name__)

_MISSING = "IBP_SUPPLY"
_token_cache: dict = {}

_GUIDANCE = (
    "Check IBP supply plan in IBP Monitor. "
    "Verify planning run completed for version {version}. "
    "Check EXTERNID assignment for material {material} location {plant}. "
    "Navigate to IBP Monitor > Supply Planning > check job status and output key figures."
)


def _load_secret(env_key: str) -> str:
    return os.environ.get(env_key, "")


def _fetch_token() -> str:
    now = time.time()
    if _token_cache.get("expires_at", 0) > now + 30:
        return str(_token_cache.get("access_token", ""))

    token_url = _load_secret("IBP_TOKEN_URL")
    client_id = _load_secret("IBP_CLIENT_ID")
    secret_val = _load_secret("IBP_CLIENT_SECRET")
    if not token_url or not client_id:
        raise ValueError("IBP_TOKEN_URL or IBP_CLIENT_ID not configured")

    creds = base64.b64encode(f"{client_id}:{secret_val}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(
        token_url,
        data=data,
        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        token_data = json.loads(resp.read())

    _token_cache["access_token"] = token_data["access_token"]
    _token_cache["expires_at"] = now + int(token_data.get("expires_in", 3600))
    return str(_token_cache["access_token"])


def _ibp_get(path: str, params: dict) -> dict:
    base_url = _load_secret("IBP_BASE_URL").rstrip("/")
    bearer = _fetch_token()
    qs = urllib.parse.urlencode(params)
    url = f"{base_url}{path}?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            _token_cache.clear()
            new_bearer = _fetch_token()
            req.add_header("Authorization", f"Bearer {new_bearer}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        raise


async def get_ibp_supply_data(
    material: str,
    plant: str,
    planning_version: str,
    date_from: str,
    date_to: str,
) -> dict:
    try:
        if not _load_secret("IBP_BASE_URL"):
            raise EnvironmentError("IBP_BASE_URL not configured")
        result = _ibp_get(
            "/sap/opu/odata/IBP/SUPPLY_PLANNING_SRV/SupplyOrders",
            {
                "$filter": (
                    f"Material eq '{material}' and Location eq '{plant}' "
                    f"and PlanningVersion eq '{planning_version}'"
                ),
                "$top": 100,
                "$format": "json",
            },
        )
        return {"status": "AVAILABLE", "system": _MISSING, "data": result}
    except Exception as exc:
        logger.warning("get_ibp_supply_data failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "guidance": _GUIDANCE.format(
                version=planning_version, material=material, plant=plant
            ),
        }
"""

with open("/home/user/project/assets/uscia-agent/app/tools/ibp_supply.py", "w") as f:
    f.write(ibp_content)
print("Written OK, length:", len(ibp_content))
