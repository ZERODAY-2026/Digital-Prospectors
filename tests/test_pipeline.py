import pytest
from src.config import load_dataset_config
from src.core.plan_schema import Plan, Metric
from src.core.pipeline import DataMindPipeline, PipelineResult
from src.db.snowflake_client import ResultObject

@pytest.fixture
def dataset_cfg():
    return load_dataset_config("config/datasets/tpch.yaml")

class FakeDbClient:
    def __init__(self, status="ok", rows=None, error=None):
        self.status = status
        self.rows = rows or []
        self.error = error

    def execute_query(self, sql, params=None, timeout_seconds=30, max_rows=1000):
        if self.status == "error":
            return ResultObject(
                sql=sql,
                params=params or {},
                columns=[],
                rows=[],
                row_count=0,
                status="error",
                error=self.error or "Synthetic DB Error"
            )
        status = "empty" if len(self.rows) == 0 else "ok"
        columns = list(self.rows[0].keys()) if self.rows else []
        return ResultObject(
            sql=sql,
            params=params or {},
            columns=columns,
            rows=self.rows,
            row_count=len(self.rows),
            status=status,
            query_id="FAKE-QUERY-ID-12345",
            elapsed_ms=45.2
        )

def test_pipeline_query_ok(dataset_cfg):
    def fake_planner(question, dataset_cfg, ollama_cfg):
        return Plan(intent="query", tables=["ORDERS"], metrics=[Metric(agg="count", col="O_ORDERKEY", as_="cnt")])

    def fake_explainer(question, plan, result, ollama_cfg):
        return "There are 1,500,000 orders in the database."

    fake_db = FakeDbClient(status="ok", rows=[{"CNT": 1500000}])

    pipeline = DataMindPipeline(
        dataset_cfg=dataset_cfg,
        db_client=fake_db,
        planner_fn=fake_planner,
        explainer_fn=fake_explainer
    )

    res: PipelineResult = pipeline.run("How many orders are there?")
    assert res.status == "ok"
    assert res.result.row_count == 1
    assert res.evidence.query_id == "FAKE-QUERY-ID-12345"
    assert "1,500,000" in res.explanation

def test_pipeline_empty_result(dataset_cfg):
    def fake_planner(question, dataset_cfg, ollama_cfg):
        return Plan(intent="query", tables=["ORDERS"], metrics=[Metric(agg="count", col="O_ORDERKEY")])

    fake_db = FakeDbClient(status="ok", rows=[])

    pipeline = DataMindPipeline(
        dataset_cfg=dataset_cfg,
        db_client=fake_db,
        planner_fn=fake_planner
    )

    res = pipeline.run("Show orders from Atlantis")
    assert res.status == "empty"
    assert "no matching rows" in res.explanation.lower()

def test_pipeline_clarify(dataset_cfg):
    def fake_planner(question, dataset_cfg, ollama_cfg):
        return Plan(intent="clarify", message="Please specify what defines the best region.")

    pipeline = DataMindPipeline(
        dataset_cfg=dataset_cfg,
        planner_fn=fake_planner
    )

    res = pipeline.run("Show the best region")
    assert res.status == "clarify"
    assert "best region" in res.explanation

def test_pipeline_unsupported(dataset_cfg):
    def fake_planner(question, dataset_cfg, ollama_cfg):
        return Plan(intent="unsupported", message="Forecasting is not supported.")

    pipeline = DataMindPipeline(
        dataset_cfg=dataset_cfg,
        planner_fn=fake_planner
    )

    res = pipeline.run("Predict next year's sales")
    assert res.status == "unsupported"
    assert "not supported" in res.explanation

def test_pipeline_validation_error(dataset_cfg):
    def fake_planner(question, dataset_cfg, ollama_cfg):
        return Plan(intent="query", tables=["INVALID_TABLE"], metrics=[Metric(agg="count", col="FOO")])

    pipeline = DataMindPipeline(
        dataset_cfg=dataset_cfg,
        planner_fn=fake_planner
    )

    res = pipeline.run("Query invalid table")
    assert res.status == "validation_error"
    assert "Unknown table" in res.explanation

def test_pipeline_db_error(dataset_cfg):
    def fake_planner(question, dataset_cfg, ollama_cfg):
        return Plan(intent="query", tables=["ORDERS"], metrics=[Metric(agg="count", col="O_ORDERKEY")])

    fake_db = FakeDbClient(status="error", error="Warehouse suspended")

    pipeline = DataMindPipeline(
        dataset_cfg=dataset_cfg,
        db_client=fake_db,
        planner_fn=fake_planner
    )

    res = pipeline.run("Count orders")
    assert res.status == "db_error"
    assert "Warehouse suspended" in res.explanation

def test_pipeline_llm_error(dataset_cfg):
    def failing_planner(question, dataset_cfg, ollama_cfg):
        raise ConnectionError("Failed to connect to 11434")

    pipeline = DataMindPipeline(
        dataset_cfg=dataset_cfg,
        planner_fn=failing_planner
    )

    res = pipeline.run("Count orders")
    assert res.status == "llm_error"
    assert "ollama is not running" in res.explanation.lower()
