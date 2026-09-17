import csv
import io
import re
from pathlib import Path

import pandas as pd

from utils.storage import load_finance_settings


CATEGORY_KEYWORDS = {
    "Food & Dining": ["restaurant", "food", "lunch", "dinner", "cafe", "pizza", "groceries", "grocery", "supermarket", "milk", "pharmacy", "medical", "doctor", "udupi", "kitchen"],
    "Transport": ["uber", "ola", "petrol", "train", "ticket", "fuel", "flight", "bus", "taxi", "bmtc", "metro"],
    "Bills & Utilities": ["electricity", "bill", "internet", "rent", "water", "mobile", "recharge", "subscription", "netflix", "home loan", "banking", "credit card"],
    "Shopping": ["amazon", "myntra", "flipkart", "shopping", "purchase", "order", "gift", "store", "retail"],
    "Education": ["tuition", "education", "school", "college", "course"],
    "Travel": ["travel", "hotel", "booking", "trip", "air", "cab", "outstation"],
    "Entertainment": ["movie", "cinema", "netflix", "games", "game"],
    "Transfer": ["transfer", "account transfer", "net banking", "upi funds transfer", "credit"],
}

BANK_ACCOUNT_KEYWORDS = {
    "Savings / Main": ["icici", "savings", "salary", "main"],
    "Credit Card": ["credit", "cred", "card"],
    "Bank Transfer": ["transfer", "account transfer", "upi", "funds transfer", "net banking"],
    "Cash / Other": ["cash", "other"],
    "Karnataka Bank": ["karnataka bank", "karnataka"],
    "IDFC": ["idfc"],
    "India Post": ["india post", "post"],
}


def _normalize_value(value):
    if value is None or pd.isna(value):
        return 0.0
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("₹", "").replace("Rs", "").replace("INR", "").replace("₹ ", "")
        cleaned = cleaned.replace("'", "").replace("\u2013", "-")
        if cleaned in ("", "-", "--", "_", "(", ")"):
            return 0.0
        try:
            return float(cleaned)
        except ValueError:
            cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
            if cleaned in ("", "-", "."):
                return 0.0
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
    return float(value)


def _normalize_column_name(value):
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _lookup_user_rules():
    settings = load_finance_settings()
    my_accounts = [item.strip().lower() for item in str(settings.get("my_accounts", "")).split(",") if item.strip()]
    salary_keywords = [item.strip().lower() for item in str(settings.get("salary_keywords", "salary,payroll,employer,payslip")).split(",") if item.strip()]
    self_transfer_keywords = [item.strip().lower() for item in str(settings.get("self_transfer_keywords", "self transfer,own account,internal transfer,internal fund transfer,to my own account")).split(",") if item.strip()]
    return my_accounts, salary_keywords, self_transfer_keywords


def _is_self_transfer(description, account=None):
    text = str(description or "").lower()
    account_text = str(account or "").lower()
    _, _, self_transfer_keywords = _lookup_user_rules()
    if any(keyword in text for keyword in self_transfer_keywords):
        return True
    if "self" in text and "transfer" in text:
        return True
    if account_text:
        my_accounts, _, _ = _lookup_user_rules()
        if account_text in my_accounts or any(name in account_text for name in my_accounts):
            return True
        if account_text in text or text in account_text:
            return True
    return False


def _detect_transaction_type(description, debit, credit, account=None):
    text = str(description).lower()
    debit_amt = _normalize_value(debit)
    credit_amt = _normalize_value(credit)
    my_accounts, salary_keywords, self_transfer_keywords = _lookup_user_rules()

    if any(word in text for word in salary_keywords):
        return "salary"
    if any(word in text for word in ["borrow", "borrowed", "loan taken", "lent to", "gave", "loan given"]):
        return "lent" if "lent" in text or "loan given" in text or "gave" in text else "borrowed"
    if any(keyword in text for keyword in self_transfer_keywords) or ("self" in text and "transfer" in text):
        return "self_transfer"
    if account and account.lower() in my_accounts:
        return "self_transfer"
    if any(word in text for word in ["income", "refund", "credit", "interest", "received", "repaid by"]):
        return "income"
    if debit_amt > 0:
        return "expense"
    if credit_amt > 0:
        return "income"
    return "expense"


def _classify_category(description):
    text = str(description).lower().strip()
    if not text or text in {"unknown", "nan", "-", "na"}:
        return "Other"
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    if "food" in text or "drink" in text or "restaurant" in text or "kitchen" in text or "udupi" in text:
        return "Food & Dining"
    if "fuel" in text or "petrol" in text or "metro" in text or "bmtc" in text:
        return "Transport"
    if "bill" in text or "loan" in text or "home loan" in text or "credit card" in text:
        return "Bills & Utilities"
    if "shopping" in text or "store" in text or "market" in text:
        return "Shopping"
    if "travel" in text or "trip" in text or "hotel" in text:
        return "Travel"
    if "transfer" in text or "upi" in text or "net banking" in text or "account transfer" in text:
        return "Transfer"
    return "Other"


def _classify_bank_account(account_name):
    account_text = str(account_name or "").lower().strip()
    if not account_text:
        return "Unknown Account"
    for category, keywords in BANK_ACCOUNT_KEYWORDS.items():
        if any(keyword in account_text for keyword in keywords):
            return category
    if "icici" in account_text:
        return "Savings / Main"
    if "idfc" in account_text:
        return "Credit Card"
    if "karnataka" in account_text:
        return "Karnataka Bank"
    return "Other Bank Account"


def _parse_time(value):
    if value is None or pd.isna(value):
        return pd.NaT
    text = str(value).strip()
    if not text:
        return pd.NaT
    patterns = ["%I:%M %p", "%H:%M", "%I:%M%p", "%I %p"]
    for fmt in patterns:
        try:
            return pd.to_datetime(text, format=fmt)
        except Exception:
            continue
    return pd.NaT


def _time_bucket(value):
    time_value = _parse_time(value)
    if pd.isna(time_value):
        return "Unknown"
    hour = time_value.hour
    if 5 <= hour <= 11:
        return "Morning"
    if 12 <= hour <= 16:
        return "Afternoon"
    if 17 <= hour <= 20:
        return "Evening"
    return "Night"


def _standardize_columns(df):
    df = df.copy()
    columns = {str(c).strip(): c for c in df.columns}
    normalized = {_normalize_column_name(k): v for k, v in columns.items()}
    rename_map = {}
    for canonical, aliases in {
        "date": ["date", "transaction date", "posted date", "value date", "booking date"],
        "time": ["time", "transaction time", "posted time"],
        "description": ["description", "narration", "details", "particulars", "transaction details", "beneficiary", "place", "merchant", "payee", "note", "remarks"],
        "amount": ["amount", "total amount", "value", "spent", "withdrawal amount", "credit amount", "debit amount"],
        "debit": ["debit", "withdrawal", "debit amount", "amount debit", "dr", "debit amount inr"],
        "credit": ["credit", "deposit", "credit amount", "amount credit", "cr", "credit amount inr"],
        "balance": ["balance", "running balance", "closing balance", "balance amount"],
        "category": ["category", "expense category", "transaction category", "income category"],
        "dr_cr": ["dr cr", "dr/cr", "type", "transaction type", "nature"],
        "account": ["account", "bank account", "account name", "bank account name", "account id"],
        "expense": ["expense", "is expense"],
        "income": ["income", "is income"],
    }.items():
        for alias in aliases:
            if alias in normalized:
                rename_map[normalized[alias]] = canonical
                break
    if rename_map:
        df = df.rename(columns=rename_map)
    if "date" not in df.columns:
        df["date"] = pd.NaT
    if "description" not in df.columns:
        df["description"] = "Unknown"
    if "debit" not in df.columns:
        df["debit"] = 0.0
    if "credit" not in df.columns:
        df["credit"] = 0.0
    if "amount" not in df.columns:
        df["amount"] = 0.0
    if "balance" not in df.columns:
        df["balance"] = 0.0
    if "category" not in df.columns:
        df["category"] = "Unknown"
    if "account" not in df.columns:
        df["account"] = "Unknown Account"
    if "dr_cr" not in df.columns:
        df["dr_cr"] = ""
    if "time" not in df.columns:
        df["time"] = ""
    return df


def _find_header_row(rows):
    for idx, row in enumerate(rows):
        normalized = [str(cell).strip().lower() for cell in row]
        row_text = " ".join(normalized)
        if "date" in row_text and "time" in row_text and ("amount" in row_text or "debit" in row_text or "credit" in row_text):
            return idx
    return None


def _read_excel_or_csv(file_obj):
    file_name = getattr(file_obj, "name", "")
    suffix = Path(file_name).suffix.lower()
    if suffix == ".csv":
        raw = file_obj.read()
        if isinstance(raw, bytes):
            text = raw.decode("utf-8-sig", errors="ignore")
        else:
            text = str(raw)
        rows = list(csv.reader(io.StringIO(text)))
        header_index = _find_header_row(rows)
        if header_index is None:
            return pd.read_csv(io.StringIO(text), engine="python")
        headers = rows[header_index]
        data_rows = rows[header_index + 1 :]
        return pd.DataFrame(data_rows, columns=headers)
    if suffix in {".xlsx", ".xls"}:
        raw_df = pd.read_excel(file_obj, header=None)
        for idx in range(len(raw_df)):
            row = raw_df.iloc[idx].fillna("").astype(str).tolist()
            row_text = " ".join(str(cell).strip().lower() for cell in row)
            if "date" in row_text and "time" in row_text and ("amount" in row_text or "debit" in row_text or "credit" in row_text):
                real_df = raw_df.iloc[idx + 1 :].copy()
                real_df.columns = row
                return real_df
        return raw_df
    raise ValueError("Unsupported file type for this parser")


def load_statement_file(uploaded_file):
    file_obj = uploaded_file
    file_name = getattr(file_obj, "name", "")
    suffix = Path(file_name).suffix.lower()
    try:
        if suffix == ".pdf":
            import pdfplumber
            raw = file_obj.read()
            text = ""
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                for page in pdf.pages:
                    text += "\n" + (page.extract_text() or "")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            rows = []
            for line in lines:
                parts = [p.strip() for p in re.split(r"\s{2,}|\t+", line) if p.strip()]
                if parts:
                    rows.append(parts)
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows)
        if suffix in {".csv", ".xlsx", ".xls"}:
            df = _read_excel_or_csv(file_obj)
            if df.empty:
                return df
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _prepare_transaction_frame(df):
    df = _standardize_columns(df)
    for col in ["debit", "credit", "amount", "balance"]:
        if col in df.columns:
            df[col] = df[col].apply(_normalize_value)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["description"] = df["description"].fillna("Unknown").astype(str)
    df["account"] = df["account"].fillna("Unknown Account").astype(str)
    df["category"] = df["description"].apply(_classify_category)
    df["bank_account_category"] = df["account"].apply(_classify_bank_account)
    df["transaction_type"] = df.apply(lambda row: _detect_transaction_type(row["description"], row["debit"], row["credit"], row["account"]), axis=1)
    df["self_transfer"] = df["description"].apply(lambda desc: _is_self_transfer(desc, None))
    df["time_bucket"] = df["time"].apply(_time_bucket)
    return df


def analyze_transactions(df):
    if df is None or df.empty:
        return {
            "total_spend": 0.0,
            "total_income": 0.0,
            "net_cash_flow": 0.0,
            "top_category": "None",
            "monthly_table": pd.DataFrame(),
            "daily_spend_table": pd.DataFrame(),
            "category_table": pd.DataFrame(),
            "category_details": pd.DataFrame(),
            "borrow_lend_table": pd.DataFrame(),
            "transactions_preview": pd.DataFrame(),
            "day_time_table": pd.DataFrame(),
            "salary_summary_table": pd.DataFrame(),
            "salary_txn_table": pd.DataFrame(),
            "monthly_balance_table": pd.DataFrame(),
            "account_category_table": pd.DataFrame(),
        }

    normalized = _prepare_transaction_frame(df)
    if normalized.empty:
        return {
            "total_spend": 0.0,
            "total_income": 0.0,
            "net_cash_flow": 0.0,
            "top_category": "None",
            "monthly_table": pd.DataFrame(),
            "daily_spend_table": pd.DataFrame(),
            "category_table": pd.DataFrame(),
            "category_details": pd.DataFrame(),
            "borrow_lend_table": pd.DataFrame(),
            "transactions_preview": pd.DataFrame(),
            "day_time_table": pd.DataFrame(),
            "salary_summary_table": pd.DataFrame(),
            "salary_txn_table": pd.DataFrame(),
            "monthly_balance_table": pd.DataFrame(),
            "account_category_table": pd.DataFrame(),
        }

    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    normalized = normalized.dropna(subset=["date"]).copy()
    normalized["amount"] = normalized.apply(lambda row: row["debit"] if row["debit"] > 0 else row["credit"], axis=1)

    monthly = normalized.groupby(normalized["date"].dt.to_period("M").astype(str)).agg(
        Spend=("debit", "sum"),
        Income=("credit", "sum"),
    ).reset_index().rename(columns={"date": "Month"})
    monthly["Month"] = monthly["Month"].astype(str)
    monthly["Net"] = monthly["Income"] - monthly["Spend"]

    daily = normalized.groupby(normalized["date"].dt.strftime("%Y-%m-%d")).agg(
        Date=("date", "max"),
        Spend=("debit", "sum"),
        Income=("credit", "sum"),
    ).reset_index(drop=True)
    daily["Net"] = daily["Income"] - daily["Spend"]

    category_summary = normalized.groupby("category").agg(Amount=("debit", "sum")).reset_index().sort_values("Amount", ascending=False)
    category_summary = category_summary.rename(columns={"category": "Category"})

    category_details = normalized.groupby(["category", "description"]).agg(Amount=("debit", "sum")).reset_index()

    credit_rows = normalized[normalized["credit"] > 0].copy()
    if not credit_rows.empty:
        salary_rows = credit_rows[credit_rows["description"].str.lower().str.contains("salary|payroll|employer|payslip", case=False, na=False)]
    else:
        salary_rows = pd.DataFrame()

    salary_summary = pd.DataFrame()
    if not salary_rows.empty:
        salary_summary = salary_rows.groupby(salary_rows["date"].dt.to_period("M").astype(str)).agg(
            Salary=("credit", "sum"),
            Transactions=("description", "count"),
        ).reset_index().rename(columns={"date": "Month"})
        salary_summary["Month"] = salary_summary["Month"].astype(str)

    borrow_lend = pd.DataFrame()
    if not normalized.empty:
        borrow_mask = normalized["description"].str.lower().str.contains("borrow|lent|loan given|loan taken|gave|repaid|repay|borrowed", case=False, na=False)
        borrow_lend = normalized[borrow_mask][["date", "description", "amount", "debit", "credit", "category"]].copy()
        borrow_lend = borrow_lend.sort_values("date", ascending=False).reset_index(drop=True)
        borrow_lend["Type"] = borrow_lend["description"].apply(lambda s: "Lent" if any(k in str(s).lower() for k in ["lent", "loan given", "gave"]) else "Borrowed" if any(k in str(s).lower() for k in ["borrow", "borrowed", "loan taken"]) else "Other")

    time_summary = normalized.groupby(["date", "time_bucket"]).size().reset_index(name="Transactions")
    time_summary = time_summary.rename(columns={"date": "Date"})

    account_category = normalized.groupby("bank_account_category").agg(Amount=("debit", "sum")).reset_index().sort_values("Amount", ascending=False)

    total_spend = float(normalized["debit"].sum())
    total_income = float(normalized["credit"].sum())
    net_cash_flow = total_income - total_spend
    top_category = category_summary["Category"].iloc[0] if not category_summary.empty else "None"

    preview = normalized[["date", "description", "debit", "credit", "amount", "category", "account", "bank_account_category", "transaction_type"]].copy()
    preview["date"] = preview["date"].dt.strftime("%Y-%m-%d")
    preview = preview.sort_values("date", ascending=False).reset_index(drop=True)

    balance_rows = []
    if not monthly.empty:
        for _, row in monthly.iterrows():
            balance_rows.append({
                "Month": row["Month"],
                "Income": float(row["Income"]),
                "Spend": float(row["Spend"]),
                "Net": float(row["Net"]),
            })
    monthly_balance = pd.DataFrame(balance_rows)

    return {
        "total_spend": total_spend,
        "total_income": total_income,
        "net_cash_flow": net_cash_flow,
        "top_category": top_category,
        "monthly_table": monthly,
        "daily_spend_table": daily,
        "category_table": category_summary,
        "category_details": category_details,
        "borrow_lend_table": borrow_lend,
        "transactions_preview": preview,
        "day_time_table": time_summary,
        "salary_summary_table": salary_summary,
        "salary_txn_table": salary_rows,
        "monthly_balance_table": monthly_balance,
        "account_category_table": account_category,
    }


__all__ = ["analyze_transactions", "load_statement_file"]
