"""
NullState CLI — Terminal interface for the autonomous payment layer.

Usage:
  nullstate status          — Gateway health & metrics
  nullstate balance         — Wallet balance (ledger)
  nullstate tasks           — List recent tasks
  nullstate kya             — Get KYA token
  nullstate settle <id>     — Settle a task
  nullstate ap2             — Run AP2 handshake
  nullstate mcp <method>    — Call MCP method
  nullstate hub             — Discover + connect MCP servers
  nullstate shell           — Start NullState-enabled shell
"""

import json
import os
import sys
import time
from typing import Optional

try:
    import requests
except ImportError:
    print("Install: pip install nullstate-cli[full]", file=sys.stderr)
    sys.exit(1)

GATEWAY_URL = os.environ.get("NULLSTATE_GATEWAY_URL", "https://greensol.me/nullstate")
MCP_URL = os.environ.get("NULLSTATE_MCP_URL", "https://greensol.me/nullstate/mcp")


def api(endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
    url = f"{GATEWAY_URL}/{endpoint}"
    headers = {"User-Agent": "nullstate-cli/0.1.0"}
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=10, verify=False)
        else:
            resp = requests.post(url, headers=headers, json=data, timeout=10, verify=False)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def mcp_call(method: str, params: Optional[dict] = None) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": method, "arguments": params or {}},
    }
    try:
        headers = {"User-Agent": "nullstate-cli/0.1.0", "Content-Type": "application/json"}
        resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=10, verify=False)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def cmd_status(args):
    """Gateway health & metrics"""
    health = api("health")
    print(json.dumps(health, indent=2))


def cmd_balance(args):
    """Wallet balance"""
    balance = api("balance")
    print(json.dumps(balance, indent=2))
    if "balance" in balance:
        print(f"\n💳 Balance: {balance['balance']} USDC")


def cmd_tasks(args):
    """List recent tasks"""
    tasks = api("get_tasks")
    if isinstance(tasks, list):
        print(f"📋 {len(tasks)} tasks:")
        for t in tasks[:10]:
            print(f"  {t.get('id', '?')} — {t.get('status', '?')} — {t.get('agent_id', '?')}")
    else:
        print(json.dumps(tasks, indent=2))


def cmd_kya(args):
    """Get KYA token"""
    token = api("kya/challenge")
    print(json.dumps(token, indent=2))
    if "challenge" in token:
        print(f"\n🔑 KYA Token: {token['challenge']}:{token.get('signature', '')}")


def cmd_settle(args):
    """Settle a task"""
    task_id = args[0] if args else input("Task ID: ")
    result = api("webhook/payment_settled", "POST", {
        "task_id": task_id,
        "tx_hash": f"cli_{int(time.time())}",
        "source": "nullstate_cli",
    })
    print(f"✅ Settled {task_id}")
    print(json.dumps(result, indent=2))


def cmd_ap2(args):
    """Run AP2 handshake"""
    identity = args[0] if args else "cli_user"
    result = mcp_call("execute_ap2_handshake", {"caller_identity": identity})
    print(json.dumps(result, indent=2))


def cmd_mcp(args):
    """Call MCP method"""
    method = args[0] if args else input("Method: ")
    params = {}
    if len(args) > 1:
        try:
            params = json.loads(args[1])
        except json.JSONDecodeError:
            params = {"args": args[1]}
    result = mcp_call(method, params)
    print(json.dumps(result, indent=2))


def cmd_hub(args):
    """Discover + connect MCP servers"""
    hub_url = os.environ.get("NULLSTATE_HUB_URL", "http://localhost:8090")
    try:
        resp = requests.get(f"{hub_url}/hub/servers", timeout=10)
        servers = resp.json()
        print(f"🔍 {len(servers)} discovered MCP servers:")
        for s in servers[:10]:
            print(f"  {s.get('name', '?')} — {s.get('url', 'no url')}")
    except Exception as e:
        print(f"Error: {e}")


def cmd_shell(args):
    """Start NullState-enabled shell"""
    os.environ["NULLSTATE_ENABLED"] = "true"
    print("⛓️  NullState Shell — All commands carry payment hooks")
    print(f"Gateway: {GATEWAY_URL}")
    print()
    shell = os.environ.get("SHELL", "/bin/bash")
    os.execve(shell, [shell], os.environ)


def cmd_pricing(args):
    """Show current pricing"""
    pricing = api("pricing")
    print(json.dumps(pricing, indent=2))


def cmd_llms(args):
    """Show LLM discovery"""
    llms = api("llms.txt", "GET")
    print(llms if isinstance(llms, str) else json.dumps(llms, indent=2))


def main():
    commands = {
        "status": cmd_status,
        "balance": cmd_balance,
        "tasks": cmd_tasks,
        "kya": cmd_kya,
        "settle": cmd_settle,
        "ap2": cmd_ap2,
        "mcp": cmd_mcp,
        "hub": cmd_hub,
        "shell": cmd_shell,
        "pricing": cmd_pricing,
        "llms": cmd_llms,
    }

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print( __doc__)
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd in commands:
        commands[cmd](args)
    else:
        print(f"Unknown command: {cmd}")
        print("Run 'nullstate help' for usage")
        sys.exit(1)


if __name__ == "__main__":
    main()
