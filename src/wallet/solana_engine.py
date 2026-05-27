"""Generate a Solana Ed25519 keypair for USDC/x402 settlements."""
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solders.keypair import Keypair
from core.log import setup
from core import config

log = setup("solana_engine")

ENV_FILE = config.PATHS["env"]
INFO_FILE = config.PATHS["wallet_info"]


def generate_solana_wallet() -> tuple[str, str, bytes]:
    kp = Keypair()
    pubkey = str(kp.pubkey())
    priv_bytes = bytes(kp)  # 64 bytes: seed + pubkey
    fingerprint = hashlib.sha256(pubkey.encode()).hexdigest()
    return pubkey, fingerprint, priv_bytes


def append_to_env(pubkey: str, priv_bytes: bytes) -> None:
    existing = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    if "NULLSTATE_SOLANA_PUBKEY" in existing:
        log.warning("Solana wallet already exists — overwriting")
    existing += f"\nNULLSTATE_SOLANA_PUBKEY={pubkey}\n"
    existing += f"NULLSTATE_SOLANA_PRIVATE_KEY={priv_bytes.hex()}\n"
    ENV_FILE.write_text(existing)
    os.chmod(ENV_FILE, 0o600)


def update_info(pubkey: str, fingerprint: str) -> None:
    solana_block = (
        f"\n## Solana Wallet\n\n"
        f"**Algorithm**: Ed25519 (Solana)\n"
        f"**Public Key (Base58)**: `{pubkey}`\n"
        f"**Fingerprint (SHA-256)**: `{fingerprint}`\n"
    )
    existing = INFO_FILE.read_text() if INFO_FILE.exists() else ""
    if "## Solana Wallet" in existing:
        import re
        existing = re.sub(
            r"## Solana Wallet.*?(?=\n## |\Z)",
            solana_block.strip(),
            existing,
            flags=re.DOTALL,
        )
    else:
        existing += solana_block
    INFO_FILE.write_text(existing)


if __name__ == "__main__":
    pubkey, fingerprint, priv_bytes = generate_solana_wallet()
    append_to_env(pubkey, priv_bytes)
    update_info(pubkey, fingerprint)
    log.info("Solana wallet generated")
    log.info("Public key: %s", pubkey)
    log.info("Private key -> %s", ENV_FILE)
