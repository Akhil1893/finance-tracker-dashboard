import pandas as pd
import streamlit as st

st.set_page_config(page_title="Day Details", page_icon="🗓️", layout="wide")

if st.button("← Back to overview"):
    st.switch_page("app.py")

if "selected_day" not in st.session_state:
    st.info("No date selected. Go back to the dashboard and choose a day.")
    st.stop()

selected_day = st.session_state.get("selected_day")
df = st.session_state.get("active_df", pd.DataFrame())

if df.empty:
    st.warning("No transaction data is available for this day.")
    st.stop()

if "date" in df.columns:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    day_df = df[df["date"].dt.strftime("%Y-%m-%d") == selected_day].copy()
else:
    day_df = pd.DataFrame()

if day_df.empty:
    st.warning(f"No transactions were found for {selected_day}.")
    st.stop()

st.title(f"Transactions for {selected_day}")

for col in ["debit", "credit", "amount"]:
    if col in day_df.columns:
        day_df[col] = day_df[col].apply(lambda x: float(x) if pd.notna(x) else 0.0)

for col in ["date", "time", "description", "amount", "debit", "credit", "category", "dr_cr", "bank_account_category", "account"]:
    if col not in day_df.columns:
        day_df[col] = ""

spend_total = float(day_df.get("debit", 0).sum())
income_total = float(day_df.get("credit", 0).sum())
net_total = income_total - spend_total

cols = st.columns(3)
cols[0].metric("Spend", f"₹{spend_total:,.0f}")
cols[1].metric("Income", f"₹{income_total:,.0f}")
cols[2].metric("Net", f"₹{net_total:,.0f}")

show_df = day_df[["date", "time", "description", "amount", "debit", "credit", "category", "account", "bank_account_category"]].copy()
show_df["date"] = pd.to_datetime(show_df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
show_df.columns = ["Date", "Time", "Description", "Amount", "Debit", "Credit", "Category", "Account", "Account Category"]

st.dataframe(show_df, use_container_width=True)
