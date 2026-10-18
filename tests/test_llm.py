import pytest
from src.config import load_dataset_config
from src.core.plan_schema import Plan, Metric
from src.db.snowflake_client import ResultObject
from src.llm.planner import preselect_tables, build_prompt
from src.llm.explainer import (
    _extract_numbers_from_text,
    _collect_numbers_from_rows,
    build_template_explanation
)

@pytest.fixture
def dataset_cfg():
    return load_dataset_config("config/datasets/tpch.yaml")

def test_preselect_tables(dataset_cfg):
    tables = preselect_tables("How many orders were placed by customers?", dataset_cfg)
    assert "ORDERS" in tables or "CUSTOMER" in tables

def test_extract_numbers():
    text = "The company made $1,250,000.50 in revenue across 42 regions, an increase of 15%."
    numbers = _extract_numbers_from_text(text)
    assert 1250000.50 in numbers
    assert 42.0 in numbers
    assert 15.0 in numbers

def test_collect_numbers_from_rows():
    rows = [{"ORDER_COUNT": 1500, "REGION": "AMERICA"}, {"ORDER_COUNT": 800, "REGION": "ASIA"}]
    nums = _collect_numbers_from_rows(rows, 2)
    assert 1500.0 in nums
    assert 800.0 in nums
    assert 2.0 in nums

def test_template_explanation_deterministic():
    plan = Plan(intent="query", tables=["ORDERS"], metrics=[Metric(agg="count", col="O_ORDERKEY")])
    result = ResultObject(
        sql="SELECT COUNT(ORDERS.O_ORDERKEY) AS CNT FROM ORDERS",
        params={},
        columns=["CNT"],
        rows=[{"CNT": 150000}],
        row_count=1,
        status="ok"
    )
    explanation = build_template_explanation("How many orders are there?", plan, result)
    assert "150,000" in explanation or "150000" in explanation
