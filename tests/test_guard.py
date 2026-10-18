import pytest
from src.core.guard import check_hallucination, GuardResult

def test_claim_present_in_rows_passes():
    rows = [{"CNT": 1500000}]
    explanation = "There are 1,500,000 orders recorded in the system."
    res = check_hallucination(
        explanation=explanation,
        rows=rows,
        sql="SELECT COUNT(*) FROM ORDERS",
        strict_mode=False
    )
    assert res.passed is True
    assert res.is_blocked is False
    assert res.explanation == explanation
    assert len(res.unmatched_claims) == 0

def test_invented_number_fails():
    rows = [{"CNT": 100}]
    explanation = "There are 999,999 orders recorded in the system."
    res = check_hallucination(
        explanation=explanation,
        rows=rows,
        sql="SELECT COUNT(*) FROM ORDERS",
        strict_mode=False
    )
    assert res.passed is False
    assert res.is_blocked is False
    assert len(res.unmatched_claims) > 0
    assert "999,999" in res.unmatched_claims[0] or "999999" in res.unmatched_claims[0]
    assert res.guard_report["status"] == "hallucination_detected_fallback"

def test_formatting_variants_pass():
    # Commas, dollar signs, decimals
    rows = [{"TOTAL_SALES": 123456.78}]
    explanation = "The total sales reached $123,456.78 across all customers."
    res = check_hallucination(
        explanation=explanation,
        rows=rows,
        sql="SELECT SUM(O_TOTALPRICE) FROM ORDERS",
        strict_mode=True
    )
    assert res.passed is True
    assert res.is_blocked is False

    # Rounding variant: 123456.78 rounded to 123457
    rounded_exp = "The total sales is approximately 123,457."
    res2 = check_hallucination(
        explanation=rounded_exp,
        rows=rows,
        sql="SELECT SUM(O_TOTALPRICE) FROM ORDERS",
        strict_mode=True
    )
    assert res2.passed is True

def test_empty_rows_with_numeric_claim_fails():
    rows = []
    explanation = "We found 42 orders matching your criteria."
    res = check_hallucination(
        explanation=explanation,
        rows=rows,
        sql="SELECT * FROM ORDERS WHERE 1=0",
        strict_mode=False
    )
    assert res.passed is False
    assert len(res.unmatched_claims) > 0

def test_strict_mode_false_branch():
    rows = [{"CNT": 50}]
    explanation = "There are 888 items in stock."
    res = check_hallucination(
        explanation=explanation,
        rows=rows,
        sql="SELECT COUNT(*) FROM LINEITEM",
        strict_mode=False,
        template_fallback_fn=lambda: "The query returned 50 record(s)."
    )
    assert res.passed is False
    assert res.is_blocked is False
    assert res.explanation == "The query returned 50 record(s)."
    assert res.guard_report["status"] == "hallucination_detected_fallback"
    assert len(res.unmatched_claims) > 0

def test_strict_mode_true_branch():
    rows = [{"CNT": 50}]
    explanation = "There are 888 items in stock."
    sql = "SELECT COUNT(*) FROM LINEITEM"
    params = {"p0": "test"}
    res = check_hallucination(
        explanation=explanation,
        rows=rows,
        sql=sql,
        params=params,
        strict_mode=True
    )
    assert res.passed is False
    assert res.is_blocked is True
    assert "[HALLUCINATION DETECTED - OUTPUT BLOCKED]" in res.explanation
    assert "- What I tried to claim:" in res.explanation
    assert "- Why it's hallucination: Value not found in Snowflake result" in res.explanation
    assert "- Executed Query:" in res.explanation
    assert sql in res.explanation
    assert "- Actual Result:" in res.explanation
    assert "Action Required From User" in res.explanation
    assert 'Please rephrase your question to be more specific' in res.explanation
    assert res.guard_report["status"] == "hallucination_blocked"
