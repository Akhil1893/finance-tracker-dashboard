import json
import os
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st

from utils.analytics import analyze_transactions, load_statement_file
from utils.storage import (
    delete_all_month_records,
    delete_month_records,
    list_saved_months,
    load_all_saved_records,
    load_finance_settings,
    load_month_records,
    save_finance_settings,
    save_month_records,
)

st.set_page_config(page_title="Finance Tracker", page_icon="💰", layout="wide")

DATA_DIR = Path(__file__).resolve().parent / "sample_data"
SAMPLE_CSV = DATA_DIR / "sample_transactions.csv"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


@st.cache_data
def get_sample_data():
    return pd.read_csv(SAMPLE_CSV)


def save_uploaded_dataframe(df):
    valid_dates = pd.to_datetime(df["date"], errors="coerce").dropna() if "date" in df.columns else pd.Series(dtype="datetime64[ns]")
    if valid_dates.empty:
        return []
    months = sorted(valid_dates.dt.to_period("M").astype(str).unique())
    saved = []
    for month_key in months:
        month_df = df[pd.to_datetime(df["date"], errors="coerce").dt.to_period("M").astype(str) == month_key].copy()
        save_month_records(month_key, month_df)
        saved.append(month_key)
    return saved


def get_ollama_model_name():
    try:
        request = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = payload.get("models", [])
        if not models:
            return None
        return models[0].get("name") or models[0].get("model")
    except Exception:
        return None


def build_ollama_context(summary, df):
    if df is None or df.empty:
        return {"summary": {}, "transactions": []}

    ordered_df = df.copy()
    if "date" in ordered_df.columns:
        ordered_df["date"] = pd.to_datetime(ordered_df["date"], errors="coerce")
    ordered_df = ordered_df.sort_values(by=["date" if "date" in ordered_df.columns else ordered_df.columns[0]], ascending=False, na_position="last")

    cleaned = ordered_df.head(200).copy()
    if "date" in cleaned.columns:
        cleaned["date"] = cleaned["date"].dt.strftime("%Y-%m-%d")
    for col in ["description", "category", "account", "bank_account_category", "debit", "credit", "amount", "time", "dr_cr"]:
        if col not in cleaned.columns:
            cleaned[col] = ""
    cleaned = cleaned.fillna("")

    return {
        "summary": {
            "total_spend": float(summary.get("total_spend", 0.0)),
            "total_income": float(summary.get("total_income", 0.0)),
            "net_cash_flow": float(summary.get("net_cash_flow", 0.0)),
            "top_category": summary.get("top_category", "None"),
            "category_breakdown": summary.get("category_table", pd.DataFrame()).head(10).to_dict(orient="records"),
        },
        "transactions": cleaned.to_dict(orient="records"),
    }


def ask_ollama(question, summary, df):
    model_name = get_ollama_model_name()
    if not model_name:
        return None

    context = build_ollama_context(summary, df)
    system_prompt = "You are a local personal finance assistant. Use only the uploaded statement data in the context. Answer concise, practical financial questions. Use Indian Rupee formatting when talking about money. If a value is not present in the data, say so clearly."
    user_prompt = f"Question: {question}\n\nFinancial data context: {json.dumps(context, default=str)}"

    payload = {
        "model": model_name,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        request = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result.get("message", {}).get("content", "").strip()
        return content if content else None
    except Exception:
        return None


def local_finance_chat(question, summary, df):
    q = str(question).lower().strip()
    if not q:
        return "Ask about spend, income, top category, or a specific day."

    llm_reply = ask_ollama(question, summary, df)
    if llm_reply:
        return llm_reply

    if any(word in q for word in ["total spend", "spent", "expense"]):
        return f"Total spend is ₹{summary['total_spend']:,.0f}."
    if any(word in q for word in ["income", "salary", "credit"]):
        return f"Total income is ₹{summary['total_income']:,.0f}."
    if any(word in q for word in ["net", "cash flow"]):
        return f"Net cash flow is ₹{summary['net_cash_flow']:,.0f}."
    if any(word in q for word in ["top category", "highest category", "most category"]):
        return f"Top category is {summary['top_category']}."
    if any(word in q for word in ["borrow", "lent", "loan", "money given", "money borrowed"]):
        if summary.get("borrow_lend_table").empty:
            return "No borrow/lend transaction data is available."
        borrow = summary["borrow_lend_table"][summary["borrow_lend_table"]["Type"] == "Borrowed"]
        lend = summary["borrow_lend_table"][summary["borrow_lend_table"]["Type"] == "Lent"]
        borrow_amt = float(borrow["Amount"].sum()) if not borrow.empty else 0.0
        lend_amt = float(lend["Amount"].sum()) if not lend.empty else 0.0
        return f"Borrowed: ₹{borrow_amt:,.0f}. Lent: ₹{lend_amt:,.0f}."
    if any(word in q for word in ["day", "date", "today", "latest"]):
        if "date" in df.columns and not df.empty:
            days = pd.to_datetime(df["date"], errors="coerce").dropna().dt.strftime("%Y-%m-%d").unique()
            if len(days):
                latest = sorted(days)[-1]
                return f"Latest available date is {latest}."
    if any(word in q for word in ["category", "categories"]):
        cats = summary["category_table"]
        if cats.empty:
            return "No category data available."
        top = cats.head(3)
        return "Top categories: " + "; ".join(f"{row['Category']} = ₹{row['Amount']:,.0f}" for _, row in top.iterrows())
    return "I can answer basic questions like total spend, top category, income, borrowed/lent, and recent day summaries."


st.title("Finance Dashboard")
st.caption("Monthly analysis, category trends, salary tracking, and account-level summaries")

with st.sidebar:
    st.header("Upload statements")
    uploaded_file = st.file_uploader(
        "Choose an Excel, CSV, or PDF statement",
        type=["xlsx", "xls", "csv", "pdf"],
        accept_multiple_files=False,
    )
    if st.button("Clear all uploaded data"):
        delete_all_month_records()
        st.session_state.clear()
        st.rerun()

    saved_months = list_saved_months()
    if saved_months:
        saved_options = [row["year_month"] for row in saved_months]
        selected_month = st.selectbox("Saved month", options=saved_options, index=0)
        if st.button("Delete selected month"):
            delete_month_records(selected_month)
            st.rerun()
        st.caption(f"Stored months: {len(saved_months)}")
    else:
        selected_month = None

    st.subheader("Classification settings")
    settings = load_finance_settings()
    my_accounts = st.text_area("My account names", value=settings.get("my_accounts", ""), height=120)
    salary_keywords = st.text_area("Salary keywords", value=settings.get("salary_keywords", "salary,payroll,employer,payslip"), height=90)
    self_transfer_keywords = st.text_area("Self transfer keywords", value=settings.get("self_transfer_keywords", "self transfer,own account,internal transfer,internal fund transfer,to my own account"), height=120)
    if st.button("Save classification rules"):
        save_finance_settings({
            "my_accounts": my_accounts,
            "salary_keywords": salary_keywords,
            "self_transfer_keywords": self_transfer_keywords,
        })
        st.success("Classification rules saved.")

    st.page_link("pages/chatbot.py", label="Open AI chatbot")
    st.info("Uploaded files are stored month-by-month in SQLite. The app keeps the full uploaded history and shows a zero-state until data is added.")

if uploaded_file is not None:
    df = load_statement_file(uploaded_file)
    if df.empty:
        st.warning("No data was detected from the uploaded file. Please upload a statement with recognizable transaction rows.")
        st.stop()
    save_uploaded_dataframe(df)
    st.session_state["active_df"] = df.copy()
    st.session_state["active_month"] = None
    st.session_state.pop("selected_day", None)
    st.success("File uploaded and saved. All months from this statement are now stored in the database.")
elif saved_months:
    selected_month = selected_month if "selected_month" in locals() else saved_months[0]["year_month"]
    df = load_month_records(selected_month)
    st.session_state["active_df"] = df.copy()
    st.session_state["active_month"] = selected_month
    if df.empty:
        df = pd.DataFrame(columns=["date", "description", "debit", "credit", "category", "account"])
else:
    df = pd.DataFrame(columns=["date", "description", "debit", "credit", "category", "account"])
    st.session_state["active_df"] = df.copy()
    st.session_state["active_month"] = None

if "date" in df.columns:
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

if df.empty:
    st.info("No statement data loaded yet. Upload a file to start analyzing expenses and chat with the finance assistant.")
    summary = analyze_transactions(pd.DataFrame(columns=["date", "description", "debit", "credit", "category", "account"]))
else:
    summary = analyze_transactions(df)

kpi_cols = st.columns(4)
kpi_cols[0].metric("Total spend", "₹0")
kpi_cols[1].metric("Income", "₹0")
kpi_cols[2].metric("Net cash flow", "₹0")
kpi_cols[3].metric("Top category", "None")

if not df.empty:
    kpi_cols[0].metric("Total spend", f"₹{summary['total_spend']:,.0f}")
    kpi_cols[1].metric("Income", f"₹{summary['total_income']:,.0f}")
    kpi_cols[2].metric("Net cash flow", f"₹{summary['net_cash_flow']:,.0f}")
    kpi_cols[3].metric("Top category", summary["top_category"])

st.subheader("Monthly expenditure")
monthly_table = summary["monthly_table"]
if not monthly_table.empty:
    st.dataframe(monthly_table, use_container_width=True)
    st.bar_chart(monthly_table.set_index("Month")["Spend"])
else:
    st.info("No monthly data available.")

st.subheader("Monthly balance")
monthly_balance_table = summary.get("monthly_balance_table", pd.DataFrame())
if not monthly_balance_table.empty:
    st.dataframe(monthly_balance_table, use_container_width=True)
else:
    st.info("No monthly balance data available.")

st.subheader("Salary analysis")
salary_summary_table = summary.get("salary_summary_table", pd.DataFrame())
if not salary_summary_table.empty:
    st.dataframe(salary_summary_table, use_container_width=True)
    salary_txn_table = summary.get("salary_txn_table", pd.DataFrame())
    if not salary_txn_table.empty:
        st.dataframe(salary_txn_table, use_container_width=True)
else:
    st.info("No salary record detected yet.")

st.subheader("Per-day expenditure")
daily_table = summary["daily_spend_table"]
if not daily_table.empty:
    st.caption("Click a row in the table to view all transactions for that day.")
    table_view = daily_table.sort_values("Date", ascending=False).reset_index(drop=True)
    selected_table = st.dataframe(
        table_view,
        selection_mode="single-row",
        use_container_width=True,
        on_select="rerun",
        hide_index=True,
    )

    row_index = None
    if hasattr(selected_table, "selection") and hasattr(selected_table.selection, "rows"):
        selected_rows = selected_table.selection.rows
        if len(selected_rows) > 0:
            row_index = selected_rows[0]
    if row_index is not None:
        selected_day = table_view.iloc[row_index]["Date"]
        st.session_state["selected_day"] = selected_day
        day_df = df[pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d") == selected_day].copy() if "date" in df.columns else pd.DataFrame()
        if not day_df.empty:
            for col in ["debit", "credit", "amount"]:
                if col in day_df.columns:
                    day_df[col] = day_df[col].apply(lambda x: float(x) if pd.notna(x) else 0.0)
            for col in ["time", "description", "category", "account", "bank_account_category", "dr_cr"]:
                if col not in day_df.columns:
                    day_df[col] = ""
            show_df = day_df[["date", "time", "description", "amount", "debit", "credit", "category", "account", "bank_account_category", "dr_cr"]].copy()
            show_df["date"] = pd.to_datetime(show_df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
            show_df.columns = ["Date", "Time", "Description", "Amount", "Debit", "Credit", "Category", "Account", "Account Category", "Dr/Cr"]
            st.subheader(f"Transactions for {selected_day}")
            st.dataframe(show_df, use_container_width=True)
        else:
            st.info(f"No transactions found for {selected_day}.")
else:
    st.info("No daily data available.")

st.subheader("Day-wise timing breakdown")
day_time_table = summary["day_time_table"]
if not day_time_table.empty:
    st.dataframe(day_time_table, use_container_width=True)
else:
    st.info("No timing breakdown available.")

st.subheader("Category details")
category_table = summary["category_table"]
category_details = summary.get("category_details", pd.DataFrame())
account_category_table = summary.get("account_category_table", pd.DataFrame())
if not category_table.empty:
    st.dataframe(category_table, use_container_width=True)
    st.bar_chart(category_table.set_index("Category")["Amount"])
    if not category_details.empty:
        st.dataframe(category_details, use_container_width=True)
    if not account_category_table.empty:
        st.subheader("Category by bank account")
        st.dataframe(account_category_table, use_container_width=True)
else:
    st.info("No category data available.")

st.subheader("Borrowed / Lent summary")
borrow_lend = summary["borrow_lend_table"]
if not borrow_lend.empty:
    st.dataframe(borrow_lend, use_container_width=True)
else:
    st.info("No borrow/lend flow detected.")

st.subheader("Transactions preview")
preview = summary["transactions_preview"]
if not preview.empty:
    st.dataframe(preview, use_container_width=True)
else:
    st.info("No transaction data found.")
