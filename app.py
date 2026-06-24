import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

import streamlit as st
import duckdb
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

# Page config — must be first Streamlit command
st.set_page_config(
    page_title="DataSentinel",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

DB_PATH = str(PROJECT_ROOT / "datasentinel.db")

# ── Cached data loaders ───────────────────────────────────────────────────

@st.cache_data(ttl=300)  # cache for 5 minutes
def load_aggregated_metrics():
    con = duckdb.connect(DB_PATH)
    df = con.execute("""
        SELECT metric_date, transaction_type,
               total_transactions, total_volume,
               avg_transaction_value, fraud_rate, success_rate
        FROM aggregated_metrics
        ORDER BY metric_date
    """).df()
    con.close()
    return df

@st.cache_data(ttl=300)
def load_pipeline_logs():
    con = duckdb.connect(DB_PATH)
    df = con.execute("""
        SELECT run_timestamp, pipeline_version,
               rows_ingested, rows_processed,
               rows_dropped, status, error_message
        FROM pipeline_run_logs
        ORDER BY run_timestamp DESC
    """).df()
    con.close()
    return df

@st.cache_data(ttl=300)
def load_transformed_sample():
    con = duckdb.connect(DB_PATH)
    df = con.execute("""
        SELECT step, transaction_type, amount,
               customer_dest, is_fraud, is_balance_mismatch
        FROM transformed_transactions
        LIMIT 50000
    """).df()
    con.close()
    return df

@st.cache_resource
def load_detection_engine():
    from Detection.statistical import run_all_detectors
    return run_all_detectors

@st.cache_resource
def load_report_generator():
    from reports.incident_generator import generate_report_for_alert
    return generate_report_for_alert

# ── Header ────────────────────────────────────────────────────────────────

st.markdown("""
<div style='padding: 1rem 0 0.5rem 0'>
    <h1 style='margin:0; font-size:2rem; font-weight:700'>
        🛡️ DataSentinel
    </h1>
    <p style='color:#888; margin:0.2rem 0 0 0; font-size:0.95rem'>
        Agentic Data Quality Intelligence — Payment Pipeline Monitor
    </p>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "📊  Live Monitor",
    "🚨  Incident Feed",
    "💬  Ask DataSentinel",
    "🔧  Pipeline Health"
])

with tab1:
    st.subheader("Pipeline Health Overview")

    metrics_df = load_aggregated_metrics()
    logs_df = load_pipeline_logs()
    sample_df = load_transformed_sample()

    # ── KPI cards row ────────────────────────────────────────────

    col1, col2, col3, col4 = st.columns(4)

    # Total transactions today (last date in data)
    latest_date = metrics_df['metric_date'].max()
    today_data = metrics_df[metrics_df['metric_date'] == latest_date]
    total_today = int(today_data['total_transactions'].sum())

    # Average over all days for comparison
    daily_avg = metrics_df.groupby('metric_date')['total_transactions'].sum().mean()
    pct_vs_avg = ((total_today - daily_avg) / daily_avg) * 100

    with col1:
        st.metric(
            label="Transactions (latest day)",
            value=f"{total_today:,}",
            delta=f"{pct_vs_avg:.1f}% vs avg"
        )

    # Overall fraud rate
    total_fraud = metrics_df['fraud_rate'].mean() * 100
    with col2:
        st.metric(
            label="Avg Fraud Rate",
            value=f"{total_fraud:.3f}%",
            delta=None
        )

    # Null rate in customer_dest (schema drift signal)
    null_count = sample_df['customer_dest'].isna().sum()
    null_rate = (null_count / len(sample_df)) * 100
    null_color = "normal" if null_rate < 2 else "inverse"
    with col3:
        st.metric(
            label="Null Rate (customer_dest)",
            value=f"{null_rate:.1f}%",
            delta=f"{'OK' if null_rate < 2 else 'DRIFT DETECTED'}",
            delta_color=null_color
        )

    # Last pipeline run status
    last_run = logs_df.iloc[0]
    drop_rate = (last_run['rows_dropped'] / last_run['rows_ingested']) * 100
    with col4:
        st.metric(
            label="Last Pipeline Run",
            value=last_run['status'],
            delta=f"{drop_rate:.1f}% rows dropped",
            delta_color="normal" if last_run['status'] == 'SUCCESS' else "inverse"
        )

    st.divider()

    # ── Volume chart ─────────────────────────────────────────────

    st.subheader("Daily Transaction Volume")

    daily_volume = (
        metrics_df.groupby('metric_date')['total_transactions']
        .sum()
        .reset_index()
    )

    # Calculate average line for reference
    avg_line = daily_volume['total_transactions'].mean()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=daily_volume['metric_date'],
        y=daily_volume['total_transactions'],
        name='Daily Volume',
        marker_color=[
            '#ef4444' if v < avg_line * 0.8 else '#3b82f6'
            for v in daily_volume['total_transactions']
        ]
    ))
    fig.add_hline(
        y=avg_line,
        line_dash="dash",
        line_color="#94a3b8",
        annotation_text=f"Average: {avg_line:,.0f}"
    )
    fig.update_layout(
        height=350,
        margin=dict(t=20, b=20),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor='rgba(100,100,100,0.1)')
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Transaction type breakdown ────────────────────────────────

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Volume by Transaction Type")
        type_volume = (
            metrics_df.groupby('transaction_type')['total_transactions']
            .sum()
            .reset_index()
        )
        fig2 = px.pie(
            type_volume,
            values='total_transactions',
            names='transaction_type',
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        fig2.update_layout(
            height=300, margin=dict(t=20, b=20),
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig2, use_container_width=True)

    with col_right:
        st.subheader("Fraud Rate by Transaction Type")
        fraud_by_type = (
            metrics_df.groupby('transaction_type')['fraud_rate']
            .mean()
            .reset_index()
        )
        fraud_by_type['fraud_rate_pct'] = fraud_by_type['fraud_rate'] * 100
        fig3 = px.bar(
            fraud_by_type,
            x='transaction_type',
            y='fraud_rate_pct',
            color='fraud_rate_pct',
            color_continuous_scale='Reds',
            labels={'fraud_rate_pct': 'Fraud Rate (%)'}
        )
        fig3.update_layout(
            height=300, margin=dict(t=20, b=20),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            showlegend=False
        )
        st.plotly_chart(fig3, use_container_width=True)

with tab2:
    st.subheader("Active Incidents")

    # Run detection on demand with a button
    # so it doesn't re-run on every page interaction
    if 'alerts' not in st.session_state:
        st.session_state.alerts = []
        st.session_state.reports = {}

    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        run_detection = st.button(
            "Run Detection Sweep",
            type="primary",
            use_container_width=True
        )
    with col_info:
        if st.session_state.alerts:
            st.info(
                f"Last sweep: {len(st.session_state.alerts)} alert(s) detected. "
                f"Click an alert to generate its incident report."
            )
        else:
            st.info("Click 'Run Detection Sweep' to check all 6 data quality indicators.")

    if run_detection:
        with st.spinner("Running statistical detection across all 6 indicators..."):
            run_all = load_detection_engine()
            st.session_state.alerts = run_all()
        st.success(
            f"Detection complete. {len(st.session_state.alerts)} alert(s) found."
        )

    # Display alerts as expandable cards
    if st.session_state.alerts:
        st.divider()

        severity_colors = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢"
        }

        for i, alert in enumerate(st.session_state.alerts):
            issue = alert.get('issue_type', 'unknown').replace('_', ' ').title()
            severity = alert.get('severity', 'medium')
            icon = severity_colors.get(severity, "⚪")

            with st.expander(
                f"{icon} {issue} — {severity.upper()}",
                expanded=(i == 0)
            ):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.write("**Issue type:**", alert.get('issue_type'))
                    st.write("**Severity:**", severity)
                    st.write("**Detected at:**", alert.get('detected_at', 'N/A'))
                with col_b:
                    # Show relevant numbers per issue type
                    if 'affected_rows' in alert:
                        st.write("**Affected rows:**", f"{alert['affected_rows']:,}")
                    if 'null_rate_pct' in alert:
                        st.write("**Null rate:**", f"{alert['null_rate_pct']}%")
                    if 'duplicate_rate_pct' in alert:
                        st.write("**Duplicate rate:**", f"{alert['duplicate_rate_pct']}%")
                    if 'worst_drop_rate_pct' in alert:
                        st.write("**Drop rate:**", f"{alert['worst_drop_rate_pct']}%")

                # Report generation button per alert
                report_key = f"report_{i}"
                if report_key not in st.session_state.reports:
                    if st.button(
                        "Generate Incident Report",
                        key=f"btn_{i}",
                        type="secondary"
                    ):
                        with st.spinner(
                            "Analysing root cause and generating report..."
                        ):
                            generate_report = load_report_generator()
                            report_text = generate_report(alert)
                            st.session_state.reports[report_key] = report_text
                        st.rerun()
                else:
                    st.divider()
                    st.markdown("**Incident Report:**")
                    st.markdown(st.session_state.reports[report_key])

                    # Download button for the report
                    st.download_button(
                        label="Download Report",
                        data=st.session_state.reports[report_key],
                        file_name=f"incident_{alert.get('issue_type')}_{datetime.now().strftime('%Y%m%d')}.txt",
                        mime="text/plain",
                        key=f"dl_{i}"
                    )

with tab3:
    st.subheader("Ask DataSentinel")
    st.caption(
        "Ask any question about the payment pipeline data. "
        "The agent will query the database and answer in plain English."
    )

    # Initialise chat history
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    # Show preset question buttons
    st.markdown("**Quick questions:**")
    preset_cols = st.columns(3)
    presets = [
        "Which days had the most significant volume drops?",
        "What is the overall fraud rate by transaction type?",
        "Show me the pipeline run that had the most dropped rows",
    ]

    for idx, (col, question) in enumerate(zip(preset_cols, presets)):
        with col:
            if st.button(question, key=f"preset_{idx}", use_container_width=True):
                st.session_state.messages.append({
                    "role": "user",
                    "content": question
                })

    st.divider()

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask anything about your payment data..."):
        st.session_state.messages.append({
            "role": "user",
            "content": prompt
        })
        with st.chat_message("user"):
            st.markdown(prompt)

    # Generate response for the latest unanswered question
    if (st.session_state.messages and
            st.session_state.messages[-1]["role"] == "user"):

        latest_question = st.session_state.messages[-1]["content"]

        with st.chat_message("assistant"):
            with st.spinner("Investigating..."):
                try:
                    from agents.root_cause import investigate_alert
                    response = investigate_alert(latest_question)
                except Exception as e:
                    response = f"Investigation error: {str(e)}"

            st.markdown(response)
            st.session_state.messages.append({
                "role": "assistant",
                "content": response
            })

    # Clear chat button
    if st.session_state.messages:
        if st.button("Clear conversation", type="secondary"):
            st.session_state.messages = []
            st.rerun()

with tab4:
    st.subheader("Pipeline Health Details")

    logs_df = load_pipeline_logs()
    sample_df = load_transformed_sample()
    metrics_df = load_aggregated_metrics()

    # ── Pipeline run log table ────────────────────────────────────

    st.markdown("**Pipeline Run History**")

    display_logs = logs_df.copy()
    display_logs['drop_rate_pct'] = (
        display_logs['rows_dropped'] /
        display_logs['rows_ingested'] * 100
    ).round(1)

    # Color status column
    def highlight_status(row):
        if row['status'] == 'PARTIAL':
            return ['background-color: #7f1d1d'] * len(row)
        elif row['status'] == 'SUCCESS':
            return ['background-color: #14532d'] * len(row)
        return [''] * len(row)

    st.dataframe(
        display_logs[[
            'run_timestamp', 'pipeline_version',
            'rows_ingested', 'rows_processed',
            'rows_dropped', 'drop_rate_pct', 'status'
        ]].style.apply(highlight_status, axis=1),
        use_container_width=True,
        height=250
    )

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        # ── Schema drift chart ────────────────────────────────────
        st.markdown("**Null Rate Over Time (Schema Drift Monitor)**")

        null_by_step = sample_df.copy()
        null_by_step['day'] = null_by_step['step'] // 24
        null_trend = (
            null_by_step.groupby('day')
            .apply(lambda x: x['customer_dest'].isna().mean() * 100)
            .reset_index()
            .rename(columns={0: 'null_rate_pct'})
        )

        fig4 = px.line(
            null_trend,
            x='day',
            y='null_rate_pct',
            labels={'day': 'Day', 'null_rate_pct': 'Null Rate (%)'},
            color_discrete_sequence=['#ef4444']
        )
        fig4.add_hline(
            y=2,
            line_dash="dash",
            line_color="#94a3b8",
            annotation_text="2% threshold"
        )
        fig4.update_layout(
            height=300,
            margin=dict(t=10, b=10),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig4, use_container_width=True)

    with col_right:
        # ── Amount distribution ───────────────────────────────────
        st.markdown("**Transaction Amount Distribution**")

        amount_data = sample_df[sample_df['amount'] < sample_df['amount'].quantile(0.98)]
        fig5 = px.histogram(
            amount_data,
            x='amount',
            nbins=50,
            color_discrete_sequence=['#3b82f6'],
            labels={'amount': 'Transaction Amount (Rs)'}
        )
        fig5.update_layout(
            height=300,
            margin=dict(t=10, b=10),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig5, use_container_width=True)

    st.divider()

    # ── Raw stats ─────────────────────────────────────────────────
    st.markdown("**Quick Database Stats**")
    col1, col2, col3 = st.columns(3)

    con = duckdb.connect(DB_PATH)
    raw_count = con.execute("SELECT COUNT(*) FROM raw_transactions").fetchone()[0]
    transformed_count = con.execute("SELECT COUNT(*) FROM transformed_transactions").fetchone()[0]
    null_count = con.execute("SELECT COUNT(*) FROM transformed_transactions WHERE customer_dest IS NULL").fetchone()[0]
    orphaned = con.execute("SELECT COUNT(*) FROM transformed_transactions WHERE customer_dest LIKE 'MERCHANT_DELETED_%'").fetchone()[0]
    con.close()

    with col1:
        st.metric("Raw Transactions", f"{raw_count:,}")
        st.metric("Transformed Transactions", f"{transformed_count:,}")
    with col2:
        drop_count = raw_count - transformed_count
        st.metric("Net Row Drop", f"{drop_count:,}")
        st.metric("Null customer_dest", f"{null_count:,}")
    with col3:
        st.metric("Orphaned Merchant Refs", f"{orphaned:,}")
        st.metric("Drop Rate", f"{drop_count/raw_count*100:.1f}%")

