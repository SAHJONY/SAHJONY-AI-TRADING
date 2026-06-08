"""
Sahjony Capital LLC — Vercel Serverless API
WSGI entry point for Vercel Python runtime.
"""
import os
import hashlib
import json
import httpx
from flask import Flask, request, jsonify
from functools import wraps

# ─── Config ───────────────────────────────────────────────────────────────────

FIRM_NAME = os.environ.get("FIRM_NAME", "Sahjony Capital LLC")
OWNER = os.environ.get("OWNER", "Juan")
OWNER_TOKEN = os.environ.get("OWNER_TOKEN", hashlib.sha256(f"{FIRM_NAME}-{OWNER}-sahjony".encode()).hexdigest()[:32])

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OUTLOOK_EMAIL = os.environ.get("OUTLOOK_EMAIL", "sahjonycapitalllc@outlook.com")
OUTLOOK_APP_PASSWORD = os.environ.get("OUTLOOK_APP_PASSWORD", "")

DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "nvidia")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "mistralai/mistral-nemotron")

PROVIDERS = {
    "nvidia": {
        "api_key": NVIDIA_API_KEY,
        "base_url": "https://integrate.api.nvidia.com/v1",
        "models": [
            "mistralai/mistral-nemotron",
            "meta/llama-3.1-70b-instruct",
            "deepseek-ai/deepseek-v4-flash",
        ],
    },
    "openai": {
        "api_key": OPENAI_API_KEY,
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4", "gpt-4-turbo", "o3-mini"],
    },
    "anthropic": {
        "api_key": ANTHROPIC_API_KEY,
        "base_url": "https://api.anthropic.com/v1",
        "models": ["claude-3-sonnet", "claude-3-opus"],
    },
}


def is_configured(name: str) -> bool:
    p = PROVIDERS.get(name, {})
    return bool(p.get("api_key") and len(p["api_key"]) > 10)


def get_provider(name: str) -> dict:
    return PROVIDERS.get(name, {})


# ─── Flask App ────────────────────────────────────────────────────────────────

app = Flask(__name__)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = auth[7:]
        if token != OWNER_TOKEN:
            return jsonify({"error": "Invalid token"}), 403
        return f(*args, **kwargs)
    return decorated


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "firm": FIRM_NAME,
        "owner": OWNER,
        "status": "operational",
        "providers": {
            k: {"configured": is_configured(k), "models": v["models"]}
            for k, v in PROVIDERS.items()
        },
    })


@app.route("/api/owner-access", methods=["POST"])
def owner_access():
    return jsonify({"token": OWNER_TOKEN, "firm": FIRM_NAME, "owner": OWNER})


@app.route("/api/trading/analyze", methods=["POST"])
@require_auth
def trading_analyze():
    data = request.get_json(force=True)
    query = data.get("query", "")
    provider_name = data.get("provider", DEFAULT_PROVIDER)
    model = data.get("model", DEFAULT_MODEL)

    if not query:
        return jsonify({"error": "Missing 'query' field"}), 400

    provider = get_provider(provider_name)
    if not is_configured(provider_name):
        return jsonify({"error": f"Provider '{provider_name}' not configured"}), 400

    try:
        result = call_ai_provider(provider_name, provider, model, query)
        if "error" in result and provider_name == "nvidia":
            for alt_model in provider["models"]:
                if alt_model != model:
                    result = call_ai_provider(provider_name, provider, alt_model, query)
                    if "error" not in result:
                        break
            if "error" in result and is_configured("openai"):
                result = call_ai_provider("openai", get_provider("openai"), "gpt-4", query)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "provider": provider_name, "model": model})


def call_ai_provider(provider_name: str, provider: dict, model: str, query: str) -> dict:
    api_key = provider["api_key"]
    base_url = provider["base_url"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": f"You are the senior quantitative analyst for {FIRM_NAME}. Provide concise, institutional-grade market analysis."},
            {"role": "user", "content": query},
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
    }

    try:
        client = httpx.Client(timeout=90.0)
        resp = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return {
            "provider": provider_name,
            "model": model,
            "analysis": data["choices"][0]["message"]["content"],
            "usage": data.get("usage", {}),
        }
    except Exception as e:
        return {"error": str(e), "provider": provider_name, "model": model}
