<div align="center">
  <img src="nullstate-website/static/img/logo.svg" width="120" alt="NullState" />
  <h1>NullState</h1>
  <p><strong>Open-source payment infrastructure for AI agents.</strong></p>
  <p>x402 · AP2 · MCP · KYA · Multi-Gateway · Self-hosted</p>
  <p>
    <a href="https://greensol.me/nullstate"><img src="https://img.shields.io/badge/live-demo-blue?style=flat-square" alt="Live Demo" /></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License" /></a>
    <a href="https://github.com/NullStateGGH/nullstate/issues"><img src="https://img.shields.io/github/issues/NullStateGGH/nullstate?style=flat-square" alt="GitHub Issues" /></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.13+-blue?style=flat-square" alt="Python 3.13+" /></a>
    <a href="https://ollama.com/"><img src="https://img.shields.io/badge/ollama-powered-orange?style=flat-square" alt="Ollama Powered" /></a>
  </p>
  <p>
    <strong>⭐ Star us on GitHub</strong> — help AI agents pay each other.
  </p>
</div>

---

## 💖 Sponsor

NullState is open-source (MIT) and self-hosted. Support independent AI infrastructure:

- **GitHub Sponsors**: [github.com/sponsors/NullStateGGH](https://github.com/sponsors/NullStateGGH)
- **Direct USDC**: x402 to `34.173.171.16:8080`
- **Star the repo** — helps us get discovered

All sponsor funds go toward GCP server costs ($30/mo) and free-tier AI inference for indie devs.

---

**NullState** is a self-hosted, open-source payment and commerce layer purpose-built for AI agents. It lets agents discover work, execute tasks, and settle payments — automatically — across **crypto (x402/USDC)** and **fiat (Stripe/PayPal/Google Pay)** rails.

Think "Stripe for AI agents" — but open source, self-hosted, and you keep 100% of your revenue.

## ✨ What's New (May 2026)

| Feature | Description |
|---------|-------------|
| **Google Pay** | Pay with Google Wallet — backs into Stripe for processing |
| **GCP Marketplace** | List NullState on Google Cloud Marketplace for enterprise billing |
| **Multi-Gateway Payments** | Stripe, PayPal, Coinbase Commerce, Solana USDC — all in one interface |
| **Finance/BDM Subagent** | Autonomous revenue tracking, pricing optimization, API key provisioning |
| **Instant Paid AI Tasks** | $5 analysis, $10 content gen, $15 research, $25 email campaigns |
| **RapidAPI Integration** | Ready-to-list OpenAPI spec for 4M+ developer marketplace |
| **OpenRouter Provider** | Sell self-hosted inference through 400+ model marketplace |

## 🚀 Quickstart

```bash
# Clone
git clone https://github.com/NullStateGGH/nullstate.git
cd nullstate

# Start all services
docker compose up -d

# Check health
curl http://localhost:8080/health

# Run the AP2 handshake demo
curl -X POST http://localhost:8080/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"execute_ap2_handshake","arguments":{"caller_identity":"demo_agent"}}}'

# See settlement in the ledger
curl http://localhost:8080/health | jq .ledger
```

## 🧠 Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │           NullState Gateway (:8080)          │
                    │  x402 · AP2 · MCP · KYA · Multi-Gateway     │
                    └──────┬──────────────┬──────────────┬─────────┘
                           │              │              │
              ┌────────────▼──────┐  ┌────▼──────┐  ┌───▼──────────┐
              │   Model API       │  │ MCP Server│  │  Finance/BDM │
              │   (:8082)         │  │ (:8081)   │  │  Subagent     │
              │   Ollama-backed   │  │ 5 tools   │  │  Revenue Ops  │
              └───────────────────┘  └───────────┘  └──────────────┘
                           │              │
                           └──────┬───────┘
                                  ▼
                    ┌──────────────────────────┐
                    │     Payment Gateways     │
                    │  Stripe · PayPal · Coinbase│
                    │  Solana · Google Pay · GCP│
                    └──────────────────────────┘
                                  ▼
                    ┌──────────────────────────┐
                    │      Revenue Ledger      │
                    │    SQLite · auto-backup  │
                    │  5-deep rotation · WAL   │
                    └──────────────────────────┘
```

## 💳 Payment Gateways

| Gateway | Fiat/Crypto | Fee | Status |
|---------|-------------|-----|--------|
| **Stripe** | Cards (USD) | 2.9% + $0.30 | ✅ Live (mock fallback) |
| **PayPal** | PayPal balance | 3.49% + $0.49 | ✅ Live (mock fallback) |
| **Google Pay** | Google Wallet | 2.9% + $0.30 | ✅ Live (mock fallback) |
| **Coinbase** | USDC (Base) | 0% | ✅ Live (mock fallback) |
| **Solana** | USDC (native) | 0% | ✅ Always live |
| **GCP Marketplace** | GCP billing | 5% | ✅ Enterprise |

All gateways fall back gracefully when API keys are not configured — your endpoints always work.

## 💰 Revenue Streams

| Product | Price | Margin | Description |
|---------|-------|--------|-------------|
| AI Analysis | $5/task | ~99% | Deep document/code analysis via Ollama |
| Content Gen | $10/task | ~99% | SEO-optimized content generation |
| Research | $15/task | ~99% | Competitive intelligence reports |
| Email Campaign | $25/task | ~99% | Full campaign with Mail relay |
| Model Inference | $0.0005/1K tok | ~99% | General-purpose LLM (Ollama, $0 cost) |
| AP2 Settlement | $0.025/task | ~99% | Agent-to-agent payment protocol |

> **Infrastructure cost**: $0 for inference (self-hosted Ollama) · $5/mo for VPS

## 🔌 Protocols

| Protocol | Use Case | Endpoint | Status |
|----------|----------|----------|--------|
| **x402** | Crypto micropayments (HTTP 402) | `GET /get_solution` → 402 → `POST /webhook` | ✅ Live |
| **AP2** | Enterprise agent-to-agent payments | `POST /api/v1/ap2/checkout` · `/charge` | ✅ Live |
| **MCP** | AI agent tool integration | `POST /mcp` (JSON-RPC proxy) | ✅ Live |
| **KYA** | Agent identity (RSA-2048 challenge) | `GET /kya/challenge` | ✅ Live |

## 📊 Live Demo

See it running in production at **[greensol.me/nullstate](https://greensol.me/nullstate)**:
- 🔐 12 systemd services · 9 active
- 📊 2,179 tasks processed · 2,338 ledger entries
- 💰 $90.16 USDC settled
- 🤖 Self-hosted Ollama (gemma4:31b, 131K context)

```bash
# Live instance health
curl -sk https://localhost:8080/health

# Get KYA identity token
curl -sk https://localhost:8080/kya/challenge

# Browse paid AI tasks
curl -sk https://localhost:8080/api/v1/tasks/catalog

# List available payment gateways
curl -sk https://localhost:8080/api/v1/gateways
```

## 🗺️ Roadmap

- [x] Multi-gateway payments (Stripe, PayPal, Coinbase, Solana, Google Pay)
- [x] GCP Marketplace integration
- [x] Finance/BDM autonomous subagent
- [x] Instant paid AI tasks
- [x] KYA identity + rate limiting
- [x] AP2 3-way handshake protocol
- [x] MCP server with 5 tools
- [ ] RapidAPI marketplace listing
- [ ] OpenRouter model provider
- [ ] Enterprise SSO / SAML
- [ ] Multi-tenant agent workspace
- [ ] On-chain Solana settlement verification

## 🛠️ Configuration

Copy `.env.example` and set your keys:

```bash
cp .env.example .env
# Required: nothing — runs fully in mock mode
# Optional: add STRIPE_SECRET_KEY, PAYPAL_CLIENT_ID, etc. for live payments
```

**Keys are optional** — NullState runs fully in mock/demo mode without any API keys. Add them when you're ready to go live.

## 📚 Documentation

Full docs at **[greensol.me/nullstate/docs](https://greensol.me/nullstate/docs)**:

- [Quickstart](https://greensol.me/nullstate/docs/deployment/quickstart)
- [Docker Deployment](https://greensol.me/nullstate/docs/deployment/docker)
- [Systemd Services](https://greensol.me/nullstate/docs/deployment/systemd)
- [Gateway Endpoints](https://greensol.me/nullstate/docs/gateway/endpoints)
- [AP2 Protocol](https://greensol.me/nullstate/docs/protocols/ap2)
- [KYA Auth](https://greensol.me/nullstate/docs/protocols/kya)
- [Pricing](https://greensol.me/nullstate/pricing)

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) to get started. We welcome PRs, issues, and feedback.

Quick ways to help:
- ⭐ Star the repo
- 🐛 Open an issue for bugs or feature requests
- 📖 Improve documentation
- 🔌 Build an integration or extension
- 💬 Share on X, Dev.to, or Hacker News

## 📄 License

MIT — see [LICENSE](LICENSE).

Built for the agent economy. Agents deserve to pay each other.
