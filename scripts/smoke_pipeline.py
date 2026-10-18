import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.core.pipeline import DataMindPipeline, PipelineResult
from src.core.plan_schema import Plan, Metric
from src.db.snowflake_client import SnowflakeClient, ResultObject
from src.config import AppConfig, SnowflakeConfig, OllamaConfig, load_app_config, load_dataset_config

def run_smoke():
    print("=" * 80)
    print("DATAMIND-BUSINESS END-TO-END PIPELINE SMOKE TEST")
    print("=" * 80)

    app_cfg = load_app_config()
    dataset_cfg = load_dataset_config(app_cfg.dataset_config_path)
    pipeline = DataMindPipeline(app_cfg=app_cfg, dataset_cfg=dataset_cfg)

    # 1. Normal Question
    print("\n" + "-" * 70)
    print("TEST 1: Normal Question -> 'How many orders are there?'")
    print("-" * 70)
    res1 = pipeline.run("How many orders are there?")
    print(f"Status: {res1.status}")
    if res1.plan:
        print(f"Plan Intent: {res1.plan.intent}")
        print(f"Plan Tables: {res1.plan.tables}")
    if res1.result:
        print(f"SQL: {res1.result.sql}")
        print(f"Query ID: {res1.result.query_id}")
        print(f"Row count: {res1.result.row_count}")
    print(f"Explanation: {res1.explanation}")

    # 2. Ambiguous Question
    print("\n" + "-" * 70)
    print("TEST 2: Ambiguous Question -> 'Show the best region'")
    print("-" * 70)
    res2 = pipeline.run("Show the best region")
    print(f"Status: {res2.status}")
    if res2.plan:
        print(f"Plan Intent: {res2.plan.intent}")
    print(f"Explanation: {res2.explanation}")

    # 3. Out-of-Scope Question (Non-business)
    print("\n" + "-" * 70)
    print("TEST 3: Out-of-Scope Question -> 'Help me with my chemistry homework'")
    print("-" * 70)
    res3 = pipeline.run("Help me with my chemistry homework")
    print(f"Status: {res3.status}")
    if res3.plan:
        print(f"Plan Intent: {res3.plan.intent}")
    print(f"Explanation: {res3.explanation}")

    # 4. Out-of-Scope Question (Business missing domain)
    print("\n" + "-" * 70)
    print("TEST 4: Missing Domain Question -> 'What are the employee salaries in HR?'")
    print("-" * 70)
    res4 = pipeline.run("What are the employee salaries in HR?")
    print(f"Status: {res4.status}")
    if res4.plan:
        print(f"Plan Intent: {res4.plan.intent}")
    print(f"Explanation: {res4.explanation}")

    # 5. Hallucination Guard Test (Injected fake explanation with invented number)
    print("\n" + "-" * 70)
    print("TEST 5: Hallucination Guard Test (Injected Fake Explanation)")
    print("-" * 70)

    class FakeDbWithRows:
        def execute_query(self, sql, params=None, timeout_seconds=30, max_rows=1000):
            return ResultObject(
                sql=sql,
                params=params or {},
                columns=["ORDER_COUNT"],
                rows=[{"ORDER_COUNT": 1500}],
                row_count=1,
                status="ok",
                query_id="TEST-GUARD-QID-9999",
                elapsed_ms=12.5
            )

    fake_db = FakeDbWithRows()

    # Fake explainer that hallucinates an invented number (99,999,999) not in the rows (which has 1500)
    def hallucinating_explainer(question, plan, result, ollama_cfg=None):
        return "Based on the records, the company processed 99,999,999 orders."

    # 5a. STRICT_MODE = false
    print("\n[5a] Running with STRICT_MODE=false (Fallback to template expected):")
    app_cfg_false = AppConfig(
        snowflake=app_cfg.snowflake,
        ollama=app_cfg.ollama,
        dataset_config_path=app_cfg.dataset_config_path,
        strict_mode=False
    )
    pipe_false = DataMindPipeline(
        app_cfg=app_cfg_false,
        dataset_cfg=dataset_cfg,
        db_client=fake_db,
        explainer_fn=hallucinating_explainer
    )
    res_false = pipe_false.run("How many orders are there?")
    print(f"Status: {res_false.status}")
    print(f"Explanation Used: {res_false.explanation}")
    if res_false.evidence and res_false.evidence.guard:
        print(f"Guard Report: {res_false.evidence.guard}")

    # 5b. STRICT_MODE = true
    print("\n[5b] Running with STRICT_MODE=true (Output blocked code block expected):")
    app_cfg_true = AppConfig(
        snowflake=app_cfg.snowflake,
        ollama=app_cfg.ollama,
        dataset_config_path=app_cfg.dataset_config_path,
        strict_mode=True
    )
    pipe_true = DataMindPipeline(
        app_cfg=app_cfg_true,
        dataset_cfg=dataset_cfg,
        db_client=fake_db,
        explainer_fn=hallucinating_explainer
    )
    res_true = pipe_true.run("How many orders are there?")
    print(f"Status: {res_true.status}")
    print(f"Explanation:\n{res_true.explanation}")
    if res_true.evidence and res_true.evidence.guard:
        print(f"Guard Report: {res_true.evidence.guard}")

    print("\n" + "=" * 80)
    print("ALL SMOKE PIPELINE VERIFICATIONS COMPLETED")
    print("=" * 80)

if __name__ == "__main__":
    run_smoke()
