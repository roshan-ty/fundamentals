"""
Yield Spread Momentum Score — Evaluates domestic 10Y bond yield trends
relative to their 50-day moving average. Returns a score 0–10.
"""

import logging
from typing import Optional

from backend.models.schemas import YieldData, clamp

logger = logging.getLogger(__name__)


# Map yield instruments to currencies
INSTRUMENT_CURRENCY_MAP: dict[str, str] = {
    "US10Y": "USD",
    "DE10Y": "EUR",
    "GB10Y": "GBP",
    "JP10Y": "JPY",
}

# For currencies without direct yield data, default to neutral
DEFAULT_CURRENCIES = ["AUD", "CAD", "CHF"]


def compute_yield_score(yield_data: YieldData) -> dict[str, float]:
    """
    Compute yield momentum scores for each currency.
    
    Score logic:
    - Current yield significantly above 50-day MA (tightening/rising) = 8 to 10
    - Yield at/near 50-day MA (flat) = 5
    - Current yield significantly below 50-day MA (crashing/rate cuts) = 0 to 2
    """
    scores: dict[str, float] = {}

    # Build lookup from instrument to latest YieldEntry
    yield_by_instrument: dict[str, float] = {}
    yield_ma50_by_instrument: dict[str, Optional[float]] = {}

    for entry in yield_data.entries:
        if entry.instrument not in yield_by_instrument:
            yield_by_instrument[entry.instrument] = entry.yield_value
            yield_ma50_by_instrument[entry.instrument] = entry.yield_ma50

    # Score each currency that has yield data
    for instrument, currency in INSTRUMENT_CURRENCY_MAP.items():
        if instrument not in yield_by_instrument:
            scores[currency] = 5.0
            continue

        current_yield = yield_by_instrument[instrument]
        ma50 = yield_ma50_by_instrument.get(instrument)

        if ma50 is None or ma50 == 0:
            scores[currency] = 5.0
            continue

        # Compute deviation from 50-day MA as percentage
        deviation = (current_yield - ma50) / abs(ma50) * 100

        # Score mapping based on deviation
        if deviation >= 1.5:
            score = 8.0 + min(2.0, (deviation - 1.5) * 0.5)  # 8–10
        elif deviation >= 0.5:
            score = 6.0 + (deviation - 0.5) * 2.0  # 6–8
        elif deviation >= -0.5:
            score = 5.0 + deviation * 2.0  # ~4–6
        elif deviation >= -1.5:
            score = 4.0 + (deviation + 0.5) * 2.0  # 2–4
        else:
            score = max(0.0, 2.0 + (deviation + 1.5) * 0.5)  # 0–2

        scores[currency] = clamp(score)
        logger.info(
            "Yield Score — %s: yield=%.4f, MA50=%.4f, dev=%.2f%%, score=%.2f",
            currency, current_yield, ma50, deviation, scores[currency],
        )

    # Default currencies (no yield data available)
    for currency in DEFAULT_CURRENCIES:
        scores[currency] = 5.0

    return scores


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from backend.models.schemas import YieldData, YieldEntry

    yd = YieldData()
    yd.entries.append(YieldEntry(instrument="US10Y", date="2026-07-15", yield_value=4.25, yield_ma50=4.10))
    yd.entries.append(YieldEntry(instrument="DE10Y", date="2026-07-15", yield_value=2.50, yield_ma50=2.60))
    yd.entries.append(YieldEntry(instrument="GB10Y", date="2026-07-15", yield_value=4.10, yield_ma50=4.05))
    yd.entries.append(YieldEntry(instrument="JP10Y", date="2026-07-15", yield_value=1.20, yield_ma50=0.95))

    scores = compute_yield_score(yd)
    print(f"Yield scores: {scores}")