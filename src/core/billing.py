"""NullState Billing Engine — prepaid credits, product registry, payment verification.
All revenue tracking flows through this module.
"""

import json
import os
import time
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.environ.get("NULLSTATE_DB_PATH", os.path.join(_BASE, "src", "core", "nullstate.db"))

PRODUCTS = {
    "solution_api": {
        "name": "Solution API Access",
        "unit": "request",
        "price_per_unit": 0.025,
        "description": "Access to AI-generated solutions per request",
    },
    "model_inference": {
        "name": "Model Inference",
        "unit": "1K tokens",
        "price_per_unit": 0.0005,
        "description": "NullState model inference per 1,000 tokens",
    },
    "email_relay": {
        "name": "Email Relay",
        "unit": "1000 emails",
        "price_per_unit": 5.00,
        "description": "Outbound email relay via NullState Mail (1000 emails)",
    },
}

_billing_lock = threading.Lock()


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS credits (
            agent_id TEXT PRIMARY KEY,
            balance_usdc REAL DEFAULT 0,
            lifetime_deposits REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS billing_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT,
            product TEXT,
            quantity REAL,
            unit_price REAL,
            total_usdc REAL,
            payment_method TEXT,
            tx_hash TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def get_credits(agent_id: str) -> float:
    with _billing_lock:
        conn = _get_conn()
        row = conn.execute("SELECT balance_usdc FROM credits WHERE agent_id = ?", (agent_id,)).fetchone()
        conn.close()
        return row["balance_usdc"] if row else 0.0


def add_credits(agent_id: str, amount_usdc: float, tx_hash: str = "") -> float:
    with _billing_lock:
        conn = _get_conn()
        conn.execute("""
            INSERT INTO credits (agent_id, balance_usdc, lifetime_deposits)
            VALUES (?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                balance_usdc = balance_usdc + ?,
                lifetime_deposits = lifetime_deposits + ?,
                updated_at = datetime('now')
        """, (agent_id, amount_usdc, amount_usdc, amount_usdc, amount_usdc))
        conn.commit()
        row = conn.execute("SELECT balance_usdc FROM credits WHERE agent_id = ?", (agent_id,)).fetchone()
        balance = row["balance_usdc"] if row else 0.0
        conn.close()
        return balance


def deduct_credits(agent_id: str, amount_usdc: float, product: str = "") -> tuple[bool, float]:
    with _billing_lock:
        conn = _get_conn()
        row = conn.execute("SELECT balance_usdc FROM credits WHERE agent_id = ?", (agent_id,)).fetchone()
        balance = row["balance_usdc"] if row else 0.0
        if balance < amount_usdc:
            conn.close()
            return False, balance
        conn.execute("""
            UPDATE credits SET balance_usdc = balance_usdc - ?, updated_at = datetime('now')
            WHERE agent_id = ?
        """, (amount_usdc, agent_id))
        conn.execute("""
            INSERT INTO billing_ledger (agent_id, product, quantity, unit_price, total_usdc, payment_method, status)
            VALUES (?, ?, ?, ?, ?, 'prepaid', 'completed')
        """, (agent_id, product, 1, amount_usdc, amount_usdc))
        conn.commit()
        row = conn.execute("SELECT balance_usdc FROM credits WHERE agent_id = ?", (agent_id,)).fetchone()
        new_balance = row["balance_usdc"] if row else 0.0
        conn.close()
        return True, new_balance


def get_product_price(product_name: str) -> float:
    product = PRODUCTS.get(product_name)
    return product["price_per_unit"] if product else 0.0


def list_products() -> dict:
    return PRODUCTS


def make_x402_challenge(agent_id: str, product: str, amount_usdc: float, task_id: str = "") -> dict:
    from core import config
    return {
        "status": 402,
        "error": "Payment Required",
        "payment_protocol": "x402",
        "settlement_currency": "USDC",
        "agent_identity_hash": agent_id,
        "product": product,
        "price_usdc": amount_usdc,
        "solana_wallet": config.SOLANA_PUBKEY,
        "payment_uri": f"x402://nullstate/{product}?agent={agent_id}&amount={amount_usdc}",
    }
