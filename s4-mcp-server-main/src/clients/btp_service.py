"""
BTP Service integration: Destination Service + Connectivity Service.

Parses VCAP_SERVICES for service credentials, fetches destination config,
and provides cached OAuth tokens for Cloud Connector SOCKS5 authentication.
"""
import json
import os
import time
import logging

import requests

logger = logging.getLogger("btp_service")

DEBUG = os.getenv("S4_DEBUG", "false").lower() == "true"


def _log(msg):
    if DEBUG:
        print(f"[BTP] {msg}")


class BtpServiceConfig:
    """Parses VCAP_SERVICES and provides BTP Destination + Connectivity access."""

    def __init__(self):
        self._dest_creds = None
        self._conn_creds = None
        self._dest_token_cache = None  # (token, expiry_timestamp)
        self._conn_token_cache = None  # (token, expiry_timestamp)
        self._parse_vcap()

    def _parse_vcap(self):
        vcap_raw = os.getenv("VCAP_SERVICES")
        if not vcap_raw:
            raise RuntimeError(
                "VCAP_SERVICES not set. BTP Destination mode requires Cloud Foundry service bindings "
                "(destination + connectivity)."
            )

        _log(f"VCAP_SERVICES length: {len(vcap_raw)} chars")

        try:
            services = json.loads(vcap_raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"VCAP_SERVICES is not valid JSON: {e}")

        try:
            self._dest_creds = services["destination"][0]["credentials"]
            _log(f"Destination service: uri={self._dest_creds.get('uri', '?')}")
        except (KeyError, IndexError):
            raise RuntimeError(
                "No 'destination' service binding found in VCAP_SERVICES. "
                "Bind a Destination Service instance to your app."
            )

        try:
            self._conn_creds = services["connectivity"][0]["credentials"]
            _log(f"Connectivity service: proxy={self._conn_creds.get('onpremise_proxy_host', '?')}")
        except (KeyError, IndexError):
            raise RuntimeError(
                "No 'connectivity' service binding found in VCAP_SERVICES. "
                "Bind a Connectivity Service instance to your app."
            )

        _log("Parsed VCAP_SERVICES: destination + connectivity OK")

    def _get_cached_token(self, cache_attr, token_url, client_id, client_secret, label):
        """OAuth client_credentials with caching. Refreshes when < 60s TTL remaining."""
        cached = getattr(self, cache_attr)
        if cached:
            token, expiry = cached
            remaining = expiry - time.time()
            if remaining > 60:
                _log(f"{label} token: cached, {remaining:.0f}s remaining")
                return token
            _log(f"{label} token: expired or < 60s remaining, refreshing")

        _log(f"{label} token: requesting from {token_url}")
        try:
            resp = requests.post(
                token_url,
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to get {label} OAuth token from {token_url}: {e}")

        token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        expiry = time.time() + expires_in
        setattr(self, cache_attr, (token, expiry))
        _log(f"{label} token: obtained, expires in {expires_in}s")
        return token

    def _get_destination_token(self):
        url = self._dest_creds.get("url", "").rstrip("/")
        if not url:
            raise RuntimeError("Destination service credentials missing 'url' (XSUAA endpoint)")
        token_url = url + "/oauth/token"
        client_id = self._dest_creds["clientid"]
        client_secret = self._dest_creds["clientsecret"]
        return self._get_cached_token("_dest_token_cache", token_url, client_id, client_secret, "Destination")

    def get_connectivity_token(self):
        """Get cached Bearer token for SOCKS5 proxy authentication."""
        token_base = self._conn_creds.get("token_service_url", "").rstrip("/")
        if not token_base:
            raise RuntimeError("Connectivity service credentials missing 'token_service_url'")
        token_url = token_base + "/oauth/token"
        client_id = self._conn_creds["clientid"]
        client_secret = self._conn_creds["clientsecret"]
        return self._get_cached_token("_conn_token_cache", token_url, client_id, client_secret, "Connectivity")

    def get_connectivity_proxy(self):
        """Get Cloud Connector SOCKS5 proxy config from VCAP_SERVICES.

        Returns: dict with proxy_host, proxy_port, token_url, client_id, client_secret
        """
        proxy_host = self._conn_creds.get("onpremise_proxy_host")
        proxy_port = int(self._conn_creds.get("onpremise_socks5_proxy_port", "20004"))
        if not proxy_host:
            raise RuntimeError("Connectivity service credentials missing 'onpremise_proxy_host'")

        token_base = self._conn_creds.get("token_service_url", "").rstrip("/")
        token_url = token_base + "/oauth/token" if token_base else None

        _log(f"Connectivity SOCKS5 proxy: {proxy_host}:{proxy_port}")
        return {
            "proxy_host": proxy_host,
            "proxy_port": proxy_port,
            "token_url": token_url,
            "client_id": self._conn_creds.get("clientid"),
            "client_secret": self._conn_creds.get("clientsecret"),
        }

    def get_http_proxy(self):
        """Get Cloud Connector HTTP proxy config from VCAP_SERVICES.

        Returns: dict with proxy_host, proxy_port
        """
        proxy_host = self._conn_creds.get("onpremise_proxy_host")
        proxy_port = int(
            self._conn_creds.get("onpremise_proxy_http_port")
            or self._conn_creds.get("onpremise_proxy_port", "20003")
        )
        if not proxy_host:
            raise RuntimeError("Connectivity service credentials missing 'onpremise_proxy_host'")

        _log(f"Connectivity HTTP proxy: {proxy_host}:{proxy_port}")
        return {"proxy_host": proxy_host, "proxy_port": proxy_port}

    def get_destination(self, name):
        """Fetch TCP destination config from BTP Destination Service.

        Validates: Type=TCP, ProxyType=OnPremise.
        Extracts: host, port, location_id from destination properties.

        Returns: dict with host, port, location_id (may be None)
        """
        config = self._fetch_destination_config(name)

        dest_type = config.get("Type", "")
        if dest_type != "TCP":
            raise RuntimeError(
                f"Destination '{name}' has Type='{dest_type}', expected 'TCP'. "
                f"Only TCP destinations are supported for SQL tunnel."
            )

        proxy_type = config.get("ProxyType", "")
        if proxy_type != "OnPremise":
            raise RuntimeError(
                f"Destination '{name}' has ProxyType='{proxy_type}', expected 'OnPremise'. "
                f"Only OnPremise (Cloud Connector) destinations are supported."
            )

        host, port = self._parse_destination_address(name, config)
        location_id = config.get("CloudConnectorLocationId") or None

        _log(f"Destination '{name}': host={host}, port={port}, location_id={location_id}, "
             f"type={dest_type}, proxy={proxy_type}")
        return {"host": host, "port": port, "location_id": location_id}

    def get_http_destination(self, name):
        """Fetch HTTP destination config from BTP Destination Service.

        Validates: Type=HTTP, ProxyType=OnPremise.
        Extracts: url, auth credentials, sap-client, location_id.

        Returns: dict with url, location_id, user, password, sap_client
        """
        config = self._fetch_destination_config(name)

        dest_type = config.get("Type", "")
        if dest_type != "HTTP":
            raise RuntimeError(
                f"Destination '{name}' has Type='{dest_type}', expected 'HTTP'."
            )

        proxy_type = config.get("ProxyType", "")
        if proxy_type != "OnPremise":
            raise RuntimeError(
                f"Destination '{name}' has ProxyType='{proxy_type}', expected 'OnPremise'."
            )

        url = config.get("URL", "")
        if not url:
            raise RuntimeError(f"Destination '{name}' has no URL configured.")

        location_id = config.get("CloudConnectorLocationId") or None
        auth_type = config.get("Authentication", "NoAuthentication")
        user = config.get("User") if auth_type == "BasicAuthentication" else None
        password = config.get("Password") if auth_type == "BasicAuthentication" else None
        sap_client = config.get("sap-client") or config.get("sap_client") or None

        _log(f"HTTP Destination '{name}': url={url}, auth={auth_type}, "
             f"location_id={location_id}, sap-client={sap_client}")
        return {
            "url": url,
            "location_id": location_id,
            "user": user,
            "password": password,
            "sap_client": sap_client,
        }

    def _fetch_destination_config(self, name):
        """Fetch raw destination config from BTP Destination Service API."""
        uri = self._dest_creds.get("uri", "").rstrip("/")
        if not uri:
            raise RuntimeError("Destination service credentials missing 'uri'")

        token = self._get_destination_token()
        url = f"{uri}/destination-configuration/v1/destinations/{name}"
        _log(f"Fetching destination: GET {url}")

        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to fetch destination '{name}': {e}")

        _log(f"Destination response keys: {list(data.keys())}")
        if DEBUG:
            safe = {k: v for k, v in data.get("destinationConfiguration", {}).items()
                    if k.lower() not in ("password", "clientsecret")}
            _log(f"Destination config: {json.dumps(safe, indent=2)}")

        config = data.get("destinationConfiguration", {})
        if not config:
            raise RuntimeError(f"Destination '{name}' returned empty configuration")

        return config

    def _parse_destination_address(self, name, config):
        """Extract host and port from destination config.

        TCP destinations use the 'Address' field (format: "host:port").
        Falls back to 'Host'+'Port' or URL parsing.
        """
        address = config.get("Address", "")
        if address:
            _log(f"Parsing Address field: '{address}'")
            addr = address.replace("tcp://", "").replace("TCP://", "")
            if ":" in addr:
                parts = addr.rsplit(":", 1)
                host = parts[0]
                try:
                    port = int(parts[1])
                    return host, port
                except ValueError:
                    pass

        host = config.get("Host", "")
        port_str = config.get("Port", "")
        if host and port_str:
            _log(f"Using Host/Port fields: {host}:{port_str}")
            return host, int(port_str)

        url = config.get("URL", "")
        if url:
            _log(f"Parsing URL field: '{url}'")
            cleaned = url.split("://", 1)[-1] if "://" in url else url
            if ":" in cleaned:
                parts = cleaned.rsplit(":", 1)
                host = parts[0]
                port_part = parts[1].split("/")[0]
                try:
                    return host, int(port_part)
                except ValueError:
                    pass

        server_node = config.get("ServerNode", "")
        if server_node and ":" in server_node:
            _log(f"Parsing ServerNode field: '{server_node}'")
            parts = server_node.rsplit(":", 1)
            try:
                return parts[0], int(parts[1])
            except ValueError:
                pass

        raise RuntimeError(
            f"Cannot determine host:port for destination '{name}'. "
            f"Checked fields: Address='{address}', Host/Port, URL='{config.get('URL', '')}', "
            f"ServerNode='{server_node}'. None yielded a valid host:port."
        )
