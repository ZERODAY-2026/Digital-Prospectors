from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from src.core.plan_schema import Plan
from src.db.snowflake_client import ResultObject

@dataclass
class EvidenceBundle:
    sql: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    query_id: Optional[str] = None
    row_count: int = 0
    result_rows: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_name: str = "gemma3n:e2b"
    filters: List[Dict[str, Any]] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    guard: Optional[Dict[str, Any]] = None

    # TODO(team): layer C was cut off in our spec. Create a clearly marked placeholder section in the UI and a TODO comment in evidence.py. Do not invent its content.
    layer_c: Optional[Dict[str, Any]] = None

    # TODO(team): layer D was cut off in our spec. Create a clearly marked placeholder section in the UI and a TODO comment in evidence.py. Do not invent its content.
    layer_d: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sql": self.sql,
            "params": self.params,
            "query_id": self.query_id,
            "row_count": self.row_count,
            "result_rows": self.result_rows,
            "tables": self.tables,
            "timestamp": self.timestamp,
            "model_name": self.model_name,
            "filters": self.filters,
            "assumptions": self.assumptions,
            "elapsed_ms": self.elapsed_ms,
            "guard": self.guard,
            "layer_c": self.layer_c,
            "layer_d": self.layer_d
        }

def build_evidence(
    plan: Optional[Plan],
    result: Optional[ResultObject],
    model_name: str = "gemma3n:e2b",
    assumptions: Optional[List[str]] = None,
    guard: Optional[Dict[str, Any]] = None
) -> EvidenceBundle:
    """Build a verifiable EvidenceBundle capturing provenance, execution id, parameters, tables, rows and assumptions."""
    if assumptions is None:
        assumptions = []

    filters = []
    tables = []
    if plan:
        if plan.filters:
            filters = [f.to_dict() for f in plan.filters]
        if plan.tables:
            tables = list(plan.tables)

    # Collect assumptions
    active_assumptions = list(assumptions)
    if plan:
        if plan.limit:
            active_assumptions.append(f"Result capped at {plan.limit} rows (default/requested limit).")
        if plan.order_by:
            dirs = [f"{o.key} {o.dir}" for o in plan.order_by]
            active_assumptions.append(f"Ordered by: {', '.join(dirs)}.")

    return EvidenceBundle(
        sql=result.sql if result else (plan.intent if plan and plan.intent != "query" else None),
        params=result.params if result else {},
        query_id=result.query_id if result else None,
        row_count=result.row_count if result else 0,
        result_rows=result.rows if result else [],
        tables=tables,
        timestamp=datetime.now(timezone.utc).isoformat(),
        model_name=model_name,
        filters=filters,
        assumptions=active_assumptions,
        elapsed_ms=result.elapsed_ms if result else 0.0,
        guard=guard
    )
