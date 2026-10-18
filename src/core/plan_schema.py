from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict

@dataclass
class Metric:
    agg: str
    col: str
    as_: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Metric":
        return cls(
            agg=d.get("agg", "").lower(),
            col=d.get("col", ""),
            as_=d.get("as") or d.get("as_")
        )

    def to_dict(self) -> Dict[str, Any]:
        res = {"agg": self.agg, "col": self.col}
        if self.as_:
            res["as"] = self.as_
        return res

@dataclass
class Dimension:
    col: str
    fn: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Dimension":
        fn_val = d.get("fn")
        return cls(
            col=d.get("col", ""),
            fn=fn_val.lower() if fn_val else None
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"col": self.col, "fn": self.fn}

@dataclass
class Filter:
    col: str
    op: str
    val: Any

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Filter":
        return cls(
            col=d.get("col", ""),
            op=d.get("op", "").lower(),
            val=d.get("val")
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"col": self.col, "op": self.op, "val": self.val}

@dataclass
class OrderBy:
    key: str
    dir: str = "asc"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OrderBy":
        return cls(
            key=d.get("key", ""),
            dir=d.get("dir", "asc").lower()
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "dir": self.dir}

@dataclass
class Plan:
    intent: str  # "query", "clarify", "unsupported"
    tables: List[str] = field(default_factory=list)
    metrics: List[Metric] = field(default_factory=list)
    dims: List[Dimension] = field(default_factory=list)
    filters: List[Filter] = field(default_factory=list)
    order_by: List[OrderBy] = field(default_factory=list)
    limit: Optional[int] = None
    message: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Plan":
        return cls(
            intent=d.get("intent", "query").lower(),
            tables=[t.upper() for t in d.get("tables", [])],
            metrics=[Metric.from_dict(m) for m in d.get("metrics", [])],
            dims=[Dimension.from_dict(dim) for dim in d.get("dims", [])],
            filters=[Filter.from_dict(f) for f in d.get("filters", [])],
            order_by=[OrderBy.from_dict(o) for o in d.get("order_by", [])],
            limit=d.get("limit"),
            message=d.get("message")
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "tables": self.tables,
            "metrics": [m.to_dict() for m in self.metrics],
            "dims": [d.to_dict() for d in self.dims],
            "filters": [f.to_dict() for f in self.filters],
            "order_by": [o.to_dict() for o in self.order_by],
            "limit": self.limit,
            "message": self.message
        }

PLAN_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["query", "clarify", "unsupported"]
        },
        "tables": {
            "type": "array",
            "items": {"type": "string"}
        },
        "metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agg": {"type": "string", "enum": ["count", "sum", "avg", "min", "max"]},
                    "col": {"type": "string"},
                    "as": {"type": "string"}
                },
                "required": ["agg", "col"]
            }
        },
        "dims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "col": {"type": "string"},
                    "fn": {"type": ["string", "null"], "enum": ["year", "month", None]}
                },
                "required": ["col"]
            }
        },
        "filters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "col": {"type": "string"},
                    "op": {"type": "string", "enum": ["=", "!=", ">", ">=", "<", "<=", "between", "in", "like"]},
                    "val": {}
                },
                "required": ["col", "op", "val"]
            }
        },
        "order_by": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "dir": {"type": "string", "enum": ["asc", "desc"]}
                },
                "required": ["key"]
            }
        },
        "limit": {"type": ["integer", "null"]},
        "message": {"type": ["string", "null"]}
    },
    "required": ["intent", "tables", "metrics", "dims", "filters", "order_by"]
}
