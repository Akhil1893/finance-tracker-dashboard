import json
import urllib.request

import pandas as pd
import streamlit as st

from utils.storage import load_all_saved_records, load_finance_settings

st.set_page_config(page_title="Finance AI Assistant", page_icon="🤖", layout="wide")

OLLAMA_BASE_URL = "http://localhost:11434"


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


def build_chat_context():
    settings = load_finance_settings()
    df = load_all_saved_records()
    if df.empty:
        return {
            "settings": settings,
            "transactions": [],
            "summary": {},
        }

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

    return {
        "settings": settings,
        "transactions": clean.head(300).to_dict(orient="records"),
        "summary": summary,
    }


def ask_ollama(question, context):
    model_name = get_ollama_model_name()
    if not model_name:
        return None

    system_prompt = "You are a finance copilot. Use the statement data and user-defined rules in the context. Distinguish salary, self-transfer, and personal account names accurately. Never invent data. Ignore internal transfers and focus on real spend, income, salary, and balance trends."
    user_prompt = f"Question: {question}\n\nContext: {json.dumps(context, default=str)}"

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


st.title("Finance AI assistant")
st.caption("Ask questions about salary, self-transfer, account movements, spending, or savings using your uploaded statement data.")

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
        st.success("Rules saved for classification and chatbot analysis.")
    st.page_link("app.py", label="Back to analysis dashboard")

context = build_chat_context()
if not context["transactions"]:
    st.info("Upload a statement first so the chatbot can analyze real transaction data.")
    st.stop()

chat_input = st.text_input("Ask the finance assistant", placeholder="Example: Which months had salary and how much did I save after each salary?")
if chat_input:
    llm_response = ask_ollama(chat_input, context)
    if llm_response:
        st.markdown(llm_response)
    else:
        st.info("Ollama is not running or no model is available. Please install Ollama and pull a model such as llama3.2.")

st.subheader("Current transaction context")
transactions_df = pd.DataFrame(context["transactions"]).head(50)
if not transactions_df.empty:
    st.dataframe(transactions_df, use_container_width=True)
