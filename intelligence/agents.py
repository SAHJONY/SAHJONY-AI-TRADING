"""The 12-agent institutional intelligence layer.

Each persona is a transparent computation over a MarketSnapshot, emitting a
directional `score` in [-1, 1] (positive = bullish), a `confidence` in [0, 1],
a short rationale, and supporting metrics. The Council aggregates them into a
single long-conviction (0-1) and a risk_multiplier (0-1) that the strategies use
to gate and size trades.

Honesty note: these are well-known estimators inspired by public descriptions of
how these firms think — NOT their proprietary models, and not a profit guarantee.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from intelligence import engines


# ── data containers ──────────────────────────────────────────────────────────
@dataclass
class MarketSnapshot:
    symbol: str
    price: float
    closes: np.ndarray
    volumes: np.ndarray
    bench_closes: np.ndarray = field(default_factory=lambda: np.array([]))

    @property
    def returns(self) -> np.ndarray:
        return engines.log_returns(self.closes)

    @property
    def bench_returns(self) -> np.ndarray:
        return engines.log_returns(self.bench_closes)

    @property
    def vol(self) -> float:
        return engines.annualized_vol(self.closes)

    def sma(self, n: int) -> float:
        c = engines.to_array(self.closes)
        if c.size < n or n <= 0:
            return float(c[-1]) if c.size else 0.0
        return float(np.mean(c[-n:]))

    def ret_over(self, n: int) -> float:
        c = engines.to_array(self.closes)
        if c.size <= n:
            return 0.0
        return float(c[-1] / c[-n - 1] - 1.0)


@dataclass
class AgentVerdict:
    name: str
    persona: str
    score: float           # [-1, 1] directional
    confidence: float      # [0, 1]
    rationale: str
    metrics: Dict[str, float] = field(default_factory=dict)

    def clamp(self) -> "AgentVerdict":
        self.score = float(max(-1.0, min(1.0, self.score)))
        self.confidence = float(max(0.0, min(1.0, self.confidence)))
        return self


def _tanh(x: float) -> float:
    return float(math.tanh(x))


# ── the twelve personas ───────────────────────────────────────────────────────
class Agent:
    name = "agent"
    persona = "generic"
    weight = 1.0

    def evaluate(self, s: MarketSnapshot) -> AgentVerdict:  # pragma: no cover - interface
        raise NotImplementedError


class CitadelSystematic(Agent):
    name, persona, weight = "Citadel Systematic", "Trend/Systematic", 1.1

    def evaluate(self, s):
        macd = engines.macd_hist(s.closes)
        slope = (s.sma(20) - s.sma(50)) / s.price if s.price else 0.0
        mom = s.ret_over(63)  # ~quarter
        score = _tanh(50 * slope + 3 * mom + np.sign(macd) * 0.3)
        return AgentVerdict(self.name, self.persona, score, min(1.0, abs(score) + 0.3),
                            f"MACD={macd:.2f}, 20-50 slope={slope:+.3f}, Q-mom={mom:+.1%}",
                            {"macd": macd, "q_momentum": mom}).clamp()


class TwoSigmaBacktest(Agent):
    name, persona, weight = "Two Sigma Backtest", "Statistical expectancy", 1.0

    def evaluate(self, s):
        r = s.returns
        if r.size < 20:
            return AgentVerdict(self.name, self.persona, 0.0, 0.2, "insufficient history").clamp()
        sharpe = float(np.mean(r) / (np.std(r) + 1e-9)) * math.sqrt(engines.TRADING_DAYS)
        win = float(np.mean(r > 0))
        score = _tanh(sharpe / 2.0)
        return AgentVerdict(self.name, self.persona, score, min(1.0, 0.4 + abs(score) * 0.5),
                            f"ann.Sharpe={sharpe:+.2f}, win-rate={win:.0%}",
                            {"sharpe": sharpe, "win_rate": win}).clamp()


class BridgewaterRisk(Agent):
    name, persona, weight = "Bridgewater Risk", "Risk parity / vol-target", 1.2

    TARGET_VOL = 0.15

    def evaluate(self, s):
        vol = s.vol or 0.0
        risk_scale = 0.0 if vol <= 0 else min(1.0, self.TARGET_VOL / vol)
        # defensive tilt when vol blows out far past target
        score = -_tanh((vol - self.TARGET_VOL) * 2.0) * 0.5
        return AgentVerdict(self.name, self.persona, score, 0.6,
                            f"ann.vol={vol:.0%} vs target {self.TARGET_VOL:.0%}, risk_scale={risk_scale:.2f}",
                            {"vol": vol, "risk_scale": risk_scale}).clamp()


class RenaissancePatterns(Agent):
    name, persona, weight = "Renaissance Patterns", "Mean-reversion", 1.0

    def evaluate(self, s):
        c = engines.to_array(s.closes)
        if c.size < 20:
            return AgentVerdict(self.name, self.persona, 0.0, 0.2, "insufficient history").clamp()
        z = (s.price - s.sma(20)) / (np.std(c[-20:]) + 1e-9)
        r = s.returns
        autocorr = float(np.corrcoef(r[:-1], r[1:])[0, 1]) if r.size > 3 else 0.0
        score = _tanh(-z * 0.6)  # oversold => bullish
        return AgentVerdict(self.name, self.persona, score, min(1.0, 0.3 + abs(z) * 0.2),
                            f"z(20)={z:+.2f} (mean-revert), autocorr={autocorr:+.2f}",
                            {"zscore": float(z), "autocorr": autocorr}).clamp()


class GoldmanTechnical(Agent):
    name, persona, weight = "Goldman Technical", "Technical analysis", 0.9

    def evaluate(self, s):
        r = engines.rsi(s.closes)
        macd = engines.macd_hist(s.closes)
        score = _tanh((50 - r) / 30.0 + np.sign(macd) * 0.25)  # RSI<50 oversold-ish + macd
        return AgentVerdict(self.name, self.persona, score, 0.5,
                            f"RSI={r:.0f}, MACD-hist={macd:+.2f}",
                            {"rsi": r, "macd": macd}).clamp()


class JPMorganFundamental(Agent):
    name, persona, weight = "JPMorgan Fundamental", "Valuation proxy", 0.9

    def evaluate(self, s):
        # offline proxy: trend health (price vs 200d) + distance from 1y high.
        sma200 = s.sma(200)
        trend = (s.price / sma200 - 1.0) if sma200 else 0.0
        c = engines.to_array(s.closes)
        hi = float(np.max(c[-252:])) if c.size else s.price
        drawdown = (s.price / hi - 1.0) if hi else 0.0
        # healthy uptrend bullish, but deep value dislocation also attractive
        score = _tanh(2 * trend + (-drawdown) * 0.5)
        return AgentVerdict(self.name, self.persona, score, 0.45,
                            f"px/200d={1+trend:.2f}, drawdown-from-1y-high={drawdown:+.0%} (proxy)",
                            {"trend_200d": trend, "drawdown": drawdown}).clamp()


class DEShawOptions(Agent):
    name, persona, weight = "D.E. Shaw Options", "Vol surface / premium", 1.0

    def evaluate(self, s):
        vol = s.vol or 0.25
        vols_hist = np.array([engines.annualized_vol(s.closes[:i]) for i in range(20, len(s.closes))]) \
            if len(s.closes) > 25 else np.array([vol])
        rank = engines.iv_rank(vol, vols_hist)
        # high IV rank => premium-selling (wheel) favorable; mild bullish bias
        favorability = rank
        score = _tanh((rank - 0.5) * 0.6)
        return AgentVerdict(self.name, self.persona, score, 0.5 + rank * 0.3,
                            f"vol={vol:.0%}, IV-rank={rank:.0%} → premium-sell favorability {favorability:.0%}",
                            {"iv_rank": rank, "options_favorability": favorability, "vol": vol}).clamp()


class AQRFactor(Agent):
    name, persona, weight = "AQR Factor", "Multi-factor", 1.0

    def evaluate(self, s):
        mom = s.ret_over(252) - s.ret_over(21)        # 12-1 momentum
        value = -s.ret_over(63)                        # contrarian value proxy
        quality = -min(1.0, (s.vol or 0.25))           # low-vol = quality
        composite = 0.5 * mom + 0.3 * value + 0.2 * quality
        score = _tanh(composite * 2.0)
        return AgentVerdict(self.name, self.persona, score, 0.55,
                            f"mom(12-1)={mom:+.1%}, value={value:+.1%}, quality={quality:+.2f}",
                            {"momentum": mom, "value": value, "quality": quality}).clamp()


class CitadelSecuritiesMM(Agent):
    name, persona, weight = "Citadel Securities MM", "Order-flow microstructure", 1.0

    def evaluate(self, s):
        tox = engines.vpin(s.closes, s.volumes)
        # high toxicity => adverse selection risk => lower confidence, defensive
        score = -_tanh((tox - 0.5) * 1.0) * 0.4
        confidence = max(0.2, 0.6 - tox * 0.4)
        return AgentVerdict(self.name, self.persona, score, confidence,
                            f"VPIN order-flow toxicity={tox:.2f} (1=max adverse selection)",
                            {"vpin": tox}).clamp()


class MillenniumPod(Agent):
    name, persona, weight = "Millennium Pod", "Residual alpha / beta-neutral", 1.2

    def evaluate(self, s):
        reg = engines.ols_alpha_beta(s.returns, s.bench_returns)
        alpha, beta = reg["alpha"], reg["beta"]
        # pure residual alpha drives the call; beta near 1 penalized (it's just market)
        beta_neutrality = max(0.0, 1.0 - abs(beta - 0.0) / 2.0)
        score = _tanh(alpha * 4.0)
        return AgentVerdict(self.name, self.persona, score, 0.5 + min(0.4, abs(alpha) * 3),
                            f"ann.alpha={alpha:+.1%}, beta={beta:+.2f}, beta-neutrality={beta_neutrality:.2f}",
                            {"alpha": alpha, "beta": beta, "beta_neutrality": beta_neutrality,
                             "r2": reg["r2"]}).clamp()


class RenaissanceMedallion(Agent):
    name, persona, weight = "Renaissance Medallion", "Regime / cointegration", 1.3

    def evaluate(self, s):
        reg = engines.regime_model(s.returns)
        coint = engines.cointegration(s.closes, s.bench_closes)
        calm = reg["state"] == 0
        drift = float(np.mean(s.returns)) if s.returns.size else 0.0
        base = _tanh(drift * 60.0)
        score = base * (1.0 if calm else 0.4)  # de-risk directional view in stress
        rationale = (f"state={'calm' if calm else 'stressed'} "
                     f"(p_stay={reg['p_stay_calm'] if calm else reg['p_stay_stress']:.2f}), "
                     f"coint-z={coint['spread_z']:+.2f}")
        return AgentVerdict(self.name, self.persona, score, 0.5 + (0.3 if calm else 0.0),
                            rationale,
                            {"regime_state": float(reg["state"]), "stressed_prob": reg["stressed_prob"],
                             "coint_z": coint["spread_z"], "cointegrated": coint["cointegrated"]}).clamp()


class SovereignWealth(Agent):
    name, persona, weight = "Sovereign Wealth", "Secular macro / SAA", 1.1

    def evaluate(self, s):
        sma200 = s.sma(200)
        secular = (s.price / sma200 - 1.0) if sma200 else 0.0
        c = engines.to_array(s.closes)
        hi = float(np.max(c)) if c.size else s.price
        dd = (s.price / hi - 1.0) if hi else 0.0
        # multi-generational: accumulate into deep dislocations, preserve in melt-ups
        score = _tanh(-dd * 1.2 + secular * 0.5)
        return AgentVerdict(self.name, self.persona, score, 0.4,
                            f"secular trend={secular:+.0%}, structural drawdown={dd:+.0%} (accumulate dips)",
                            {"secular_trend": secular, "drawdown": dd}).clamp()


ALL_AGENTS: List[Agent] = [
    CitadelSystematic(), TwoSigmaBacktest(), BridgewaterRisk(), RenaissancePatterns(),
    GoldmanTechnical(), JPMorganFundamental(), DEShawOptions(), AQRFactor(),
    CitadelSecuritiesMM(), MillenniumPod(), RenaissanceMedallion(), SovereignWealth(),
]


# ── council aggregation ───────────────────────────────────────────────────────
@dataclass
class CouncilVerdict:
    symbol: str
    conviction: float          # 0-1 long conviction
    direction: str             # 'long' | 'flat'
    composite_score: float     # [-1, 1]
    risk_multiplier: float     # 0-1 position-size scaler
    options_favorability: float
    verdicts: List[AgentVerdict]
    metrics: Dict[str, float]

    def summary(self) -> str:
        return (f"{self.symbol}: conviction={self.conviction:.0%} {self.direction.upper()} "
                f"(score={self.composite_score:+.2f}, risk_mult={self.risk_multiplier:.2f})")


class Council:
    def __init__(self, agents: Optional[List[Agent]] = None):
        self.agents = agents or ALL_AGENTS

    def deliberate(self, snap: MarketSnapshot) -> CouncilVerdict:
        verdicts: List[AgentVerdict] = []
        for agent in self.agents:
            try:
                verdicts.append(agent.evaluate(snap).clamp())
            except Exception as exc:  # one bad agent never sinks the council
                verdicts.append(AgentVerdict(agent.name, agent.persona, 0.0, 0.0,
                                             f"error: {exc}"))
        wsum = sum(a.weight * v.confidence for a, v in zip(self.agents, verdicts))
        composite = 0.0
        if wsum > 0:
            composite = sum(a.weight * v.confidence * v.score
                            for a, v in zip(self.agents, verdicts)) / wsum
        conviction = max(0.0, min(1.0, 0.5 + 0.5 * composite))

        # risk multiplier from Bridgewater risk_scale × VPIN toxicity haircut
        risk_scale = next((v.metrics.get("risk_scale", 0.5) for v in verdicts
                           if v.name == "Bridgewater Risk"), 0.5)
        vpin = next((v.metrics.get("vpin", 0.0) for v in verdicts
                     if v.name == "Citadel Securities MM"), 0.0)
        risk_mult = max(0.1, min(1.0, risk_scale * (1.0 - 0.5 * vpin)))

        opt_fav = next((v.metrics.get("options_favorability", 0.5) for v in verdicts
                        if v.name == "D.E. Shaw Options"), 0.5)
        alpha = next((v.metrics.get("alpha", 0.0) for v in verdicts
                      if v.name == "Millennium Pod"), 0.0)
        beta = next((v.metrics.get("beta", 1.0) for v in verdicts
                     if v.name == "Millennium Pod"), 1.0)

        return CouncilVerdict(
            symbol=snap.symbol,
            conviction=conviction,
            direction="long" if composite > 0 else "flat",
            composite_score=composite,
            risk_multiplier=risk_mult,
            options_favorability=opt_fav,
            verdicts=verdicts,
            metrics={"alpha": alpha, "beta": beta, "vpin": vpin, "vol": snap.vol,
                     "iv_rank": opt_fav, "risk_scale": risk_scale},
        )
