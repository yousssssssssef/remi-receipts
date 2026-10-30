"""Step 3: save a parsed receipt. SQLite stands in for Remi's real database."""
import json
import sqlite3

from .models import Receipt

SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY,
    store_name TEXT, store_address TEXT,
    purchase_date TEXT, purchase_time TEXT,
    currency TEXT, subtotal REAL, tax REAL, total REAL,
    payment_method TEXT,
    needs_review INTEGER NOT NULL,
    warnings TEXT, ocr_text TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS receipt_items (
    id INTEGER PRIMARY KEY,
    receipt_id INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    name TEXT NOT NULL, category TEXT, raw_text TEXT,
    quantity REAL, unit TEXT, unit_price REAL, total_price REAL, discount REAL,
    barcode TEXT, department TEXT
);
"""


def save_receipt(db_path: str, receipt: Receipt, warnings: list[str], ocr_lines: list[str]) -> int:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        with conn:
            cur = conn.execute(
                "INSERT INTO receipts (store_name, store_address, purchase_date, purchase_time, currency,"
                " subtotal, tax, total, payment_method, needs_review, warnings, ocr_text)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (receipt.store_name, receipt.store_address, receipt.purchase_date, receipt.purchase_time,
                 receipt.currency, receipt.subtotal, receipt.tax, receipt.total, receipt.payment_method,
                 int(bool(warnings or receipt.notes)), json.dumps(warnings + receipt.notes), "\n".join(ocr_lines)),
            )
            receipt_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO receipt_items (receipt_id, name, category, raw_text, quantity, unit,"
                " unit_price, total_price, discount, barcode, department) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(receipt_id, i.name, i.category, i.raw_text, i.quantity, i.unit,
                  i.unit_price, i.total_price, i.discount, i.barcode, i.department) for i in receipt.items],
            )
        return receipt_id
    finally:
        conn.close()
