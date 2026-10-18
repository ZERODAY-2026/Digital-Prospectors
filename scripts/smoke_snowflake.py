import os
import sys
from dotenv import load_dotenv
import snowflake.connector

def run_smoke():
    load_dotenv()
    
    account = os.getenv("SNOWFLAKE_ACCOUNT")
    user = os.getenv("SNOWFLAKE_USER")
    password = os.getenv("SNOWFLAKE_PASSWORD")
    role = os.getenv("SNOWFLAKE_ROLE")
    warehouse = os.getenv("SNOWFLAKE_WAREHOUSE")
    database = os.getenv("SNOWFLAKE_DATABASE")
    schema = os.getenv("SNOWFLAKE_SCHEMA")
    
    if not all([account, user, password, role, warehouse, database, schema]):
        print("ERROR: Missing one or more Snowflake environment variables in .env.")
        sys.exit(1)
        
    print("Connecting to Snowflake with app role...")
    try:
        conn = snowflake.connector.connect(
            account=account,
            user=user,
            password=password,
            role=role,
            warehouse=warehouse,
            database=database,
            schema=schema,
            autocommit=False
        )
    except Exception as e:
        print(f"FAILED to connect to Snowflake: {type(e).__name__}: {e}")
        sys.exit(2)
        
    try:
        cur = conn.cursor()
        print("Executing: SELECT COUNT(*) FROM ORDERS")
        cur.execute("SELECT COUNT(*) FROM ORDERS")
        rows = cur.fetchall()
        sfqid = cur.sfqid
        print(f"Row count result: {rows}")
        print(f"Snowflake Query ID (sfqid): {sfqid}")
        
        print("\nTesting read-only role enforcement: Attempting UPDATE on ORDERS...")
        try:
            cur.execute("UPDATE ORDERS SET O_COMMENT = 'test' WHERE 1 = 0")
            print("WARNING: UPDATE succeeded or was not blocked! Expected privilege failure.")
        except Exception as e:
            print(f"SUCCESS: UPDATE was blocked as expected: {type(e).__name__}: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_smoke()
