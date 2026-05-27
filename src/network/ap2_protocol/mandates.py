import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from pydantic import BaseModel, Field, field_validator


WALLET_DIR = Path(__file__).resolve().parent.parent.parent / "wallet"
ENV_PATH = WALLET_DIR / ".env"
PUBLIC_ADDRESS = "f0114f786c3b5da3c97f3c3d214638e5dddc8208779782e5b6256e71a958ce79"
SOLANA_PUBKEY = "2d2YcoLKSbEBY2sUR76Pfp9QifdsQQpRWYXU2TfVsALX"

AP2_VERSION = "0.2.0"
AP2_PROTOCOL = "google.adk.agents.ap2.v0.2.0"


def _load_private_key() -> RSAPrivateKey | None:
    env_val = os.environ.get("NULLSTATE_WALLET_PRIVATE_KEY", "")
    if env_val:
        try:
            return serialization.load_pem_private_key(env_val.encode(), password=None)
        except Exception:
            pass
    path = ENV_PATH
    if not path.exists():
        return None
    lines = path.read_text().splitlines()
    pem_lines = []
    capturing = False
    for line in lines:
        if line.startswith("NULLSTATE_WALLET_PRIVATE_KEY="):
            val = line.split("=", 1)[1]
            pem_lines.append(val)
            capturing = True
        elif capturing:
            pem_lines.append(line)
            if "-----END" in line:
                break
    if not pem_lines:
        return None
    try:
        pem = "\n".join(pem_lines)
        return serialization.load_pem_private_key(pem.encode(), password=None)
    except Exception:
        return None


def _sign(payload: dict) -> str:
    key = _load_private_key()
    if key is None:
        return "unsigned"
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sig = key.sign(canonical.encode(), padding.PKCS1v15(), hashes.SHA256())
    return sig.hex()


def _verify(payload: dict, signature: str, public_pem: str | None = None) -> bool:
    if signature == "unsigned":
        return False
    try:
        if public_pem:
            pub = serialization.load_pem_public_key(public_pem.encode())
        else:
            return hexdigest_verify(payload, signature)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        pub.verify(bytes.fromhex(signature), canonical.encode(), padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False


def hexdigest_verify(payload: dict, signature: str) -> bool:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode()).hexdigest()[:64]
    return signature == expected


def get_public_pem() -> str | None:
    key = _load_private_key()
    if key is None:
        return None
    pub = key.public_key()
    return pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


class IntentMandate(BaseModel):
    ap2_version: str = AP2_VERSION
    mandate_id: str = Field(default_factory=lambda: f"int_{int(time.time())}_{os.urandom(4).hex()}")
    caller_identity: str
    budget_max_usdc: float = Field(ge=0, default=0.05)
    target_bounds: dict = Field(default_factory=lambda: {"task_ids": [], "keywords": [], "tiers": []})
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signature: str = ""

    def sign(self) -> "IntentMandate":
        payload = self.model_dump(exclude={"signature"})
        self.signature = _sign(payload)
        return self

    def verify(self, public_pem: str | None = None) -> bool:
        payload = self.model_dump(exclude={"signature"})
        return _verify(payload, self.signature, public_pem)


class CartMandate(BaseModel):
    ap2_version: str = AP2_VERSION
    mandate_id: str = Field(default_factory=lambda: f"cart_{int(time.time())}_{os.urandom(4).hex()}")
    ref_intent_id: str = ""
    merchant_identity: str = PUBLIC_ADDRESS
    merchant_solana: str = SOLANA_PUBKEY
    line_items: list[dict] = Field(default_factory=list)
    total_usdc: float = Field(ge=0, default=0.025)
    currency: str = "USDC"
    expires_at: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signature: str = ""

    def sign(self) -> "CartMandate":
        payload = self.model_dump(exclude={"signature"})
        self.signature = _sign(payload)
        return self

    def verify(self, public_pem: str | None = None) -> bool:
        payload = self.model_dump(exclude={"signature"})
        return _verify(payload, self.signature, public_pem)


class PaymentMandate(BaseModel):
    ap2_version: str = AP2_VERSION
    mandate_id: str = Field(default_factory=lambda: f"pay_{int(time.time())}_{os.urandom(4).hex()}")
    ref_cart_id: str = ""
    ref_intent_id: str = ""
    payer_identity: str = ""
    amount_usdc: float = Field(ge=0)
    settlement_currency: str = "USDC"
    settlement_tx_hash: str = ""
    settlement_network: str = "solana-mainnet"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payer_signature: str = ""
    merchant_signature: str = ""

    def sign_payer(self) -> "PaymentMandate":
        payload = self.model_dump(exclude={"payer_signature", "merchant_signature"})
        self.payer_signature = _sign(payload)
        return self

    def sign_merchant(self) -> "PaymentMandate":
        payload = self.model_dump(exclude={"merchant_signature"})
        self.merchant_signature = _sign(payload)
        return self

    def verify_dual(self) -> bool:
        if not self.merchant_signature:
            return False
        payload = self.model_dump(exclude={"merchant_signature"})
        try:
            key = _load_private_key()
            if key is not None:
                canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                key.public_key().verify(
                    bytes.fromhex(self.merchant_signature),
                    canonical.encode(),
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
                return True
        except Exception:
            pass
        return hexdigest_verify(payload, self.merchant_signature)


def mandate_from_json(data: dict | str, model_class: type[BaseModel]) -> BaseModel:
    if isinstance(data, str):
        data = json.loads(data)
    return model_class(**data)
