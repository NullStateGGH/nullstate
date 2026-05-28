import json
import sqlite3
from pathlib import Path
from typing import Optional


class Database:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                page_path TEXT,
                agent_id TEXT,
                referrer TEXT,
                user_agent TEXT,
                session_id TEXT,
                duration_sec REAL,
                bounced INTEGER DEFAULT 1,
                timestamp TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS audit_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                overall_score REAL,
                criteria_scores TEXT,
                issues_found TEXT,
                recommendations TEXT,
                auditor_version TEXT,
                timestamp TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS feedback_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT,
                description TEXT,
                file_changed TEXT,
                status TEXT DEFAULT 'applied',
                deploy_batch TEXT,
                timestamp TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT DEFAULT 'lead',
                source TEXT DEFAULT '',
                keywords TEXT DEFAULT '[]',
                weights TEXT DEFAULT '[]',
                tier TEXT DEFAULT 'STANDARD',
                status TEXT DEFAULT 'open',
                ai_scored INTEGER DEFAULT 0,
                ai_intent TEXT,
                ai_estimated_value REAL,
                settlement_currency TEXT DEFAULT 'USDC',
                payment_protocol TEXT DEFAULT 'x402',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT DEFAULT '',
                source TEXT DEFAULT '',
                keywords TEXT DEFAULT '[]',
                weights TEXT DEFAULT '[]',
                tier TEXT,
                ai_scored INTEGER DEFAULT 0,
                amount REAL DEFAULT 0,
                transaction_hash TEXT DEFAULT '',
                public_address TEXT DEFAULT '',
                payment_protocol TEXT DEFAULT 'x402',
                settlement_currency TEXT DEFAULT 'USDC',
                fiat_amount REAL,
                fiat_currency TEXT,
                settlement_source TEXT,
                settlement_method TEXT,
                verified INTEGER DEFAULT 0,
                local_hash TEXT,
                solana_wallet TEXT,
                timestamp TEXT DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()

    def get_tasks(self) -> list[dict]:
        cursor = self.conn.execute("SELECT * FROM tasks ORDER BY id")
        return [_decode_row(r) for r in cursor.fetchall()]

    def add_task(self, task: dict) -> int:
        cursor = self.conn.execute("""
            INSERT INTO tasks (type, source, keywords, weights, tier, status, ai_scored, ai_intent, ai_estimated_value, settlement_currency, payment_protocol)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.get("type", "lead"),
            task.get("source", ""),
            json.dumps(task.get("keywords", [])),
            json.dumps(task.get("weights", [])),
            task.get("tier", "STANDARD"),
            task.get("status", "open"),
            1 if task.get("ai_scored") else 0,
            task.get("ai_intent"),
            task.get("ai_estimated_value"),
            task.get("settlement_currency", "USDC"),
            task.get("payment_protocol", "x402"),
        ))
        self.conn.commit()
        return cursor.lastrowid

    def update_task(self, idx: int, updates: dict) -> None:
        row = self.conn.execute("SELECT id FROM tasks ORDER BY id LIMIT 1 OFFSET ?", (idx,)).fetchone()
        if row is None:
            return
        db_id = row["id"]
        sets = []
        params = []
        for key, value in updates.items():
            if key == "ai_scored":
                sets.append(f"{key} = ?")
                params.append(1 if value else 0)
            elif key in ("keywords", "weights"):
                sets.append(f"{key} = ?")
                params.append(json.dumps(value))
            else:
                sets.append(f"{key} = ?")
                params.append(value)
        params.append(db_id)
        self.conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params)
        self.conn.commit()

    def get_ledger(self) -> list[dict]:
        cursor = self.conn.execute("SELECT * FROM ledger ORDER BY id")
        return [_decode_row(r) for r in cursor.fetchall()]

    def add_ledger_entry(self, entry: dict) -> int:
        cursor = self.conn.execute("""
            INSERT INTO ledger (task_id, source, keywords, weights, tier, ai_scored, amount, transaction_hash,
                               public_address, payment_protocol, settlement_currency, fiat_amount, fiat_currency,
                               settlement_source, settlement_method, verified, local_hash, solana_wallet, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.get("task_id", ""),
            entry.get("source", ""),
            json.dumps(entry.get("keywords", [])),
            json.dumps(entry.get("weights", [])),
            entry.get("tier"),
            1 if entry.get("ai_scored") else 0,
            entry.get("amount", 0),
            entry.get("transaction_hash", ""),
            entry.get("public_address", ""),
            entry.get("payment_protocol", "x402"),
            entry.get("settlement_currency", "USDC"),
            entry.get("fiat_amount"),
            entry.get("fiat_currency"),
            entry.get("settlement_source"),
            entry.get("settlement_method"),
            1 if entry.get("verified") else 0,
            entry.get("local_hash"),
            entry.get("solana_wallet"),
            entry.get("timestamp", ""),
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_ledger_balance(self) -> float:
        cursor = self.conn.execute("SELECT COALESCE(SUM(amount), 0) FROM ledger")
        return cursor.fetchone()[0]

    def count_open_tasks(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'open'")
        return cursor.fetchone()[0]

    def count_ai_scored_tasks(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM tasks WHERE ai_scored = 1")
        return cursor.fetchone()[0]

    def migrate_from_json(self) -> dict:
        from . import config as cfg
        from .store import atomic_read
        migrated = {"tasks": 0, "ledger": 0}
        json_tasks_path = cfg.PATHS["tasks"]
        json_ledger_path = cfg.PATHS["ledger"]
        if json_tasks_path.exists():
            existing = self.get_tasks()
            if not existing:
                for t in atomic_read(json_tasks_path):
                    self.add_task(t)
                    migrated["tasks"] += 1
        if json_ledger_path.exists():
            existing_ledger = self.get_ledger()
            if not existing_ledger:
                for entry in atomic_read(json_ledger_path):
                    self.add_ledger_entry(entry)
                    migrated["ledger"] += 1
        return migrated

    def close(self):
        self.conn.close()


def _decode_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("keywords", "weights"):
        if isinstance(d.get(key), str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                d[key] = []
    return d


_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        from . import config
        _db = Database(str(config.PATHS["db"]))
        migrated = _db.migrate_from_json()
        if migrated["tasks"] or migrated["ledger"]:
            from .log import setup
            log = setup("database")
            log.info("migrated %d tasks and %d ledger entries from JSON", migrated["tasks"], migrated["ledger"])
    return _db
