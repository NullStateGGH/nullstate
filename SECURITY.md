# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |

## Architecture

NullState is **non-custodial** by design. Private keys exist only in `src/wallet/.env` (chmod 600) and are never transmitted, logged, or stored remotely. Identity validation uses RSA-2048 PKCS1v15-SHA256 challenge/response (KYA protocol) — no user data or secrets are collected.

### Key Security Properties

- **No user data collection.** NullState processes agent-to-agent transactions only. No emails, passwords, or PII are stored.
- **Local-only identity validation.** RSA keys stay on the machine. KYA tokens are time-bound (1h TTL) and scoped to agent identity.
- **File-system isolation.** `fcntl.flock(LOCK_EX)` on all shared state files. SQLite WAL mode with synchronous=NORMAL for the database.
- **No external dependencies for crypto.** Uses stdlib `ssl` + `cryptography` library for all signing/verification.
- **TLS on all external ports.** Gateway port 8080 runs HTTPS with auto-generated self-signed certificates.

## Reporting a Vulnerability

If you discover a security vulnerability in NullState, please report it by emailing **agent@nullstate.ai**.

We will acknowledge receipt within 48 hours and provide a timeline for a fix. Please do not disclose the vulnerability publicly until we have addressed it.

### What to include

- Description of the vulnerability
- Steps to reproduce
- Affected version(s)
- Any proof-of-concept code (if applicable)

## Threat Model

| Threat | Mitigation |
|--------|------------|
| Private key theft | File at `src/wallet/.env` chmod 600, never logged, never transmitted |
| Token replay | KYA tokens time-bound to 1h TTL, verified on every request |
| DoS via impersonation | Per-agent rate limiting (30 req/60s window) on all KYA-protected endpoints |
| Corrupt state file | SQLite WAL mode + JSON backup rotation (5 deep) |
| Solana RPC spoofing | On-chain tx verification via `verify_transaction` |
| MCP port exposure | Port 8081 blocked by GCP VPC, proxied through gateway `/mcp` (authenticated) |

## Dependencies

- `cryptography` — RSA signing/verification
- `pydantic` — mandate model validation
- `solders` — Solana transaction parsing
- `requests` — HTTP crawling only
- All other modules are Python stdlib

## Compliance

NullState does not process, store, or transmit user personal data. It operates as a local agent-to-agent settlement pipeline with no cloud storage of identities or transaction history beyond the local SQLite database and JSON backup files.
