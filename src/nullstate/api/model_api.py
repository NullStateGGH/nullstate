"""NullState Model Inference API — monetized model access.
Serves the NullState Ollama model with per-token pricing.
OpenAI-compatible /v1/chat/completions endpoint.
"""

import os
import json
import time
import uuid
import hashlib
import logging
import subprocess
import sqlite3
import threading
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Union, Dict, Any, Literal

# ─── Configuration ───────────────────────────────────────────────────

MODEL_NAME = os.environ.get("NULLSTATE_MODEL", "nullstate")
API_KEY = os.environ.get("NULLSTATE_API_KEY", "ns_key_demo")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
TOKEN_PRICE = float(os.environ.get("TOKEN_PRICE", "0.0005"))  # $0.0005 per 1K tokens
FREE_TIER_LIMIT = int(os.environ.get("FREE_TIER_LIMIT", "1000"))  # free tokens per day per key
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))
DB_PATH = "src/core/nullstate.db"

from core.billing import get_credits, deduct_credits, add_credits, get_product_price, PRODUCTS, make_x402_challenge as billing_challenge

log = logging.getLogger("nullstate-model-api")

_rl: dict[str, list[float]] = {}
_rl_lock = threading.Lock()

def rate_limited(ip: str) -> bool:
    now = time.time()
    with _rl_lock:
        if ip not in _rl:
            _rl[ip] = []
        _rl[ip] = [t for t in _rl[ip] if now - t < RATE_LIMIT_WINDOW]
        if len(_rl[ip]) >= RATE_LIMIT_REQUESTS:
            return True
        _rl[ip].append(now)
    return False

# ─── Models ───────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = MODEL_NAME
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.3
    max_tokens: Optional[int] = 2048
    stream: Optional[bool] = False

class CompletionRequest(BaseModel):
    model: str = MODEL_NAME
    prompt: str
    temperature: Optional[float] = 0.3
    max_tokens: Optional[int] = 2048
    stream: Optional[bool] = False

class ModelResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]

class ModelList(BaseModel):
    object: str = "list"
    data: List[Dict[str, Any]]

# ─── Database for usage tracking ───────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS api_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT,
        tokens_in INTEGER,
        tokens_out INTEGER,
        total_tokens INTEGER,
        cost REAL,
        endpoint TEXT,
        model TEXT,
        ip TEXT,
        timestamp TEXT
    )""")
    conn.commit()
    return conn

def record_usage(api_key, tokens_in, tokens_out, cost, endpoint, model, ip):
    try:
        conn = init_db()
        conn.execute(
            "INSERT INTO api_usage (api_key, tokens_in, tokens_out, total_tokens, cost, endpoint, model, ip, timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
            (api_key, tokens_in, tokens_out, tokens_in + tokens_out, cost, endpoint, model, ip, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_daily_usage(api_key):
    try:
        conn = init_db()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COALESCE(SUM(total_tokens), 0) FROM api_usage WHERE api_key=? AND timestamp LIKE ?",
            (api_key, f"{today}%")
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0

# ─── Ollama Client ───────────────────────────────────────────────────

def call_ollama(prompt, model=MODEL_NAME, temperature=0.3, max_tokens=2048, stream=False):
    """Call Ollama generate API."""
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream
    }
    import requests
    try:
        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Model inference timed out")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Model not available (Ollama not running)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

def call_ollama_stream(prompt, model=MODEL_NAME, temperature=0.3, max_tokens=2048):
    """Stream from Ollama generate API."""
    import requests
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True
    }
    try:
        resp = requests.post(url, json=payload, stream=True, timeout=300)
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                yield line
    except Exception as e:
        yield json.dumps({"error": str(e)}).encode()

def format_messages(messages):
    """Convert chat messages to Ollama prompt format."""
    formatted = ""
    for msg in messages:
        role = msg.role if hasattr(msg, 'role') else msg.get('role', 'user')
        content = msg.content if hasattr(msg, 'content') else msg.get('content', '')
        if role == "system":
            formatted += f"System: {content}\n"
        elif role == "user":
            formatted += f"User: {content}\n"
        elif role == "assistant":
            formatted += f"Assistant: {content}\n"
    formatted += "Assistant: "
    return formatted

# ─── API Key Verification ───────────────────────────────────────────

def verify_api_key(request: Request):
    """Verify API key from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        key = auth[7:]
    else:
        key = auth
    
    # Demo key always works
    if key == API_KEY or key == "ns_key_demo":
        return key
    
    # Check free tier
    if key and len(key) > 8:
        usage = get_daily_usage(key)
        if usage < FREE_TIER_LIMIT:
            return key
    
    raise HTTPException(status_code=401, detail="Invalid or expired API key. Get access at greensol.me/nullstate/pricing")

# ─── FastAPI App ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        os.environ["NULLSTATE_SERVICE"] = "model-api"
        from extensions.google.telemetry import init as ns_telemetry_init
        ns_telemetry_init()
    except Exception:
        pass
    yield

app = FastAPI(
    title="NullState Model API",
    description="Monetized inference API for the NullState agent-payment specialized model",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    if rate_limited(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limit_exceeded", "message": f"Max {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW}s"}
        )
    return await call_next(request)

# ─── Endpoints ───────────────────────────────────────────────────────

@app.get("/v1/models", response_model=ModelList)
async def list_models(request: Request):
    verify_api_key(request)
    return ModelList(data=[
        {"id": MODEL_NAME, "object": "model", "created": int(time.time()), "owned_by": "nullstate"},
        {"id": "nullstate-v1", "object": "model", "created": int(time.time()), "owned_by": "nullstate"},
    ])

@app.post("/v1/chat/completions")
async def chat_completions(request: Request, body: ChatRequest):
    api_key = verify_api_key(request)
    client_ip = request.client.host if request.client else "unknown"
    
    prompt = format_messages(body.messages)
    model_to_use = body.model if body.model in [MODEL_NAME, "nullstate-v1"] else MODEL_NAME
    
    # Count input tokens (approximate)
    tokens_in = len(prompt.split())
    
    # Check free tier
    daily_usage = get_daily_usage(api_key)
    if daily_usage >= FREE_TIER_LIMIT and api_key not in [API_KEY, "ns_key_demo"]:
        estimated_tokens = tokens_in + 200  # estimate ~200 out tokens
        cost_for_request = (estimated_tokens / 1000) * TOKEN_PRICE
        
        # Check prepaid credits
        credits = get_credits(api_key)
        if credits >= cost_for_request:
            ok, new_balance = deduct_credits(api_key, cost_for_request, product="model_inference")
            if not ok:
                raise HTTPException(
                    status_code=402,
                    detail=billing_challenge(api_key, "model_inference", cost_for_request)
                )
            log.info("Model API: %s paid $%.4f from credits (balance: $%.4f)", api_key[:8], cost_for_request, new_balance)
        else:
            raise HTTPException(
                status_code=402,
                detail=billing_challenge(api_key, "model_inference", cost_for_request)
            )
    
    if body.stream:
        async def generate():
            cost_per_token = TOKEN_PRICE / 1000
            tokens_out = 0
            first_chunk = True
            
            for raw_line in call_ollama_stream(prompt, model_to_use, body.temperature, body.max_tokens):
                if isinstance(raw_line, bytes):
                    raw_line = raw_line.decode()
                try:
                    data = json.loads(raw_line)
                    if "response" in data:
                        chunk = data["response"]
                        tokens_out += 1
                        if first_chunk:
                            chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
                            first_chunk_data = {
                                "id": chunk_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model_to_use,
                                "choices": [{"delta": {"role": "assistant"}, "index": 0, "finish_reason": None}]
                            }
                            yield f"data: {json.dumps(first_chunk_data)}\n\n"
                            first_chunk = False
                        
                        yield f"data: {json.dumps({
                            'id': chunk_id if not first_chunk else f'chatcmpl-{uuid.uuid4().hex[:12]}',
                            'object': 'chat.completion.chunk',
                            'created': int(time.time()),
                            'model': model_to_use,
                            'choices': [{'delta': {'content': chunk}, 'index': 0, 'finish_reason': None}]
                        })}\n\n"
                    
                    if data.get("done"):
                        yield f"data: {json.dumps({
                            'id': chunk_id if not first_chunk else f'chatcmpl-{uuid.uuid4().hex[:12]}',
                            'object': 'chat.completion.chunk',
                            'created': int(time.time()),
                            'model': model_to_use,
                            'choices': [{'delta': {}, 'index': 0, 'finish_reason': 'stop'}]
                        })}\n\ndata: [DONE]\n"
                        
                        cost = (tokens_in + tokens_out) * cost_per_token
                        record_usage(api_key, tokens_in, tokens_out, cost, "/v1/chat/completions", model_to_use, client_ip)
                        
                        try:
                            from extensions.google.telemetry import record_model_call
                            record_model_call(tokens_in + tokens_out, 0)
                            if cost > 0:
                                from extensions.google.telemetry import record_revenue
                                record_revenue(float(cost), "model_api")
                        except Exception:
                            pass
                except json.JSONDecodeError:
                    continue
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    else:
        result = call_ollama(prompt, model_to_use, body.temperature, body.max_tokens)
        response_text = result.get("response", "")
        tokens_out = len(response_text.split())
        cost = (tokens_in + tokens_out) * (TOKEN_PRICE / 1000)
        
        record_usage(api_key, tokens_in, tokens_out, cost, "/v1/chat/completions", model_to_use, client_ip)
        try:
            from extensions.google.telemetry import record_model_call, record_revenue
            record_model_call(tokens_in + tokens_out, 0)
            if cost > 0:
                record_revenue(float(cost), "model_api")
        except Exception:
            pass
        
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_to_use,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": tokens_in,
                "completion_tokens": tokens_out,
                "total_tokens": tokens_in + tokens_out,
                "cost_usd": round(cost, 6)
            }
        }

@app.post("/v1/completions")
async def completions(request: Request, body: CompletionRequest):
    api_key = verify_api_key(request)
    client_ip = request.client.host if request.client else "unknown"
    
    tokens_in = len(body.prompt.split())
    
    daily_usage = get_daily_usage(api_key)
    if daily_usage >= FREE_TIER_LIMIT and api_key not in [API_KEY, "ns_key_demo"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "payment_required",
                "message": f"Free tier limit ({FREE_TIER_LIMIT} tokens/day) exceeded",
                "payment_url": "https://greensol.me/nullstate/pricing"
            }
        )
    
    result = call_ollama(body.prompt, body.model, body.temperature, body.max_tokens, body.stream)
    
    if body.stream:
        async def generate():
            for raw_line in call_ollama_stream(body.prompt, body.model, body.temperature, body.max_tokens):
                if isinstance(raw_line, bytes):
                    raw_line = raw_line.decode()
                yield f"data: {raw_line}\n\n"
            yield "data: [DONE]\n"
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    response_text = result.get("response", "")
    tokens_out = len(response_text.split())
    cost = (tokens_in + tokens_out) * (TOKEN_PRICE / 1000)
    
    record_usage(api_key, tokens_in, tokens_out, cost, "/v1/completions", body.model, client_ip)
    
    return {
        "id": f"cmpl-{uuid.uuid4().hex[:12]}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [{"text": response_text, "index": 0, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": tokens_in,
            "completion_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
            "cost_usd": round(cost, 6)
        }
    }

@app.get("/v1/usage")
async def get_usage(request: Request):
    """Get current usage statistics for your API key."""
    api_key = verify_api_key(request)
    daily = get_daily_usage(api_key)
    remaining = max(0, FREE_TIER_LIMIT - daily) if api_key not in [API_KEY, "ns_key_demo"] else -1
    
    return {
        "api_key": api_key[:8] + "...",
        "daily_tokens_used": daily,
        "daily_tokens_remaining": remaining,
        "free_tier_limit": FREE_TIER_LIMIT,
        "is_demo_key": api_key in [API_KEY, "ns_key_demo"],
        "token_price_per_1k": TOKEN_PRICE
    }

@app.get("/health")
async def health():
    """Health check endpoint."""
    # Check if Ollama is running
    import requests
    try:
        ollama_resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        models = [m["name"] for m in ollama_resp.json().get("models", [])]
        model_available = any(m.startswith(MODEL_NAME) for m in models)
    except Exception:
        models = []
        model_available = False
    
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "model_available": model_available,
        "loaded_models": models,
        "token_price_per_1k": TOKEN_PRICE,
        "free_tier_daily_tokens": FREE_TIER_LIMIT,
        "endpoints": ["/v1/models", "/v1/chat/completions", "/v1/completions", "/v1/usage", "/health"],
        "api_docs": "/docs"
    }

# ─── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MODEL_API_PORT", "8082"))
    print(f"NullState Model API starting on port {port}")
    print(f"Model: {MODEL_NAME}")
    print(f"Price: ${TOKEN_PRICE}/1K tokens")
    print(f"Free tier: {FREE_TIER_LIMIT} tokens/day")
    print(f"API docs at http://localhost:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
