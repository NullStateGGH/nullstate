"""Track per-agent usage for tiered pricing enforcement."""

from datetime import datetime, timezone
from pathlib import Path

from . import config
from .store import atomic_read, atomic_write

USAGE_FILE = config.PATHS["backups"].parent / "usage.json"


def _ensure_file() -> None:
    if not USAGE_FILE.exists():
        atomic_write(USAGE_FILE, [])


def record_request(agent_hash: str) -> None:
    _ensure_file()
    records: list = atomic_read(USAGE_FILE)
    records.append({
        "agent": agent_hash,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    atomic_write(USAGE_FILE, records)


def count_requests_this_month(agent_hash: str) -> int:
    _ensure_file()
    records: list = atomic_read(USAGE_FILE)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return sum(
        1 for r in records
        if r.get("agent") == agent_hash
        and r.get("ts", "") >= month_start.isoformat()
    )


def get_tier(agent_hash: str) -> str:
    count = count_requests_this_month(agent_hash)
    for tier_name, tier_cfg in sorted(
        config.PRICING.items(),
        key=lambda x: x[1].get("requests_per_month", 0),
    ):
        if count <= tier_cfg.get("requests_per_month", 0):
            return tier_name
    return "free"


def remaining_requests(agent_hash: str) -> int:
    count = count_requests_this_month(agent_hash)
    tier = get_tier(agent_hash)
    limit = config.PRICING.get(tier, {}).get("requests_per_month", 0)
    return max(0, limit - count)
