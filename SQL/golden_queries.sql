-- =====================================================
-- QUERY 1: DAY OVER DAY VOLUME WITH LAG
-- =====================================================

SELECT
    metric_date,
    transaction_type,
    total_transactions,
    LAG(total_transactions) OVER (
        PARTITION BY transaction_type
        ORDER BY metric_date
    ) AS prev_day_volume,
    ROUND(
        (total_transactions - LAG(total_transactions) OVER (
            PARTITION BY transaction_type
            ORDER BY metric_date)
        ) * 100.0 / NULLIF(LAG(total_transactions) OVER (
            PARTITION BY transaction_type
            ORDER BY metric_date), 0)
    , 2) AS day_over_day_pct_change
FROM aggregated_metrics
ORDER BY metric_date DESC, transaction_type;

-- =====================================================
-- QUERY 2: 7-DAY ROLLING FRAUD RATE
-- =====================================================

SELECT
    metric_date,
    transaction_type,
    ROUND(fraud_rate * 100, 4) AS fraud_rate_pct,
    ROUND(AVG(fraud_rate) OVER (
        PARTITION BY transaction_type
        ORDER BY metric_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) * 100, 4) AS fraud_rate_7day_avg,
    ROUND((fraud_rate - AVG(fraud_rate) OVER (
        PARTITION BY transaction_type
        ORDER BY metric_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )) * 100, 4) AS deviation_from_avg
FROM aggregated_metrics
ORDER BY metric_date DESC;

-- =====================================================
-- QUERY 3: BALANCE MISMATCH RATE BY DAY
-- =====================================================

SELECT
    CAST(DATE '2024-01-01' + INTERVAL (step / 24) DAY AS DATE) AS txn_date,
    transaction_type,
    COUNT(*) AS total,
    SUM(CASE WHEN is_balance_mismatch THEN 1 ELSE 0 END) AS mismatch_count,
    ROUND(
        SUM(CASE WHEN is_balance_mismatch THEN 1 ELSE 0 END) * 100.0
        / COUNT(*), 2
    ) AS mismatch_rate_pct
FROM transformed_transactions
GROUP BY 1, 2
ORDER BY 1 DESC, mismatch_rate_pct DESC;

-- =====================================================
-- QUERY 4: NULL RATE OVER TIME
-- =====================================================

SELECT
    CAST(DATE '2024-01-01' + INTERVAL (step / 24) DAY AS DATE) AS txn_date,
    ROUND(
        SUM(CASE WHEN customer_dest IS NULL THEN 1 ELSE 0 END)
        * 100.0 / COUNT(*), 2
    ) AS customer_dest_null_pct,
    ROUND(
        SUM(CASE WHEN amount IS NULL THEN 1 ELSE 0 END)
        * 100.0 / COUNT(*), 2
    ) AS amount_null_pct
FROM transformed_transactions
GROUP BY 1
ORDER BY 1 DESC;

-- =====================================================
-- QUERY 5: DUPLICATE DETECTION
-- =====================================================

WITH potential_dupes AS (
    SELECT
        transaction_id,
        customer_origin,
        customer_dest,
        amount,
        step,
        COUNT(*) OVER (
            PARTITION BY customer_origin, customer_dest, amount
            ORDER BY step
            ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
        ) AS nearby_identical_count
    FROM transformed_transactions
)
SELECT
    COUNT(*) AS total_transactions,
    SUM(CASE WHEN nearby_identical_count > 1
        THEN 1 ELSE 0 END) AS potential_duplicates,
    ROUND(
        SUM(CASE WHEN nearby_identical_count > 1
            THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 3
    ) AS duplicate_rate_pct
FROM potential_dupes;

-- =====================================================
-- QUERY 6: AMOUNT DISTRIBUTION PERCENTILES
-- =====================================================

SELECT
    transaction_type,
    ROUND(PERCENTILE_CONT(0.50)
        WITHIN GROUP (ORDER BY amount), 2) AS median_amount,
    ROUND(PERCENTILE_CONT(0.95)
        WITHIN GROUP (ORDER BY amount), 2) AS p95_amount,
    ROUND(PERCENTILE_CONT(0.99)
        WITHIN GROUP (ORDER BY amount), 2) AS p99_amount,
    ROUND(MAX(amount), 2) AS max_amount,
    ROUND(
        MAX(amount) /
        NULLIF(
            PERCENTILE_CONT(0.95)
            WITHIN GROUP (ORDER BY amount), 0
        ),
        1
    ) AS max_to_p95_ratio
FROM transformed_transactions
GROUP BY 1
ORDER BY max_to_p95_ratio DESC;

-- =====================================================
-- QUERY 7: PIPELINE ROW RECONCILIATION
-- =====================================================

SELECT
    run_timestamp,
    pipeline_version,
    rows_ingested,
    rows_processed,
    rows_dropped,
    ROUND(
        rows_dropped * 100.0 /
        NULLIF(rows_ingested, 0), 2
    ) AS drop_rate_pct,
    status,
    error_message
FROM pipeline_run_logs
ORDER BY run_timestamp DESC;

-- =====================================================
-- QUERY 8: FRESHNESS CHECK
-- =====================================================

SELECT
    MAX(step) AS latest_step_in_db,
    744 AS expected_max_step,
    744 - MAX(step) AS missing_steps,
    744 - MAX(step) AS estimated_hours_stale
FROM transformed_transactions;

-- =====================================================
-- QUERY 9: REFERENTIAL INTEGRITY CHECK
-- =====================================================

SELECT
    COUNT(*) AS total_transactions,
    SUM(
        CASE
            WHEN customer_dest LIKE 'MERCHANT_DELETED_%'
            THEN 1 ELSE 0
        END
    ) AS orphaned_refs,
    SUM(
        CASE
            WHEN customer_dest IS NULL
            THEN 1 ELSE 0
        END
    ) AS null_refs,
    ROUND(
        (
            SUM(CASE
                    WHEN customer_dest LIKE 'MERCHANT_DELETED_%'
                    THEN 1 ELSE 0
                END)
            +
            SUM(CASE
                    WHEN customer_dest IS NULL
                    THEN 1 ELSE 0
                END)
        ) * 100.0 / COUNT(*),
        3
    ) AS integrity_failure_pct
FROM transformed_transactions;

-- =====================================================
-- QUERY 10: COHORT TRANSACTION HEALTH
-- =====================================================

WITH customer_cohorts AS (
    SELECT
        customer_origin,
        MIN(step / 24) AS cohort_day
    FROM transformed_transactions
    GROUP BY customer_origin
)
SELECT
    CAST(c.cohort_day AS INTEGER) AS cohort_day,
    COUNT(DISTINCT t.customer_origin) AS cohort_size,
    COUNT(*) AS total_transactions,
    SUM(CASE WHEN t.is_fraud = 0
        THEN 1 ELSE 0 END) AS clean_transactions,
    ROUND(
        SUM(CASE WHEN t.is_fraud = 0
            THEN 1 ELSE 0 END) * 100.0
        / COUNT(*),
        2
    ) AS clean_rate_pct
FROM transformed_transactions t
JOIN customer_cohorts c
    ON t.customer_origin = c.customer_origin
GROUP BY 1
ORDER BY 1;