import re
from typing import List, Dict, Any, Optional, Set
import ollama
from src.config import OllamaConfig, load_app_config
from src.core.plan_schema import Plan
from src.db.snowflake_client import ResultObject

def _extract_numbers_from_text(text: str) -> List[float]:
    """Extract numeric tokens from natural language text, ignoring formatting."""
    # Find patterns like 12, 1,234, 45.67, 100%
    cleaned = re.sub(r"[\$,€£%]", "", text)
    tokens = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", cleaned)
    numbers = []
    for t in tokens:
        try:
            num = float(t.replace(",", ""))
            numbers.append(num)
        except ValueError:
            pass
    return numbers

def _collect_numbers_from_rows(rows: List[Dict[str, Any]], row_count: int) -> Set[float]:
    """Collect all valid numbers present in the real query result rows."""
    valid_nums: Set[float] = {float(row_count), 0.0, 1.0, 2.0, 3.0}
    for row in rows:
        for val in row.values():
            if isinstance(val, (int, float)):
                valid_nums.add(float(val))
            elif isinstance(val, str):
                for n in _extract_numbers_from_text(val):
                    valid_nums.add(n)
    return valid_nums

def build_template_explanation(question: str, plan: Plan, result: ResultObject) -> str:
    """Deterministic fallback explanation that strictly relies on real data without hallucination."""
    if result.status == "empty" or not result.rows:
        return f"The query for '{question}' returned no matching records in the dataset."

    row_count = result.row_count
    first_row = result.rows[0]

    if len(result.columns) == 1:
        col = result.columns[0]
        val = first_row.get(col)
        return f"The result for '{question}' is {val:,}." if isinstance(val, (int, float)) else f"The result for '{question}' is {val}."

    # Multi-column / grouped results
    metric_cols = [c for c in result.columns if any(m in c.lower() for m in ["count", "sum", "avg", "total", "sales", "price"])]
    dim_cols = [c for c in result.columns if c not in metric_cols]

    if dim_cols and metric_cols:
        dim_val = first_row.get(dim_cols[0])
        metric_val = first_row.get(metric_cols[0])
        return f"Based on the analysis, {dim_cols[0]} '{dim_val}' has the top value of {metric_val}. A total of {row_count} records were retrieved."

    return f"The query returned {row_count} record(s) matching your criteria."

def explain_result(
    question: str,
    plan: Plan,
    result: ResultObject,
    ollama_cfg: Optional[OllamaConfig] = None
) -> str:
    """Generate a concise 2-3 sentence explanation with zero hallucination verification."""
    if result.status == "empty" or not result.rows:
        return f"No matching records found for query: '{question}'."

    if result.status == "error":
        return f"An error occurred while executing the query: {result.error}"

    # Take up to 20 rows for context
    sample_rows = result.rows[:20]

    plan_summary = f"Tables: {', '.join(plan.tables)}"
    if plan.metrics:
        plan_summary += f", Metrics: {', '.join([m.as_ or m.col for m in plan.metrics])}"
    if plan.dims:
        plan_summary += f", Dimensions: {', '.join([d.col for d in plan.dims])}"

    prompt = f"""You are DataMind, an AI data explainer. Write a concise 2 to 3 sentence explanation answering the user question based STRICTLY on the query result rows provided below.
CRITICAL RULE: NEVER invent, hallucinate, or estimate numbers. You may ONLY reference numbers that appear directly in the data rows below.

User Question: {question}
Plan Summary: {plan_summary}
Result Rows (max 20):
{sample_rows}

Explanation:"""

    if ollama_cfg is None:
        app_cfg = load_app_config()
        ollama_cfg = app_cfg.ollama

    try:
        client = ollama.Client(host=ollama_cfg.host)
        resp = client.generate(
            model=ollama_cfg.model,
            prompt=prompt,
            options={
                "temperature": 0,
                "num_predict": 150,
            },
            keep_alive="30m"
        )
        text = resp.get("response", "").strip()

        # Deterministic verification: verify every number in text exists in rows
        text_numbers = _extract_numbers_from_text(text)
        valid_numbers = _collect_numbers_from_rows(sample_rows, result.row_count)

        for num in text_numbers:
            # Check with a small tolerance for float rounding
            if not any(abs(num - vn) < 0.01 for vn in valid_numbers):
                # Hallucination detected! Revert to safe deterministic template
                return build_template_explanation(question, plan, result)

        return text

    except Exception:
        return build_template_explanation(question, plan, result)
