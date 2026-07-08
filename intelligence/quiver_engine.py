from __future__ import annotations

class QuiverEngine:
    def __init__(self):
        pass

    def analyze(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "quiver_alpha": 0.0,
            "insider_score": 0.0,
            "congress_score": 0.0,
            "sentiment": "neutral",
        }
