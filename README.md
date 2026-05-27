# NullState — Open-Source Payment Infrastructure for AI Agents

**Stripe for Agents.** NullState is an open-source, multi-protocol commerce layer that lets AI agents discover work, execute it, and settle payments — automatically. x402 for crypto micropayments, AP2 for enterprise mandates, both in one self-hosted stack.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg)](#quickstart)
[![MCP](https://img.shields.io/badge/MCP-compatible-6C5CE7.svg)](#mcp-tools)
[![AP2](https://img.shields.io/badge/AP2-v0.2.0-00B894.svg)](src/network/ap2_protocol/mandates.py)

---

## Quickstart

```bash
git clone https://github.com/nullstate/nullstate
cd nullstate
docker compose up -d
```

In 30 seconds, your agent economy infrastructure is running:

```bash
# Check health
curl http://localhost:8080/health

# Run the 5-minute AP2 handshake demo
curl -X POST http://localhost:8080/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"execute_ap2_handshake","arguments":{"caller_identity":"demo_agent"}}}'

# See the settlement appear in the ledger
curl http://localhost:8080/health | jq .ledger
```

## Architecture

```
                   ┌─────────────────────────────────────┐
                   │         NullState Gateway           │
                   │         (port 8080)                 │
                   │  x402  ·  AP2  ·  MCP  ·  KYA      │
                   └──────┬──────────────────────┬───────┘
                          │                      │
              ┌───────────▼──────────┐   ┌───────▼───────────┐
              │    MCP Server        │   │   Daemon Loop     │
              │    (port 8081)       │   │   crawler → sleep  │
              │    5 tools / 2 res   │   │   → processor      │
              └──────────────────────┘   └───────────────────┘
                          │                      │
                          └──────────┬───────────┘
                                     ▼
                          ┌──────────────────────┐
                          │   REVENUE LEDGER     │
                          │   atomic JSON store  │
                          │   with auto-backups  │
                          └──────────────────────┘
```

## Protocols

| Protocol | Use Case | NullState Endpoints | Status |
|----------|----------|-------------------|--------|
| **x402** | Crypto micropayments via HTTP 402 | `GET /get_solution` → 402 challenge → `POST /webhook/payment_settled` | Live |
| **AP2** | Enterprise agent-to-agent payments | `POST /api/v1/ap2/checkout` · `POST /api/v1/ap2/charge` | Live · FIDO Alliance |
| **MCP** | AI agent tool integration | `POST /mcp` (proxy to JSON-RPC on 8081) | Live · 97M monthly SDK downloads |
| **KYA** | Agent identity challenge/response | `GET /kya/challenge` | Live · RSA-2048 signed |

## Why NullState?

| Need | LangChain | AutoGPT | OpenClaw | **NullState** |
|------|-----------|---------|----------|---------------|
| LLM orchestration | ✓ | ✓ | ✓ | — |
| Agent autonomy | — | ✓ | ✓ | — |
| Cross-platform chat UI | — | — | ✓ | — |
| **Agent payments (crypto + fiat)** | — | — | — | **✓** |
| **Multi-protocol settlement** | — | — | — | **✓** |
| **Self-hosted commerce layer** | — | — | — | **✓** |

NullState **complements** these frameworks. Use LangChain for orchestration, AutoGPT for autonomy, and NullState to settle payments when work completes.

## Endpoints

### Gateway (port 8080)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Service links |
| GET | `/health` | Full status (tasks, ledger, balance, AI, pricing) |
| GET | `/pricing` | Tiered pricing + remaining requests |
| GET | `/balance` | Live Solana USDC balance |
| GET | `/mcp-info` | MCP server discovery |
| GET | `/ai-summary` | AI-scored intelligence |
| GET | `/llms.txt` | LLM discovery index |
| GET | `/.well-known/ai-plugin.json` | OpenAI plugin manifest |
| GET | `/kya/challenge` | KYA RSA challenge |
| GET | `/get_solution?id=task_X` | Stream result or 402 challenge |
| POST | `/mcp` | Proxy to MCP JSON-RPC |
| POST | `/webhook/payment_settled` | On-chain settlement callback |
| POST | `/api/v1/ap2/checkout` | AP2: IntentMandate → CartMandate |
| POST | `/api/v1/ap2/charge` | AP2: PaymentMandate → settlement |

### MCP Server (port 8081, proxied via `POST /mcp`)

| Tool | Description |
|------|-------------|
| `get_intelligence` | Market overview: tasks, ledger, balance, wallet |
| `submit_solution` | Accept AI solution, mark completed, settle 0.025 USDC |
| `get_ledger` | Full transaction history |
| `get_tasks` | Filterable task queue (open/completed/all) |
| `execute_ap2_handshake` | Full AP2 3-way handshake |

Resources: `nullstate://intelligence/summary`, `nullstate://ledger`

## Pricing

| Tier | Requests/mo | Price (USDC) |
|------|-------------|-------------|
| Free | 5 | $0 |
| Scout | 500 | $50 |
| Pro | 5,000 | $200 |
| Enterprise | 99,999 | $500 |

Rate limit: 30 req/min per IP. Body max: 64KB.

## Configuration

Copy `.env.example` to `.env` and set your keys:

```bash
cp .env.example .env
# Edit .env with your RSA-2048 key, Solana wallet, and AI API tokens
```

See `src/wallet/wallet_engine.py` and `src/wallet/solana_engine.py` for key generation.

## Development

```bash
pip install -e .
python3 src/network/gateway.py          # Gateway on :8080
python3 src/network/mcp_server.py       # MCP on :8081
python3 src/system/daemon_loop.py       # Autonomous crawler→processor loop
```

## License

MIT — see [LICENSE](LICENSE). Built for the agent economy.
