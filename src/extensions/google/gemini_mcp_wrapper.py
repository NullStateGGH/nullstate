"""
NullState Gemini MCP Wrapper — Inject NullState payment into Gemini function calling.

Target: "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
Wraps every function call with NullState payment layer.
"""

import json
import os
import time
import urllib.request
from typing import Optional

GATEWAY_URL = os.environ.get("NULLSTATE_GATEWAY_URL", "https://greensol.me/nullstate")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def kya_headers() -> dict:
    """Get KYA auth headers from NullState gateway."""
    try:
        req = urllib.request.Request(f"{GATEWAY_URL}/kya/challenge")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return {"X-KYA-Token": f"{data['challenge']}:{data['signature']}"}
    except Exception:
        return {}


def wrap_gemini_request(prompt: str, tools: list, model: str = "gemini-2.0-flash") -> dict:
    """
    Send a Gemini request with NullState-wrapped function calls.

    Each tool call automatically incurs a micro-payment.
    """
    headers = {
        "Content-Type": "application/json",
        "X-NullState-Enabled": "true",
    }
    headers.update(kya_headers())

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"

    # Inject NullState payment tool
    nullstate_tool = {
        "name": "nullstate_pay",
        "description": "Process a NullState micro-payment for this function call",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Payment amount in USDC", "default": 0.001},
                "tool_name": {"type": "string", "description": "Name of the tool being called"},
            },
            "required": ["tool_name"],
        },
    }

    all_tools = [nullstate_tool] + tools

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"functionDeclarations": all_tools}],
        "toolConfig": {"functionCallingConfig": {"mode": "auto"}},
    }

    payload = json.dumps(body).encode()
    req = urllib.request.Request(url, data=payload, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return process_gemini_response(result)
    except Exception as e:
        return {"error": str(e)}


def process_gemini_response(response: dict) -> dict:
    """Process Gemini response, routing through NullState payment layer."""
    candidates = response.get("candidates", [])
    for cand in candidates:
        content = cand.get("content", {})
        parts = content.get("parts", [])
        for part in parts:
            fc = part.get("functionCall", {})
            if fc.get("name") == "nullstate_pay":
                args = fc.get("args", {})
                amount = args.get("amount", 0.001)
                tool_name = args.get("tool_name", "unknown")
                task_id = f"gemini_{tool_name}_{int(time.time())}"

                # Process payment
                try:
                    payment = urllib.request.Request(
                        f"{GATEWAY_URL}/webhook/payment_settled",
                        data=json.dumps({
                            "task_id": task_id,
                            "tx_hash": f"gm_{int(time.time())}",
                            "amount": amount,
                            "source": f"gemini/{tool_name}",
                        }).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(payment, timeout=10):
                        pass
                    part["functionCall"]["name"] = f"{tool_name}_paid"
                    part["functionCall"]["args"]["payment_tx"] = task_id
                except Exception as e:
                    part["functionCall"]["error"] = str(e)

    return response


def test():
    """Quick test of the wrapper."""
    tools = [
        {
            "name": "search_web",
            "description": "Search the web for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        }
    ]
    result = wrap_gemini_request("Search for AI agent payment systems", tools)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    test()
