import os
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

WALLET_DIR = Path(__file__).parent
ENV_FILE = WALLET_DIR / ".env"
INFO_FILE = WALLET_DIR / "WALLET_INFO.md"


def generate_wallet() -> tuple[str, str]:
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    address = hashlib.sha256(public_pem).hexdigest()
    return address, private_pem.decode()


def save_env(private_key_pem: str) -> None:
    env_path = Path(ENV_FILE)
    env_path.write_text(f"NULLSTATE_WALLET_PRIVATE_KEY={private_key_pem}\n")
    os.chmod(env_path, 0o600)


def save_public(address: str) -> None:
    content = (
        f"# NullState Wallet — Public Address\n\n"
        f"**Algorithm**: RSA-2048\n"
        f"**Address (SHA-256 of public key)**: `{address}`\n"
    )
    Path(INFO_FILE).write_text(content)


if __name__ == "__main__":
    address, private_pem = generate_wallet()
    save_env(private_pem)
    save_public(address)
    print(f"[OK] Wallet generated. Public address: {address}")
    print(f"[OK] Public info  -> {INFO_FILE}")
    print(f"[OK] Private key  -> {ENV_FILE} (permissions 600)")
