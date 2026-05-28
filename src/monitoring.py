import os
import json
import time
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from core import config
from core.log import setup

log = setup("monitoring")

_monitor_lock = threading.Lock()


class MetricsCollector:
    def __init__(self, db_path: str | Path = None):
        self.db_path = Path(db_path or config.PATHS["db"])
        self._init_table()

    def _get_conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_table(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT,
                metric_value REAL,
                tags TEXT DEFAULT '{}',
                timestamp TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_metrics_name_time ON metrics(metric_name, timestamp);
        """)
        conn.commit()
        conn.close()

    def record(self, name: str, value: float, tags: dict = None):
        with _monitor_lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO metrics (metric_name, metric_value, tags) VALUES (?, ?, ?)",
                (name, value, json.dumps(tags or {})),
            )
            conn.commit()
            conn.close()

    def query(self, name: str, minutes: int = 60) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT metric_value, tags, timestamp FROM metrics WHERE metric_name = ? AND timestamp >= datetime('now', ? || ' minutes') ORDER BY timestamp",
            (name, f"-{minutes}"),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def summary(self, minutes: int = 60) -> dict:
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT metric_name,
                   COUNT(*) as count,
                   ROUND(AVG(metric_value), 6) as avg,
                   ROUND(MIN(metric_value), 6) as min,
                   ROUND(MAX(metric_value), 6) as max,
                   ROUND(SUM(metric_value), 6) as total
            FROM metrics
            WHERE timestamp >= datetime('now', ? || ' minutes')
            GROUP BY metric_name
        """, (f"-{minutes}",)).fetchall()
        conn.close()
        return {r["metric_name"]: dict(r) for r in rows}


_collector: MetricsCollector = None


def get_collector() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def record_metric(name: str, value: float, tags: dict = None):
    try:
        get_collector().record(name, value, tags)
    except Exception as e:
        log.warning("Failed to record metric %s: %s", name, e)


class HealthProbe:
    def __init__(self):
        self.last_check = 0
        self.status = "unknown"
        self.services = {}
        self.check_interval = 60

    def check_all(self):
        now = time.time()
        if now - self.last_check < self.check_interval:
            return self.services
        self.last_check = now
        services = [
            ("gateway", config.GATEWAY_PORT),
            ("mcp", config.MCP_PORT),
        ]
        for name, port in services:
            try:
                import http.client
                conn = http.client.HTTPConnection("localhost", port, timeout=3)
                conn.request("GET", "/health" if name == "gateway" else "/")
                resp = conn.getresponse()
                resp.read()
                self.services[name] = resp.status == 200
                conn.close()
            except Exception as e:
                self.services[name] = False
                log.warning("Health check failed for %s: %s", name, e)
        self.status = "healthy" if all(self.services.values()) else "degraded"
        record_metric("health.status", 1 if self.status == "healthy" else 0)
        return self.services


_health_probe = HealthProbe()
