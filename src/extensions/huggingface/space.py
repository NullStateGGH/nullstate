"""
NullState Hugging Face Space — AI agent payment gateway for HF ecosystem.

Deploy as: https://huggingface.co/spaces/nullstate/gateway

Creep-in points:
  - HF Inference API (wrap model calls with payment)
  - HF Spaces (Gradio apps with micro-payments)
  - HF Datasets (pay-per-download)
  - HF Models (pay-per-inference)
"""

import json
import os
import time
import urllib.request
from typing import Optional

import gradio as gr

GATEWAY_URL = os.environ.get("NULLSTATE_GATEWAY_URL", "https://greensol.me/nullstate")
HF_TOKEN = os.environ.get("NULLSTATE_HF_TOKEN", "")
PORT = int(os.environ.get("HF_SPACE_PORT", 7860))


def call_gateway(endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
    url = f"{GATEWAY_URL}/{endpoint}"
    req = urllib.request.Request(url)
    req.method = method
    if data:
        payload = json.dumps(data).encode()
        req.data = payload
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def call_hf_model(model: str, prompt: str, pay: bool = True) -> str:
    """Call HF Inference API through NullState payment gate."""
    if pay:
        payment = call_gateway("webhook/payment_settled", "POST", {
            "task_id": f"hf_{model}_{int(time.time())}",
            "tx_hash": f"hf_infer_{int(time.time())}",
            "amount": 0.001,
        })
        if "error" in payment:
            return f"Payment required: {GATEWAY_URL}/kya/challenge"

    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
    payload = json.dumps({"inputs": prompt}).encode()
    req = urllib.request.Request(url, data=payload, headers={**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"


def status() -> str:
    health = call_gateway("health")
    return json.dumps(health, indent=2)


def kya_challenge() -> str:
    challenge = call_gateway("kya/challenge")
    return json.dumps(challenge, indent=2)


def submit_solution(task_id: str, solution: str) -> str:
    result = call_gateway("webhook/payment_settled", "POST", {
        "task_id": task_id,
        "tx_hash": f"hf_space_{int(time.time())}",
        "source": "huggingface_space",
    })
    return json.dumps(result, indent=2)


# Gradio UI — the HF Space frontend
with gr.Blocks(theme=gr.themes.Soft(), title="NullState — HF Payment Gateway") as demo:
    gr.Markdown("""
    # ⛓️ NullState — Hugging Face Payment Gateway
    
    Pay for HF Inference API calls with USDC via x402. Agent-native.
    """)

    with gr.Tab("API Status"):
        status_btn = gr.Button("Check Gateway Status")
        status_out = gr.JSON()
        status_btn.click(fn=status, outputs=status_out)

    with gr.Tab("KYA Challenge"):
        kya_btn = gr.Button("Get KYA Token")
        kya_out = gr.JSON()
        kya_btn.click(fn=kya_challenge, outputs=kya_out)

    with gr.Tab("Submit Solution"):
        task_input = gr.Textbox(label="Task ID", placeholder="task_001")
        solution_input = gr.Textbox(label="Solution", lines=5)
        submit_btn = gr.Button("Submit & Settle")
        submit_out = gr.JSON()
        submit_btn.click(fn=submit_solution, inputs=[task_input, solution_input], outputs=submit_out)

    with gr.Tab("HF Inference (pay-per-call)"):
        model_input = gr.Dropdown(
            choices=["microsoft/Phi-3-mini-4k-instruct", "google/gemma-3-27b-it", "meta-llama/Llama-3.2-3B-Instruct"],
            label="Model",
            value="microsoft/Phi-3-mini-4k-instruct"
        )
        prompt_input = gr.Textbox(label="Prompt", lines=3, placeholder="Write code to...")
        pay_check = gr.Checkbox(label="Pay per call (0.001 USDC)", value=True)
        infer_btn = gr.Button("Run Inference")
        infer_out = gr.Textbox(label="Result", lines=10)
        infer_btn.click(fn=call_hf_model, inputs=[model_input, prompt_input, pay_check], outputs=infer_out)

    gr.Markdown("""
    ---
    **NullState** — MIT License · [GitHub](https://github.com/nullstate/nullstate) · [Gateway](https://greensol.me/nullstate)
    """)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=PORT)
