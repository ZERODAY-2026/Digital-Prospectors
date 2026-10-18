import json
import re
from typing import Dict, Any, List, Optional, Set
import ollama
from src.config import OllamaConfig, load_app_config, load_dataset_config
from src.core.plan_schema import Plan, PLAN_JSON_SCHEMA

FEW_SHOT_EXAMPLES = [
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
        "question": "Predict next year's sales",
        "plan": {
            "intent": "unsupported",
            "tables": [],
            "metrics": [],
            "dims": [],
            "filters": [],
            "order_by": [],
            "limit": None,
            "message": "Predictive modeling and future forecasting are not supported by this analytical dataset."
        }
    }
]

def preselect_tables(question: str, dataset_cfg: Dict[str, Any]) -> List[str]:
    """Pre-select candidate tables based on keyword and synonym matches in question."""
    q_lower = question.lower()
    matched_tables: Set[str] = set()

    for tbl_name, tbl_info in dataset_cfg.get("tables", {}).items():
        if tbl_name.lower() in q_lower:
            matched_tables.add(tbl_name)
            continue
        for syn in tbl_info.get("synonyms", []):
            if syn.lower() in q_lower:
                matched_tables.add(tbl_name)
                break
        for col_name, col_info in tbl_info.get("columns", {}).items():
            if col_name.lower() in q_lower:
                matched_tables.add(tbl_name)
                break
            for col_syn in col_info.get("synonyms", []):
                if col_syn.lower() in q_lower:
                    matched_tables.add(tbl_name)
                    break

    # If nothing matched or ambiguous, return all tables
    if not matched_tables:
        return list(dataset_cfg.get("tables", {}).keys())

    return sorted(list(matched_tables))

def build_prompt(question: str, dataset_cfg: Dict[str, Any], candidate_tables: List[str]) -> str:
    """Build a compact schema prompt with few-shot examples for Gemma."""
    schema_lines = []
    for tbl_name in candidate_tables:
        tbl_info = dataset_cfg.get("tables", {}).get(tbl_name, {})
        cols = []
        for cname, cinfo in tbl_info.get("columns", {}).items():
            cols.append(f"{cname} ({cinfo.get('type')}, {cinfo.get('role')}: {cinfo.get('description')})")
        schema_lines.append(f"TABLE {tbl_name}: {', '.join(cols)}")

    schema_text = "\n".join(schema_lines)

    examples_text = ""
    for ex in FEW_SHOT_EXAMPLES:
        examples_text += f"\nUser: {ex['question']}\nPlan: {json.dumps(ex['plan'])}\n"

    prompt = f"""You are DataMind, an AI analytical planner. Given a user question, return ONLY a JSON plan following the JSON schema.
- intent="query": factual data present in dataset.
- intent="clarify": ambiguous terms without explicit measure (e.g. "top", "best").
- intent="unsupported": forecasting, future predictions, or topics outside the dataset.

Available Schema:
{schema_text}

Examples:
{examples_text}

User Question: {question}
Plan:"""
    return prompt

def generate_plan(
    question: str,
    dataset_cfg: Optional[Dict[str, Any]] = None,
    ollama_cfg: Optional[OllamaConfig] = None
) -> Plan:
    """Generate a structured Plan from user question using Gemma via Ollama."""
    if dataset_cfg is None:
        dataset_cfg = load_dataset_config()
    if ollama_cfg is None:
        app_cfg = load_app_config()
        ollama_cfg = app_cfg.ollama

    # Check for direct unsupported concepts early
    q_lower = question.lower()
    unsupported_terms = ["predict", "forecast", "future", "next year's sales", "weather", "crypto", "stock price"]
    if any(t in q_lower for t in unsupported_terms):
        return Plan(
            intent="unsupported",
            message="Predictive forecasting and future modeling are outside the scope of this historical analytical dataset."
        )

    # Check for clarify terms lacking metrics
    clarify_terms = ["best region", "best customer", "top nation", "top customer", "best product"]
    if any(t in q_lower for t in clarify_terms) and not any(m in q_lower for m in ["sales", "revenue", "order", "price", "count", "quantity", "balance"]):
        return Plan(
            intent="clarify",
            message="Please clarify the metric to rank by (e.g., total sales revenue, order volume, or average order value)."
        )

    candidate_tables = preselect_tables(question, dataset_cfg)
    prompt = build_prompt(question, dataset_cfg, candidate_tables)

    client = ollama.Client(host=ollama_cfg.host)

    for attempt in range(2):
        try:
            resp = client.generate(
                model=ollama_cfg.model,
                prompt=prompt if attempt == 0 else prompt + "\nInvalid JSON previously. Return strictly valid JSON object matching the schema:",
                format=PLAN_JSON_SCHEMA,
                options={
                    "temperature": 0,
                    "num_predict": 300,
                },
                keep_alive="30m"
            )

            raw_text = resp.get("response", "").strip()
            # Clean possible markdown wrapping
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

            parsed = json.loads(raw_text)
            return Plan.from_dict(parsed)

        except Exception as e:
            if attempt == 1:
                return Plan(
                    intent="clarify",
                    message=f"Could not generate a structured plan for the query: {str(e)}"
                )

    return Plan(intent="clarify", message="Unable to parse query into a valid analytical plan.")
