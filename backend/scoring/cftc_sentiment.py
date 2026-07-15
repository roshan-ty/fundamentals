"""
CFTC CoT Sentiment Score — Determined by the Speculative 52-Week Percentile Rank.
Applies the Overcrowded Trade Rule for extreme percentiles.
Returns a score 0–10.
"""

import logging
from typing import Optional

from backend.models.schemas import CftcData, clamp

logger = logging.getLogger(__name__)


# Map CFTC market codes to currencies/asset classes
CFTC_CURRENCY_MAP: dict[str, str] = {
    "EUR":   "EUR",
    "GBP":   "GBP",
    "JPY":   "JPY",
    "CAD":   "CAD",
    "CHF":   "CHF",
    "AUD":   "AUD",
    "XAU":   "XAU",   # Gold (metal)
    "XAG":   "XAG",   # Silver (metal)
    "WTI":   "WTI",   # Crude Oil (energy)
    "SP500": "SP500", # S&P 500 (index)
    "NAS100":"NAS100",# NASDAQ-100 (index)
}


def compute_cftc_sentiment_score(cftc_data: CftcData) -> dict[str, float]:
    """
    Compute CFTC sentiment scores for each currency/asset.
    
    Score logic (Percentile Rank):
    - 75% to 90%  = 8 to 10 (Highly Bullish momentum)
    - 60% to 75%  = 6 to 8 (Bullish)
    - 40% to 60%  = 5 (Neutral)
    - 25% to 40%  = 2 to 4 (Bearish)
    - 10% to 25%  = 0 to 2 (Highly Bearish)
    
    Overcrowded Trade Rule:
    - If Percentile Rank > 95% or < 5%, cap the score closer to 5
      to account for impending profit-taking/reversals.
    """
    scores: dict[str, float] = {}

    if not cftc_data.positions:
        logger.warning("CFTC Sentiment: No position data available.")
        return {c: 5.0 for c in CFTC_CURRENCY_MAP.keys()}

    for position in cftc_data.positions:
        market = position.market
        pctl = position.percentile_52w

        if market not in CFTC_CURRENCY_MAP:
            continue

        # Apply Overcrowded Trade Rule
        effective_pctl = pctl
        if pctl > 95.0:
            # Overcrowded long — cap score near neutral
            effective_pctl = 50.0
            logger.info("CFTC Sentiment — %s: Overcrowded long (pctl=%.1f%%), capping.", market, pctl)
        elif pctl < 5.0:
            # Overcrowded short — cap score near neutral
            effective_pctl = 50.0
            logger.info("CFTC Sentiment — %s: Overcrowded short (pctl=%.1f%%), capping.", market, pctl)

        # Score mapping based on effective percentile
        if effective_pctl >= 90.0:
            score = 9.0 + (effective_pctl - 90.0) / 10.0  # 9–10
        elif effective_pctl >= 75.0:
            score = 8.0 + (effective_pctl - 75.0) / 15.0  # 8–9
        elif effective_pctl >= 60.0:
            score = 6.0 + (effective_pctl - 60.0) / 15.0 * 2.0  # 6–8
        elif effective_pctl >= 40.0:
            score = 5.0  # Neutral
        elif effective_pctl >= 25.0:
            score = 2.0 + (effective_pctl - 25.0) / 15.0 * 3.0  # 2–5
        elif effective_pctl >= 10.0:
            score = 0.0 + (effective_pctl - 10.0) / 15.0 * 2.0  # 0–2
        else:
            score = 0.0

        scores[market] = clamp(score)
        logger.info(
            "CFTC Sentiment — %s: raw_pctl=%.1f%%, effective_pctl=%.1f%%, score=%.2f",
            market, pctl, effective_pctl, score,
        )

    # Fill in missing currencies with neutral
    for market in CFTC_CURRENCY_MAP:
        if market not in scores:
            scores[market] = 5.0

    return scores


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from backend.models.schemas import CftcData, CftcPosition

    cd = CftcData()
    cd.positions.append(CftcPosition(market="EUR", report_date="2026-07-14", noncomm_long=200000, noncomm_short=100000, net_speculative=100000, weekly_change=5000, percentile_52w=82.5))
    cd.positions.append(CftcPosition(market="GBP", report_date="2026-07-14", noncomm_long=50000, noncomm_short=60000, net_speculative=-10000, weekly_change=-2000, percentile_52w=35.0))
    cd.positions.append(CftcPosition(market="JPY", report_date="2026-07-14", noncomm_long=30000, noncomm_short=80000, net_speculative=-50000, weekly_change=-3000, percentile_52w=12.0))
    cd.positions.append(CftcPosition(market="XAU", report_date="2026-07-14", noncomm_long=150000, noncomm_short=50000, net_speculative=100000, weekly_change=12000, percentile_52w=96.0))  # Overcrowded

    scores = compute_cftc_sentiment_score(cd)
    print(f"CFTC Sentiment scores: {scores}")