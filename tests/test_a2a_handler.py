import json
import pytest

from network.a2a_handler import (
    handle_a2a_task,
    get_extension_declaration,
    check_extension_activation,
)


@pytest.mark.unit
def test_get_extension_declaration():
    decl = get_extension_declaration()
    assert decl["uri"] == "https://github.com/google-a2a/a2a-x402/v0.1"
    assert decl["required"] is False


@pytest.mark.unit
def test_check_extension_activation():
    assert check_extension_activation({}) is False
    assert check_extension_activation({"X-A2A-Extensions": ""}) is False
    assert check_extension_activation({"X-A2A-Extensions": "https://github.com/google-a2a/a2a-x402/v0.1"}) is True


@pytest.mark.unit
def test_handle_invalid_json():
    code, resp = handle_a2a_task("not json", {})
    assert code == 400
    data = json.loads(resp)
    assert "error" in data


@pytest.mark.unit
def test_handle_unknown_method():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "unknown"})
    code, resp = handle_a2a_task(body, {})
    assert code == 404
    data = json.loads(resp)
    assert data["error"]["message"] == "Unknown method: unknown"


@pytest.mark.unit
def test_handle_tasks_send_no_credits():
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tasks/send",
        "params": {"task": {"message": {"role": "user", "parts": [{"text": "hello"}]}}}
    })
    code, resp = handle_a2a_task(body, {})
    assert code == 402
    data = json.loads(resp)
    assert data["error"]["message"] == "Payment required"
    assert data["result"]["task"]["status"]["state"] == "payment-required"


@pytest.mark.unit
def test_handle_tasks_send_with_x402_extension():
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tasks/send",
        "params": {"task": {"message": {"role": "user", "parts": [{"text": "hello"}]}}}
    })
    headers = {"X-A2A-Extensions": "https://github.com/google-a2a/a2a-x402/v0.1"}
    code, resp = handle_a2a_task(body, headers)
    assert code == 402
    data = json.loads(resp)
    metadata = data["result"]["task"]["status"]["message"]["metadata"]
    assert "x402.payment.required" in metadata
    assert metadata["x402.payment.status"] == "payment-required"
    assert metadata["x402.payment.required"]["params"][0]["amount"] == "0.025"


@pytest.mark.unit
def test_handle_tasks_get():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tasks/get"})
    code, resp = handle_a2a_task(body, {})
    assert code == 200
    data = json.loads(resp)
    assert data["result"]["task"]["status"]["state"] == "completed"
