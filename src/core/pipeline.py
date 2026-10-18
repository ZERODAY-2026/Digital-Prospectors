from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from src.config import load_app_config, load_dataset_config, AppConfig
from src.core.plan_schema import Plan
from src.core.validator import validate_plan, ValidationResult
from src.core.sql_builder import build_sql
from src.core.evidence import EvidenceBundle, build_evidence
from src.db.snowflake_client import SnowflakeClient, ResultObject
from src.llm.planner import generate_plan
from src.llm.explainer import explain_result

@dataclass
class PipelineResult:
    status: str  # "ok", "empty", "clarify", "unsupported", "validation_error", "db_error", "llm_error"
    question: str
    plan: Optional[Plan] = None
    result: Optional[ResultObject] = None
    evidence: Optional[EvidenceBundle] = None
    explanation: str = ""
    message: Optional[str] = None

class DataMindPipeline:
    def __init__(
        self,
        app_cfg: Optional[AppConfig] = None,
        dataset_cfg: Optional[Dict[str, Any]] = None,
        db_client: Optional[SnowflakeClient] = None,
        planner_fn=None,
        explainer_fn=None
    ):
        self.app_cfg = app_cfg or load_app_config()
        self.dataset_cfg = dataset_cfg or load_dataset_config(self.app_cfg.dataset_config_path)
        self.db_client = db_client or SnowflakeClient(self.app_cfg.snowflake)
        self.planner_fn = planner_fn or generate_plan
        self.explainer_fn = explainer_fn or explain_result

    def run(self, question: str) -> PipelineResult:
        """Execute the end-to-end DataMind pipeline for a user question."""
        if not question or not question.strip():
            return PipelineResult(
                status="clarify",
                question=question,
                message="Please ask a question about the sales, orders, or customers dataset.",
                explanation="Please provide a query."
            )

        # 1. Gemma Planner
        try:
            plan = self.planner_fn(
                question=question,
                dataset_cfg=self.dataset_cfg,
                ollama_cfg=self.app_cfg.ollama
            )
        except Exception as e:
            err_msg = str(e)
            if "connection refused" in err_msg.lower() or "11434" in err_msg:
                friendly = "Ollama is not running. Please ensure Ollama service is active on localhost:11434."
            else:
                friendly = f"LLM planning failed: {err_msg}"
            return PipelineResult(
                status="llm_error",
                question=question,
                explanation=friendly,
                message=friendly
            )

        # 2. Check for Clarify or Unsupported intents
        if plan.intent == "clarify":
            msg = plan.message or "The question is ambiguous. Please clarify your request with specific metrics or filters."
            evidence = build_evidence(plan=plan, result=None, model_name=self.app_cfg.ollama.model)
            return PipelineResult(
                status="clarify",
                question=question,
                plan=plan,
                evidence=evidence,
                explanation=msg,
                message=msg
            )

        if plan.intent == "unsupported":
            msg = plan.message or "This request asks for data or forecasting capabilities outside this analytical dataset."
            evidence = build_evidence(plan=plan, result=None, model_name=self.app_cfg.ollama.model)
            return PipelineResult(
                status="unsupported",
                question=question,
                plan=plan,
                evidence=evidence,
                explanation=msg,
                message=msg
            )

        # 3. Plan Validator against allowlist
        val_res: ValidationResult = validate_plan(plan, self.dataset_cfg)
        if not val_res.is_valid:
            err = val_res.error or "Plan rejected by security validator."
            evidence = build_evidence(plan=plan, result=None, model_name=self.app_cfg.ollama.model)
            return PipelineResult(
                status="validation_error",
                question=question,
                plan=plan,
                evidence=evidence,
                explanation=f"Query validation failed: {err}",
                message=err
            )

        validated_plan = val_res.plan

        # 4. SQL Builder
        try:
            sql, params = build_sql(validated_plan, self.dataset_cfg)
        except Exception as e:
            err = f"Failed to construct SQL: {str(e)}"
            evidence = build_evidence(plan=validated_plan, result=None, model_name=self.app_cfg.ollama.model)
            return PipelineResult(
                status="validation_error",
                question=question,
                plan=validated_plan,
                evidence=evidence,
                explanation=err,
                message=err
            )

        # 5. Snowflake DB Client execution
        db_res: ResultObject = self.db_client.execute_query(sql, params)

        if db_res.status == "error":
            evidence = build_evidence(plan=validated_plan, result=db_res, model_name=self.app_cfg.ollama.model)
            return PipelineResult(
                status="db_error",
                question=question,
                plan=validated_plan,
                result=db_res,
                evidence=evidence,
                explanation=f"Database execution error: {db_res.error}",
                message=db_res.error
            )

        # 6. Build Evidence Bundle
        evidence = build_evidence(plan=validated_plan, result=db_res, model_name=self.app_cfg.ollama.model)

        # 7. Check for Empty Result
        if db_res.status == "empty" or db_res.row_count == 0:
            msg = f"The query returned no matching rows in the dataset."
            return PipelineResult(
                status="empty",
                question=question,
                plan=validated_plan,
                result=db_res,
                evidence=evidence,
                explanation=msg,
                message=msg
            )

        # 8. Gemma Explainer
        try:
            explanation = self.explainer_fn(
                question=question,
                plan=validated_plan,
                result=db_res,
                ollama_cfg=self.app_cfg.ollama
            )
        except Exception as e:
            # Fall back cleanly without crashing
            from src.llm.explainer import build_template_explanation
            explanation = build_template_explanation(question, validated_plan, db_res)

        return PipelineResult(
            status="ok",
            question=question,
            plan=validated_plan,
            result=db_res,
            evidence=evidence,
            explanation=explanation,
            message=None
        )
