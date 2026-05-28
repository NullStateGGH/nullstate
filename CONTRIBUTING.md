# Contributing to NullState

We love contributions! Here's how to get started.

## 🚀 Quick Start

```bash
git clone https://github.com/NullStateGGH/nullstate.git
cd nullstate
pip install -e . --break-system-packages
python3 src/network/gateway.py &
python3 src/network/mcp_server.py &
```

## 🧪 Testing

```bash
# Unit tests (fast, no deps)
pytest tests/ -m unit -v

# All tests
pytest tests/ -v
```

## 🔍 Linting

```bash
ruff check src/
ruff check src/ --fix  # auto-fix
```

We follow PEP 8 with line-length 120 (configured in `pyproject.toml`).

## 📋 PR Guidelines

1. **One PR = one feature/bug**. Keep it focused.
2. **Tests included** for new functionality.
3. **No secrets** — never commit `.env`, keys, or credentials.
4. **Lint clean** — run `ruff check src/` before submitting.
5. **Update docs** if you change endpoints or config.

## 🏗️ Project Structure

```
src/
├── core/           # Database, billing, payment gateways, config
├── network/        # HTTP gateway, MCP server, AP2 protocol
├── nullstate/      # HOD engine, model API, feedback loops
├── finance_bdm/   # Finance & business development subagent
├── integrations/   # RapidAPI, OpenRouter, marketplace handlers
├── wallet/         # RSA + Solana key management
├── worker/         # Processing, telemetry, content engine
├── agents/         # AI crawler and scoring
├── system/         # Daemon loop, self-healing
└── extensions/     # GitHub, VS Code, browser, MCP Hub
```

## 💬 Need Help?

- Open a [Discussion](https://github.com/NullStateGGH/nullstate/discussions)
- Check the [docs](https://greensol.me/nullstate/docs)

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.
