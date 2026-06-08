"""
Sahjony Capital LLC — Configuration Loader
Single source of truth for all credentials and settings.
"""
import os
from pathlib import Path
from typing import Optional

ENV_PATH = Path(__file__).parent / ".env"

def load_env():
    """Load .env file into os.environ (idempotent)."""
    if not ENV_PATH.exists():
        raise FileNotFoundError(f"Missing .env at {ENV_PATH}")
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value and value != "PENDING":
                os.environ.setdefault(key, value)

load_env()

# --- Credentials ---
NVIDIA_API_KEY: str = os.environ.get("NVIDIA_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
OUTLOOK_EMAIL: str = os.environ.get("OUTLOOK_EMAIL", "")
OUTLOOK_APP_PASSWORD: str = os.environ.get("OUTLOOK_APP_PASSWORD", "")

# --- Firm Identity ---
FIRM_NAME: str = os.environ.get("FIRM_NAME", "Sahjony Capital LLC")
OWNER: str = os.environ.get("OWNER", "Juan")

# --- Model Routing ---
DEFAULT_PROVIDER: str = os.environ.get("DEFAULT_PROVIDER", "nvidia")
DEFAULT_MODEL: str = os.environ.get("DEFAULT_MODEL", "mistralai/mistral-nemotron")

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

def get_provider(name: Optional[str] = None) -> dict:
    """Return provider config, falling back to DEFAULT_PROVIDER."""
    name = name or DEFAULT_PROVIDER
    return PROVIDERS.get(name, PROVIDERS[DEFAULT_PROVIDER])

def is_configured(provider: str) -> bool:
    """Check if a provider has a real (non-empty) API key."""
    return bool(PROVIDERS.get(provider, {}).get("api_key", ""))
