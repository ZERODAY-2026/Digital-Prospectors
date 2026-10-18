from typing import Dict, Any, Tuple, List, Set, Optional
from collections import deque
from src.core.plan_schema import Plan

def _find_join_condition(t1: str, t2: str, joins: List[Dict[str, Any]]) -> Optional[str]:
    for j in joins:
        jt1 = j["from_table"].upper()
        jt2 = j["to_table"].upper()
        if (jt1 == t1 and jt2 == t2) or (jt1 == t2 and jt2 == t1):
            return f"{j['from_table']}.{j['from_column']} = {j['to_table']}.{j['to_column']}"
    return None

def _resolve_join_order(tables: List[str], joins: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Determine the order in which to join tables and return list of (table_to_join, join_condition)."""
    if len(tables) <= 1:
        return []

    joined_tables = {tables[0]}
    remaining = set(tables[1:])
    join_steps: List[Tuple[str, str]] = []

    while remaining:
        found = False
        for cand in list(remaining):
            for existing in joined_tables:
                cond = _find_join_condition(existing, cand, joins)
                if cond:
                    join_steps.append((cand, cond))
                    joined_tables.add(cand)
                    remaining.remove(cand)
                    found = True
                    break
            if found:
                break
        if not found:
            # Fallback if no direct link to existing set
            cand = next(iter(remaining))
            for j in joins:
                jt1 = j["from_table"].upper()
                jt2 = j["to_table"].upper()
                if cand in (jt1, jt2):
                    other = jt2 if cand == jt1 else jt1
                    cond = f"{j['from_table']}.{j['from_column']} = {j['to_table']}.{j['to_column']}"
                    join_steps.append((cand, cond))
                    joined_tables.add(cand)
                    remaining.remove(cand)
                    found = True
                    break
            if not found:
                break

    return join_steps

def build_sql(plan: Plan, dataset_cfg: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Build a secure, single-statement parameterized SQL query from a validated Plan."""
    if plan.intent != "query":
        raise ValueError(f"Cannot build SQL for non-query intent: {plan.intent}")

    params: Dict[str, Any] = {}
    param_counter = 0

    def next_param(val: Any) -> str:
        nonlocal param_counter
        p_name = f"p{param_counter}"
        param_counter += 1
        params[p_name] = val
        return f"%({p_name})s"

    # SELECT items
    select_items: List[str] = []
    group_by_items: List[str] = []

    # Dimensions
    for d in plan.dims:
        if d.fn == "year":
            expr = f"EXTRACT(YEAR FROM {d.col})"
            alias = f"{d.col.split('.')[-1].lower()}_year"
            select_items.append(f"{expr} AS {alias}")
            group_by_items.append(expr)
        elif d.fn == "month":
            expr = f"EXTRACT(MONTH FROM {d.col})"
            alias = f"{d.col.split('.')[-1].lower()}_month"
            select_items.append(f"{expr} AS {alias}")
            group_by_items.append(expr)
        else:
            select_items.append(d.col)
            group_by_items.append(d.col)

    # Metrics
    for m in plan.metrics:
        agg_upper = m.agg.upper()
        alias = m.as_ or f"{m.agg}_{m.col.split('.')[-1].lower()}"
        select_items.append(f"{agg_upper}({m.col}) AS {alias}")

    if not select_items:
        # Fallback if no dims or metrics specified
        select_items.append("*")

    # FROM & JOINs
    root_table = plan.tables[0]
    from_clause = f"FROM {root_table}"

    joins_cfg = dataset_cfg.get("joins", [])
    join_steps = _resolve_join_order(plan.tables, joins_cfg)
    join_clauses: List[str] = []
    for tbl, cond in join_steps:
        join_clauses.append(f"JOIN {tbl} ON {cond}")

    # WHERE
    where_clauses: List[str] = []
    for f in plan.filters:
        op = f.op.lower()
        if op == "between":
            if isinstance(f.val, (list, tuple)) and len(f.val) == 2:
                p1 = next_param(f.val[0])
                p2 = next_param(f.val[1])
                where_clauses.append(f"{f.col} BETWEEN {p1} AND {p2}")
            else:
                p = next_param(f.val)
                where_clauses.append(f"{f.col} = {p}")
        elif op == "in":
            if isinstance(f.val, (list, tuple)) and f.val:
                p_list = [next_param(v) for v in f.val]
                where_clauses.append(f"{f.col} IN ({', '.join(p_list)})")
            else:
                p = next_param(f.val)
                where_clauses.append(f"{f.col} = {p}")
        elif op == "like":
            p = next_param(f.val)
            where_clauses.append(f"{f.col} LIKE {p}")
        else:
            p = next_param(f.val)
            where_clauses.append(f"{f.col} {op} {p}")

    # ORDER BY
    order_by_clauses: List[str] = []
    for o in plan.order_by:
        dir_str = "DESC" if o.dir.lower() == "desc" else "ASC"
        order_by_clauses.append(f"{o.key} {dir_str}")

    # Assemble query parts
    sql_parts = [f"SELECT {', '.join(select_items)}", from_clause]
    if join_clauses:
        sql_parts.extend(join_clauses)
    if where_clauses:
        sql_parts.append(f"WHERE {' AND '.join(where_clauses)}")
    if group_by_items and plan.metrics:
        sql_parts.append(f"GROUP BY {', '.join(group_by_items)}")
    if order_by_clauses:
        sql_parts.append(f"ORDER BY {', '.join(order_by_clauses)}")
    if plan.limit:
        sql_parts.append(f"LIMIT {int(plan.limit)}")

    sql = "\n".join(sql_parts)
    # Strict invariant: no semicolons
    sql = sql.replace(";", "")
    return sql, params
