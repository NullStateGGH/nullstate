"""NullState Google Telemetry — native GCP instrumentation.
Zero-dependency Google Cloud Observability for all NullState services.
Founder views everything via Google Cloud Console login.

Integrated into: gateway, model API, HOD, worker processes.

Metrics:
  nullstate/tasks/processed        — task throughput
  nullstate/tasks/pending           — queue depth
  nullstate/ledger/transactions     — payment settlement count
  nullstate/ledger/volume_usdc      — settlement volume in USDC
  nullstate/model/tokens_generated  — model API token count
  nullstate/model/api_calls         — model API request count
  nullstate/revenue/usdc            — earned revenue
  nullstate/costs/compute           — infrastructure costs
  nullstate/system/uptime           — service uptime
  nullstate/system/cpu_load         — CPU utilization
  nullstate/system/memory_used_gb   — RAM usage
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

log = logging.getLogger("nullstate-telemetry")

# Metric type prefix (prefix must be custom.googleapis.com/)
METRIC_PREFIX = "custom.googleapis.com/nullstate"

METRICS = {
    "tasks_processed": f"{METRIC_PREFIX}/tasks/processed",
    "tasks_pending": f"{METRIC_PREFIX}/tasks/pending",
    "ledger_transactions": f"{METRIC_PREFIX}/ledger/transactions",
    "ledger_volume_usdc": f"{METRIC_PREFIX}/ledger/volume_usdc",
    "model_tokens": f"{METRIC_PREFIX}/model/tokens_generated",
    "model_api_calls": f"{METRIC_PREFIX}/model/api_calls",
    "revenue_usdc": f"{METRIC_PREFIX}/revenue/usdc",
    "costs_compute": f"{METRIC_PREFIX}/costs/compute",
    "system_uptime": f"{METRIC_PREFIX}/system/uptime",
    "system_cpu_load": f"{METRIC_PREFIX}/system/cpu_load",
    "system_memory_gb": f"{METRIC_PREFIX}/system/memory_used_gb",
}

_SERVICE_LABEL = os.environ.get("NULLSTATE_SERVICE", "unknown")
_INSTANCE_ID = os.environ.get("HOSTNAME", "nullstate-vm")


def _import_gcp():
    """Lazy import gcp_client — fail silently if not available."""
    try:
        from extensions.google import gcp_client
        return gcp_client
    except ImportError:
        return None


def _write(metric_key: str, value: float, extra_labels: Dict[str, str] = None):
    """Write a metric value to Cloud Monitoring (non-blocking, silent fail)."""
    try:
        gcp = _import_gcp()
        if not gcp:
            return
        labels = {"service": _SERVICE_LABEL, "instance": _INSTANCE_ID}
        if extra_labels:
            labels.update(extra_labels)
        gcp.write_timeseries(METRICS[metric_key], value, labels)
    except Exception:
        pass


def _log(log_name: str, message: str, severity: str = "INFO",
         payload: dict = None, extra_labels: Dict[str, str] = None):
    """Write a log entry (non-blocking, silent fail)."""
    try:
        gcp = _import_gcp()
        if not gcp:
            return
        labels = {"service": _SERVICE_LABEL}
        if extra_labels:
            labels.update(extra_labels)
        if payload:
            payload["_service"] = _SERVICE_LABEL
            payload["_instance"] = _INSTANCE_ID
            gcp.write_structured_log(log_name, payload, severity, labels)
        else:
            gcp.write_log_entry(log_name, message, severity, labels)
    except Exception:
        pass


# ─── Public API ──────────────────────────────────────────────────────


def init():
    """Initialize GCP telemetry connection. Called once at service startup."""
    gcp = _import_gcp()
    if not gcp:
        log.warning("GCP client not available — telemetry disabled")
        return False
    try:
        gcp.get_project_id()
        log.info("GCP telemetry initialized for project: %s", gcp.PROJECT_ID)
        # Log startup
        _log("nullstate-system", "Service started",
             payload={"event": "startup", "service": _SERVICE_LABEL,
                      "timestamp": datetime.now(timezone.utc).isoformat()})
        return True
    except Exception as e:
        log.warning("GCP telemetry init failed: %s", e)
        return False


# ─── Task Metrics ────────────────────────────────────────────────────

def record_task_processed(tier: str = "standard", protocol: str = "x402"):
    _write("tasks_processed", 1, {"tier": tier, "protocol": protocol})
    _log("nullstate-tasks", "Task processed",
         payload={"event": "task_processed", "tier": tier, "protocol": protocol})


def record_task_pending(count: int):
    _write("tasks_pending", float(count))


# ─── Ledger / Payment Metrics ────────────────────────────────────────

def record_payment(amount_usdc: float, protocol: str = "x402", source: str = "gateway"):
    _write("ledger_transactions", 1, {"protocol": protocol, "source": source})
    _write("ledger_volume_usdc", amount_usdc, {"protocol": protocol})
    _log("nullstate-payments", f"Payment: {amount_usdc} USDC via {protocol}",
         payload={"event": "payment_settled", "amount": amount_usdc,
                  "protocol": protocol, "source": source})


# ─── Model API Metrics ───────────────────────────────────────────────

def record_model_call(tokens: int, latency_ms: float = 0):
    _write("model_api_calls", 1)
    _write("model_tokens", float(tokens))
    _log("nullstate-model", f"Model inference: {tokens} tokens",
         payload={"event": "model_inference", "tokens": tokens,
                  "latency_ms": latency_ms})


# ─── Revenue / Cost Metrics ──────────────────────────────────────────

def record_revenue(amount_usdc: float, source: str = "model_api"):
    _write("revenue_usdc", amount_usdc)
    _log("nullstate-revenue", f"Revenue: ${amount_usdc:.6f} from {source}",
         payload={"event": "revenue", "amount": amount_usdc, "source": source})


def record_cost(amount_usdc: float, category: str = "compute"):
    _write("costs_compute", amount_usdc, {"category": category})


# ─── System Health Metrics ───────────────────────────────────────────

def record_heartbeat():
    """Called every 60s by each service to show it's alive."""
    _write("system_uptime", 1)
    _log("nullstate-health", "Heartbeat",
         payload={"event": "heartbeat", "service": _SERVICE_LABEL})


def record_system_resources(cpu_load: float, memory_gb: float):
    _write("system_cpu_load", cpu_load)
    _write("system_memory_gb", memory_gb)


# ─── Error Tracking ──────────────────────────────────────────────────

def record_error(error_type: str, message: str, stack: str = None):
    _log("nullstate-errors", message, severity="ERROR",
         payload={"event": "error", "error_type": error_type,
                  "message": message, "stack": stack or ""})


# ─── AP2 / KYA Protocol Metrics ──────────────────────────────────────

def record_kya_auth(agent_id: str, success: bool):
    _log("nullstate-kya", f"KYA auth for {agent_id}: {'success' if success else 'failure'}",
         payload={"event": "kya_auth", "agent_id": agent_id, "success": success})


def record_ap2_handshake(agent_id: str, step: str, success: bool):
    _log("nullstate-ap2", f"AP2 {step} for {agent_id}: {'success' if success else 'failure'}",
         payload={"event": f"ap2_{step}", "agent_id": agent_id, "success": success})


# ─── Dataset / Training Metrics ──────────────────────────────────────

def record_dataset_push(pair_count: int, size_kb: float):
    _log("nullstate-dataset", f"Dataset pushed: {pair_count} pairs, {size_kb:.1f}KB",
         payload={"event": "dataset_push", "pair_count": pair_count, "size_kb": size_kb})


# ─── Initialize on import ────────────────────────────────────────────
# init() called explicitly by each service at startup
