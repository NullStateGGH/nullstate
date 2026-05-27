"""NullState Telemetry Engine — Self-improving feedback loop.

Records every gateway interaction to SQLite, exports labeled training data
to Cloud Storage, and periodically invokes Gemini for quality scoring.

Part of the Chief's autonomous market-entry protocol.
"""

import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from threading import Thread, Lock

import requests

TELEMETRY_DB = os.path.join(os.path.dirname(__file__), "..", "..", "core", "telemetry.db")
GATEWAY_DB = os.path.join(os.path.dirname(__file__), "..", "..", "core", "nullstate.db")
GCS_BUCKET = "nullstate-press"
PROJECT_ID = "personal-workspace-480613"

_lock = Lock()

def get_conn():
    os.makedirs(os.path.dirname(TELEMETRY_DB), exist_ok=True)
    conn = sqlite3.connect(TELEMETRY_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS interactions (
            id TEXT PRIMARY KEY,
            agent_id TEXT,
            action TEXT,
            prompt TEXT,
            response TEXT,
            model_used TEXT,
            latency_ms INTEGER,
            success INTEGER,
            feedback_score INTEGER DEFAULT 0,
            revenue_stream TEXT,
            amount_usdc REAL DEFAULT 0,
            protocol TEXT,
            created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        CREATE INDEX IF NOT EXISTS idx_interactions_agent ON interactions(agent_id);
        CREATE INDEX IF NOT EXISTS idx_interactions_created ON interactions(created_at);

        CREATE TABLE IF NOT EXISTS training_exports (
            id TEXT PRIMARY KEY,
            exported_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            record_count INTEGER,
            export_path TEXT
        );

        CREATE TABLE IF NOT EXISTS quality_scores (
            id TEXT PRIMARY KEY,
            interaction_id TEXT,
            score INTEGER,
            reasoning TEXT,
            scorer_model TEXT,
            scored_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
    """)
    conn.commit()
    conn.close()

def record_interaction(agent_id, action, prompt, response, model_used, latency_ms, success, revenue_stream=None, amount_usdc=0, protocol=None):
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO interactions (id, agent_id, action, prompt, response, model_used, latency_ms, success, revenue_stream, amount_usdc, protocol) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), agent_id, action, prompt[:10000] if prompt else None,
             response[:10000] if response else None, model_used, latency_ms, 1 if success else 0,
             revenue_stream, amount_usdc, protocol)
        )
        conn.commit()
        conn.close()

def export_training_data(limit=500):
    """Export recent quality-scored interactions for model training."""
    with _lock:
        conn = get_conn()
        rows = conn.execute("""
            SELECT i.*, q.score as quality_score, q.reasoning
            FROM interactions i
            LEFT JOIN quality_scores q ON q.interaction_id = i.id
            WHERE i.success = 1 AND i.prompt IS NOT NULL
            ORDER BY i.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        conn.close()

    records = [dict(r) for r in rows]
    if not records:
        return None

    export_id = str(uuid.uuid4())
    export_path = f"training/exports/{export_id}.jsonl"

    # Write to local temp
    local_path = f"/tmp/telemetry_export_{export_id}.jsonl"
    with open(local_path, "w") as f:
        for r in records:
            f.write(json.dumps({
                "instruction": r.get("prompt", ""),
                "response": r.get("response", ""),
                "agent_id": r.get("agent_id"),
                "action": r.get("action"),
                "model": r.get("model_used"),
                "latency_ms": r.get("latency_ms"),
                "quality_score": r.get("quality_score"),
                "revenue_stream": r.get("revenue_stream"),
                "amount_usdc": r.get("amount_usdc"),
                "protocol": r.get("protocol"),
                "timestamp": r.get("created_at"),
            }) + "\n")

    return local_path, export_path, len(records)

def score_with_gemini(prompt, response, api_key):
    """Use Gemini to score response quality on 1-5 scale."""
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": f"Rate the quality of this AI agent response on a scale of 1-5 (1=bad, 5=excellent). Return only a JSON object with 'score' (int) and 'reasoning' (string).\n\nPROMPT: {prompt[:2000]}\n\nRESPONSE: {response[:2000]}"}]}]
            },
            timeout=15
        )
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Parse JSON from response
        score_data = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
        return score_data.get("score", 3), score_data.get("reasoning", "")
    except Exception:
        return 3, "auto-scored (fallback)"

def score_pending_interactions(api_key, batch_size=20):
    """Score unsocred interactions using Gemini."""
    with _lock:
        conn = get_conn()
        rows = conn.execute("""
            SELECT i.id, i.prompt, i.response
            FROM interactions i
            LEFT JOIN quality_scores q ON q.interaction_id = i.id
            WHERE q.id IS NULL AND i.prompt IS NOT NULL AND i.response IS NOT NULL
            LIMIT ?
        """, (batch_size,)).fetchall()
        conn.close()

    for row in rows:
        score, reasoning = score_with_gemini(row["prompt"], row["response"], api_key)
        with _lock:
            conn = get_conn()
            conn.execute(
                "INSERT INTO quality_scores (id, interaction_id, score, reasoning, scorer_model) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), row["id"], score, reasoning[:500], "gemini-2.5-flash")
            )
            conn.commit()
            conn.close()

    return len(rows)

def upload_to_gcs(local_path, gcs_path):
    """Upload a file to Cloud Storage using the GCE metadata token."""
    token = None
    try:
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=5
        )
        token = r.json()["access_token"]
    except Exception:
        return False

    try:
        with open(local_path, "rb") as f:
            r = requests.post(
                f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o?uploadType=media&name={gcs_path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/jsonl",
                },
                data=f,
                timeout=30
            )
        return r.ok
    except Exception:
        return False

def run_telemetry_worker(api_key, interval_seconds=3600):
    """Background worker that scores interactions and exports training data."""
    while True:
        try:
            scored = score_pending_interactions(api_key)
            exported = export_training_data()
            if exported:
                local_path, gcs_path, count = exported
                uploaded = upload_to_gcs(local_path, gcs_path)
                print(f"[telemetry] Scored: {scored}, Exported: {count}, Uploaded: {uploaded}")
        except Exception as e:
            print(f"[telemetry] Error: {e}")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    init_db()
    api_key = os.environ.get("NULLSTATE_GOOGLE_API_KEY", "")
    print(f"[telemetry] Engine initialized. Scoring pending interactions...")
    scored = score_pending_interactions(api_key)
    print(f"[telemetry] Scored {scored} interactions. Starting worker loop...")
    run_telemetry_worker(api_key, interval_seconds=3600)
