import json

import pandas as pd
import streamlit as st

from utils.storage import load_all_saved_records, load_finance_settings

st.set_page_config(page_title="Finance AI Assistant", page_icon="🤖", layout="wide")

# Chatbot/LLM integration is intentionally disabled for now.
# This page shows a placeholder and the current transaction context.

st.title("Finance AI assistant — Coming soon")
st.caption("Chatbot and LLM-based analysis will be enabled later. For now this page shows your uploaded transaction context and classification rules.")

settings = load_finance_settings()
with st.sidebar:
    st.header("Finance rules")
    my_accounts = st.text_area("My account names", value=settings.get("my_accounts", ""), height=120)
    salary_keywords = st.text_area("Salary keywords", value=settings.get("salary_keywords", "salary,payroll,employer,payslip"), height=90)
    self_transfer_keywords = st.text_area("Self transfer keywords", value=settings.get("self_transfer_keywords", "self transfer,own account,internal transfer,internal fund transfer,to my own account"), height=120)
    if st.button("Save rules"):
        from utils.storage import save_finance_settings

        save_finance_settings({
            "my_accounts": my_accounts,
            "salary_keywords": salary_keywords,
            "self_transfer_keywords": self_transfer_keywords,
        })
        st.success("Rules saved for classification and future chatbot analysis.")
    st.page_link("app.py", label="Back to analysis dashboard")

# Build a lightweight transaction context for display only

def build_chat_context():
    settings = load_finance_settings()
    df = load_all_saved_records()
    if df.empty:
        return {"settings": settings, "transactions": [], "summary": {}}

    clean = df.copy()
    if "date" in clean.columns:
        clean["date"] = pd.to_datetime(clean["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for col in ["description", "category", "account", "debit", "credit", "amount", "time", "dr_cr"]:
        if col not in clean.columns:
            clean[col] = ""
    clean = clean.fillna("")

    summary = {
        "rows": len(clean),
        "accounts": sorted(clean.get("account", pd.Series(dtype="object")).astype(str).unique().tolist())[:20],
        "categories": sorted(clean.get("category", pd.Series(dtype="object")).astype(str).unique().tolist())[:20],
    }

    return {"settings": settings, "transactions": clean.head(300).to_dict(orient="records"), "summary": summary}


context = build_chat_context()

if not context["transactions"]:
    st.info("No transaction data yet. Upload a statement in the dashboard first to populate the context.")
else:
    st.subheader("Current transaction context (preview)")
    transactions_df = pd.DataFrame(context["transactions"]).head(50)
    if not transactions_df.empty:
        st.dataframe(transactions_df, use_container_width=True)

    st.info("LLM/chatbot is currently disabled. When enabled, the assistant will use the above context and your saved rules to answer finance questions.")