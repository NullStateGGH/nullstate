import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"

ENV_PATH = SRC / "wallet" / ".env"
if ENV_PATH.exists():
    content = ENV_PATH.read_text()
    current_key = None
    current_val = []
    for line in content.splitlines():
        if "=" in line and not line.startswith("-----"):
            if current_key:
                os.environ.setdefault(current_key, "\n".join(current_val))
            current_key, v = line.split("=", 1)
            current_key = current_key.strip()
            current_val = [v.strip()]
        elif current_key and line.startswith("-----"):
            current_val.append(line)
        elif current_key:
            current_val.append(line)
    if current_key:
        os.environ.setdefault(current_key, "\n".join(current_val))

CRITICAL_ENV_VARS = [
    "NULLSTATE_SOLANA_PUBKEY",
    "NULLSTATE_SOLANA_PRIVATE_KEY",
    "NULLSTATE_WALLET_PRIVATE_KEY",
]

MISSING = [v for v in CRITICAL_ENV_VARS if not os.environ.get(v)]
if MISSING:
    print(f"WARNING: Missing critical env vars (in .env or environment): {', '.join(MISSING)}", file=sys.stderr)

PATHS = {
    "tasks": SRC / "core" / "tasks.json",
    "wallet_info": SRC / "wallet" / "WALLET_INFO.md",
    "ledger": SRC / "wallet" / "REVENUE_LEDGER.json",
    "delivery": ROOT / "delivery",
    "backups": ROOT / "backups",
    "logs": ROOT / "logs",
    "env": ENV_PATH,
    "db": SRC / "core" / "nullstate.db",
    "ssl_cert": ROOT / ".ssl" / "cert.pem",
    "ssl_key": ROOT / ".ssl" / "key.pem",
}

GATEWAY_PORT = 8080
MCP_PORT = 8081
DAEMON_CRAWL_SLEEP = 300
DAEMON_PROCESSOR_SLEEP = 300
HEARTBEAT_INTERVAL = 60
HTTP_TIMEOUT = 30
SUBPROCESS_TIMEOUT = 120
MAX_REQUEST_BYTES = 65536
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 30

HF_TOKEN = os.environ.get("NULLSTATE_HF_TOKEN", "")
GOOGLE_API_KEY = os.environ.get("NULLSTATE_GOOGLE_API_KEY", "")

HF_MODEL = "microsoft/Phi-3-mini-4k-instruct"
HF_API_URL = "https://api-inference.huggingface.co/models/" + HF_MODEL
GOOGLE_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

SOLANA_NETWORK = os.environ.get("NULLSTATE_SOLANA_NETWORK", "devnet")
IS_MAINNET = SOLANA_NETWORK == "mainnet"
if IS_MAINNET:
    SOLANA_RPC_URL = os.environ.get("NULLSTATE_SOLANA_RPC", "https://api.mainnet-beta.solana.com")
else:
    SOLANA_RPC_URL = os.environ.get("NULLSTATE_SOLANA_RPC", "https://api.devnet.solana.com")
SOLANA_PUBKEY = os.environ.get("NULLSTATE_SOLANA_PUBKEY", "")
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

PRICING = {
    "free": {"requests_per_month": 5, "price_usdc": 0, "label": "Free"},
    "scout": {"requests_per_month": 500, "price_usdc": 50, "label": "Scout"},
    "pro": {"requests_per_month": 5000, "price_usdc": 200, "label": "Pro"},
    "enterprise": {"requests_per_month": 99999, "price_usdc": 500, "label": "Enterprise"},
}
PUBLIC_HOST = "greensol.me"

KEYWORD_WEIGHTS = {
    "mcp-server": 3,
    "automation-workflow": 2,
    "agentic-patch": 2,
    "solana-wallet-bug": 3,
    "usdc-escrow": 1,
}

SOURCES = [
    "https://api.github.com/search/repositories?q=mcp-server&sort=updated&per_page=20",
    "https://api.github.com/search/repositories?q=agentic+automation&sort=updated&per_page=20",
    "https://api.github.com/search/repositories?q=solana+wallet+bug&sort=updated&per_page=20",
    "https://api.github.com/search/repositories?q=x402+payment&sort=updated&per_page=20",
    "https://api.github.com/search/repositories?q=usdc+escrow+agent&sort=updated&per_page=20",
    "https://api.github.com/search/repositories?q=mcp+server+integration&sort=updated&per_page=20",
    "https://api.github.com/search/topics?q=agentic",
    "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md",
    "https://raw.githubusercontent.com/sindresorhus/awesome/main/readme.md",
    "https://api.github.com/search/repositories?q=solana+wallet+patch&sort=updated&per_page=20",
]
