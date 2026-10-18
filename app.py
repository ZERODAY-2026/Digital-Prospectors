import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import streamlit as st
import pandas as pd
from src.core.pipeline import DataMindPipeline, PipelineResult
from src.config import load_app_config, load_dataset_config

st.set_page_config(
    page_title="DataMind-Business | Enterprise Data Assistant",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom sleek styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.1rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .answer-card {
        background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%);
        border-left: 5px solid #0284C7;
        padding: 1.2rem 1.5rem;
        border-radius: 8px;
        margin: 1.0rem 0 1.5rem 0;
    }
    .metric-value {
        font-size: 2.0rem;
        font-weight: 700;
        color: #0369A1;
    }
    .metric-label {
        font-size: 0.9rem;
        text-transform: uppercase;
        color: #64748B;
        font-weight: 600;
        letter-spacing: 0.05em;
    }
    .section-header {
        font-size: 1.25rem;
        font-weight: 700;
        color: #1F2937;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        padding-bottom: 0.3rem;
        border-bottom: 2px solid #E5E7EB;
    }
    .evidence-box {
        background-color: #F9FAFB;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 1.2rem;
        margin-bottom: 1.5rem;
    }
    .placeholder-box {
        background-color: #F3F4F6;
        border: 1px dashed #9CA3AF;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 1.2rem;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_pipeline() -> DataMindPipeline:
    app_cfg = load_app_config()
    dataset_cfg = load_dataset_config(app_cfg.dataset_config_path)
    return DataMindPipeline(app_cfg=app_cfg, dataset_cfg=dataset_cfg)

def render_sidebar():
    st.sidebar.title("💼 DataMind-Business")
    st.sidebar.markdown("**Team Digital Prospectors**")
    st.sidebar.markdown("---")

    st.sidebar.subheader("System Architecture")
    st.sidebar.info("""
    - **Scope**: Organizational Data Only
    - **LLM**: Local Gemma 3n (2B) via Ollama
    - **Database**: Snowflake (Read-Only App Role)
    - **Dataset**: TPC-H Benchmark (5 Tables)
    - **Verification**: Zero-Hallucination Guard
    """)

    st.sidebar.subheader("Example Questions")
    examples = [
        "How many orders are there?",
        "Which market segment has the most customers?",
        "Total sales by region",
        "Show the best region",
        "Help me with my chemistry homework",
        "What are the employee salaries in the sales department?",
        "How many orders were placed by customers in a nation that does not exist, like Atlantis?",
        "What is the average account balance of customers by market segment?"
    ]

    selected_example = None
    for ex in examples:
        if st.sidebar.button(ex, key=f"ex_{ex}", use_container_width=True):
            selected_example = ex

    return selected_example

def render_layer_a_direct_answer(res: PipelineResult):
    """Layer A: Direct Answer (1-2 plain-language sentences, numbers from ResultObject)."""
    st.markdown('<div class="section-header">Layer A: Direct Answer</div>', unsafe_allow_html=True)

    if res.result and res.result.rows:
        first_row = res.result.rows[0]
        cols = res.result.columns

        st.markdown('<div class="answer-card">', unsafe_allow_html=True)
        # Primary numeric highlight directly from ResultObject
        if len(cols) == 1 and res.result.row_count == 1:
            col_name = cols[0]
            val = first_row[col_name]
            formatted_val = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}" if isinstance(val, int) else str(val)
            st.markdown(f'<div class="metric-label">{col_name.replace("_", " ")}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="metric-value">{formatted_val}</div>', unsafe_allow_html=True)
        elif len(cols) >= 2 and res.result.row_count > 0:
            metric_cols = [c for c in cols if any(m in c.lower() for m in ["count", "sum", "avg", "total", "sales", "price", "bal"])]
            dim_cols = [c for c in cols if c not in metric_cols]
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Total Records", res.result.row_count)
            if metric_cols and dim_cols:
                top_dim = first_row.get(dim_cols[0], "N/A")
                top_metric = first_row.get(metric_cols[0], "N/A")
                formatted_top_m = f"{top_metric:,.2f}" if isinstance(top_metric, float) else f"{top_metric:,}" if isinstance(top_metric, int) else str(top_metric)
                with c2:
                    st.metric(f"Top {dim_cols[0]}", str(top_dim))
                with c3:
                    st.metric(f"Top {metric_cols[0]}", formatted_top_m)
        st.markdown('</div>', unsafe_allow_html=True)

    if res.explanation:
        st.markdown(f"**Answer:** {res.explanation}")

def render_layer_b_evidence_block(res: PipelineResult):
    """Layer B: Evidence Block (always visible, not collapsed)."""
    st.markdown('<div class="section-header">Layer B: Evidence Block (Audit Provenance)</div>', unsafe_allow_html=True)

    ev = res.evidence
    st.markdown('<div class="evidence-box">', unsafe_allow_html=True)

    # 1. Executed SQL & Bound Parameters
    st.markdown("#### 1. Executed SQL Query")
    if res.result and res.result.sql:
        st.code(res.result.sql, language="sql")
    elif ev and ev.sql:
        st.code(ev.sql, language="sql")
    else:
        st.code("N/A (Query was not executed on database)", language="text")

    st.markdown("#### 2. Bound Query Parameters")
    params = res.result.params if (res.result and res.result.params) else (ev.params if ev else {})
    if params:
        st.json(params)
    else:
        st.caption("No dynamic parameters bound.")

    # 3. Execution Metadata (Query ID, Rows, Latency, Timestamp, Model)
    st.markdown("#### 3. Execution & System Provenance")
    c1, c2, c3 = st.columns(3)
    with c1:
        qid = res.result.query_id if (res.result and res.result.query_id) else (ev.query_id if ev else "N/A")
        st.markdown(f"**Snowflake Query ID:** `{qid}`")
        rc = res.result.row_count if res.result else (ev.row_count if ev else 0)
        st.markdown(f"**Row Count:** `{rc}`")
    with c2:
        model = ev.model_name if ev else "gemma3n:e2b"
        st.markdown(f"**LLM Model:** `{model}`")
        latency = res.result.elapsed_ms if res.result else (ev.elapsed_ms if ev else 0.0)
        st.markdown(f"**Execution Latency:** `{latency:.1f} ms`")
    with c3:
        ts = ev.timestamp if ev else "N/A"
        st.markdown(f"**Timestamp (UTC):** `{ts}`")

    # 4. Tables, Filters, and Assumptions
    st.markdown("#### 4. Scope, Tables & Safeguard Assumptions")
    tables = ev.tables if (ev and ev.tables) else (res.plan.tables if res.plan else [])
    st.markdown(f"- **Tables Used:** {', '.join(tables) if tables else 'None'}")
    
    filters = ev.filters if (ev and ev.filters) else (res.plan.filters if res.plan else [])
    if filters:
        f_strs = [f"{f['col']} {f['op']} {f['val']}" if isinstance(f, dict) else f"{f.col} {f.op} {f.val}" for f in filters]
        st.markdown(f"- **Filters Applied:** {', '.join(f_strs)}")
    else:
        st.markdown("- **Filters Applied:** None")

    if ev and ev.assumptions:
        for ass in ev.assumptions:
            st.markdown(f"- **Assumption/Constraint:** {ass}")

    if ev and ev.guard:
        st.markdown(f"- **Hallucination Guard Status:** `{ev.guard.get('status', 'passed')}`")
        if ev.guard.get("unmatched_claims"):
            st.markdown(f"- **Guard Filtered Claims:** {ev.guard.get('unmatched_claims')}")

    # 5. Result Rows (Preview with truncation note)
    st.markdown("#### 5. Result Rows")
    rows = res.result.rows if (res.result and res.result.rows) else (ev.result_rows if ev else [])
    if rows:
        preview_limit = 100
        preview_rows = rows[:preview_limit]
        if len(rows) > preview_limit:
            st.caption(f"ℹ️ Previewing first {preview_limit} rows of {len(rows)} records (truncated for display).")
        else:
            st.caption(f"Showing all {len(rows)} record(s).")
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)
    else:
        st.caption("No tabular rows returned.")

    st.markdown('</div>', unsafe_allow_html=True)

def render_layer_c_placeholder():
    """Layer C: TODO(team) placeholder section."""
    st.markdown('<div class="section-header">Layer C: [TODO(team) - Specification Pending]</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="placeholder-box">
        <strong>TODO(team):</strong> Layer C was cut off in the project specification. 
        Reserved placeholder for future analytical breakdown, variance analysis, or secondary metrics.
    </div>
    """, unsafe_allow_html=True)

def render_layer_d_placeholder():
    """Layer D: TODO(team) placeholder section."""
    st.markdown('<div class="section-header">Layer D: [TODO(team) - Specification Pending]</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="placeholder-box">
        <strong>TODO(team):</strong> Layer D was cut off in the project specification. 
        Reserved placeholder for future enterprise export (CSV/Excel), lineage graphing, or webhook integration.
    </div>
    """, unsafe_allow_html=True)

def main():
    selected_example = render_sidebar()

    st.markdown('<div class="main-title">DataMind-Business: Natural Language Data Assistant</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Zero-hallucination enterprise data intelligence powered by Google Gemma 3n & Snowflake.</div>', unsafe_allow_html=True)

    if "current_question" not in st.session_state:
        st.session_state["current_question"] = ""

    if selected_example:
        st.session_state["current_question"] = selected_example

    with st.form("query_form"):
        question_input = st.text_input(
            "Ask a business question about sales, orders, customers, or logistics:",
            value=st.session_state["current_question"],
            placeholder="e.g. Which market segment has the most customers?",
            key="user_query_input"
        )
        submit_clicked = st.form_submit_button("Analyze Data", use_container_width=True)

    if submit_clicked and question_input.strip():
        pipeline = get_pipeline()
        with st.spinner("Analyzing business question, planning with Gemma, and querying Snowflake..."):
            res: PipelineResult = pipeline.run(question_input.strip())

        # Check outcome status
        if res.status == "ok":
            st.success("Query analyzed and verified successfully.")
            render_layer_a_direct_answer(res)
            render_layer_b_evidence_block(res)
            render_layer_c_placeholder()
            render_layer_d_placeholder()

        elif res.status == "hallucination_blocked":
            st.error("🛡️ Hallucination Guard: Output Blocked")
            st.code(res.explanation, language="text")
            # In strict mode, do NOT show Layer A. Still show Layer B Evidence.
            render_layer_b_evidence_block(res)
            render_layer_c_placeholder()
            render_layer_d_placeholder()

        elif res.status == "clarify":
            st.warning("⚠️ Clarification Needed")
            st.markdown(f"**Gemma asks:** {res.explanation}")
            render_layer_b_evidence_block(res)
            render_layer_c_placeholder()
            render_layer_d_placeholder()

        elif res.status == "unsupported":
            st.warning("🚫 Scope Limitation")
            st.markdown(f"**DataMind Policy:** {res.explanation}")
            render_layer_b_evidence_block(res)
            render_layer_c_placeholder()
            render_layer_d_placeholder()

        elif res.status == "empty":
            st.info("ℹ️ No matching records found.")
            st.markdown(f"> {res.explanation}")
            render_layer_b_evidence_block(res)
            render_layer_c_placeholder()
            render_layer_d_placeholder()

        elif res.status == "validation_error":
            st.error("🛡️ Schema & Security Validation Error")
            st.markdown(f"**Validator rejection:** {res.explanation}")
            render_layer_b_evidence_block(res)
            render_layer_c_placeholder()
            render_layer_d_placeholder()

        elif res.status == "db_error":
            st.error("🔌 Snowflake Database Execution Error")
            st.markdown(f"**Error:** {res.explanation}")
            render_layer_b_evidence_block(res)
            render_layer_c_placeholder()
            render_layer_d_placeholder()

        elif res.status == "llm_error":
            st.error("🤖 Local LLM Communication Error")
            st.markdown(f"**Error:** {res.explanation}")

if __name__ == "__main__":
    main()
