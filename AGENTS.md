# AGENTS.md — NullState

NullState is an open-source payment/settlement layer for AI agents. Workspace: `/home/Nullstate-linux-vm/`.

## First-Read Architecture

- **12 systemd services + 2 timers** (all user=amjad): 9 active/running, 3 failed*.
  - **Active**: `nullstate.service` (daemon v2), `nullstate-gateway.service` (:8080 HTTPS), `nullstate-mcp.service` (:8081 HTTP), `nullstate-mail.service` (:2525 SMTP + :8083 API), `nullstate-hub.service` (:8090 MCP Hub), `nullstate-github.service` (:8091 GitHub webhook), `nullstate-model-api.service` (:8082 model API), `nullstate-hod.service` (autonomous engine), `nullstate-harvester.service` (broken — disabled)
  - **Timers**: `nullstate-feedback.timer` (3h), `nullstate-global-feedback.timer` (12h)
  - ***Failed**: `nullstate-broker.service` (broken path), `nullstate-feedback.service`, `nullstate-global-feedback.service` — check `systemctl --failed`
- **Ollama**: `nullstate:latest` model (9.6GB, 131072 context, ~12GB RAM) on `:11434`. Also `ns-unbound:latest` and `llama3.1:latest` available.
- **Model API**: FastAPI on `:8082`, per-token pricing ($0.0005/1K tokens), free 1000 tok/day — Ollama-backed
- **Billing engine** (`src/core/billing.py`): prepaid credits, 3 products ($0.025/req, $0.0005/1K tokens, $5/1000 emails), x402 challenge fallback
- **All services** set `Environment=PYTHONPATH=/home/Nullstate-linux-vm/src`
- **Tests exist** at `tests/` (5 files: test_database, test_billing, test_gateway, test_store) — pytest
- **pip install** requires `--break-system-packages`
- **Git**: project root — `.local/` and `*.db-shm/wal` gitignored. ~500+ auto-evolutionary commits exist (noisy history pattern).

## Dual Import Namespace (CRITICAL)

Two parallel import namespaces coexist — confusing imports are the #1 gotcha:

| Context | Import Root | How Invoked |
|---------|-------------|-------------|
| systemd services | `src/` via PYTHONPATH → `from core import config` | `python3 src/network/gateway.py` |
| pip package | `src/` mapped to `nullstate/` via pyproject.toml → `from nullstate.api import model_api` | `python3 -m nullstate.hod.engine` |

`core.store`, `core.database`, `network.*`, `agents.*` are NOT importable via `nullstate.*`. If an import fails, check which namespace you're in.

## Critical Rules

1. Document every tooling change in `WORKSPACE.md` — version output, install, path changes.
2. Never log/print/write private keys to stdout, markdown, or any file except `src/wallet/.env`.
3. Never edit `src/core/store.py` or `config.py` without updating ALL consumers.
4. Backups in `backups/` — auto-rotated (5 deep per file). Corrupt state files auto-restore from newest valid backup.
5. `src/wallet/.env` contains BOTH the RSA-2048 private key AND Solana keypair — chmod 600.
6. Config auto-loads `.env` on import: reads lines with `=` and calls `os.environ.setdefault()`. Multi-line PEM keys are NOT fully captured — use explicit file reader in `mandates.py` or `kya_auth.py`.
7. MCP port 8081 blocked externally by GCP VPC — access via gateway proxy `POST /mcp` on port 8080.
8. **SQLite DB** (`src/core/nullstate.db`) replaces JSON files for tasks + ledger — use `core.database.get_db()` not `core.store.atomic_read()`. `store.py` kept as fallback for usage.json.
9. **KYA enforcement** on `POST /api/v1/ap2/*` — missing/expired `X-KYA-Token` header returns 401. Get token from `GET /kya/challenge` first. Per-agent rate limit (30 req/60s).
10. **HTTPS on port 8080** — auto-generated self-signed certs in `.ssl/cert.pem` + `.ssl/key.pem`. Gateway curl needs `-k` flag.
11. **Tests** — `pytest tests/ -m unit -v` (fast, no deps), `pytest tests/` (includes gateway tests that need live services). `pytest -m slow` for integration.
12. **Lint** — `ruff check src/` (config in pyproject.toml: line-length 120, ignores E501/E402/F401/E731/F403).

## Architecture — Shared Data Layer

Tasks and ledger use `core.database.get_db()` (SQLite WAL mode). Other files (usage.json, .env) still use `core.store.atomic_read()`/`atomic_write()` — temp file → fsync → rename → `fcntl.flock(LOCK_EX)` → auto-backup (5 rotated) → corruption recovery.

Two wallet identities:
| Type | Key | Public Address |
|------|-----|----------------|
| RSA-2048 | `NULLSTATE_WALLET_PRIVATE_KEY` | `f0114f786c3b5da3c97f3c3d214638e5dddc8208779782e5b6256e71a958ce79` |
| Solana Ed25519 | `NULLSTATE_SOLANA_PRIVATE_KEY` | `2d2YcoLKSbEBY2sUR76Pfp9QifdsQQpRWYXU2TfVsALX` |

## Protocols

- **AP2** (`src/network/ap2_protocol/mandates.py`): Pydantic v2 models, RSA-2048 PKCS1v15-SHA256 signing. 3-way handshake: `/api/v1/ap2/checkout` → `/api/v1/ap2/charge`. MCP tool `execute_ap2_handshake`. Fixed price: 0.025 USDC/task.
- **Protocol Shield** (`src/network/proxy/protocol_shield.py`): `ShieldedRequest` + `normalize()` auto-detects AP2/x402/MCP/discovery.
- **KYA Auth** (`src/network/proxy/kya_auth.py`): RSA-2048 challenge/response at `GET /kya/challenge`. `verify_token()` adds TTL expiry (1h) + result cache (5min).
- **Processor v3**: dynamic `settlement_currency`, `fiat_amount`, `fiat_currency`. AP2 routes produce zero crypto gas metadata.

## Commands

| Action | Command |
|--------|---------|
| Service status | `systemctl list-units 'nullstate*' \\\| grep -v LOAD` |
| Failed services | `systemctl --failed` |
| Check Ollama | `ollama ps \\\| grep nullstate` |
| Tests (fast) | `pytest tests/ -m unit -v` |
| Tests (all) | `pytest tests/ -v` |
| Lint | `ruff check src/` |
| Start daemon | `sudo systemctl start nullstate.service` |
| Start gateway | `python3 src/network/gateway.py` |
| Start MCP | `python3 src/network/mcp_server.py` |
| Start MCP Hub | `python3 src/extensions/mcp-hub/hub.py` |
| Start GitHub app | `python3 src/extensions/github/server.py` |
| CLI | `nullstate status`, `nullstate kya`, `nullstate synth`, `nullstate serve`, `nullstate email*` |
| Gateway health | `curl -sk https://localhost:8080/health` |
| AP2 handshake | `curl -sk -X POST https://localhost:8080/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"execute_ap2_handshake","arguments":{"caller_identity":"demo"}}}'` |
| MCP Hub servers | `curl http://localhost:8090/hub/servers` |
| KYA challenge | `curl -sk https://localhost:8080/kya/challenge` |
| LLM discovery | `curl -sk https://localhost:8080/llms.txt` |
| Model API | `curl http://localhost:8082/v1/models` |
| Run processor | `python3 src/worker/processor.py` |
| Run crawler | `python3 src/agents/crawler.py` |
| Reset queue | `python3 -c "from core.database import get_db; db=get_db(); db.conn.execute('DELETE FROM tasks'); db.conn.commit(); db.conn.execute('DELETE FROM ledger'); db.conn.commit()"` |
| Demo store | `python3 examples/five_minute_store.py` |
| Generate dataset | `python3 -m nullstate.training.synthesize_dataset --count 20 --domain ap2_protocol --workers 16` |

## Gateway Endpoints (port 8080 HTTPS)

Full 14-endpoint surface. Key ones:
- `GET /health` — tasks, ledger, AI, pricing (sanitized — no wallet/port/IP leaks)
- `GET /get_solution?id=task_X` — stream result or HTTP 402 x402 challenge
- `POST /webhook/payment_settled` — on-chain settlement callback
- `POST /mcp` — proxy to MCP JSON-RPC (8081 blocked externally)
- `POST /api/v1/ap2/checkout` and `/api/v1/ap2/charge` — AP2 3-way handshake
- `GET|POST /mail/*` — proxy to Mail Server API (8083)
- `GET /api/v1/credits`, `POST /api/v1/credits/add`, `POST /api/v1/credits/deduct` — billing
- `GET /api/v1/products` — product pricing catalogue
- `POST /api/v1/analytics/track` — website analytics ingestion
- `POST /chat` — landing page chatbot with structured onboarding flow

## MCP Tools (8081, proxied via 8080/mcp)

`get_intelligence`, `submit_solution`, `get_ledger`, `get_tasks`, `execute_ap2_handshake`
Resources: `nullstate://intelligence/summary`, `nullstate://ledger`

## Mail Server (2525 SMTP + 8083 API, proxied via /mail/*)

REST API via gateway `/mail/*`. Outbound queue with 5 retries. SMTP relay configurable via env vars. Current accounts (greensol.me): `ceo` (catch-all), `support`, `admin`, `info`, `contact` — all active.

| Action | Command |
|--------|---------|
| List accounts | `curl -sk https://localhost:8080/mail/api/accounts` |
| Create account | `curl -sk -X POST https://localhost:8080/mail/api/accounts -H 'Content-Type: application/json' -d '{"email":"user@greensol.me"}'` |
| Send email | `curl -sk -X POST https://localhost:8080/mail/api/send -H 'Content-Type: application/json' -d '{"to":"user@example.com","subject":"Hi","body":"Hello"}'` |
| Process queue | `curl -sk -X POST https://localhost:8080/mail/api/queue/process` |

## AI Integration

- **Ollama** (primary): `nullstate:latest` model (gemma4:31b base, 9.6GB, 131072 ctx, ~12GB RAM). API at `http://localhost:11434`. Used by Model API + HOD engine.
- **Hugging Face**: `microsoft/Phi-3-mini-4k-instruct` (API keys in `.env`, graceful degradation when unreachable).
- **Google Gemini 2.0 Flash**: API key in `.env`, graceful degradation.
- **Graceful degradation**: All AI falls back to keyword-only when APIs unreachable.

## Key Modules

- **HOD Engine** (`src/nullstate/hod/engine.py`): Autonomous self-management — revenue tracking, growth (blog/deploy), self-healing (service/disk/response checks), emergency mode. Runs as `nullstate-hod.service`.
- **Global Feedback** (`src/nullstate/hod/global_feedback.py`): Scans 10+ sources for ecosystem signals → adaptation decisions.
- **360 Reporting** (`src/nullstate/hod/reporting.py`): Per-minute P&L for 11 departments. Cost: $0.01070000/min. Revenue: only Gateway ($0.242200 rev) and Billing ($10.00 rev) generate income.
- **Adaptation Engine** (`src/nullstate/hod/adaptation.py`): Reads decisions from DB, auto-applies config/content/deploy actions.
- **Feedback Loop** (`src/nullstate/hod/feedback_loop.py`): Website analytics + AI auditing + SEO blog + auto-deploy.
- **Landing Page Chatbot**: `POST /chat` on gateway, keyword-routed with AI enrichment. Conversations stored → fed into `ecosystem_signals`.

## Environment

- Python 3.13.5, Node v22.22.3, Git 2.47.3
- OpenCode: `/home/Nullstate-linux-vm/.opencode/bin/opencode` v1.15.10
- Ollama: running with `nullstate:latest` (9.6GB model)
- Dependencies: `cryptography`, `pydantic`, `requests`, `solders`, `fastapi`, `uvicorn`
