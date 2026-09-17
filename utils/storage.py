import json
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "finance_data.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_database():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS uploaded_months (
            year_month TEXT PRIMARY KEY,
            month_label TEXT NOT NULL,
            records_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def save_month_records(month_key, df):
    ensure_database()
    records = df.copy()
    if "date" in records.columns:
        records["date"] = pd.to_datetime(records["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    payload = records.to_dict(orient="records")
    month_label = pd.to_datetime(f"{month_key}-01", errors="coerce")
    display_month = month_label.strftime("%b %Y") if pd.notna(month_label) else month_key
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO uploaded_months (year_month, month_label, records_json, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(year_month) DO UPDATE SET
                month_label = excluded.month_label,
                records_json = excluded.records_json,
                updated_at = datetime('now')
            """,
            (month_key, display_month, json.dumps(payload)),
        )
        conn.commit()


def list_saved_months():
    ensure_database()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT year_month, month_label FROM uploaded_months ORDER BY year_month DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def load_month_records(month_key):
    ensure_database()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT records_json FROM uploaded_months WHERE year_month = ?",
            (month_key,),
        ).fetchone()
    if row is None:
        return pd.DataFrame()
    payload = json.loads(row["records_json"])
    return pd.DataFrame(payload)


def load_all_saved_records():
    ensure_database()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT records_json FROM uploaded_months ORDER BY year_month ASC"
        ).fetchall()
    all_payload = []
    for row in rows:
        payload = json.loads(row["records_json"])
        if payload:
            all_payload.extend(payload)
    return pd.DataFrame(all_payload)


def delete_month_records(month_key):
    ensure_database()
    with get_connection() as conn:
        conn.execute("DELETE FROM uploaded_months WHERE year_month = ?", (month_key,))
        conn.commit()


def delete_all_month_records():
    ensure_database()
    with get_connection() as conn:
        conn.execute("DELETE FROM uploaded_months")
        conn.commit()


def save_finance_settings(settings):
    ensure_database()
    payload = json.dumps(settings)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO finance_settings (key, value) VALUES ('rules', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (payload,),
        )
        conn.commit()


def load_finance_settings():
    ensure_database()
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS finance_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute("SELECT value FROM finance_settings WHERE key = 'rules'").fetchone()
    if row is None:
        return {
            "my_accounts": "",
            "salary_keywords": "salary,payroll,employer,payslip",
            "self_transfer_keywords": "self transfer,own account,internal transfer,internal fund transfer,to my own account",
        }
    try:
        data = json.loads(row["value"])
        return {
            "my_accounts": data.get("my_accounts", ""),
            "salary_keywords": data.get("salary_keywords", "salary,payroll,employer,payslip"),
            "self_transfer_keywords": data.get("self_transfer_keywords", "self transfer,own account,internal transfer,internal fund transfer,to my own account"),
        }
    except Exception:
        return {
            "my_accounts": "",
            "salary_keywords": "salary,payroll,employer,payslip",
            "self_transfer_keywords": "self transfer,own account,internal transfer,internal fund transfer,to my own account",
        }
