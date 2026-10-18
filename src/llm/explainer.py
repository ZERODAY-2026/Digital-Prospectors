from typing import List, Dict, Any, Optional, Set
import ollama
from src.config import OllamaConfig, load_app_config
from src.core.plan_schema import Plan
from src.db.snowflake_client import ResultObject
from src.llm.prompts import EXPLAINER_SYSTEM_PROMPT_TEMPLATE

def _extract_numbers_from_text(text: str) -> List[float]:
    from src.core.guard import extract_numbers
    return [num for _, num in extract_numbers(text)]

def _collect_numbers_from_rows(rows: List[Dict[str, Any]], row_count: int) -> Set[float]:
    from src.core.guard import collect_row_values
    valid_nums, _ = collect_row_values(rows, row_count)
    return valid_nums

def build_template_explanation(question: str, plan: Plan, result: ResultObject) -> str:
    """Deterministic fallback explanation that strictly relies on real data without hallucination."""
    if result.status == "empty" or not result.rows:
        return f"No matching data was found for '{question}'."

    row_count = result.row_count
    first_row = result.rows[0]

    # Mention main filter or grouping
    filter_desc = ""
    if plan and plan.filters:
        f_strs = [f"{f.col.split('.')[-1]} {f.op} '{f.val}'" for f in plan.filters]
        filter_desc = f" filtered by {', '.join(f_strs)}"

    grouping_desc = ""
    if plan and plan.dims:
        d_strs = [d.col.split('.')[-1] for d in plan.dims]
        grouping_desc = f" grouped by {', '.join(d_strs)}"

    if len(result.columns) == 1 and row_count == 1:
        col = result.columns[0]
        val = first_row.get(col)
        formatted_val = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}" if isinstance(val, int) else str(val)
        return f"The total {col.lower().replace('_', ' ')} is {formatted_val}{filter_desc}."

    # Multi-column / grouped results
    metric_cols = [c for c in result.columns if any(m in c.lower() for m in ["count", "sum", "avg", "total", "sales", "price", "bal"])]
    dim_cols = [c for c in result.columns if c not in metric_cols]

    if dim_cols and metric_cols:
        dim_val = first_row.get(dim_cols[0])
        metric_val = first_row.get(metric_cols[0])
        formatted_m = f"{metric_val:,.2f}" if isinstance(metric_val, float) else f"{metric_val:,}" if isinstance(metric_val, int) else str(metric_val)
        return f"For {dim_cols[0].replace('_', ' ')} '{dim_val}', the {metric_cols[0].replace('_', ' ')} is {formatted_m}. A total of {row_count} records were retrieved{filter_desc}{grouping_desc}."

    return f"The query returned {row_count} record(s){filter_desc}{grouping_desc}."

def explain_result(
    question: str,
    plan: Plan,
    result: ResultObject,
    ollama_cfg: Optional[OllamaConfig] = None
) -> str:
    """Generate a concise 2-3 sentence explanation for a business user using Gemma via Ollama."""
    if result.status == "empty" or not result.rows:
        return f"No matching data was found for '{question}'."

    if result.status == "error":
        return f"An error occurred while executing the query: {result.error}"

    # Take up to 20 rows for context
    sample_rows = result.rows[:20]

    plan_summary = f"Tables: {', '.join(plan.tables)}"
    if plan.metrics:
        plan_summary += f", Metrics: {', '.join([m.as_ or m.col for m in plan.metrics])}"
    if plan.dims:
        plan_summary += f", Dimensions: {', '.join([d.col for d in plan.dims])}"
    if plan.filters:
        plan_summary += f", Filters: {', '.join([f'{f.col} {f.op} {f.val}' for f in plan.filters])}"

    prompt = EXPLAINER_SYSTEM_PROMPT_TEMPLATE.format(
        question=question,
        plan_summary=plan_summary,
        rows=sample_rows
    )

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
        if not text:
            return build_template_explanation(question, plan, result)
        return text

    except Exception:
        return build_template_explanation(question, plan, result)
