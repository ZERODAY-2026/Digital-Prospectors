import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.core.pipeline import DataMindPipeline, PipelineResult
from src.db.snowflake_client import SnowflakeClient

QUESTIONS = [
    ("How many orders are there?", "count"),
    ("Which market segment has the most customers?", "ranking"),
    ("Total sales by region", "multi-table join"),
    ("Show the best region", "clarify"),
    ("Predict next year's sales", "unsupported"),
    ("How many orders were placed by customers in a nation that does not exist, like Atlantis?", "empty/filter")
]

def run_smoke():
    print("=" * 80)
    print("DATAMIND END-TO-END PIPELINE SMOKE TEST")
    print("=" * 80)

    pipeline = DataMindPipeline()

    for idx, (question, category) in enumerate(QUESTIONS, 1):
        print(f"\n[{idx}] Question: '{question}' (Expected category: {category})")
        print("-" * 60)
        
        res: PipelineResult = pipeline.run(question)
        print(f"Status: {res.status}")
        
        if res.plan:
            print(f"Plan Intent: {res.plan.intent}")
            print(f"Plan Tables: {res.plan.tables}")
            if res.plan.metrics:
                print(f"Metrics: {[m.to_dict() for m in res.plan.metrics]}")
            if res.plan.dims:
                print(f"Dimensions: {[d.to_dict() for d in res.plan.dims]}")
            if res.plan.filters:
                print(f"Filters: {[f.to_dict() for f in res.plan.filters]}")

        if res.result:
            print(f"Executed SQL:\n{res.result.sql}")
            if res.result.params:
                print(f"Parameters: {res.result.params}")
            print(f"Snowflake Query ID (sfqid): {res.result.query_id}")
            print(f"Rows count: {res.result.row_count}")
            print(f"Sample Rows: {res.result.rows[:5]}")
        
        print(f"Explanation: {res.explanation}")
        if res.message:
            print(f"Message: {res.message}")

    # Compare (a) and (b) with direct SQL if database is accessible
    print("\n" + "=" * 80)
    print("GROUND TRUTH VERIFICATION AGAINST SNOWFLAKE")
    print("=" * 80)
    
    db_client = SnowflakeClient()
    
    print("\nComparing (a) 'How many orders are there?':")
    direct_a = db_client.execute_query("SELECT COUNT(*) AS ORDER_COUNT FROM ORDERS")
    if direct_a.status == "ok":
        print(f"Direct SQL Row: {direct_a.rows}")
        print(f"Direct Query ID: {direct_a.query_id}")
    else:
        print(f"Direct SQL execution status: {direct_a.status} ({direct_a.error})")

    print("\nComparing (b) 'Which market segment has the most customers?':")
    direct_b = db_client.execute_query(
        "SELECT C_MKTSEGMENT, COUNT(*) AS CUSTOMER_COUNT FROM CUSTOMER GROUP BY C_MKTSEGMENT ORDER BY CUSTOMER_COUNT DESC LIMIT 1"
    )
    if direct_b.status == "ok":
        print(f"Direct SQL Row: {direct_b.rows}")
        print(f"Direct Query ID: {direct_b.query_id}")
    else:
        print(f"Direct SQL execution status: {direct_b.status} ({direct_b.error})")

if __name__ == "__main__":
    run_smoke()
