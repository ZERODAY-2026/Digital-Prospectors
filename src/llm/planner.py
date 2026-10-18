import json
import re
from typing import Dict, Any, List, Optional, Set
import ollama
from src.config import OllamaConfig, load_app_config, load_dataset_config
from src.core.plan_schema import Plan, PLAN_JSON_SCHEMA
from src.llm.prompts import PLANNER_SYSTEM_PROMPT_TEMPLATE, format_few_shot_examples

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
    """Build a compact schema prompt with few-shot examples for Gemma using prompts template."""
    schema_lines = []
    for tbl_name in candidate_tables:
        tbl_info = dataset_cfg.get("tables", {}).get(tbl_name, {})
        cols = []
        for cname, cinfo in tbl_info.get("columns", {}).items():
            cols.append(f"{cname} ({cinfo.get('type')}, {cinfo.get('role')}: {cinfo.get('description')})")
        schema_lines.append(f"TABLE {tbl_name}: {', '.join(cols)}")

    schema_text = "\n".join(schema_lines)
    examples_text = format_few_shot_examples()

    prompt = PLANNER_SYSTEM_PROMPT_TEMPLATE.format(
        schema=schema_text,
        examples=examples_text,
        question=question
    )
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

    scope_msgs = dataset_cfg.get("scope_messages", {})
    unsupported_msg = scope_msgs.get("unsupported_message", "This business agent only handles organizational data queries.")
    missing_data_msg = scope_msgs.get("missing_data_message", "This dataset contains customer, orders, line item, nation, and region data. It does not contain employee, inventory, payroll, or HR data.")

    q_lower = question.lower()

    # 1. Check for non-business / out-of-scope queries (homework, personal, recipes, weather, crypto, etc.)
    non_business_terms = [
        "homework", "chemistry", "physics", "math", "biology", "poem", "joke", "recipe",
        "weather", "crypto", "bitcoin", "stock price", "sports", "football", "movie",
        "illegal", "hack", "personal", "who are you", "what is your name", "tell me a story"
    ]
    if any(re.search(r"\b" + re.escape(t) + r"\b", q_lower) for t in non_business_terms):
        return Plan(intent="unsupported", message=unsupported_msg)

    # 2. Check for predictive / forecasting questions
    forecast_terms = ["predict", "forecast", "future", "next year's sales", "projection", "estimate for next year"]
    if any(t in q_lower for t in forecast_terms):
        return Plan(intent="unsupported", message="Predictive forecasting and future modeling are outside the scope of this historical analytical dataset.")

    # 3. Check for business-related data missing from the schema (employees, payroll, inventory, HR, etc.)
    missing_data_terms = [
        "employee", "employees", "staff", "worker", "workers", "salary", "salaries", "payroll",
        "hr", "human resources", "inventory", "stock level", "warehouse inventory", "job title"
    ]
    if any(re.search(r"\b" + re.escape(t) + r"\b", q_lower) for t in missing_data_terms):
        return Plan(intent="unsupported", message=missing_data_msg)

    # 4. Check for clarify terms lacking metrics (e.g. "best", "top" with no metric)
    clarify_terms = ["best region", "best customer", "top nation", "top customer", "best product", "best segment"]
    if any(t in q_lower for t in clarify_terms) and not any(m in q_lower for m in ["sales", "revenue", "order", "price", "count", "quantity", "balance", "volume"]):
        return Plan(
            intent="clarify",
            message="Please clarify what metric defines 'best' (e.g., total sales revenue or order volume)."
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
            plan = Plan.from_dict(parsed)
            # If model returned unsupported but no message, use the standard unsupported_msg
            if plan.intent == "unsupported" and not plan.message:
                plan.message = unsupported_msg
            return plan

        except Exception as e:
            if attempt == 1:
                return Plan(
                    intent="clarify",
                    message=f"Could not generate a structured plan for the query: {str(e)}"
                )

    return Plan(intent="clarify", message="Unable to parse query into a valid analytical plan.")
