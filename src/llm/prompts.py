import json
from typing import List, Dict, Any

PLANNER_SYSTEM_PROMPT_TEMPLATE = """You convert a business question into a JSON query plan. Output JSON only. Use only the tables and columns listed below. Never write SQL. intent is 'query' if the data can answer it, 'clarify' if a term such as 'best' or 'top' has no measure, 'unsupported' if the data lacks it or the request is not a business data question. If intent is not 'query', put a one-sentence reason in 'message'.
SCHEMA:
{schema}

EXAMPLES:
{examples}

User Question: {question}
Plan:"""

EXPLAINER_SYSTEM_PROMPT_TEMPLATE = """Explain the query result in 2-3 plain sentences for a business user. Use only the numbers and names in RESULT ROWS. Do not calculate, estimate or add outside facts. If there are no rows, say no matching data was found. Mention the main filter or grouping.
QUESTION: {question}
PLAN: {plan_summary}
RESULT ROWS: {rows}

Explanation:"""

FEW_SHOT_EXAMPLES: List[Dict[str, Any]] = [
    {
        "question": "How many orders are there?",
        "plan": {
            "intent": "query",
            "tables": ["ORDERS"],
            "metrics": [{"agg": "count", "col": "O_ORDERKEY", "as": "order_count"}],
            "dims": [],
            "filters": [],
            "order_by": [],
            "limit": 100,
            "message": None
        }
    },
    {
        "question": "Which market segment has the most customers?",
        "plan": {
            "intent": "query",
            "tables": ["CUSTOMER"],
            "metrics": [{"agg": "count", "col": "C_CUSTKEY", "as": "customer_count"}],
            "dims": [{"col": "C_MKTSEGMENT", "fn": None}],
            "filters": [],
            "order_by": [{"key": "customer_count", "dir": "desc"}],
            "limit": 100,
            "message": None
        }
    },
    {
        "question": "Total sales by region",
        "plan": {
            "intent": "query",
            "tables": ["ORDERS", "CUSTOMER", "NATION", "REGION"],
            "metrics": [{"agg": "sum", "col": "O_TOTALPRICE", "as": "total_sales"}],
            "dims": [{"col": "R_NAME", "fn": None}],
            "filters": [],
            "order_by": [{"key": "total_sales", "dir": "desc"}],
            "limit": 100,
            "message": None
        }
    },
    {
        "question": "Show the best region",
        "plan": {
            "intent": "clarify",
            "tables": [],
            "metrics": [],
            "dims": [],
            "filters": [],
            "order_by": [],
            "limit": None,
            "message": "Please clarify what metric defines 'best' (e.g., total sales revenue or order volume)."
        }
    },
    {
        "question": "Help me with my chemistry homework",
        "plan": {
            "intent": "unsupported",
            "tables": [],
            "metrics": [],
            "dims": [],
            "filters": [],
            "order_by": [],
            "limit": None,
            "message": "This business agent only handles organizational data queries."
        }
    }
]

def format_few_shot_examples() -> str:
    """Format few-shot examples for the planner prompt."""
    res = []
    for ex in FEW_SHOT_EXAMPLES:
        res.append(f"User: {ex['question']}\nPlan: {json.dumps(ex['plan'])}")
    return "\n\n".join(res)
