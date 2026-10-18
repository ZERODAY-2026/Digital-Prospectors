import pytest
from src.config import load_dataset_config
from src.core.plan_schema import Plan, Metric, Dimension, Filter, OrderBy
from src.core.validator import validate_plan, ValidationResult

@pytest.fixture
def dataset_cfg():
    return load_dataset_config("config/datasets/tpch.yaml")

def test_non_query_intent_rejected(dataset_cfg):
    plan = Plan(intent="clarify", message="Please specify measure")
    res = validate_plan(plan, dataset_cfg)
    assert not res.is_valid
    assert "non-query intent" in res.error.lower()

def test_unknown_table_rejected(dataset_cfg):
    plan = Plan(
        intent="query",
        tables=["UNKNOWN_TABLE"],
        metrics=[Metric(agg="count", col="O_ORDERKEY")]
    )
    res = validate_plan(plan, dataset_cfg)
    assert not res.is_valid
    assert "unknown table" in res.error.lower()

def test_unknown_column_rejected(dataset_cfg):
    plan = Plan(
        intent="query",
        tables=["ORDERS"],
        metrics=[Metric(agg="count", col="NON_EXISTENT_COL")]
    )
    res = validate_plan(plan, dataset_cfg)
    assert not res.is_valid
    assert "unknown column" in res.error.lower()

def test_wrong_aggregate_for_type_rejected(dataset_cfg):
    # O_ORDERSTATUS is string: sum is not allowed
    plan = Plan(
        intent="query",
        tables=["ORDERS"],
        metrics=[Metric(agg="sum", col="O_ORDERSTATUS")]
    )
    res = validate_plan(plan, dataset_cfg)
    assert not res.is_valid
    assert "aggregate" in res.error.lower() or "not allowed" in res.error.lower()

def test_limit_above_max_rejected(dataset_cfg):
    plan = Plan(
        intent="query",
        tables=["ORDERS"],
        metrics=[Metric(agg="count", col="O_ORDERKEY")],
        limit=5000  # max_limit is 1000
    )
    res = validate_plan(plan, dataset_cfg)
    assert not res.is_valid
    assert "limit" in res.error.lower()

def test_default_limit_applied(dataset_cfg):
    plan = Plan(
        intent="query",
        tables=["ORDERS"],
        metrics=[Metric(agg="count", col="O_ORDERKEY")],
        limit=None
    )
    res = validate_plan(plan, dataset_cfg)
    assert res.is_valid
    assert res.plan.limit == 100

def test_valid_single_table_plan(dataset_cfg):
    plan = Plan(
        intent="query",
        tables=["ORDERS"],
        metrics=[Metric(agg="count", col="O_ORDERKEY", as_="order_count")],
        dims=[Dimension(col="O_ORDERSTATUS")],
        filters=[Filter(col="O_ORDERSTATUS", op="=", val="O")],
        order_by=[OrderBy(key="order_count", dir="desc")],
        limit=50
    )
    res = validate_plan(plan, dataset_cfg)
    assert res.is_valid
    assert res.error is None
    assert res.plan.limit == 50

def test_valid_multi_table_join_plan(dataset_cfg):
    plan = Plan(
        intent="query",
        tables=["ORDERS", "CUSTOMER", "NATION", "REGION"],
        metrics=[Metric(agg="sum", col="O_TOTALPRICE", as_="total_sales")],
        dims=[Dimension(col="R_NAME")],
        order_by=[OrderBy(key="total_sales", dir="desc")]
    )
    res = validate_plan(plan, dataset_cfg)
    assert res.is_valid
    assert res.error is None
