"""
Local TCP tunnel that forwards HANA SQL connections through Cloud Connector SOCKS5 proxy.

hdbcli connects to localhost:<local_port> as if it were the HANA DB directly.
The tunnel runs in a subprocess to avoid GIL/C-extension issues with hdbcli.

  hdbcli --TCP--> localhost:<port> --SOCKS5+Bearer--> CC:20004 --> HANA vhryvhb4db01:30641
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time

from dotenv import load_dotenv

load_dotenv()

DEBUG = os.getenv("S4_DEBUG", "false").lower() == "true"


def _log(msg):
    if DEBUG:
        print(f"[SQL-TUNNEL] {msg}")


def _run_tunnel_process(local_port, dest_host, dest_port, cc_proxy_host, cc_proxy_port,
                        token_url, client_id, client_secret, location_id):
    """Entry point for the tunnel subprocess. Runs accept loop and relay."""
    import select
    import requests as req
    from clients.cloud_connector_socket import CloudConnectorSocket

    debug = os.getenv("S4_DEBUG", "false").lower() == "true"

    def _p(msg):
        print(f"[SQL-TUNNEL-SUB] {msg}", flush=True)

    token_cache = {"token": None, "expiry": 0}

    def get_token():
        now = time.time()
        if token_cache["token"] and token_cache["expiry"] - now > 60:
            if debug:
                _p(f"Token cached, {token_cache['expiry'] - now:.0f}s remaining")
            return token_cache["token"]

        if debug:
            _p(f"Requesting OAuth token from {token_url}")
        resp = req.post(
            token_url,
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token_cache["token"] = data["access_token"]
        token_cache["expiry"] = now + data.get("expires_in", 3600)
        if debug:
            _p(f"Token obtained, expires in {data.get('expires_in', 3600)}s")
        return token_cache["token"]

    def relay(sock1, sock2):
        """Relay data bidirectionally using select()."""
        sock1.setblocking(False)
        sock2.setblocking(False)
        sockets = [sock1, sock2]
        try:
            while True:
                readable, _, errored = select.select(sockets, [], sockets, 60)
                if errored:
                    break
                for s in readable:
                    data = s.recv(16384)
                    if not data:
                        return
                    dst = sock2 if s is sock1 else sock1
                    dst.sendall(data)
        except Exception as e:
            _p(f"Relay error: {e}")
        finally:
            try:
                sock1.close()
            except Exception:
                pass
            try:
                sock2.close()
            except Exception:
                pass

    def handle(client_sock):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                token = get_token()
                cc_sock = CloudConnectorSocket()
                if debug:
                    _p(f"Connecting attempt {attempt + 1}: {dest_host}:{dest_port} via {cc_proxy_host}:{cc_proxy_port}")
                cc_sock.connect(
                    dest_host=dest_host,
                    dest_port=dest_port,
                    proxy_host=cc_proxy_host,
                    proxy_port=cc_proxy_port,
                    token=token,
                    location_id=location_id,
                )
                _p(f"Connected to {dest_host}:{dest_port} via Cloud Connector")
                relay(client_sock, cc_sock)
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    _p(f"Attempt {attempt + 1} failed: {e}, retrying in 2s...")
                    time.sleep(2)
                else:
                    _p(f"Failed after {max_retries} attempts: {e}")
                    try:
                        client_sock.close()
                    except Exception:
                        pass

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", local_port))
    server.listen(5)
    _p(f"Listening on 127.0.0.1:{local_port} -> {dest_host}:{dest_port}")

    while True:
        try:
            client_sock, addr = server.accept()
            if debug:
                _p(f"Accepted connection from {addr}")
            t = threading.Thread(target=handle, args=(client_sock,), daemon=True)
            t.start()
        except Exception as e:
            _p(f"Accept error: {e}")


class SqlTunnel:
    """Local TCP tunnel forwarding to HANA via Cloud Connector SOCKS5.

    Runs in a subprocess to avoid GIL/C-extension issues.
    Uses OS-assigned free port to avoid collisions.
    """

    def __init__(self, dest_host, dest_port, cc_proxy_host, cc_proxy_port,
                 token_url, client_id, client_secret, location_id):
        self.dest_host = dest_host
        self.dest_port = dest_port
        self.cc_proxy_host = cc_proxy_host
        self.cc_proxy_port = cc_proxy_port
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.location_id = location_id
        self.local_port = None
        self._process = None

    def start(self):
        """Start tunnel subprocess, wait for it to be ready, return local port."""
        if self._process and self._process.poll() is None:
            return self.local_port

        self.local_port = self._find_free_port()
        _log(f"Starting tunnel subprocess on port {self.local_port}")

        cmd = [
            sys.executable, "-c",
            f"import sys; sys.path.insert(0, 'src'); "
            f"from clients.sql_tunnel import _run_tunnel_process; "
            f"_run_tunnel_process("
            f"{self.local_port}, {self.dest_host!r}, {self.dest_port}, "
            f"{self.cc_proxy_host!r}, {self.cc_proxy_port}, "
            f"{self.token_url!r}, {self.client_id!r}, {self.client_secret!r}, "
            f"{self.location_id!r})"
        ]
        self._process = subprocess.Popen(cmd, env=os.environ.copy())

        for i in range(50):
            time.sleep(0.1)
            try:
                s = socket.socket()
                s.settimeout(0.1)
                s.connect(("127.0.0.1", self.local_port))
                s.close()
                _log(f"Tunnel ready on 127.0.0.1:{self.local_port}")
                return self.local_port
            except (ConnectionRefusedError, OSError):
                continue

        if self._process.poll() is not None:
            raise RuntimeError(
                f"Tunnel subprocess exited with code {self._process.returncode}. "
                f"Check logs for [SQL-TUNNEL-SUB] errors."
            )

        _log("Warning: tunnel port not yet accepting, proceeding anyway")
        return self.local_port

    def _find_free_port(self):
        """Let OS assign a free port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


_tunnel = None


def start_sql_tunnel(destination_name):
    """Start SQL tunnel for a BTP destination (singleton).

    Fetches destination config and connectivity proxy details from VCAP_SERVICES,
    then starts a local TCP tunnel subprocess.

    Returns: local port number to connect hdbcli to.
    """
    global _tunnel
    if _tunnel is not None:
        _log(f"Tunnel already running on port {_tunnel.local_port}")
        return _tunnel.local_port

    _log(f"Initializing tunnel for destination '{destination_name}'")

    from clients.btp_service import BtpServiceConfig

    btp = BtpServiceConfig()
    dest = btp.get_destination(destination_name)
    conn = btp.get_connectivity_proxy()

    _tunnel = SqlTunnel(
        dest_host=dest["host"],
        dest_port=dest["port"],
        cc_proxy_host=conn["proxy_host"],
        cc_proxy_port=conn["proxy_port"],
        token_url=conn["token_url"],
        client_id=conn["client_id"],
        client_secret=conn["client_secret"],
        location_id=dest.get("location_id"),
    )
    port = _tunnel.start()
    print(f"[SQL-TUNNEL] 127.0.0.1:{port} -> {dest['host']}:{dest['port']} via CC SOCKS5")
    return port
