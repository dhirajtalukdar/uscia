"""
CloudConnectorSocket - Python Socket to connect to the SAP Cloud Connector via Connectivity Service.
Based on: https://github.com/fyx99/sap-cloud-connector-python-socket
"""
import os
import functools
import socket
import struct
import base64
import logging

logger = logging.getLogger("cloud_connector_socket")
logger.addHandler(logging.NullHandler())

DEBUG = os.getenv("S4_DEBUG", "false").lower() == "true"

def _log(msg):
    if DEBUG:
        print(f"[CC-SOCKET] {msg}")


def format_status_byte(status_byte) -> str:
    """Helper function to log the CC specific error bytes."""
    status_byte_messages = {
        b"\x00": "SUCCESS",
        b"\x01": "FAILURE: Connection closed by backend",
        b"\x02": "FORBIDDEN: No matching host mapping in Cloud Connector",
        b"\x03": "NETWORK_UNREACHABLE: Cloud Connector not connected",
        b"\x04": "HOST_UNREACHABLE: Cannot reach backend host",
        b"\x05": "CONNECTION_REFUSED: Authentication failure",
        b"\x06": "TTL_EXPIRED",
        b"\x07": "COMMAND_UNSUPPORTED: Only CONNECT supported",
        b"\x08": "ADDRESS_UNSUPPORTED: Only DOMAIN and IPv4 supported"
    }
    return status_byte_messages.get(status_byte, "Unknown error")


def set_self_blocking(function):
    """Helper to use blocking on socket object."""
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        self = args[0]
        try:
            _is_blocking = self.gettimeout()
            if _is_blocking == 0:
                self.setblocking(True)
            return function(*args, **kwargs)
        finally:
            if _is_blocking == 0:
                self.setblocking(False)
    return wrapper


class CloudConnectorSocket(socket.socket):
    """Cloud Connector socket based on SOCKS5 with SAP custom auth."""

    def __init__(self, family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, *args, **kwargs):
        super().__init__(family, type, proto, *args, **kwargs)

    timeout = 30

    @set_self_blocking
    def connect(self, dest_host: str, dest_port: int, proxy_host: str, proxy_port: int, token: str, location_id: str = None):
        """
        Connect to destination via Cloud Connector proxy.

        Args:
            dest_host: Virtual host configured in Cloud Connector
            dest_port: Destination port
            proxy_host: Cloud Connector proxy host
            proxy_port: Cloud Connector SOCKS5 port (usually 20004)
            token: OAuth token from connectivity service
            location_id: Optional Cloud Connector location ID
        """
        _log(f"Connecting to Cloud Connector {proxy_host}:{proxy_port}")
        _log(f"Destination: {dest_host}:{dest_port}")
        _log(f"Location ID: {location_id or 'not set'}")
        super().settimeout(self.timeout)

        try:
            _log("Opening TCP connection to proxy")
            super().connect((proxy_host, proxy_port))
            _log("TCP connection established")
        except Exception as e:
            _log(f"TCP connect failed: {e}")
            self.close()
            raise Exception(f"Failed to connect to proxy: {e}")

        try:
            self._negotiate_auth(dest_host, dest_port, token, location_id)
        except Exception as e:
            _log(f"Auth negotiation failed: {e}")
            self.close()
            raise Exception(f"Auth negotiation failed: {e}")

        _log("Cloud Connector socket ready")

    def _negotiate_auth(self, dest_host, dest_port, token, location_id):
        """SAP Cloud Connector specific SOCKS5 authentication using direct socket I/O."""
        _log("Starting SOCKS5 auth negotiation")

        # Send greeting: SOCKS5, 1 auth method, 0x80 (SAP custom)
        _log("Sending SOCKS5 greeting (auth method 0x80)")
        self.sendall(b"\x05\x01\x80")

        chosen_auth = self._recv_exact(2)
        _log(f"Received auth choice: {chosen_auth.hex()}")
        if chosen_auth[0:1] != b"\x05":
            raise Exception("Invalid SOCKS5 response")

        if chosen_auth[1:2] != b"\x80":
            raise Exception("Unexpected auth type")

        _log("Server accepted SAP auth (0x80), sending bearer token")
        location_id_part = b"\x00"
        if location_id:
            encoded_loc = base64.b64encode(location_id.encode())
            location_id_part = len(encoded_loc).to_bytes(1, byteorder="big") + encoded_loc

        auth_msg = b"\x01" + len(token.encode()).to_bytes(4, byteorder="big") + token.encode() + location_id_part
        self.sendall(auth_msg)

        auth_status = self._recv_exact(2)
        _log(f"Auth status: {auth_status.hex()}")
        if auth_status[0:1] != b"\x01":
            raise Exception("Invalid auth response")
        if auth_status[1:2] != b"\x00":
            raise Exception(f"Auth failed: {format_status_byte(auth_status[1:2])}")
        _log("Authentication successful")

        # Send connect command
        _log(f"Sending CONNECT command for {dest_host}:{dest_port}")
        host_bytes = dest_host.encode("idna")
        connect_msg = (
            b"\x05\x01\x00"
            + b"\x03" + bytes([len(host_bytes)]) + host_bytes
            + struct.pack(">H", dest_port)
        )
        self.sendall(connect_msg)

        # Read response header (VER, REP, RSV)
        resp = self._recv_exact(3)
        _log(f"Connect response: {resp.hex()}")
        if resp[0:1] != b"\x05":
            raise Exception("Invalid SOCKS5 response")

        status = resp[1:2]
        if status != b"\x00":
            raise Exception(f"Connect failed: {format_status_byte(status)}")

        # Read bound address (ATYP + addr + port)
        atyp = self._recv_exact(1)
        if atyp == b"\x01":
            self._recv_exact(4 + 2)  # IPv4 + port
        elif atyp == b"\x03":
            length = self._recv_exact(1)[0]
            self._recv_exact(length + 2)  # domain + port
        elif atyp == b"\x04":
            self._recv_exact(16 + 2)  # IPv6 + port

        _log("SOCKS5 tunnel established")

    def _recv_exact(self, count):
        """Receive exactly count bytes from socket."""
        data = b""
        while len(data) < count:
            chunk = self.recv(count - len(data))
            if not chunk:
                raise Exception("Connection closed")
            data += chunk
        return data
