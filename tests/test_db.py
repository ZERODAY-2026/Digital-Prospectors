import os
import pytest
from decimal import Decimal
from datetime import date, datetime
from src.db.snowflake_client import SnowflakeClient, ResultObject, make_json_safe, sanitize_error
from src.config import SnowflakeConfig, load_app_config

def test_make_json_safe():
    assert make_json_safe(Decimal("100.50")) == 100.50
    assert make_json_safe(Decimal("100")) == 100
    assert make_json_safe(date(2026, 10, 18)) == "2026-10-18"
    assert make_json_safe(datetime(2026, 10, 18, 12, 30, 0)) == "2026-10-18T12:30:00"
    nested = {"a": Decimal("42.0"), "b": [date(2026, 1, 1)]}
    assert make_json_safe(nested) == {"a": 42, "b": ["2026-01-01"]}

def test_sanitize_error():
    raw_error = "Connection failed: user='DATAMIND_APP_USER' password='super_secret_password' host='xyz'"
    clean = sanitize_error(raw_error)
    assert "super_secret_password" not in clean
    assert "password=***" in clean

def test_unconfigured_credentials_returns_error():
    cfg = SnowflakeConfig(
        account="",
        user="DATAMIND_APP_USER",
        password="",
        role="DATAMIND_APP_ROLE",
        warehouse="DATAMIND_WH",
        database="DATAMIND_DB",
        schema="SALES"
    )
    client = SnowflakeClient(config=cfg)
    res = client.execute_query("SELECT 1")
    assert res.status == "error"
    assert "credentials" in res.error.lower()
    assert res.row_count == 0

@pytest.mark.skipif(
    not os.path.exists(".env") or not os.getenv("SNOWFLAKE_ACCOUNT") or not os.getenv("SNOWFLAKE_PASSWORD"),
    reason="Snowflake credentials not present in environment or .env"
)
def test_snowflake_live_integration():
    client = SnowflakeClient()
    res = client.execute_query("SELECT COUNT(*) AS CNT FROM ORDERS")
    assert res.status == "ok"
    assert res.row_count == 1
    assert res.query_id is not None
    assert "CNT" in res.columns
