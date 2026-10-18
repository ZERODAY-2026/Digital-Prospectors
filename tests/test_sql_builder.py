import pytest
from src.config import load_dataset_config
from src.core.plan_schema import Plan, Metric, Dimension, Filter, OrderBy
from src.core.validator import validate_plan
from src.core.sql_builder import build_sql

@pytest.fixture
def dataset_cfg():
    return load_dataset_config("config/datasets/tpch.yaml")

def test_single_table_count_sql(dataset_cfg):
    plan = Plan(
        intent="query",
        tables=["ORDERS"],
        metrics=[Metric(agg="count", col="O_ORDERKEY", as_="order_count")]
    )
    val_res = validate_plan(plan, dataset_cfg)
    assert val_res.is_valid
    sql, params = build_sql(val_res.plan, dataset_cfg)
    assert ";" not in sql
    assert sql.strip().startswith("SELECT")
    assert "COUNT(ORDERS.O_ORDERKEY) AS order_count" in sql or "COUNT(ORDERS.O_ORDERKEY) AS ORDER_COUNT" in sql.upper()
    assert "FROM ORDERS" in sql
    assert "LIMIT 100" in sql
    assert params == {}

def test_sql_with_filter_and_params(dataset_cfg):
    plan = Plan(
        intent="query",
        tables=["ORDERS"],
        metrics=[Metric(agg="count", col="O_ORDERKEY", as_="order_count")],
        filters=[Filter(col="O_ORDERSTATUS", op="=", val="O")]
    )
    val_res = validate_plan(plan, dataset_cfg)
    sql, params = build_sql(val_res.plan, dataset_cfg)
    assert ";" not in sql
    assert "WHERE" in sql
    assert "ORDERS.O_ORDERSTATUS = %(p0)s" in sql
    assert params == {"p0": "O"}

def test_injection_attempt_is_safely_parameterized(dataset_cfg):
    malicious_val = "'; DROP TABLE ORDERS; --"
    plan = Plan(
        intent="query",
        tables=["CUSTOMER"],
        metrics=[Metric(agg="count", col="C_CUSTKEY", as_="cnt")],
        filters=[Filter(col="C_MKTSEGMENT", op="=", val=malicious_val)]
    )
    val_res = validate_plan(plan, dataset_cfg)
    assert val_res.is_valid
    sql, params = build_sql(val_res.plan, dataset_cfg)
    assert ";" not in sql
    assert "DROP TABLE" not in sql
    assert params == {"p0": malicious_val}

def test_multi_table_join_resolution(dataset_cfg):
    plan = Plan(
        intent="query",
        tables=["ORDERS", "CUSTOMER", "NATION", "REGION"],
        metrics=[Metric(agg="sum", col="O_TOTALPRICE", as_="total_sales")],
        dims=[Dimension(col="R_NAME")],
        order_by=[OrderBy(key="total_sales", dir="desc")],
        limit=10
    )
    val_res = validate_plan(plan, dataset_cfg)
    assert val_res.is_valid
    sql, params = build_sql(val_res.plan, dataset_cfg)
    assert ";" not in sql
    assert "JOIN" in sql
    assert "GROUP BY" in sql
    assert "ORDER BY total_sales DESC" in sql or "ORDER BY TOTAL_SALES DESC" in sql.upper()
    assert "LIMIT 10" in sql

def test_date_dimension_fn(dataset_cfg):
    plan = Plan(
        intent="query",
        tables=["ORDERS"],
        metrics=[Metric(agg="sum", col="O_TOTALPRICE", as_="total_sales")],
        dims=[Dimension(col="O_ORDERDATE", fn="year")]
    )
    val_res = validate_plan(plan, dataset_cfg)
    assert val_res.is_valid
    sql, params = build_sql(val_res.plan, dataset_cfg)
    assert "EXTRACT(YEAR FROM ORDERS.O_ORDERDATE)" in sql
    assert "GROUP BY" in sql
