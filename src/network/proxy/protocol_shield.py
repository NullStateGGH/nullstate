from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

AP2_PATHS = {"/api/v1/ap2/checkout", "/api/v1/ap2/charge"}
MCP_PATHS = {"/mcp"}
X402_PATHS = {"/get_solution", "/webhook/payment_settled"}
DISCOVERY_PATHS = {"/llms.txt", "/.well-known/ai-plugin.json"}


@dataclass
class ShieldedRequest:
    protocol: str
    method: str
    path: str
    headers: dict
    body: dict
    agent_identity: str
    client_ip: str
    raw_body: str
    query_params: dict = field(default_factory=dict)


def normalize(
    path: str,
    headers: dict,
    body: str,
    method: str = "GET",
    client_ip: str = "unknown",
) -> ShieldedRequest:
    parsed = urlparse(path)
    clean_path = parsed.path.rstrip("/") or "/"
    qs = {}
    if parsed.query:
        for part in parsed.query.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                qs[k] = v

    raw = body or ""
    body_dict: dict = {}
    if raw and method == "POST":
        try:
            import json
            body_dict = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            body_dict = {"_raw": raw}

    protocol = _detect_protocol(clean_path, headers, body_dict)
    agent = (
        headers.get("X-Agent-Identity", "")
        or headers.get("X-KYA-Token", "")
        or body_dict.get("caller_identity", "")
        or body_dict.get("params", {}).get("caller_identity", "")
        or client_ip
    )

    return ShieldedRequest(
        protocol=protocol,
        method=method,
        path=clean_path,
        headers=headers,
        body=body_dict,
        agent_identity=agent,
        client_ip=client_ip,
        raw_body=raw,
        query_params=qs,
    )


def _detect_protocol(path: str, headers: dict, body: dict) -> str:
    if path in AP2_PATHS:
        return "ap2"
    if path in MCP_PATHS:
        return "mcp"
    if path in X402_PATHS:
        return "x402"
    if path in DISCOVERY_PATHS or path.startswith("/."):
        return "discovery"
    body_str = str(body)
    if '"jsonrpc"' in body_str and '"method"' in body_str:
        return "mcp"
    if '"IntentMandate"' in body_str or '"mandate_id"' in body_str:
        return "ap2"
    if '"payment_protocol"' in body_str:
        return "x402"
    return "generic"
