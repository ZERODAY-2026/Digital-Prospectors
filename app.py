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
    page_title="DataMind | AI Analytical Assistant",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom sleek styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
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
        margin: 1.2rem 0;
    }
    .metric-value {
        font-size: 1.8rem;
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
    .badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-ok { background-color: #DEF7EC; color: #03543F; }
    .badge-warn { background-color: #FEF08A; color: #713F12; }
    .badge-err { background-color: #FDE8E8; color: #9B1C1C; }
    .badge-info { background-color: #E1EFFE; color: #1E429F; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_pipeline() -> DataMindPipeline:
    app_cfg = load_app_config()
    dataset_cfg = load_dataset_config(app_cfg.dataset_config_path)
    return DataMindPipeline(app_cfg=app_cfg, dataset_cfg=dataset_cfg)

def render_sidebar():
    st.sidebar.title("🧠 DataMind Engine")
    st.sidebar.markdown("**Team Digital Prospectors**")
    st.sidebar.markdown("---")
    
    st.sidebar.subheader("System Architecture")
    st.sidebar.info("""
    - **LLM**: Local Gemma 3n (2B) via Ollama
    - **Database**: Snowflake (Read-Only App Role)
    - **Dataset**: TPC-H Benchmark (5 Tables)
    - **Security**: Strict YAML Schema Allowlist & Parameterized SQL
    """)

    st.sidebar.subheader("Example Questions")
    examples = [
        "How many orders are there?",
        "Which market segment has the most customers?",
        "Total sales by region",
        "Show the best region",
        "Predict next year's sales",
        "How many orders were placed by customers in a nation that does not exist, like Atlantis?",
        "What is the average account balance of customers by market segment?",
        "Top 5 highest total price orders"
    ]

    selected_example = None
    for ex in examples:
        if st.sidebar.button(ex, key=f"ex_{ex}", use_container_width=True):
            selected_example = ex

    return selected_example

def render_answer_card(res: PipelineResult):
    if not res.result or not res.result.rows:
        return

    # Extract primary numeric highlights from ResultObject directly (Zero Hallucination)
    first_row = res.result.rows[0]
    cols = res.result.columns

    st.markdown('<div class="answer-card">', unsafe_allow_html=True)
    
    # If single aggregate metric
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
            st.metric("Total Rows Returned", res.result.row_count)
        if metric_cols and dim_cols:
            top_dim = first_row.get(dim_cols[0], "N/A")
            top_metric = first_row.get(metric_cols[0], "N/A")
            formatted_top_m = f"{top_metric:,.2f}" if isinstance(top_metric, float) else f"{top_metric:,}" if isinstance(top_metric, int) else str(top_metric)
            with c2:
                st.metric(f"Top {dim_cols[0]}", str(top_dim))
            with c3:
                st.metric(f"Top {metric_cols[0]}", formatted_top_m)
                
    st.markdown("</div>", unsafe_allow_html=True)

def render_details(res: PipelineResult):
    # Short Explanation
    if res.explanation:
        st.markdown("### Explanation")
        st.write(res.explanation)

    # Expander 1: Executed SQL
    if res.result and res.result.sql:
        with st.expander("Executed SQL", expanded=True):
            st.code(res.result.sql, language="sql")
            if res.result.params:
                st.markdown("**Bound Parameters:**")
                st.json(res.result.params)

    # Expander 2: Result rows
    if res.result and res.result.rows:
        with st.expander(f"Result Rows ({res.result.row_count} records)", expanded=True):
            if res.result.row_count >= 100:
                st.caption("ℹ️ Showing results capped by safety limit.")
            df = pd.DataFrame(res.result.rows)
            st.dataframe(df, use_container_width=True)

    # Expander 3: Plan, filters and assumptions
    if res.plan:
        with st.expander("Plan, filters and assumptions", expanded=False):
            st.markdown(f"**Intent:** `{res.plan.intent}`")
            if res.plan.tables:
                st.markdown(f"**Tables:** {', '.join(res.plan.tables)}")
            if res.plan.metrics:
                m_str = ", ".join([f"{m.agg.upper()}({m.col}) AS {m.as_}" for m in res.plan.metrics])
                st.markdown(f"**Metrics:** {m_str}")
            if res.plan.dims:
                d_str = ", ".join([f"{d.col} (fn: {d.fn})" if d.fn else d.col for d in res.plan.dims])
                st.markdown(f"**Dimensions:** {d_str}")
            if res.plan.filters:
                f_str = ", ".join([f"{f.col} {f.op} {f.val}" for f in res.plan.filters])
                st.markdown(f"**Filters:** {f_str}")
            if res.evidence and res.evidence.assumptions:
                st.markdown("**Assumptions & Safeguards:**")
                for ass in res.evidence.assumptions:
                    st.markdown(f"- {ass}")

    # Expander 4: Evidence
    if res.evidence:
        with st.expander("Evidence & Provenance", expanded=False):
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Snowflake Query ID:** `{res.evidence.query_id or 'N/A'}`")
                st.markdown(f"**Row Count:** `{res.evidence.row_count}`")
                st.markdown(f"**Execution Latency:** `{res.evidence.elapsed_ms:.1f} ms`")
            with col_b:
                st.markdown(f"**Model Name:** `{res.evidence.model_name}`")
                st.markdown(f"**Timestamp (UTC):** `{res.evidence.timestamp}`")

def main():
    selected_example = render_sidebar()

    st.markdown('<div class="main-title">DataMind: Natural Language Data Assistant</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Zero-hallucination natural language to verified SQL powered by local Gemma & Snowflake.</div>', unsafe_allow_html=True)

    # State management for query box
    if "current_question" not in st.session_state:
        st.session_state["current_question"] = ""

    if selected_example:
        st.session_state["current_question"] = selected_example

    with st.form("query_form"):
        question_input = st.text_input(
            "Ask a question about the dataset:",
            value=st.session_state["current_question"],
            placeholder="e.g. Which market segment has the most customers?",
            key="user_query_input"
        )
        submit_clicked = st.form_submit_button("Analyze Data", use_container_width=True)

    if submit_clicked and question_input.strip():
        pipeline = get_pipeline()
        with st.spinner("Analyzing schema, planning query with Gemma, and executing securely on Snowflake..."):
            res: PipelineResult = pipeline.run(question_input.strip())

        if res.status == "ok":
            st.success("Query executed successfully.")
            render_answer_card(res)
            render_details(res)

        elif res.status == "empty":
            st.info("ℹ️ No matching records found.")
            st.markdown(f"> {res.explanation}")
            render_details(res)

        elif res.status == "clarify":
            st.warning("⚠️ Clarification Needed")
            st.markdown(f"**Gemma asks:** {res.explanation}")
            if res.plan:
                with st.expander("Plan Details"):
                    st.json(res.plan.to_dict())

        elif res.status == "unsupported":
            st.warning("🚫 Scope Limitation")
            st.markdown(f"**DataMind Policy:** {res.explanation}")
            if res.plan:
                with st.expander("Plan Details"):
                    st.json(res.plan.to_dict())

        elif res.status == "validation_error":
            st.error("🛡️ Security & Allowlist Validation Error")
            st.markdown(f"**Validator rejection:** {res.explanation}")
            if res.plan:
                with st.expander("Attempted Plan"):
                    st.json(res.plan.to_dict())

        elif res.status == "db_error":
            st.error("🔌 Snowflake Execution Error")
            st.markdown(f"**Database returned error:** {res.explanation}")
            render_details(res)

        elif res.status == "llm_error":
            st.error("🤖 Local LLM Communication Error")
            st.markdown(f"**Ollama error:** {res.explanation}")

if __name__ == "__main__":
    main()
