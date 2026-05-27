# AGENTS.md — NullState

NullState is an open-source payment/settlement layer for AI agents. Workspace: `/home/Nullstate-linux-vm/`.

## First-Read Architecture

- **6 systemd services** (all `active`, `enabled`, user=amjad): `nullstate.service` (daemon v2), `nullstate-gateway.service` (:8080 HTTPS), `nullstate-mcp.service` (:8081 HTTP), `nullstate-hub.service` (:8090 MCP Hub), `nullstate-github.service` (:8091 GitHub webhook)
- **All services** set `Environment=PYTHONPATH=/home/Nullstate-linux-vm/src`
- **No tests exist** — verify via curl against localhost endpoints
- **pip install** requires `--break-system-packages`
- **Git**: project root at `/home/Nullstate-linux-vm/` — `.local/` and `*.db-shm/wal` now gitignored

## Critical Rules

1. Document every tooling change in `WORKSPACE.md` — version output, install, path changes.
2. Never log/print/write private keys to stdout, markdown, or any file except `src/wallet/.env`.
3. Never edit `src/core/store.py` or `config.py` without updating ALL consumers.
4. Backups in `backups/` — auto-rotated (5 deep per file). Corrupt state files auto-restore from newest valid backup.
5. `src/wallet/.env` contains BOTH the RSA-2048 private key AND Solana keypair — chmod 600.
6. Config auto-loads `.env` on import: reads lines with `=` and calls `os.environ.setdefault()`. Multi-line PEM keys are NOT fully captured by this — use the explicit file reader in `mandates.py` or `kya_auth.py` instead.
7. MCP port 8081 blocked externally by GCP VPC — access via gateway proxy `POST /mcp` on port 8080.
8. **SQLite DB** (`src/core/nullstate.db`) replaces JSON files for tasks + ledger — use `core.database.get_db()` not `core.store.atomic_read()`. `store.py` kept as fallback for other files (usage.json).
9. **KYA enforcement** on `POST /api/v1/ap2/*` — missing/expired `X-KYA-Token` header returns 401. Get token from `GET /kya/challenge` first. Per-agent rate limit (30 req/60s).
10. **HTTPS on port 8080** — auto-generated self-signed certs in `.ssl/cert.pem` + `.ssl/key.pem`. Gateway curl now needs `-k` flag.

## Architecture — Shared Data Layer

Tasks and ledger use `core.database.get_db()` (SQLite WAL mode). Other files (usage.json, .env) still use `core.store.atomic_read()`/`atomic_write()` — temp file → fsync → rename → `fcntl.flock(LOCK_EX)` → auto-backup (5 rotated) → corruption recovery.

Two wallet identities:
| Type | Key | Public Address |
|------|-----|----------------|
| RSA-2048 | `NULLSTATE_WALLET_PRIVATE_KEY` | `f0114f786c3b5da3c97f3c3d214638e5dddc8208779782e5b6256e71a958ce79` |
| Solana Ed25519 | `NULLSTATE_SOLANA_PRIVATE_KEY` | `2d2YcoLKSbEBY2sUR76Pfp9QifdsQQpRWYXU2TfVsALX` |

## Protocols

- **AP2** (`src/network/ap2_protocol/mandates.py`): Pydantic v2 models (`IntentMandate`, `CartMandate`, `PaymentMandate`), RSA-2048 PKCS1v15-SHA256 signing. 3-way handshake: `/api/v1/ap2/checkout` → `/api/v1/ap2/charge`. MCP tool `execute_ap2_handshake` wraps the full cycle. Fixed price: 0.025 USDC/task.
- **Protocol Shield** (`src/network/proxy/protocol_shield.py`): `ShieldedRequest` dataclass + `normalize()` auto-detects AP2/x402/MCP/discovery from path, headers, body.
- **KYA Auth** (`src/network/proxy/kya_auth.py`): RSA-2048 challenge/response at `GET /kya/challenge`. `verify_agent()` uses RSA verification (falls back to hexdigest). `verify_token()` adds TTL expiry (1h) + result cache (5min). Pass token via `X-KYA-Token` header. **Enforced** on `POST /api/v1/ap2/*` (returns 401 on missing/expired).
- **Processor v3**: `settlement_currency`, `fiat_amount`, `fiat_currency` dynamic fields. AP2 routes produce zero crypto gas metadata.

## Commands

| Action | Command |
|--------|---------|
| Start daemon | `sudo systemctl start nullstate.service` |
| Start gateway | `python3 src/network/gateway.py` |
| Start MCP | `python3 src/network/mcp_server.py` |
| Start MCP Hub | `python3 src/extensions/mcp-hub/hub.py` |
| Start GitHub app | `python3 src/extensions/github/server.py` |
| Start HF Space | `python3 src/extensions/huggingface/space.py` |
| CLI | `nullstate status`, `nullstate kya`, `nullstate tasks`, `nullstate ap2`, `nullstate hub` |
| Docker up | `docker compose up -d` |
| Docker logs | `docker compose logs -f gateway` |
| Gateway health | `curl -k https://localhost:8080/health` |
| AP2 handshake | `curl -k -X POST https://localhost:8080/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"execute_ap2_handshake","arguments":{"caller_identity":"demo"}}}'` |
| MCP Hub servers | `curl http://localhost:8090/hub/servers` |
| KYA challenge | `curl -k https://localhost:8080/kya/challenge` |
| LLM discovery | `curl -k https://localhost:8080/llms.txt` |
| Run processor | `python3 src/worker/processor.py` |
| Run crawler | `python3 src/agents/crawler.py` |
| Reset queue | `python3 -c "from core.database import get_db; db=get_db(); db.conn.execute('DELETE FROM tasks'); db.conn.commit(); db.conn.execute('DELETE FROM ledger'); db.conn.commit()"` |
| Demo store | `python3 examples/five_minute_store.py` |

## Gateway Endpoints (port 8080)

Full 14-endpoint surface documented in `README.md`. Key ones:
- `GET /health` — tasks, ledger, Solana balance, AI, pricing
- `GET /get_solution?id=task_X` — stream result or HTTP 402 x402 challenge
- `POST /webhook/payment_settled` — on-chain settlement callback
- `POST /mcp` — proxy to MCP JSON-RPC (8081 blocked externally)
- `POST /api/v1/ap2/checkout` and `/api/v1/ap2/charge` — AP2 3-way handshake

## MCP Tools (8081, proxied via 8080/mcp)

`get_intelligence`, `submit_solution`, `get_ledger`, `get_tasks`, `execute_ap2_handshake`
Resources: `nullstate://intelligence/summary`, `nullstate://ledger`

## AI Integration

Dual-model: Hugging Face (`microsoft/Phi-3-mini-4k-instruct`) + Google Gemini 2.0 Flash. API keys in `.env`. Graceful degradation to keyword-only when APIs unreachable.

## Environment

- Python 3.13.5, Node v22.22.3, Git 2.47.3
- OpenCode: `/home/Nullstate-linux-vm/.opencode/bin/opencode` v1.15.10
- Dependencies: `cryptography`, `pydantic`, `requests`, `solders`
