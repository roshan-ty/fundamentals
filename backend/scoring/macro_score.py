"""
Structural Macro Score (FRED) — Compares current GDP and Unemployment
to historical trends. Returns a score 0–10.
"""

import logging
from typing import Optional

from backend.models.schemas import FredData, clamp

logger = logging.getLogger(__name__)


def compute_macro_score(fred_data: FredData) -> dict[str, float]:
    """
    Compute macro scores for each currency based on FRED data.
    Currently scores USD using US-specific FRED series.
    Returns dict of {currency: score}.
    
    Score logic:
    - GDP rising and Unemployment falling = 8 to 10
    - Stagnant, matching 10-year median averages = 5
    - GDP contraction (Recession) and spiking Unemployment = 0 to 2
    """
    scores: dict[str, float] = {}

    # Extract latest and historical values for USD
    usd_score = _score_usd_macro(fred_data)
    scores["USD"] = usd_score

    # For non-USD currencies, default to neutral (5) since we only have US FRED data
    # In a production system, each country's central bank stats would be added
    for currency in ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF"]:
        scores[currency] = 5.0

    logger.info("Macro Score — USD: %.2f", usd_score)
    return scores


def _score_usd_macro(fred_data: FredData) -> float:
    """
    Score USD structural macro health using GDPC1 and UNRATE.
    """
    # Get GDP observations (sorted by date desc from API)
    gdp_obs = [s for s in fred_data.series if s.series_id == "GDPC1"]
    gdp_obs.sort(key=lambda x: x.date)

    unrate_obs = [s for s in fred_data.series if s.series_id == "UNRATE"]
    unrate_obs.sort(key=lambda x: x.date)

    if not gdp_obs or not unrate_obs:
        logger.warning("Macro: Insufficient FRED data for scoring.")
        return 5.0

    # Latest GDP value
    latest_gdp = gdp_obs[-1].value

    # Compare GDP current vs 4 quarters ago (year-over-year growth)
    gdp_4q_ago = None
    if len(gdp_obs) >= 5:
        gdp_4q_ago = gdp_obs[-5].value

    # Latest unemployment
    latest_unrate = unrate_obs[-1].value

    # Unemployment 3 months ago
    unrate_3m_ago = None
    if len(unrate_obs) >= 4:
        unrate_3m_ago = unrate_obs[-4].value

    # Compute GDP growth direction
    gdp_growing = True
    if gdp_4q_ago is not None and gdp_4q_ago > 0:
        gdp_growth = (latest_gdp - gdp_4q_ago) / gdp_4q_ago * 100
        gdp_growing = gdp_growth > 0.5  # > 0.5% YoY growth = growing
    else:
        gdp_growing = False

    # Compute unemployment direction
    unemployment_falling = True
    if unrate_3m_ago is not None:
        unrate_change = latest_unrate - unrate_3m_ago
        unemployment_falling = unrate_change < -0.1  # Dropping by >0.1% = falling
    else:
        unemployment_falling = False

    # Score logic
    if gdp_growing and unemployment_falling:
        # Strong expansion
        if gdp_growing and unrate_3m_ago and (unrate_3m_ago - latest_unrate) > 0.3:
            return 9.0  # Very strong
        return 8.0  # Moderate expansion
    elif gdp_growing and not unemployment_falling:
        # GDP growing but unemployment rising/sideways
        return 6.0  # Mixed signals
    elif not gdp_growing and unemployment_falling:
        # GDP stagnant but unemployment falling
        return 5.0
    elif not gdp_growing and latest_unrate > 6.0:
        # Contraction + high unemployment = recession
        return 2.0
    else:
        # Stagnant
        return 5.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test with empty data (should return neutral 5)
    from backend.models.schemas import FredData, FredSeries
    fd = FredData()
    fd.series.append(FredSeries(series_id="GDPC1", series_name="GDP", date="2026-01-01", value=23000.0))
    fd.series.append(FredSeries(series_id="GDPC1", series_name="GDP", date="2025-10-01", value=22800.0))
    fd.series.append(FredSeries(series_id="GDPC1", series_name="GDP", date="2025-07-01", value=22600.0))
    fd.series.append(FredSeries(series_id="GDPC1", series_name="GDP", date="2025-04-01", value=22400.0))
    fd.series.append(FredSeries(series_id="GDPC1", series_name="GDP", date="2025-01-01", value=22100.0))
    fd.series.append(FredSeries(series_id="UNRATE", series_name="UNRATE", date="2026-01-01", value=4.0))
    fd.series.append(FredSeries(series_id="UNRATE", series_name="UNRATE", date="2025-10-01", value=4.2))
    fd.series.append(FredSeries(series_id="UNRATE", series_name="UNRATE", date="2025-07-01", value=4.5))
    fd.series.append(FredSeries(series_id="UNRATE", series_name="UNRATE", date="2025-04-01", value=4.7))

    scores = compute_macro_score(fd)
    print(f"Macro scores: {scores}")