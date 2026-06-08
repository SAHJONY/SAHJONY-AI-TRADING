"""
Sahjony Capital LLC — Trading Engine
AI-powered market analysis with multi-provider support and signal generation.
"""
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional
import config


@dataclass
class TradeSignal:
    symbol: str
    direction: str  # LONG, SHORT, HOLD
    confidence: float  # 0.0 - 1.0
    rationale: str
    provider: str
    model: str
    timestamp: float = field(default_factory=time.time)


class TradingEngine:
    """Core trading engine — routes analysis through AI providers."""

    def __init__(self):
        self.signals: List[TradeSignal] = []
        self.active_provider = config.DEFAULT_PROVIDER
        self.active_model = config.DEFAULT_MODEL

    def get_available_providers(self) -> List[str]:
        return [p for p in config.PROVIDERS if config.is_configured(p)]

    def set_provider(self, provider: str, model: Optional[str] = None):
        if provider not in config.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")
        if not config.is_configured(provider):
            raise ValueError(f"Provider not configured: {provider}")
        self.active_provider = provider
        self.active_model = model or config.PROVIDERS[provider]["models"][0]

    def analyze(self, symbol: str, context: str = "") -> dict:
        """Run AI analysis on a symbol and return structured result."""
        import httpx

        provider = config.get_provider(self.active_provider)
        api_key = provider["api_key"]
        base_url = provider["base_url"]
        model = self.active_model

        prompt = (
            f"Analyze {symbol} for {config.FIRM_NAME}. "
            f"Provide: 1) Direction (LONG/SHORT/HOLD) 2) Confidence (0-100%) "
            f"3) Key factors 4) Risk assessment. "
            f"{'Additional context: ' + context if context else ''}"
            f"Respond in JSON: {{\"direction\": \"...\", \"confidence\": 0.0, \"rationale\": \"...\", \"risk\": \"...\"}}"
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"You are the senior quant analyst for {config.FIRM_NAME}. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }

        try:
            resp = httpx.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # Parse JSON from response
            try:
                # Handle markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                analysis = json.loads(content)
            except json.JSONDecodeError:
                analysis = {"direction": "HOLD", "confidence": 0.0, "rationale": content, "risk": "parse_error"}

            signal = TradeSignal(
                symbol=symbol,
                direction=analysis.get("direction", "HOLD"),
                confidence=float(analysis.get("confidence", 0)),
                rationale=analysis.get("rationale", ""),
                provider=self.active_provider,
                model=self.active_model,
            )
            self.signals.append(signal)

            return {
                "symbol": symbol,
                "direction": signal.direction,
                "confidence": signal.confidence,
                "rationale": signal.rationale,
                "risk": analysis.get("risk", "N/A"),
                "provider": self.active_provider,
                "model": self.active_model,
                "usage": data.get("usage", {}),
            }
        except Exception as e:
            return {"error": str(e), "symbol": symbol, "provider": self.active_provider}

    def get_signals(self, limit: int = 20) -> List[dict]:
        """Return recent signals."""
        return [
            {
                "symbol": s.symbol,
                "direction": s.direction,
                "confidence": s.confidence,
                "rationale": s.rationale[:100],
                "provider": s.provider,
                "timestamp": s.timestamp,
            }
            for s in self.signals[-limit:]
        ]


# Singleton
engine = TradingEngine()
