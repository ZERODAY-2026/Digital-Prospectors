
def execute_datamind_query(session, sql):
    """Execute a basic read-only query using a Snowflake session."""

    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("SQL query cannot be empty.")

    cleaned_sql = sql.strip().rstrip(";")

    # Basic prototype checks only; not production-grade SQL validation.
    normalized = cleaned_sql.upper()

    if not (
        normalized.startswith("SELECT ")
        or normalized.startswith("WITH ")
    ):
        raise ValueError("Only SELECT or WITH queries are allowed.")

    forbidden = [
        "INSERT ", "UPDATE ", "DELETE ", "DROP ",
        "ALTER ", "CREATE ", "TRUNCATE ", "MERGE ",
        "CALL ", "EXECUTE "
    ]

    padded_sql = " " + normalized + " "

    if any(keyword in padded_sql for keyword in forbidden):
        raise ValueError("Query contains a prohibited SQL operation.")

    # Limit returned rows, not necessarily the cost of query execution.
    rows = session.sql(cleaned_sql).limit(100).collect()

    return {
        "sql": cleaned_sql,
        "columns": list(rows[0].as_dict().keys()) if rows else [],
        "rows": [row.as_dict() for row in rows],
        "row_count": len(rows),
    }
