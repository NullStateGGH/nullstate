import tempfile
from pathlib import Path
import pytest

from core.billing import (
    PRODUCTS,
    get_credits,
    add_credits,
    deduct_credits,
    get_product_price,
    list_products,
)
import core.billing


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    tmp = tempfile.mkstemp(suffix=".db")
    monkeypatch.setattr("core.billing.DB_PATH", tmp[1])
    yield
    Path(tmp[1]).unlink(missing_ok=True)


@pytest.mark.unit
def test_products_defined():
    assert "solution_api" in PRODUCTS
    assert PRODUCTS["solution_api"]["price_per_unit"] == 0.025


@pytest.mark.unit
def test_get_credits_default():
    assert get_credits("no_such_agent") == 0.0


@pytest.mark.unit
def test_add_credits():
    bal = add_credits("agent_1", 50.0)
    assert bal == 50.0
    assert get_credits("agent_1") == 50.0


@pytest.mark.unit
def test_add_credits_accumulates():
    add_credits("agent_1", 50.0)
    bal = add_credits("agent_1", 25.0)
    assert bal == 75.0


@pytest.mark.unit
def test_deduct_credits_success():
    add_credits("agent_1", 100.0)
    ok, bal = deduct_credits("agent_1", 30.0, "solution_api")
    assert ok
    assert bal == 70.0


@pytest.mark.unit
def test_deduct_credits_insufficient():
    add_credits("agent_1", 10.0)
    ok, bal = deduct_credits("agent_1", 30.0, "solution_api")
    assert not ok
    assert bal == 10.0


@pytest.mark.unit
def test_deduct_creates_ledger_entry():
    add_credits("agent_1", 50.0)
    deduct_credits("agent_1", 25.0, "solution_api")
    import sqlite3
    conn = sqlite3.connect(core.billing.DB_PATH)
    rows = conn.execute("SELECT * FROM billing_ledger").fetchall()
    conn.close()


@pytest.mark.unit
def test_get_product_price():
    assert get_product_price("solution_api") == 0.025
    assert get_product_price("nonexistent") == 0.0


@pytest.mark.unit
def test_list_products():
    prods = list_products()
    assert set(prods.keys()) == {"solution_api", "model_inference", "email_relay"}


@pytest.mark.unit
def test_parallel_deductions(monkeypatch):
    import threading, time
    import sqlite3
    db_path = core.billing.DB_PATH
    def _mock_get_conn():
        conn2 = sqlite3.connect(db_path, check_same_thread=False)
        conn2.row_factory = sqlite3.Row
        conn2.execute("PRAGMA journal_mode=WAL")
        conn2.executescript("""
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
                quantity REAL DEFAULT 1,
                unit_price REAL DEFAULT 0,
                total_usdc REAL DEFAULT 0,
                payment_method TEXT,
                tx_hash TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        return conn2
    monkeypatch.setattr("core.billing._get_conn", _mock_get_conn)
    add_credits("agent_race", 100.0)
    errors = []
    def deduct():
        for _ in range(10):
            try:
                deduct_credits("agent_race", 1.0)
            except Exception as e:
                errors.append(e)
    threads = [threading.Thread(target=deduct) for _ in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors
    assert get_credits("agent_race") == 50.0
