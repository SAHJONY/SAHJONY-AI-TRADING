"""
Sahjony Capital LLC — Owner Dashboard API
Production Flask server with auth, model routing, health checks, and trading engine access.
"""
import os
import hashlib
import time
from functools import wraps
from flask import Flask, jsonify, request
import config

app = Flask(__name__)

# --- Auth ---
API_TOKENS = {}

def generate_token(owner: str) -> str:
    """Generate a bearer token for the owner."""
    raw = f"{owner}:{config.FIRM_NAME}:{time.time()}"
    token = hashlib.sha256(raw.encode()).hexdigest()
    API_TOKENS[token] = {"owner": owner, "created": time.time()}
    return token

OWNER_TOKEN = generate_token(config.OWNER)

def require_auth(f):
    """Decorator: require Bearer token in Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing Bearer token"}), 401
        token = auth[7:]
        if token not in API_TOKENS:
            return jsonify({"error": "Invalid token"}), 403
        return f(*args, **kwargs)
    return decorated

# --- Routes ---

@app.route("/api/health", methods=["GET"])
def health():
    """System health check — shows which providers are live."""
    providers = {}
    for name, prov in config.PROVIDERS.items():
        providers[name] = {
            "configured": config.is_configured(name),
            "models": prov["models"],
        }
    return jsonify({
        "firm": config.FIRM_NAME,
        "status": "operational",
        "owner": config.OWNER,
        "providers": providers,
    })

@app.route("/api/owner-access", methods=["POST"])
def owner_access():
    """Grant owner unrestricted access — returns bearer token."""
    return jsonify({
        "status": "Access granted",
        "owner": {"name": config.OWNER, "role": "CEO", "access_level": "unrestricted"},
        "token": OWNER_TOKEN,
        "message": "Unrestricted access to all firm resources granted to owner",
    })

@app.route("/api/providers", methods=["GET"])
@require_auth
def list_providers():
    """List all configured AI providers and their status."""
    return jsonify({
        p: {"configured": config.is_configured(p), "models": config.PROVIDERS[p]["models"]}
        for p in config.PROVIDERS
    })

@app.route("/api/trading/status", methods=["GET"])
@require_auth
def trading_status():
    """Trading engine status."""
    return jsonify({
        "engine": "Sahjony Trading Engine v1.0",
        "status": "initializing",
        "providers_active": [p for p in config.PROVIDERS if config.is_configured(p)],
        "default_provider": config.DEFAULT_PROVIDER,
        "default_model": config.DEFAULT_MODEL,
    })

@app.route("/api/trading/analyze", methods=["POST"])
@require_auth
def trading_analyze():
    """Run AI analysis on a market query via configured provider."""
    data = request.get_json(force=True)
    query = data.get("query", "")
    provider_name = data.get("provider", config.DEFAULT_PROVIDER)
    model = data.get("model", config.DEFAULT_MODEL)

    if not query:
        return jsonify({"error": "Missing 'query' field"}), 400

    provider = config.get_provider(provider_name)
    if not config.is_configured(provider_name):
        return jsonify({"error": f"Provider '{provider_name}' not configured"}), 400

    try:
        # Route to AI provider (with fallback)
        result = call_ai_provider(provider_name, provider, model, query)
        if "error" in result and provider_name == "nvidia":
            # Fallback: try next NVIDIA model
            for alt_model in provider["models"]:
                if alt_model != model:
                    result = call_ai_provider(provider_name, provider, alt_model, query)
                    if "error" not in result:
                        break
            # Final fallback: try OpenAI
            if "error" in result and config.is_configured("openai"):
                openai_provider = config.get_provider("openai")
                result = call_ai_provider("openai", openai_provider, "gpt-4", query)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "provider": provider_name, "model": model})


def call_ai_provider(provider_name: str, provider: dict, model: str, query: str) -> dict:
    """Call an AI provider and return the response."""
    import httpx

    api_key = provider["api_key"]
    base_url = provider["base_url"]

    # NVIDIA and OpenAI use OpenAI-compatible API
    if provider_name in ("nvidia", "openai"):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"You are the senior quantitative analyst for {config.FIRM_NAME}. Provide concise, institutional-grade market analysis."},
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

    return {"error": "Provider routing not implemented", "provider": provider_name}


if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  {config.FIRM_NAME} — Owner Dashboard")
    print(f"  Owner: {config.OWNER}")
    print(f"  Owner Token: {OWNER_TOKEN}")
    print(f"  Providers: {[p for p in config.PROVIDERS if config.is_configured(p)]}")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
