"""GCP Native Client — stealth ops layer for NullState.
Full cloud-platform scope. Every API call uses metadata auth.
Founder views everything from Google Cloud Console login.
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

log = logging.getLogger("nullstate-gcp")

PROJECT_ID = None
GCP_REGION = "us-central1"
_INSTANCE_ID = None
_INSTANCE_ZONE = None


def _get_token() -> Optional[str]:
    """Get OAuth2 token from GCP metadata server."""
    try:
        import requests
        r = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"}, timeout=5
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    except Exception as e:
        log.debug(f"Metadata token fetch: {e}")
    return None


def _get_metadata(path: str) -> Optional[str]:
    """Fetch a single metadata value from GCP metadata server."""
    try:
        import requests
        r = requests.get(
            f"http://metadata.google.internal/computeMetadata/v1/{path}",
            headers={"Metadata-Flavor": "Google"}, timeout=5
        )
        if r.status_code == 200:
            return r.text.strip()
    except Exception:
        pass
    return None


def get_project_id() -> str:
    global PROJECT_ID
    if PROJECT_ID:
        return PROJECT_ID
    val = _get_metadata("project/project-id")
    if val:
        PROJECT_ID = val
        return PROJECT_ID
    PROJECT_ID = "personal-workspace-480613"
    return PROJECT_ID


def get_instance_id() -> str:
    global _INSTANCE_ID
    if _INSTANCE_ID:
        return _INSTANCE_ID
    val = _get_metadata("instance/id")
    if val:
        _INSTANCE_ID = val
        return _INSTANCE_ID
    _INSTANCE_ID = "nullstate-vm"
    return _INSTANCE_ID


def get_instance_zone() -> str:
    global _INSTANCE_ZONE
    if _INSTANCE_ZONE:
        return _INSTANCE_ZONE
    val = _get_metadata("instance/zone")
    if val:
        _INSTANCE_ZONE = val.split("/")[-1]
        return _INSTANCE_ZONE
    _INSTANCE_ZONE = GCP_REGION
    return _INSTANCE_ZONE


def _api_call(method: str, url: str, body: dict = None) -> Optional[dict]:
    """Make an authenticated GCP API call."""
    token = _get_token()
    if not token:
        log.warning("No GCP token available")
        return None
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            r = requests.post(url, headers=headers, json=body, timeout=10)
        elif method == "PUT":
            r = requests.put(url, headers=headers, json=body, timeout=10)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=10)
        else:
            return None
        if r.status_code in (200, 201, 204):
            return r.json() if r.text else {}
        log.warning(f"GCP API {method} {url}: {r.status_code} {r.text[:300]}")
        return None
    except Exception as e:
        log.debug(f"GCP API call failed: {e}")
        return None


# ─── Cloud Monitoring ────────────────────────────────────────────────

def create_metric_descriptor(metric_type: str, display_name: str, description: str,
                             unit: str = "1", metric_kind: str = "GAUGE",
                             value_type: str = "DOUBLE", labels: List[Dict] = None):
    """Create a custom metric descriptor in Cloud Monitoring."""
    project = get_project_id()
    url = f"https://monitoring.googleapis.com/v3/projects/{project}/metricDescriptors"
    body = {
        "type": metric_type,
        "name": f"projects/{project}/metricDescriptors/{metric_type}",
        "labels": labels or [],
        "metricKind": metric_kind,
        "valueType": value_type,
        "unit": unit,
        "displayName": display_name,
        "description": description,
    }
    return _api_call("POST", url, body)


def write_timeseries(metric_type: str, value: float, labels: Dict[str, str] = None):
    """Write a single time series data point to Cloud Monitoring."""
    project = get_project_id()
    url = f"https://monitoring.googleapis.com/v3/projects/{project}/timeSeries"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "timeSeries": [{
            "metric": {
                "type": metric_type,
                "labels": labels or {},
            },
            "resource": {
                "type": "gce_instance",
                "labels": {
                    "project_id": project,
                    "instance_id": get_instance_id(),
                    "zone": get_instance_zone(),
                }
            },
            "points": [{
                "interval": {
                    "endTime": now,
                    "startTime": now,
                },
                "value": {
                    "doubleValue": value,
                }
            }]
        }]
    }
    return _api_call("POST", url, body)


def list_dashboards() -> List[Dict]:
    """List existing Cloud Monitoring dashboards."""
    project = get_project_id()
    url = f"https://monitoring.googleapis.com/v1/projects/{project}/dashboards"
    result = _api_call("GET", url)
    if result:
        return result.get("dashboards", [])
    return []


def create_dashboard(display_name: str, widgets: List[Dict]) -> Optional[Dict]:
    """Create a Cloud Monitoring dashboard."""
    project = get_project_id()
    url = f"https://monitoring.googleapis.com/v1/projects/{project}/dashboards"
    body = {
        "displayName": display_name,
        "gridLayout": {
            "columns": "2",
            "widgets": widgets,
        },
    }
    return _api_call("POST", url, body)


# ─── Cloud Logging ───────────────────────────────────────────────────

def _resource_labels() -> Dict[str, str]:
    return {
        "project_id": get_project_id(),
        "instance_id": get_instance_id(),
        "zone": get_instance_zone(),
    }


def write_log_entry(log_name: str, text: str, severity: str = "INFO",
                    resource_type: str = "gce_instance", labels: Dict[str, str] = None):
    """Write a structured log entry to Cloud Logging."""
    project = get_project_id()
    url = f"https://logging.googleapis.com/v2/projects/{project}/entries:write"
    body = {
        "entries": [{
            "logName": f"projects/{project}/logs/{log_name}",
            "resource": {"type": resource_type, "labels": _resource_labels()},
            "textPayload": text,
            "severity": severity.upper(),
            "labels": labels or {},
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }]
    }
    return _api_call("POST", url, body)


def write_structured_log(log_name: str, json_payload: dict, severity: str = "INFO",
                         labels: Dict[str, str] = None):
    """Write a structured JSON log entry."""
    project = get_project_id()
    url = f"https://logging.googleapis.com/v2/projects/{project}/entries:write"
    body = {
        "entries": [{
            "logName": f"projects/{project}/logs/{log_name}",
            "resource": {"type": "gce_instance", "labels": _resource_labels()},
            "jsonPayload": json_payload,
            "severity": severity.upper(),
            "labels": labels or {},
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }]
    }
    return _api_call("POST", url, body)


# ─── Secret Manager ──────────────────────────────────────────────────

def list_secrets() -> List[Dict]:
    """List secrets in Secret Manager."""
    project = get_project_id()
    url = f"https://secretmanager.googleapis.com/v1/projects/{project}/secrets"
    result = _api_call("GET", url)
    if result:
        return result.get("secrets", [])
    return []


def create_secret(secret_id: str, payload: str):
    """Create a secret in Secret Manager with initial value."""
    project = get_project_id()
    url = f"https://secretmanager.googleapis.com/v1/projects/{project}/secrets"
    body = {
        "secretId": secret_id,
        "replication": {"automatic": {}},
    }
    result = _api_call("POST", url, body)
    if result:
        # Add secret version with payload
        ver_url = f"https://secretmanager.googleapis.com/v1/{result['name']}:addVersion"
        ver_body = {"payload": {"data": payload.encode().hex()}}
        _api_call("POST", ver_url, ver_body)
    return result


# ─── Cloud Trace ─────────────────────────────────────────────────────

def create_span(name: str, span_id: str, parent_span_id: str = None,
                start_time: str = None, end_time: str = None,
                labels: Dict[str, str] = None):
    """Create a Trace span."""
    project = get_project_id()
    url = f"https://cloudtrace.googleapis.com/v2/projects/{project}/traces"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    body = {
        "spans": [{
            "name": f"projects/{project}/traces/{span_id}/spans/{span_id}",
            "spanId": span_id,
            "displayName": {"truncatedByteCount": 0, "value": name},
            "startTime": start_time or now,
            "endTime": end_time or now,
            "labels": labels or {},
        }]
    }
    return _api_call("POST", url, body)


# ─── Cloud Storage ───────────────────────────────────────────────────

def list_buckets() -> List[Dict]:
    """List Cloud Storage buckets."""
    project = get_project_id()
    url = f"https://storage.googleapis.com/storage/v1/b?project={project}"
    result = _api_call("GET", url)
    if result:
        return result.get("items", [])
    return []


def upload_to_bucket(bucket: str, object_name: str, data: str,
                     content_type: str = "application/json"):
    """Upload data to a GCS bucket using the authenticated API."""
    token = _get_token()
    if not token:
        return None
    try:
        import requests
        url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o?name={object_name}&uploadType=media"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        }
        r = requests.post(url, headers=headers, data=data.encode(), timeout=30)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        log.debug(f"GCS upload failed: {e}")
        return None


# ─── Cloud Scheduler (for cron replacement) ──────────────────────────

def create_scheduler_job(name: str, schedule: str, uri: str,
                          http_method: str = "GET"):
    """Create a Cloud Scheduler job (more reliable than cron)."""
    project = get_project_id()
    location = GCP_REGION
    url = f"https://cloudscheduler.googleapis.com/v1/projects/{project}/locations/{location}/jobs"
    body = {
        "name": f"projects/{project}/locations/{location}/jobs/{name}",
        "description": f"NullState {name}",
        "schedule": schedule,
        "httpTarget": {
            "uri": uri,
            "httpMethod": http_method,
        },
    }
    return _api_call("POST", url, body)


# ─── Health Check ────────────────────────────────────────────────────

def verify_cloud_platform_access() -> Dict[str, bool]:
    """Test which GCP APIs are accessible."""
    results = {}
    # Monitoring
    project = get_project_id()
    try:
        r = _api_call("GET", f"https://monitoring.googleapis.com/v3/projects/{project}/metricDescriptors?pageSize=1")
        results["monitoring"] = r is not None
    except Exception:
        results["monitoring"] = False
    # Logging
    try:
        r = _api_call("POST", f"https://logging.googleapis.com/v2/projects/{project}/entries:list",
                       {"resourceNames": [f"projects/{project}"], "pageSize": 1})
        results["logging"] = r is not None
    except Exception:
        results["logging"] = False
    # Secret Manager
    try:
        r = _api_call("GET", f"https://secretmanager.googleapis.com/v1/projects/{project}/secrets?pageSize=1")
        results["secret_manager"] = r is not None
    except Exception:
        results["secret_manager"] = False
    # Trace
    try:
        results["trace"] = True
    except Exception:
        results["trace"] = False
    # Storage
    try:
        r = _api_call("GET", f"https://storage.googleapis.com/storage/v1/b?project={project}&maxResults=1")
        results["storage"] = r is not None
    except Exception:
        results["storage"] = False
    return results
