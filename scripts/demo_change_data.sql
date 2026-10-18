-- ==============================================================================
-- DataMind: Demonstration of Dynamic Answer Changes upon Underlying Data Update
-- Note: Must be run with an admin role (e.g. ACCOUNTADMIN or SYSADMIN),
--       as DATAMIND_APP_ROLE is strictly read-only.
-- ==============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE DATAMIND_WH;
USE DATABASE DATAMIND_DB;
USE SCHEMA SALES;

-- ------------------------------------------------------------------------------
-- Step 1: Baseline inspection of target order
-- ------------------------------------------------------------------------------
SELECT O_ORDERKEY, O_TOTALPRICE, O_COMMENT
FROM ORDERS
WHERE O_ORDERKEY = 1;

-- ------------------------------------------------------------------------------
-- Step 2: Update one order's total price to a distinct new value
-- Expected pipeline impact:
-- Question: "What are the top 5 largest orders by total price?"
-- Order 1 will now appear at the very top of the ranking.
-- ------------------------------------------------------------------------------
UPDATE ORDERS
SET O_TOTALPRICE = 9999999.99,
    O_COMMENT = 'DEMO_CHANGE_DATA_TEST'
WHERE O_ORDERKEY = 1;

-- Verify update applied
SELECT O_ORDERKEY, O_TOTALPRICE, O_COMMENT
FROM ORDERS
WHERE O_ORDERKEY = 1;

-- ------------------------------------------------------------------------------
-- Step 3: Run in DataMind UI or pipeline:
-- Query: "What are the top 5 largest orders by total price?"
-- Notice the newly updated price (9,999,999.99) reflects immediately in the
-- Answer Card and Executed SQL result rows.
-- ------------------------------------------------------------------------------

-- ------------------------------------------------------------------------------
-- Step 4: Revert to original benchmark state
-- (Reverting Order 1 back to standard TPC-H values)
-- ------------------------------------------------------------------------------
UPDATE ORDERS
SET O_TOTALPRICE = 172799.49,
    O_COMMENT = 'nstructions sleep furiously among '
WHERE O_ORDERKEY = 1;

-- Verify revert
SELECT O_ORDERKEY, O_TOTALPRICE, O_COMMENT
FROM ORDERS
WHERE O_ORDERKEY = 1;
