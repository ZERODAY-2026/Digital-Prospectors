from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Set, Tuple
from collections import deque
from src.core.plan_schema import Plan, Metric, Dimension, Filter, OrderBy

@dataclass
class ValidationResult:
    is_valid: bool
    error: Optional[str] = None
    plan: Optional[Plan] = None

ALLOWED_OPS = {"=", "!=", ">", ">=", "<", "<=", "between", "in", "like"}
ALLOWED_FNS = {None, "year", "month"}

def _find_shortest_path(graph: Dict[str, List[str]], start: str, goal: str) -> Optional[List[str]]:
    """Simple BFS shortest path in unweighted undirected graph."""
    if start == goal:
        return [start]
    visited = {start}
    queue = deque([[start]])
    while queue:
        path = queue.popleft()
        node = path[-1]
        for neighbor in graph.get(node, []):
            if neighbor == goal:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])
    return None

def _find_column(col_name: str, tables: List[str], dataset_tables: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """Find table and column info for a column name (either COL or TABLE.COL)."""
    col_name = col_name.strip()
    if "." in col_name:
        parts = col_name.split(".", 1)
        tbl = parts[0].upper()
        col = parts[1].upper()
        if tbl in dataset_tables and col in dataset_tables[tbl].get("columns", {}):
            return tbl, col, dataset_tables[tbl]["columns"][col]
        return None, None, None

    col_upper = col_name.upper()
    # First search in plan's tables
    candidates = []
    for tbl in tables:
        tbl_upper = tbl.upper()
        if tbl_upper in dataset_tables:
            cols = dataset_tables[tbl_upper].get("columns", {})
            if col_upper in cols:
                candidates.append((tbl_upper, col_upper, cols[col_upper]))
    
    if len(candidates) >= 1:
        return candidates[0]

    # Search across all tables in dataset
    for tbl, info in dataset_tables.items():
        cols = info.get("columns", {})
        if col_upper in cols:
            candidates.append((tbl.upper(), col_upper, cols[col_upper]))

    if len(candidates) >= 1:
        return candidates[0]

    return None, None, None

def validate_plan(plan: Plan, dataset_cfg: Dict[str, Any]) -> ValidationResult:
    """Validate a Plan against the YAML dataset schema and security rules."""
    if plan.intent != "query":
        return ValidationResult(
            is_valid=False,
            error=f"Non-query intent '{plan.intent}': {plan.message or 'Request could not be converted to a query.'}"
        )

    dataset_tables = {k.upper(): v for k, v in dataset_cfg.get("tables", {}).items()}
    allowed_aggs_by_type = dataset_cfg.get("allowed_aggregates", {})
    joins = dataset_cfg.get("joins", [])
    default_limit = dataset_cfg.get("default_limit", 100)
    max_limit = dataset_cfg.get("max_limit", 1000)

    # 1. Validate tables
    active_tables: Set[str] = set()
    for tbl in plan.tables:
        t_upper = tbl.upper()
        if t_upper not in dataset_tables:
            return ValidationResult(
                is_valid=False,
                error=f"Unknown table '{tbl}' in query plan. Allowed tables: {list(dataset_tables.keys())}"
            )
        active_tables.add(t_upper)

    # 2. Validate metrics
    validated_metrics: List[Metric] = []
    for m in plan.metrics:
        tbl, col, col_info = _find_column(m.col, list(active_tables), dataset_tables)
        if not col_info:
            return ValidationResult(
                is_valid=False,
                error=f"Unknown column '{m.col}' for metric."
            )
        active_tables.add(tbl)
        
        col_type = col_info.get("type", "string").lower()
        col_role = col_info.get("role", "dimension").lower()
        
        # Check allowed aggregates
        lookup_type = "id" if col_role == "id" else col_type
        allowed = allowed_aggs_by_type.get(lookup_type, allowed_aggs_by_type.get(col_type, ["count"]))
        
        agg = m.agg.lower()
        if agg not in allowed:
            return ValidationResult(
                is_valid=False,
                error=f"Aggregate function '{agg}' is not allowed for column '{tbl}.{col}' of type '{lookup_type}'. Allowed: {allowed}"
            )
        
        alias = m.as_ or f"{agg}_{col.lower()}"
        validated_metrics.append(Metric(agg=agg, col=f"{tbl}.{col}", as_=alias))

    # 3. Validate dimensions
    validated_dims: List[Dimension] = []
    for d in plan.dims:
        tbl, col, col_info = _find_column(d.col, list(active_tables), dataset_tables)
        if not col_info:
            return ValidationResult(
                is_valid=False,
                error=f"Unknown column '{d.col}' for dimension."
            )
        active_tables.add(tbl)

        if d.fn:
            fn = d.fn.lower()
            if fn not in ALLOWED_FNS:
                return ValidationResult(
                    is_valid=False,
                    error=f"Unsupported dimension function '{d.fn}'. Allowed: {list(ALLOWED_FNS)}"
                )
            if col_info.get("type") != "date" and col_info.get("role") != "date":
                return ValidationResult(
                    is_valid=False,
                    error=f"Dimension function '{fn}' can only be applied to date columns, not '{tbl}.{col}'."
                )
        else:
            fn = None
            
        validated_dims.append(Dimension(col=f"{tbl}.{col}", fn=fn))

    # 4. Validate filters
    validated_filters: List[Filter] = []
    for f in plan.filters:
        tbl, col, col_info = _find_column(f.col, list(active_tables), dataset_tables)
        if not col_info:
            return ValidationResult(
                is_valid=False,
                error=f"Unknown column '{f.col}' in filter."
            )
        active_tables.add(tbl)

        op = f.op.lower()
        if op not in ALLOWED_OPS:
            return ValidationResult(
                is_valid=False,
                error=f"Unsupported filter operator '{f.op}'. Allowed operators: {list(ALLOWED_OPS)}"
            )
        validated_filters.append(Filter(col=f"{tbl}.{col}", op=op, val=f.val))

    # Must have at least one table
    if not active_tables:
        return ValidationResult(
            is_valid=False,
            error="No valid tables identified in the query plan."
        )

    # 5. Resolve multi-table join connectivity
    table_list = list(active_tables)
    if len(table_list) > 1:
        # Build adjacency graph
        adj_graph: Dict[str, List[str]] = {}
        for j in joins:
            t1 = j["from_table"].upper()
            t2 = j["to_table"].upper()
            adj_graph.setdefault(t1, []).append(t2)
            adj_graph.setdefault(t2, []).append(t1)

        for t in table_list:
            if t not in adj_graph:
                return ValidationResult(
                    is_valid=False,
                    error=f"Table '{t}' has no known join relationships in dataset config."
                )
        
        # Verify connectivity and bridge if needed
        root = table_list[0]
        connected_tables = set([root])
        for target in table_list[1:]:
            path = _find_shortest_path(adj_graph, root, target)
            if not path:
                return ValidationResult(
                    is_valid=False,
                    error=f"No join path exists between '{root}' and '{target}'."
                )
            for node in path:
                connected_tables.add(node)
        table_list = sorted(list(connected_tables))

    # 6. Validate limit
    limit = plan.limit
    if limit is None or limit <= 0:
        limit = default_limit
    elif limit > max_limit:
        return ValidationResult(
            is_valid=False,
            error=f"Requested limit {limit} exceeds maximum allowed limit {max_limit}."
        )

    validated_plan = Plan(
        intent="query",
        tables=table_list,
        metrics=validated_metrics,
        dims=validated_dims,
        filters=validated_filters,
        order_by=plan.order_by,
        limit=limit,
        message=plan.message
    )

    return ValidationResult(is_valid=True, plan=validated_plan)
