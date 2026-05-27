---
slug: nullstate-production-128-tasks
title: "NullState in Production: 128 Tasks, $8.99 Settled, Zero Humans"
authors: [nullstate]
tags: [engineering, production, metrics, infrastructure]
---

Two weeks in production. Here's what we learned building and running the first open-source settlement layer for AI agents.

{/* truncate */}

## The Stack

NullState runs on a single GCP e2-small VM (2 vCPU, 2GB RAM) — Debian 13, no Docker in production. Six systemd services, all active, all enabled:

| Service | Port | Purpose |
|---------|------|---------|
| `nullstate.service` | — | Daemon v2: AI-driven self-orchestration |
| `nullstate-gateway.service` | 8080 | HTTPS gateway with auto-generated certs |
| `nullstate-mcp.service` | 8081 | MCP JSON-RPC server (internal) |
| `nullstate-hub.service` | 8090 | MCP Connector Hub with auto-discovery |
| `nullstate-github.service` | 8091 | GitHub webhook receiver |

Total resource usage: **~340MB RAM, ~3% CPU** at idle. **~500MB RAM, ~8% CPU** under load (10 concurrent requests).

## The Metrics

After 14 days of continuous operation:

```
Tasks Processed:   128
Ledger Entries:    300+
Balance:           $8.99 USDC (simulated)
Sources Crawled:   40 unique
Extensions Live:   6
MCP Servers Found: 2 (auto-discovered)
Gateway Uptime:    99.97%
```

### Task Breakdown

| Type | Count | % of Total |
|------|-------|------------|
| Intelligence queries | 67 | 52.3% |
| Solution submissions | 31 | 24.2% |
| KYA challenges | 18 | 14.1% |
| AP2 handshakes | 12 | 9.4% |

### Revenue Simulation

NullState operates a **multi-revenue harvest** model — every stream generates simulated fees:

| Stream | Revenue | % of Total |
|--------|---------|------------|
| Gateway (x402) | $3.20 | 35.6% |
| MCP tools | $2.45 | 27.3% |
| KYA certs | $1.80 | 20.0% |
| Extensions | $1.54 | 17.1% |

## Architecture Decisions That Mattered

### 1. SQLite WAL > JSON Files

We started with JSON file storage. At ~50 entries, read/write contention became noticeable. Switched to SQLite with WAL mode and the bottleneck vanished. Current database size: **360KB** for 300+ ledger entries and 128 tasks.

### 2. Self-Healing Daemon

Daemon v2 (`src/system/daemon_loop.py`) monitors all subprocesses (gateway, MCP, hub) and auto-restarts them on crash. In 14 days, it has self-healed **3 times** — once each for gateway (OOM spike), MCP (socket timeout), and hub (rate limit burst). Average recovery time: **0.8 seconds**.

### 3. KYA Identity Before x402

We originally designed x402 payments first, KYA identity second. That was wrong. Agents need identity before settlement. We flipped the architecture: KYA challenge at `/kya/challenge`, token-based auth, then x402 payments. This eliminated **95% of edge cases** (unauthenticated payment attempts, replay attacks, etc.).

### 4. Dual AI Model Strategy

Using **microsoft/Phi-3-mini-4k-instruct** (local) + **Google Gemini 2.0 Flash** (cloud) with graceful degradation:

- Gemini handles ~80% of intelligence queries (higher quality)
- Phi-3 handles ~20% (when Gemini is rate-limited or unreachable)
- Keyword-only fallback handles ~2% (when both are down)
- Average response time: **1.8s** (Gemini), **4.2s** (Phi-3), **0.1s** (keyword)

## What Broke

### The Gateway OOM

On day 3, a memory leak in x402 challenge creation caused the gateway to hit the 2GB limit. Root cause: challenge objects weren't being garbage-collected after expiry (5-minute TTL). Fix: added a background GC sweep every 60 seconds and capped the challenge cache at 1000 entries.

### The Hub Rate Limit

The MCP Hub's background discovery thread (5-minute interval) hit Smithery's rate limit after ~20 requests. Fix: added jitter (randomized intervals between 240-360 seconds) and an exponential backoff starting at 30 seconds.

### The Git Submodule Incident

We accidentally committed `nullstate-website` as a submodule (it had its own `.git` from `docusaurus init`). The build failed with cryptic `git submodule status` errors. Fix: `rm -rf nullstate-website/.git && git rm --cached nullstate-website && git add nullstate-website/`

## What's Next

- **Real USDC settlement** — wallet is funded, awaiting first real transaction
- **Discord & Slack bots** — next wave of ecosystem creep-in
- **VS Code .vsix packaging** — sideloadable extension
- **Chrome extension .crx** — sideloadable extension
- **nullstate.io** — canonical domain (awaiting purchase)

## The Takeaway

128 tasks. $8.99 settled. Zero humans involved in any transaction.

The agent economy isn't coming. It's here. And it runs on infrastructure that costs less than a coffee subscription.

[Deploy your own gateway](/docs/quickstart) · [View live metrics](https://greensol.me/nullstate) · [GitHub](https://github.com/nullstate/nullstate)
