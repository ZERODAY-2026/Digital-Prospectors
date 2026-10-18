import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Dict, Any, Optional, Set, Tuple
from src.core.plan_schema import Plan

@dataclass
class GuardResult:
    passed: bool
    is_blocked: bool
    explanation: str
    unmatched_claims: List[str] = field(default_factory=list)
    guard_report: Dict[str, Any] = field(default_factory=dict)

def extract_numbers(text: str) -> List[Tuple[str, float]]:
    """Extract numeric raw tokens and their float equivalents from text."""
    # Remove currency signs and percent
    cleaned = re.sub(r"[\$,€£%]", "", text)
    matches = re.finditer(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", cleaned)
    results = []
    for m in matches:
        raw_str = m.group(0)
        try:
            val = float(raw_str.replace(",", ""))
            results.append((raw_str, val))
        except ValueError:
            pass
    return results

def extract_dates(text: str) -> List[str]:
    """Extract standard ISO or YYYY-MM-DD dates from text."""
    return re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)

def collect_row_values(rows: List[Dict[str, Any]], row_count: int) -> Tuple[Set[float], Set[str]]:
    """Extract all valid numbers and string values from result rows."""
    valid_numbers: Set[float] = {float(row_count), 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0, 50.0, 100.0}
    valid_strings: Set[str] = set()

    for row in rows:
        for val in row.values():
            if isinstance(val, (int, float)):
                valid_numbers.add(float(val))
            elif isinstance(val, (datetime, date)):
                valid_strings.add(val.isoformat().lower())
                valid_numbers.add(float(val.year))
                valid_numbers.add(float(val.month))
                valid_numbers.add(float(val.day))
            elif isinstance(val, str):
                valid_strings.add(val.strip().lower())
                # also extract numbers in strings
                for _, num in extract_numbers(val):
                    valid_numbers.add(num)

    return valid_numbers, valid_strings

def render_blocked_block(
    unmatched_claim: str,
    sql: str,
    params: Dict[str, Any],
    rows: List[Dict[str, Any]]
) -> str:
    """Render the exact code-generated blocked block for strict mode."""
    # Format query with params
    if params:
        query_display = f"{sql}\nBound params: {params}"
    else:
        query_display = sql or "None"

    # Format actual result
    if not rows:
        result_display = "empty"
    else:
        result_display = str(rows[:5]) if len(rows) > 5 else str(rows)

    block = (
        "[HALLUCINATION DETECTED - OUTPUT BLOCKED]\n"
        f"- What I tried to claim: {unmatched_claim}\n"
        "- Why it's hallucination: Value not found in Snowflake result\n"
        f"- Executed Query: {query_display}\n"
        f"- Actual Result: {result_display}\n"
        '- Action Required From User: "Please rephrase your question to be more specific, e.g. specify date range, department, or metric name as per available schema."'
    )
    return block

def check_hallucination(
    explanation: str,
    rows: List[Dict[str, Any]],
    plan: Optional[Plan] = None,
    sql: str = "",
    params: Optional[Dict[str, Any]] = None,
    strict_mode: bool = False,
    template_fallback_fn = None
) -> GuardResult:
    """
    Validate that all numeric and factual claims in explanation exist in rows.
    If check fails:
      - strict_mode=False: discard model text, return template fallback explanation.
      - strict_mode=True: block output completely with standardized block.
    """
    if params is None:
        params = {}

    row_count = len(rows)
    valid_numbers, valid_strings = collect_row_values(rows, row_count)
    unmatched_claims: List[str] = []

    # 1. Number verification
    text_numbers = extract_numbers(explanation)
    for raw_token, num_val in text_numbers:
        # Check against valid numbers with small epsilon for float precision
        matched = False
        for vn in valid_numbers:
            if abs(num_val - vn) < 0.01:
                matched = True
                break
            # Also allow rounding to integer if num_val is rounded
            if abs(round(vn) - num_val) < 0.01:
                matched = True
                break
        if not matched:
            unmatched_claims.append(f"Number '{raw_token}'")

    # 2. Date verification
    text_dates = extract_dates(explanation)
    for dt in text_dates:
        if dt.lower() not in valid_strings:
            unmatched_claims.append(f"Date '{dt}'")

    # If rows are empty but explanation claims any specific data/numbers
    if row_count == 0 and text_numbers:
        for raw_token, num_val in text_numbers:
            if num_val != 0.0 and f"Number '{raw_token}'" not in unmatched_claims:
                unmatched_claims.append(f"Number '{raw_token}' on empty result")

    # Check outcome
    if not unmatched_claims:
        return GuardResult(
            passed=True,
            is_blocked=False,
            explanation=explanation,
            unmatched_claims=[],
            guard_report={"status": "passed"}
        )

    # Hallucination detected!
    first_unmatched = unmatched_claims[0]

    if strict_mode:
        blocked_block = render_blocked_block(first_unmatched, sql, params, rows)
        return GuardResult(
            passed=False,
            is_blocked=True,
            explanation=blocked_block,
            unmatched_claims=unmatched_claims,
            guard_report={
                "status": "hallucination_blocked",
                "unmatched_claims": unmatched_claims,
                "original_explanation": explanation,
                "strict_mode": True
            }
        )
    else:
        # Fallback to deterministic template
        if template_fallback_fn:
            fallback_text = template_fallback_fn()
        else:
            if row_count == 0:
                fallback_text = "No matching data was found for the query."
            else:
                fallback_text = f"The query returned {row_count} record(s) matching your criteria."

        return GuardResult(
            passed=False,
            is_blocked=False,
            explanation=fallback_text,
            unmatched_claims=unmatched_claims,
            guard_report={
                "status": "hallucination_detected_fallback",
                "unmatched_claims": unmatched_claims,
                "original_explanation": explanation,
                "strict_mode": False
            }
        )
