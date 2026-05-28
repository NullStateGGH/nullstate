import tempfile
from pathlib import Path
import pytest

from core.database import Database, get_db


@pytest.fixture
def db():
    tmp = tempfile.mkstemp(suffix=".db")
    d = Database(tmp[1])
    yield d
    d.close()
    Path(tmp[1]).unlink(missing_ok=True)


@pytest.mark.unit
def test_add_and_get_tasks(db):
    task = {"type": "test", "source": "ci", "keywords": ["ai"], "tier": "STANDARD"}
    tid = db.add_task(task)
    tasks = db.get_tasks()
    assert len(tasks) >= 1
    assert tasks[-1]["source"] == "ci"


@pytest.mark.unit
def test_add_and_get_ledger(db):
    entry = {"task_id": "1", "amount": 42.0, "settlement_currency": "USDC"}
    eid = db.add_ledger_entry(entry)
    ledger = db.get_ledger()
    assert len(ledger) >= 1


@pytest.mark.unit
def test_ledger_balance(db):
    db.add_ledger_entry({"task_id": "1", "amount": 100.0})
    db.add_ledger_entry({"task_id": "2", "amount": 50.0})
    assert db.get_ledger_balance() == 150.0


@pytest.mark.unit
def test_count_open_tasks(db):
    db.add_task({"type": "lead", "status": "open"})
    db.add_task({"type": "lead", "status": "closed"})
    assert db.count_open_tasks() == 1


@pytest.mark.unit
def test_count_ai_scored(db):
    db.add_task({"type": "lead", "ai_scored": True})
    db.add_task({"type": "lead", "ai_scored": False})
    assert db.count_ai_scored_tasks() == 1


@pytest.mark.unit
def test_singleton_get_db(monkeypatch):
    from core.config import PATHS as REAL_PATHS
    import copy
    tmp = tempfile.mkstemp(suffix=".db")
    fake_paths = copy.deepcopy(REAL_PATHS)
    fake_paths["db"] = tmp[1]
    monkeypatch.setattr("core.config.PATHS", fake_paths)
    d1 = get_db()
    d2 = get_db()
    assert d1 is d2
    d1.close()
    Path(tmp[1]).unlink(missing_ok=True)
