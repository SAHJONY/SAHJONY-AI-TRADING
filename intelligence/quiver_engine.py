from __future__ import annotations

import os
import requests


class QuiverEngine:
    def __init__(self):
        self.api_key = os.getenv("QUIVER_API_KEY", "").strip()
        self.base_url = "https://api.quiverquant.com/beta"

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}

    def _get(self, path: str, symbol: str):
        if not self.api_key:
            return None

        try:
            url = f"{self.base_url}/{path}/{symbol}"
            r = requests.get(url, headers=self._headers(), timeout=10)
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:
            return None

    def analyze(self, symbol: str) -> dict:
        ticker = symbol.split("/")[0].upper()

        insiders = self._get("insiders", ticker)
        congress = self._get("historical/congresstrading", ticker)

        insider_score = 0.5 if not insiders else 0.7
        congress_score = 0.5 if not congress else 0.65

        quiver_alpha = round(
            insider_score * 0.55 + congress_score * 0.45,
            3,
        )

        sentiment = "bullish" if quiver_alpha > 0.6 else "neutral"

        return {
            "symbol": symbol,
            "ticker": ticker,
            "quiver_alpha": quiver_alpha,
            "insider_score": insider_score,
            "congress_score": congress_score,
            "sentiment": sentiment,
        }
