import os
import logging

from dotenv import load_dotenv
from hdbcli import dbapi

load_dotenv()

logger = logging.getLogger("s4-mcp-server")
DEBUG = os.getenv("S4_DEBUG", "false").lower() == "true"


def _log(msg):
    if DEBUG:
        print(f"[SQL] {msg}")


class S4SQLClient:
    """SQL client for SAP HANA database connections.

    Supports two modes:
    - Direct: S4_SQL_HOST + S4_SQL_PORT (direct TCP to HANA)
    - Destination: S4_SQL_DESTINATION (via BTP Destination + Cloud Connector tunnel)
    """

    def __init__(self):
        self.hana_user = os.getenv("S4_SQL_USER")
        self.hana_password = os.getenv("S4_SQL_PASSWORD")
        self.destination = os.getenv("S4_SQL_DESTINATION")

        if self.destination:
            _log(f"Destination mode: {self.destination}")
            from clients.sql_tunnel import start_sql_tunnel
            self.local_port = start_sql_tunnel(self.destination)
            self.hana_host = "127.0.0.1"
            self.hana_port = self.local_port
            _log(f"Connecting via tunnel: 127.0.0.1:{self.local_port}")
        else:
            self.hana_host = os.getenv("S4_SQL_HOST")
            self.hana_port = os.getenv("S4_SQL_PORT")
            self.local_port = None
            if self.hana_host:
                _log(f"Direct mode: {self.hana_host}:{self.hana_port}")

        if not all([self.hana_host, self.hana_port, self.hana_user, self.hana_password]):
            print("Warning: S4 SQL connection details are missing in environment variables.")

    def execute_query(self, sql: str):
        """Executes a SQL query directly against the SAP HANA database."""
        if not all([self.hana_host, self.hana_port, self.hana_user, self.hana_password]):
            return {"error": "HANA connection details are missing in environment variables."}
        try:
            _log(f"Connecting to {self.hana_host}:{self.hana_port}")
            conn = dbapi.connect(
                address=self.hana_host,
                port=int(self.hana_port),
                user=self.hana_user,
                password=self.hana_password
            )
            _log(f"Connected, executing query: {sql[:100]}...")
            cursor = conn.cursor()
            cursor.execute(sql)
            if not cursor.description:
                rowcount = cursor.rowcount
                _log(f"Statement executed, {rowcount} rows affected")
                cursor.close()
                conn.close()
                return {"message": "Statement executed successfully", "rowcount": rowcount}
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            result = [dict(zip(columns, row)) for row in rows]
            _log(f"Query returned {len(result)} rows")
            cursor.close()
            conn.close()
            return result
        except Exception as e:
            _log(f"Query failed: {e}")
            return {"error": f"HANA SQL Execution Error: {str(e)}"}


s4_sql_client = S4SQLClient()
