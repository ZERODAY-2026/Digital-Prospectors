import time
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from typing import List, Dict, Any, Optional
import snowflake.connector
from snowflake.connector.errors import ProgrammingError, DatabaseError, OperationalError
from src.config import SnowflakeConfig, load_app_config

@dataclass
class ResultObject:
    sql: str
    params: Dict[str, Any]
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    status: str  # "ok", "empty", "error"
    error: Optional[str] = None
    query_id: Optional[str] = None
    elapsed_ms: float = 0.0

def make_json_safe(val: Any) -> Any:
    """Convert non-JSON-serializable Snowflake data types into clean JSON-safe Python types."""
    if isinstance(val, Decimal):
        # If integer decimal (e.g. 10.0000 with no frac), convert to int, else float
        if val % 1 == 0:
            return int(val)
        return float(val)
    elif isinstance(val, (datetime, date)):
        return val.isoformat()
    elif isinstance(val, dt_time):
        return val.strftime("%H:%M:%S")
    elif isinstance(val, (bytes, bytearray)):
        return val.hex()
    elif isinstance(val, dict):
        return {k: make_json_safe(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [make_json_safe(item) for item in val]
    return val

def sanitize_error(err_msg: str) -> str:
    """Remove potential passwords, tokens, or raw secrets from error messages."""
    msg = re.sub(r"password=['\"][^'\"]*['\"]", "password=***", err_msg, flags=re.IGNORECASE)
    msg = re.sub(r"pwd=['\"][^'\"]*['\"]", "pwd=***", msg, flags=re.IGNORECASE)
    msg = re.sub(r"token=['\"][^'\"]*['\"]", "token=***", msg, flags=re.IGNORECASE)
    return msg

class SnowflakeClient:
    def __init__(self, config: Optional[SnowflakeConfig] = None):
        if config is None:
            app_cfg = load_app_config()
            self.config = app_cfg.snowflake
        else:
            self.config = config

    def execute_query(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 30,
        max_rows: int = 1000
    ) -> ResultObject:
        """Execute a read-only parameterized query against Snowflake and return ResultObject."""
        if params is None:
            params = {}

        if not self.config.account or not self.config.password:
            return ResultObject(
                sql=sql,
                params=params,
                columns=[],
                rows=[],
                row_count=0,
                status="error",
                error="Snowflake credentials are not configured in .env."
            )

        start_time = time.time()
        conn = None
        cur = None
        query_id = None

        try:
            conn = snowflake.connector.connect(
                account=self.config.account,
                user=self.config.user,
                password=self.config.password,
                role=self.config.role,
                warehouse=self.config.warehouse,
                database=self.config.database,
                schema=self.config.schema,
                autocommit=False,
                session_parameters={
                    "STATEMENT_TIMEOUT_IN_SECONDS": timeout_seconds,
                    "QUERY_TAG": "DATAMIND_AI_AGENT"
                }
            )

            cur = conn.cursor(snowflake.connector.DictCursor)
            cur.execute(sql, params)
            query_id = cur.sfqid

            raw_rows = cur.fetchmany(max_rows)
            elapsed_ms = (time.time() - start_time) * 1000.0

            if cur.description:
                columns = [desc[0] for desc in cur.description]
            else:
                columns = []

            safe_rows = [
                {k: make_json_safe(v) for k, v in row.items()}
                for row in raw_rows
            ]

            status = "empty" if len(safe_rows) == 0 else "ok"

            return ResultObject(
                sql=sql,
                params=params,
                columns=columns,
                rows=safe_rows,
                row_count=len(safe_rows),
                status=status,
                error=None,
                query_id=query_id,
                elapsed_ms=round(elapsed_ms, 2)
            )

        except (ProgrammingError, DatabaseError, OperationalError, Exception) as e:
            elapsed_ms = (time.time() - start_time) * 1000.0
            sanitized = sanitize_error(str(e))
            return ResultObject(
                sql=sql,
                params=params,
                columns=[],
                rows=[],
                row_count=0,
                status="error",
                error=sanitized,
                query_id=query_id,
                elapsed_ms=round(elapsed_ms, 2)
            )
        finally:
            if cur:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
