from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketInputs:
    trend_score: float  # -1 strong bearish, 0 neutral, +1 strong bullish
    realized_vol_percentile: float  # 0-100
    iv_percentile: float  # 0-100
    iv_change: float  # percentage-point change over the chosen lookback
    theta_vega: float


@dataclass(frozen=True)
class RegimeResult:
    regime: str
    selling_score: int
    preferred_strategy: str
    action: str
    reasons: tuple[str, ...]


def classify(inputs: MarketInputs) -> RegimeResult:
    """Prototype rule engine.

    These thresholds are intentionally research defaults. They must be validated on
    historical 1-minute NIFTY data before being treated as trading rules.
    """
    trend = inputs.trend_score
    rv = inputs.realized_vol_percentile
    iv = inputs.iv_percentile
    iv_change = inputs.iv_change
    tv = inputs.theta_vega

    if trend >= 0.55:
        regime = "STRONG BULLISH"
    elif trend <= -0.55:
        regime = "STRONG BEARISH"
    elif abs(trend) < 0.25:
        regime = "SIDEWAYS"
    elif trend > 0:
        regime = "MILD BULLISH"
    else:
        regime = "MILD BEARISH"

    score = 50
    reasons: list[str] = []

    # Theta/Vega efficiency: primary seller input.
    if tv >= 0.40:
        score += 25
        reasons.append("Very strong Theta/Vega efficiency")
    elif tv >= 0.30:
        score += 18
        reasons.append("Favorable Theta/Vega efficiency")
    elif tv >= 0.20:
        score += 8
        reasons.append("Moderate Theta/Vega efficiency")
    elif tv < 0.10:
        score -= 18
        reasons.append("Weak Theta/Vega efficiency")
    else:
        score -= 8
        reasons.append("Low Theta/Vega efficiency")

    # IV regime.
    if iv >= 70 and iv_change < 0:
        score += 15
        reasons.append("High IV with falling volatility")
    elif iv >= 70 and iv_change > 0:
        score -= 10
        reasons.append("High IV but volatility is expanding")
    elif iv < 30:
        score -= 8
        reasons.append("Low IV leaves less premium to sell")

    # Realized volatility / expansion risk.
    if rv >= 75:
        score -= 18
        reasons.append("High realized volatility")
    elif rv <= 40:
        score += 8
        reasons.append("Contained realized volatility")

    # Strategy selection from regime.
    if regime == "SIDEWAYS":
        preferred = "IRON CONDOR"
        if iv >= 70 and tv >= 0.30:
            preferred = "WIDE IRON CONDOR"
    elif regime == "MILD BULLISH":
        preferred = "BULL PUT SPREAD"
    elif regime == "MILD BEARISH":
        preferred = "BEAR CALL SPREAD"
    elif regime == "STRONG BULLISH":
        preferred = "BULL PUT SPREAD (DEFENSIVE)"
        score -= 8
        reasons.append("Strong directional risk: avoid two-sided selling")
    else:
        preferred = "BEAR CALL SPREAD (DEFENSIVE)"
        score -= 8
        reasons.append("Strong directional risk: avoid two-sided selling")

    score = max(0, min(100, int(round(score))))

    if score >= 80:
        action = "SELL / PAPER TRADE"
    elif score >= 65:
        action = "SELECTIVE / SMALL SIZE"
    elif score >= 50:
        action = "WAIT / MONITOR"
    else:
        action = "AVOID NEW SELLING"

    return RegimeResult(
        regime=regime,
        selling_score=score,
        preferred_strategy=preferred,
        action=action,
        reasons=tuple(reasons),
    )
