import pandas as pd
import numpy as np
import duckdb
import uuid
from datetime import datetime, timezone

DB_PATH = r"C:\Users\user\Desktop\Datasentinel\datasentinel.db"
CSV_PATH = r"C:\Users\user\Desktop\Datasentinel\data\raw\PS_20174392719_1491204439457_log.csv"


def get_raw_data():
    print("Reading full CSV file. This covers all 744 steps, so it takes a bit longer.")
    full_df = pd.read_csv(CSV_PATH)
    print(f"Full dataset: {len(full_df):,} rows, step range {full_df['step'].min()} to {full_df['step'].max()}")

    df = full_df.sample(n=500000, random_state=1).reset_index(drop=True)
    print(f"Sampled: {len(df):,} rows, step range {df['step'].min()} to {df['step'].max()}")

    df = df.rename(columns={
        'type':           'transaction_type',
        'nameOrig':       'customer_origin',
        'oldbalanceOrg':  'balance_origin_before',
        'newbalanceOrig': 'balance_origin_after',
        'nameDest':       'customer_dest',
        'oldbalanceDest': 'balance_dest_before',
        'newbalanceDest': 'balance_dest_after',
        'isFraud':        'is_fraud',
        'isFlaggedFraud': 'is_flagged_fraud'
    })

    df['transaction_id'] = [str(uuid.uuid4()) for _ in range(len(df))]
    df['ingested_at'] = datetime.now(timezone.utc)
    df['pipeline_version'] = 'v1.0.0'

    df['step'] = df['step'].astype(int)
    df['amount'] = df['amount'].astype(float)
    df['is_fraud'] = df['is_fraud'].astype(int)
    df['is_flagged_fraud'] = df['is_flagged_fraud'].astype(int)

    return df


def issue_1_silent_row_drop(df, drop_rate=0.048):
    keep_mask = np.random.random(len(df)) > drop_rate
    dropped = (~keep_mask).sum()
    print(f"Issue 1 — Silent row drop: {dropped:,} rows dropped")
    return df[keep_mask].copy()


def issue_2_schema_drift(df):
    df = df.copy()
    drift_mask = df['step'] >= 400
    df.loc[drift_mask, 'customer_dest'] = None
    print(f"Issue 2 — Schema drift: {drift_mask.sum():,} rows affected")
    return df


def issue_3_duplicates(df, dupe_rate=0.008):
    n_dupes = int(len(df) * dupe_rate)
    dupe_rows = df.sample(n=n_dupes, random_state=42).copy()
    dupe_rows['transaction_id'] = [str(uuid.uuid4()) for _ in range(n_dupes)]
    result = pd.concat([df, dupe_rows], ignore_index=True)
    print(f"Issue 3 — Duplicates: {n_dupes:,} duplicate rows inserted")
    return result


def issue_4_value_anomaly(df):
    df = df.copy()
    anomaly_idx = df.sample(n=200, random_state=99).index
    df.loc[anomaly_idx, 'amount'] = df.loc[anomaly_idx, 'amount'] * 1000
    print(f"Issue 4 — Value anomaly: 200 transactions with 1000x amounts")
    return df


def issue_5_referential_integrity(df):
    df = df.copy()
    bad_idx = df.sample(n=500, random_state=77).index
    df.loc[bad_idx, 'customer_dest'] = 'MERCHANT_DELETED_' + bad_idx.astype(str)
    print(f"Issue 5 — Referential integrity: 500 orphaned merchant refs")
    return df


def issue_6_freshness_failure(df):
    df = df.copy()
    max_step = df['step'].max()
    stale_mask = df['step'] > (max_step - 48)
    removed = stale_mask.sum()
    df = df[~stale_mask].copy()
    print(f"Issue 6 — Freshness failure: {removed:,} recent rows missing")
    return df


def add_transformation_columns(df):
    df = df.copy()

    df['balance_delta_origin'] = df['balance_origin_after'] - df['balance_origin_before']
    df['balance_delta_dest'] = df['balance_dest_after'] - df['balance_dest_before']

    df['amount_bucket'] = pd.cut(
        df['amount'],
        bins=[0, 1000, 10000, 100000, float('inf')],
        labels=['SMALL', 'MEDIUM', 'LARGE', 'WHALE']
    ).astype(str)

    df['is_balance_mismatch'] = (
        abs(df['balance_origin_before'] - df['balance_origin_after'] - df['amount']) > 0.01
    )

    df['transformed_at'] = datetime.now(timezone.utc)
    df['pipeline_version'] = 'v1.0.1'

    return df


def build_transformed_table():
    print("\nBuilding transformed_transactions table...\n")

    df = get_raw_data()
    print(f"Raw data: {len(df):,} rows\n")

    df = issue_1_silent_row_drop(df)
    df = issue_2_schema_drift(df)
    df = issue_3_duplicates(df)
    df = issue_4_value_anomaly(df)
    df = issue_5_referential_integrity(df)
    df = issue_6_freshness_failure(df)

    df = add_transformation_columns(df)

    columns = [
        'transaction_id', 'step', 'transaction_type', 'amount',
        'amount_bucket', 'customer_origin', 'customer_dest',
        'balance_delta_origin', 'balance_delta_dest',
        'is_fraud', 'is_flagged_fraud', 'is_balance_mismatch',
        'transformed_at', 'pipeline_version'
    ]
    df = df[columns]

    con = duckdb.connect(DB_PATH)
    con.register('df_view', df)
    con.execute("DELETE FROM transformed_transactions")
    con.execute("""
        INSERT INTO transformed_transactions
        SELECT
            transaction_id, step, transaction_type, amount,
            amount_bucket, customer_origin, customer_dest,
            balance_delta_origin, balance_delta_dest,
            is_fraud, is_flagged_fraud, is_balance_mismatch,
            transformed_at, pipeline_version
        FROM df_view
    """)

    count = con.execute("SELECT COUNT(*) FROM transformed_transactions").fetchone()[0]
    con.close()

    print(f"\nTransformed table loaded: {count:,} rows")
    print(f"Issues planted: 6/6\n")


if __name__ == "__main__":
    build_transformed_table()