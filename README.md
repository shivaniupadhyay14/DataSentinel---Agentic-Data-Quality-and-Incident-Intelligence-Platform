# DataSentinel

Agentic data quality intelligence platform for payment pipeline monitoring.

## The Problem

Every data team faces the same silent threat: pipelines that degrade without 
throwing errors. Metrics look fine, dashboards load, but the numbers are wrong.
A schema change nulls out a key field at 2am. A retry bug doubles your 
transaction count. A batch job stalls and nobody notices for 14 hours.

By the time an analyst catches it, three business decisions have already been 
made on bad data.

## What DataSentinel Does

DataSentinel autonomously monitors a payment data pipeline for 6 classes of 
failure, traces root cause through data lineage, quantifies business impact 
in rupee terms, and generates plain-English incident reports — before anyone 
opens a dashboard.

## Architecture

<img width="1821" height="2901" alt="paysim_architecture" src="https://github.com/user-attachments/assets/2caeb247-ca01-4f99-b0bc-725630ac5c5f" />



## Detection Capabilities

| Issue Type | Detection Method | Business Impact |
|---|---|---|
| Silent row drop | IQR on daily volume | Revenue understatement |
| Schema drift | Null rate vs baseline | Merchant attribution failure |
| Duplicate records | Window function similarity | Inflated KPIs |
| Value anomaly | Z-score on amounts | Distorted averages |
| Pipeline failure | Run log reconciliation | Stale dashboards |
| Referential integrity | Pattern matching | Orphaned records |

## Tech Stack

- **Data:** DuckDB, Python, Pandas
- **Detection:** Statistical Process Control, IQR, Z-score
- **LLM:** Groq (Llama 3.1 70B) for report generation
- **RAG:** HuggingFace sentence-transformers + FAISS (local, no API)
- **Agent:** LangChain ReAct agent with 4 tools
- **UI:** Streamlit
- **Deployment:** Streamlit Cloud

## Run Locally

```bash
git clone https://github.com/shivaniupadhyay14/datasentinel.git
cd datasentinel
pip install -r requirements.txt
streamlit run app.py
```

## Project Structure

```
detection/     — 6 statistical detectors
pipeline/      — ETL pipeline simulation
rag/           — RAG knowledge base (local embeddings)
reports/       — Incident report generator
agents/        — LangChain root cause agent
app.py         — Streamlit application
```
