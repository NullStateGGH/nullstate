import json
import http.client
import threading
import time
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from core.config import GATEWAY_PORT, PATHS


def _get_health(port=8080):
    conn = http.client.HTTPConnection("localhost", port, timeout=5)
    conn.request("GET", "/health")
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return resp.status, data


@pytest.mark.slow
def test_gateway_health():
    status, data = _get_health()
    assert status == 200
    assert data.get("status") == "ok"
    assert "tasks" in data
    assert "ledger" in data


@pytest.mark.slow
def test_gateway_cors():
    conn = http.client.HTTPConnection("localhost", 8080, timeout=5)
    conn.request("OPTIONS", "/health", headers={"Origin": "https://greensol.me"})
    resp = conn.getresponse()
    resp.read()
    assert resp.getheader("Access-Control-Allow-Origin") == "*"
    conn.close()
