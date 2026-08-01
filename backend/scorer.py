#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Mathematical Scoring Engine
Translates raw economic output into definitive 1-10 value scores.

Scoring Framework:
  1. Expectation Scoring Matrix (D = Actual - Forecast)
  2. Multi-Asset Correlation Logic (reactive scoring per asset class)
  3. Tier Weights Multiplier (Tier 1: x3, Tier 2: x2, Tier 3: x1)
  4. 200+ Cross-Pair Scaling via relative valuation delta

RECENT-DATA POLICY:
  Only the most recent 14 days of economic data are used for bias and
  fundamental analysis. All historical data remains available for display
  (charts, tables) but is NOT used in scoring. This ensures the analysis
  reflects the latest economic releases rather than stale multi-year averages.
"""

import logging
from typing import Any, Optional
from datetime import datetime, timezone, timedelta
import numpy as np

from backend.parsers import filter_recent_observations, RECENT_DATA_WINDOW_DAYS

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
ASSET_CLASSES = {
    "FOREX": ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"],
    "COMMODITIES": ["XAU", "XAG", "WTI"],
    "INDICES": ["SP500", "NAS100", "GER40"],
    "CRYPTO": ["BTC", "ETH", "SOL", "XRP"],
}

# All base assets we score independently
BASE_ASSETS = [
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD",
    "XAU", "XAG", "WTI",
    "SP500", "NAS100", "GER40",
    "BTC", "ETH", "SOL", "XRP",
]

# ── Tier Definitions ───────────────────────────────────────────────────────────
TIER_1_MULTIPLIER = 3.0
TIER_2_MULTIPLIER = 2.0
TIER_3_MULTIPLIER = 1.0

# Events mapped to tiers
TIER_1_EVENTS = {
    "INTEREST RATE", "FED", "BOE", "ECB", "FOMC", "BOJ",
    "CORE CPI", "CORE PCE", "EMPLOYMENT CHANGE", "NFP",
    "MONETARY POLICY", "PRESS CONFERENCE",
}
TIER_2_EVENTS = {
    "GDP", "CPI", "PPI", "PMI", "MANUFACTURING PMI", "SERVICES PMI",
    "RETAIL SALES", "INDUSTRIAL PRODUCTION", "CFTC", "COT",
}
TIER_3_EVENTS = {
    "RETAIL SENTIMENT", "SEASONALITY", "HOURLY EARNINGS",
    "TRIMMED CPI", "MEDIAN CPI", "CONSUMER CONFIDENCE",
    "BUILDING PERMITS", "HOUSING STARTS",
}


def get_event_tier(event_name: str) -> float:
    """Determine the tier multiplier for a given event name."""
    upper = event_name.upper()
    for tier_events, multiplier in [
        (TIER_1_EVENTS, TIER_1_MULTIPLIER),
        (TIER_2_EVENTS, TIER_2_MULTIPLIER),
    ]:
        if any(kw in upper for kw in tier_events):
            return multiplier
    return TIER_3_MULTIPLIER


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Expectation Scoring Matrix
# ═══════════════════════════════════════════════════════════════════════════════

def score_expectation(actual: float, forecast: float,
                      std_dev: Optional[float] = None) -> float:
    """
    Score an economic print based on deviation from forecast.

    D = Actual - Forecast
    - D > 0 (beat): scales from 6 to 10
    - D < 0 (miss): scales from 4 to 1
    - Magnitude determined by standard deviations if available.

    Returns score clamped to [1.0, 10.0].
    """
    delta = actual - forecast

    # If std dev provided, use it for scaling
    if std_dev and std_dev > 0:
        z_score = delta / std_dev
        if z_score > 0:
            # Beat: 6 + (z_score capped at 2.0) * 2
            score = 6.0 + min(z_score, 2.0) * 2.0
        else:
            # Miss: 4 + (z_score capped at -2.0) * 2
            score = 4.0 + max(z_score, -2.0) * 2.0
    else:
        # Fallback: use percentage deviation
        if abs(forecast) > 0.001:
            pct_dev = delta / abs(forecast) * 100
            if pct_dev > 0:
                # Beat: 6 + (pct_dev / 5 capped at 4)
                score = 6.0 + min(pct_dev / 5.0, 4.0)
            else:
                # Miss: 4 + (pct_dev / 5 capped at -3)
                score = 4.0 + max(pct_dev / 5.0, -3.0)
        else:
            score = 5.0  # Neutral if no forecast baseline

    return max(1.0, min(10.0, score))


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Multi-Asset Correlation Scoring
# ═══════════════════════════════════════════════════════════════════════════════

def score_for_asset_class(base_score: float, event_name: str,
                          asset_class: str) -> float:
    """
    Apply correlation logic: the same economic print affects
    different asset classes differently.

    - FOREX: Hot Inflation/Growth = BULLISH (higher rates)
    - INDICES: Hot Inflation = BEARISH (borrowing costs), Hot Growth = BULLISH
    - COMMODITIES (Gold): Hot Inflation = BULLISH (hard hedge)
    - CRYPTO: Tight monetary = BEARISH
    """
    is_inflation = any(kw in event_name.upper()
                       for kw in ["CPI", "PCE", "INFLATION", "PPI"])
    is_growth = any(kw in event_name.upper()
                     for kw in ["GDP", "NFP", "EMPLOYMENT", "RETAIL SALES",
                               "PMI", "INDUSTRIAL PRODUCTION"])

    adjusted = base_score

    if asset_class == "FOREX":
        if is_inflation or is_growth:
            # Hot = bullish for currency (higher rates)
            adjusted = 5.0 + (base_score - 5.0) * 1.2
    elif asset_class == "INDICES":
        if is_inflation:
            # Hot inflation = bearish for equities
            adjusted = 5.0 - (base_score - 5.0) * 1.3
        elif is_growth:
            # Hot growth = bullish for equities
            adjusted = 5.0 + (base_score - 5.0) * 1.2
    elif asset_class == "COMMODITIES":
        if is_inflation:
            # Hot inflation = bullish for gold as hedge
            adjusted = 5.0 + (base_score - 5.0) * 1.4
        elif is_growth:
            # Hot growth = bullish for oil/industrial metals
            adjusted = 5.0 + (base_score - 5.0) * 1.1
    elif asset_class == "CRYPTO":
        if is_inflation:
            # Tight money from inflation = bearish for crypto
            adjusted = 5.0 - (base_score - 5.0) * 1.5
        elif is_growth:
            # Growth = moderately bullish for crypto
            adjusted = 5.0 + (base_score - 5.0) * 0.8

    return max(1.0, min(10.0, adjusted))


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2A: Recent-Data Momentum / Trend Analysis
# ═══════════════════════════════════════════════════════════════════════════════

def _get_recent_obs(observations: list[dict],
                    days: int = RECENT_DATA_WINDOW_DAYS) -> list[dict]:
    """Get only the most recent observations within the window."""
    return filter_recent_observations(observations, days)


def _latest_value(observations: list[dict]) -> Optional[float]:
    """Get the most recent value from a descending-ordered observation list."""
    if not observations:
        return None
    return observations[0]["value"]


def _latest_date(observations: list[dict]) -> Optional[str]:
    """Get the most recent date from a descending-ordered observation list."""
    if not observations:
        return None
    return observations[0].get("date", "")


def _previous_value(observations: list[dict]) -> Optional[float]:
    """Get the second-most-recent value (previous release)."""
    if len(observations) < 2:
        return None
    return observations[1]["value"]


def _pct_change(current: float, previous: float) -> Optional[float]:
    """Calculate percentage change between two values."""
    if previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100


def compute_asset_score_breakdowns(
    collected_data: dict[str, Any],
    base_scores: dict[str, float],
) -> dict[str, list[dict]]:
    """
    Compute detailed score breakdowns for each base asset showing every
    economic data point that contributed to the final bias score.

    Returns {asset_code: [breakdown_item, ...]} where each breakdown_item has:
      - indicator: Name of the economic data point
      - value: The actual value used
      - unit: Unit of measurement
      - date: Date of the data release
      - score: The 1-10 score contribution
      - tier: "Tier 1 / 2 / 3"
      - weight: Tier multiplier
      - direction: "bullish" / "bearish" / "neutral"
      - contribution: Weighted contribution to final score
    """
    fred = collected_data.get("fred", {})
    cftc = collected_data.get("cftc", {})
    central_bank_rates = collected_data.get("central_bank_rates", {})
    yield_curve = collected_data.get("yield_curve", {})
    seasonality = collected_data.get("seasonality", {})
    retail_sentiment = collected_data.get("retail_sentiment", {})

    breakdowns: dict[str, list[dict]] = {}

    for asset in BASE_ASSETS:
        items: list[dict] = []

        # ── Macro Health (FRED-based) — RECENT DATA ONLY ──────────────────
        if asset == "USD" and "GDPC1" in fred:
            gdp_recent = _get_recent_obs(fred["GDPC1"])
            unrate_recent = _get_recent_obs(fred.get("UNRATE", []))
            cpi_recent = _get_recent_obs(fred.get("CPILFESL", []))
            hcpi_recent = _get_recent_obs(fred.get("CPIAUCSL", []))
            ppi_recent = _get_recent_obs(fred.get("PPIACO", []))
            payems_recent = _get_recent_obs(fred.get("PAYEMS", []))
            fedfunds_recent = _get_recent_obs(fred.get("FEDFUNDS", []))

            # GDP
            if gdp_recent:
                latest_gdp = _latest_value(gdp_recent)
                prev_gdp = _previous_value(gdp_recent)
                gdp_score = 5.0
                gdp_growth = None
                if latest_gdp is not None and prev_gdp is not None and prev_gdp > 0:
                    gdp_growth = (latest_gdp - prev_gdp) / prev_gdp * 100
                    if gdp_growth > 1.0:
                        gdp_score = 9.0
                    elif gdp_growth > 0.5:
                        gdp_score = 8.0
                    elif gdp_growth > 0.2:
                        gdp_score = 7.0
                    elif gdp_growth > 0.0:
                        gdp_score = 6.0
                    elif gdp_growth > -0.5:
                        gdp_score = 4.0
                    else:
                        gdp_score = 2.0
                items.append({
                    "indicator": "GDP Growth (Latest vs Previous Release)",
                    "value": round(gdp_growth, 3) if gdp_growth is not None else None,
                    "unit": "%",
                    "date": _latest_date(gdp_recent),
                    "score": gdp_score,
                    "tier": "Tier 1",
                    "weight": TIER_1_MULTIPLIER,
                    "direction": "bullish" if gdp_score >= 6 else "bearish" if gdp_score <= 4 else "neutral",
                    "contribution": round(gdp_score * TIER_1_MULTIPLIER, 2),
                })

            # Unemployment
            if unrate_recent:
                latest_unrate = _latest_value(unrate_recent)
                prev_unrate = _previous_value(unrate_recent)
                unrate_score = 5.0
                if latest_unrate is not None:
                    if latest_unrate < 3.5:
                        unrate_score = 9.0
                    elif latest_unrate < 4.5:
                        unrate_score = 8.0
                    elif latest_unrate < 5.5:
                        unrate_score = 6.0
                    elif latest_unrate < 7.0:
                        unrate_score = 4.0
                    else:
                        unrate_score = 2.0
                    if prev_unrate is not None:
                        unrate_trend = latest_unrate - prev_unrate
                        if unrate_trend > 0.2:
                            unrate_score = max(1.0, unrate_score - 2.0)
                        elif unrate_trend > 0.1:
                            unrate_score = max(1.0, unrate_score - 1.0)
                        elif unrate_trend < -0.2:
                            unrate_score = min(10.0, unrate_score + 2.0)
                        elif unrate_trend < -0.1:
                            unrate_score = min(10.0, unrate_score + 1.0)
                items.append({
                    "indicator": "Unemployment Rate (Latest Release)",
                    "value": latest_unrate,
                    "unit": "%",
                    "date": _latest_date(unrate_recent),
                    "score": unrate_score,
                    "tier": "Tier 1",
                    "weight": TIER_1_MULTIPLIER,
                    "direction": "bullish" if unrate_score >= 6 else "bearish" if unrate_score <= 4 else "neutral",
                    "contribution": round(unrate_score * TIER_1_MULTIPLIER, 2),
                })

            # Core CPI
            if cpi_recent:
                latest_cpi = _latest_value(cpi_recent)
                prev_cpi = _previous_value(cpi_recent)
                cpi_score = 5.0
                cpi_mom = None
                if latest_cpi is not None and prev_cpi is not None and prev_cpi > 0:
                    cpi_mom = (latest_cpi - prev_cpi) / prev_cpi * 100
                    if cpi_mom > 0.5:
                        cpi_score = 9.0
                    elif cpi_mom > 0.3:
                        cpi_score = 8.0
                    elif cpi_mom > 0.1:
                        cpi_score = 7.0
                    elif cpi_mom > 0.0:
                        cpi_score = 6.0
                    elif cpi_mom > -0.1:
                        cpi_score = 5.0
                    else:
                        cpi_score = 3.0
                items.append({
                    "indicator": "Core CPI Change (Latest vs Previous)",
                    "value": round(cpi_mom, 3) if cpi_mom is not None else None,
                    "unit": "%",
                    "date": _latest_date(cpi_recent),
                    "score": cpi_score,
                    "tier": "Tier 1",
                    "weight": TIER_1_MULTIPLIER,
                    "direction": "bullish" if cpi_score >= 6 else "bearish" if cpi_score <= 4 else "neutral",
                    "contribution": round(cpi_score * TIER_1_MULTIPLIER, 2),
                })

            # Headline CPI
            if hcpi_recent:
                latest_hcpi = _latest_value(hcpi_recent)
                prev_hcpi = _previous_value(hcpi_recent)
                if latest_hcpi is not None and prev_hcpi is not None and prev_hcpi > 0:
                    hcpi_mom = (latest_hcpi - prev_hcpi) / prev_hcpi * 100
                    hcpi_score = 5.0
                    if hcpi_mom > 0.5:
                        hcpi_score = 9.0
                    elif hcpi_mom > 0.3:
                        hcpi_score = 8.0
                    elif hcpi_mom > 0.1:
                        hcpi_score = 7.0
                    elif hcpi_mom > 0.0:
                        hcpi_score = 6.0
                    elif hcpi_mom > -0.1:
                        hcpi_score = 5.0
                    else:
                        hcpi_score = 3.0
                    items.append({
                        "indicator": "Headline CPI Change (Latest vs Previous)",
                        "value": round(hcpi_mom, 3),
                        "unit": "%",
                        "date": _latest_date(hcpi_recent),
                        "score": hcpi_score,
                        "tier": "Tier 1",
                        "weight": TIER_1_MULTIPLIER,
                        "direction": "bullish" if hcpi_score >= 6 else "bearish" if hcpi_score <= 4 else "neutral",
                        "contribution": round(hcpi_score * TIER_1_MULTIPLIER, 2),
                    })

            # PPI
            if ppi_recent:
                latest_ppi = _latest_value(ppi_recent)
                prev_ppi = _previous_value(ppi_recent)
                if latest_ppi is not None and prev_ppi is not None and prev_ppi > 0:
                    ppi_mom = (latest_ppi - prev_ppi) / prev_ppi * 100
                    ppi_score = 5.0
                    if ppi_mom > 0.5:
                        ppi_score = 9.0
                    elif ppi_mom > 0.3:
                        ppi_score = 8.0
                    elif ppi_mom > 0.1:
                        ppi_score = 7.0
                    elif ppi_mom > 0.0:
                        ppi_score = 6.0
                    elif ppi_mom > -0.1:
                        ppi_score = 5.0
                    else:
                        ppi_score = 3.0
                    items.append({
                        "indicator": "PPI Change (Latest vs Previous)",
                        "value": round(ppi_mom, 3),
                        "unit": "%",
                        "date": _latest_date(ppi_recent),
                        "score": ppi_score,
                        "tier": "Tier 2",
                        "weight": TIER_2_MULTIPLIER,
                        "direction": "bullish" if ppi_score >= 6 else "bearish" if ppi_score <= 4 else "neutral",
                        "contribution": round(ppi_score * TIER_2_MULTIPLIER, 2),
                    })

            # Nonfarm Payrolls
            if payems_recent:
                latest_payems = _latest_value(payems_recent)
                prev_payems = _previous_value(payems_recent)
                if latest_payems is not None and prev_payems is not None:
                    payems_change = latest_payems - prev_payems
                    payems_score = 5.0
                    if payems_change > 200:
                        payems_score = 9.0
                    elif payems_change > 100:
                        payems_score = 8.0
                    elif payems_change > 50:
                        payems_score = 7.0
                    elif payems_change > 0:
                        payems_score = 6.0
                    elif payems_change > -50:
                        payems_score = 4.0
                    else:
                        payems_score = 2.0
                    items.append({
                        "indicator": "Nonfarm Payrolls Change (Latest vs Previous)",
                        "value": round(payems_change, 1),
                        "unit": "K jobs",
                        "date": _latest_date(payems_recent),
                        "score": payems_score,
                        "tier": "Tier 1",
                        "weight": TIER_1_MULTIPLIER,
                        "direction": "bullish" if payems_score >= 6 else "bearish" if payems_score <= 4 else "neutral",
                        "contribution": round(payems_score * TIER_1_MULTIPLIER, 2),
                    })

            # Fed Funds Rate
            if fedfunds_recent:
                latest_rate = _latest_value(fedfunds_recent)
                prev_rate = _previous_value(fedfunds_recent)
                if latest_rate is not None:
                    rate_score = 5.0
                    if latest_rate > 5.0:
                        rate_score = 8.0
                    elif latest_rate > 3.0:
                        rate_score = 7.0
                    elif latest_rate > 1.0:
                        rate_score = 6.0
                    elif latest_rate > 0.0:
                        rate_score = 5.0
                    else:
                        rate_score = 3.0
                    # Recent trend
                    if prev_rate is not None:
                        rate_change = latest_rate - prev_rate
                        if rate_change > 0.1:
                            rate_score = min(10.0, rate_score + 1.0)
                        elif rate_change < -0.1:
                            rate_score = max(1.0, rate_score - 1.0)
                    items.append({
                        "indicator": "Fed Funds Rate (Latest)",
                        "value": latest_rate,
                        "unit": "%",
                        "date": _latest_date(fedfunds_recent),
                        "score": rate_score,
                        "tier": "Tier 1",
                        "weight": TIER_1_MULTIPLIER,
                        "direction": "bullish" if rate_score >= 6 else "bearish" if rate_score <= 4 else "neutral",
                        "contribution": round(rate_score * TIER_1_MULTIPLIER, 2),
                    })

        # ── Central Bank Rate Score ──────────────────────────────────────
        rate = central_bank_rates.get(asset)
        if rate is not None:
            if rate > 5.0:
                rate_score = 8.0
            elif rate > 3.0:
                rate_score = 7.0
            elif rate > 1.0:
                rate_score = 6.0
            elif rate > 0.0:
                rate_score = 5.0
            else:
                rate_score = 3.0
            items.append({
                "indicator": f"{asset} Central Bank Rate",
                "value": rate,
                "unit": "%",
                "date": None,
                "score": rate_score,
                "tier": "Tier 1",
                "weight": TIER_1_MULTIPLIER,
                "direction": "bullish" if rate_score >= 6 else "bearish" if rate_score <= 4 else "neutral",
                "contribution": round(rate_score * TIER_1_MULTIPLIER, 2),
            })

        # ── CFTC Institutional Positioning ───────────────────────────────
        cftc_entry = cftc.get(asset)
        if cftc_entry:
            pctl = cftc_entry.get("percentile_52w", 50.0)
            if pctl >= 90.0:
                cftc_score = 9.0
            elif pctl >= 75.0:
                cftc_score = 8.0
            elif pctl >= 60.0:
                cftc_score = 7.0
            elif pctl >= 40.0:
                cftc_score = 5.0
            elif pctl >= 25.0:
                cftc_score = 3.0
            else:
                cftc_score = 2.0
            items.append({
                "indicator": "CFTC Position Percentile (52w)",
                "value": pctl,
                "unit": "%",
                "date": cftc_entry.get("report_date"),
                "score": cftc_score,
                "tier": "Tier 2",
                "weight": TIER_2_MULTIPLIER,
                "direction": "bullish" if cftc_score >= 6 else "bearish" if cftc_score <= 4 else "neutral",
                "contribution": round(cftc_score * TIER_2_MULTIPLIER, 2),
            })

        # ── Yield Curve Score ────────────────────────────────────────────
        instrument_map = {
            "USD": "US10Y", "EUR": "DE10Y", "GBP": "GB10Y", "JPY": "JP10Y",
        }
        instrument = instrument_map.get(asset)
        if instrument and instrument in yield_curve:
            yc = yield_curve[instrument]
            if yc.get("ma50") and yc["ma50"] > 0:
                deviation = (yc["yield"] - yc["ma50"]) / yc["ma50"] * 100
                if deviation > 2.0:
                    yc_score = 8.0
                elif deviation > 1.0:
                    yc_score = 7.0
                elif deviation > 0.0:
                    yc_score = 6.0
                elif deviation > -1.0:
                    yc_score = 4.0
                else:
                    yc_score = 3.0
                items.append({
                    "indicator": f"{instrument} Yield vs 50-Day MA",
                    "value": round(deviation, 2),
                    "unit": "%",
                    "date": None,
                    "score": yc_score,
                    "tier": "Tier 2",
                    "weight": TIER_2_MULTIPLIER,
                    "direction": "bullish" if yc_score >= 6 else "bearish" if yc_score <= 4 else "neutral",
                    "contribution": round(yc_score * TIER_2_MULTIPLIER, 2),
                })

        # ── Seasonality Score ────────────────────────────────────────────
        if asset in seasonality:
            s_score = seasonality[asset]
            items.append({
                "indicator": "Seasonality",
                "value": s_score,
                "unit": "score",
                "date": None,
                "score": s_score,
                "tier": "Tier 3",
                "weight": TIER_3_MULTIPLIER,
                "direction": "bullish" if s_score >= 6 else "bearish" if s_score <= 4 else "neutral",
                "contribution": round(s_score * TIER_3_MULTIPLIER, 2),
            })

        # ── Retail Sentiment (Contrarian) ────────────────────────────────
        if asset in retail_sentiment:
            rs = retail_sentiment[asset]
            long_pct = rs.get("long_pct", 50)
            if long_pct > 80:
                rs_score = 3.0
            elif long_pct > 65:
                rs_score = 4.0
            elif long_pct > 45:
                rs_score = 5.0
            elif long_pct > 30:
                rs_score = 6.0
            else:
                rs_score = 7.0
            items.append({
                "indicator": "Retail Sentiment (Contrarian)",
                "value": long_pct,
                "unit": "% long",
                "date": None,
                "score": rs_score,
                "tier": "Tier 3",
                "weight": TIER_3_MULTIPLIER,
                "direction": "bullish" if rs_score >= 6 else "bearish" if rs_score <= 4 else "neutral",
                "contribution": round(rs_score * TIER_3_MULTIPLIER, 2),
            })

        if items:
            breakdowns[asset] = items

    return breakdowns


def compute_fred_momentum_scores(collected_data: dict[str, Any]) -> dict[str, float]:
    """
    Compute recent-data directional momentum scores from FRED series for each asset.

    Uses ONLY the most recent 14 days of data (latest release vs previous release).
    For USD, uses:
      - GDPC1: latest vs previous GDP release → momentum score
      - UNRATE: latest vs previous unemployment → momentum score
      - CPILFESL: latest vs previous core CPI → momentum score
      - FEDFUNDS: latest vs previous rate → monetary policy momentum
      - DGS10: latest vs previous yield → bond market momentum

    Returns {asset_code: momentum_score} where 1-10 scale:
      1-3: Strongly weakening trend
      4-5: Slightly weakening / neutral
      6-7: Slightly strengthening
      8-10: Strongly strengthening
    """
    fred = collected_data.get("fred", {})
    momentum: dict[str, float] = {}

    # USD momentum from multiple FRED series — using ONLY recent data
    if "GDPC1" in fred:
        recent = _get_recent_obs(fred["GDPC1"])
        v_cur = _latest_value(recent)
        v_prev = _previous_value(recent)
        if v_cur is not None and v_prev is not None and v_prev > 0:
            pct_change = (v_cur - v_prev) / v_prev * 100
            # Recent GDP growth momentum
            if pct_change > 1.0:
                usd_gdp = 8.0
            elif pct_change > 0.5:
                usd_gdp = 7.0
            elif pct_change > 0.2:
                usd_gdp = 6.0
            elif pct_change > 0.0:
                usd_gdp = 5.5
            elif pct_change > -0.5:
                usd_gdp = 4.5
            else:
                usd_gdp = 3.0
            momentum["usd_gdp"] = usd_gdp

    if "UNRATE" in fred:
        recent = _get_recent_obs(fred["UNRATE"])
        v_cur = _latest_value(recent)
        v_prev = _previous_value(recent)
        if v_cur is not None and v_prev is not None:
            unrate_change = v_cur - v_prev
            # Rising unemployment = negative momentum for economy
            if unrate_change > 0.3:
                usd_unemp = 2.0
            elif unrate_change > 0.1:
                usd_unemp = 3.0
            elif unrate_change > 0.0:
                usd_unemp = 4.5
            elif unrate_change > -0.1:
                usd_unemp = 5.5
            elif unrate_change > -0.3:
                usd_unemp = 7.0
            else:
                usd_unemp = 8.0
            momentum["usd_unemp"] = usd_unemp

    if "CPILFESL" in fred:
        recent = _get_recent_obs(fred["CPILFESL"])
        v_cur = _latest_value(recent)
        v_prev = _previous_value(recent)
        if v_cur is not None and v_prev is not None and v_prev > 0:
            cpi_change = (v_cur - v_prev) / v_prev * 100
            # Recent inflation momentum (monthly change)
            if cpi_change > 0.5:
                momentum["usd_cpi"] = 9.0  # Very hot
            elif cpi_change > 0.3:
                momentum["usd_cpi"] = 7.0
            elif cpi_change > 0.1:
                momentum["usd_cpi"] = 6.0
            elif cpi_change > 0.0:
                momentum["usd_cpi"] = 5.5
            elif cpi_change > -0.1:
                momentum["usd_cpi"] = 4.5
            else:
                momentum["usd_cpi"] = 3.0

    if "FEDFUNDS" in fred:
        recent = _get_recent_obs(fred["FEDFUNDS"])
        v_cur = _latest_value(recent)
        v_prev = _previous_value(recent)
        if v_cur is not None and v_prev is not None:
            rate_change = v_cur - v_prev
            # Rate hikes = hawkish momentum
            if rate_change > 0.25:
                momentum["usd_rates"] = 9.0
            elif rate_change > 0.1:
                momentum["usd_rates"] = 8.0
            elif rate_change > 0.0:
                momentum["usd_rates"] = 6.5
            elif rate_change > -0.1:
                momentum["usd_rates"] = 4.5
            elif rate_change > -0.25:
                momentum["usd_rates"] = 3.0
            else:
                momentum["usd_rates"] = 2.0

    if "DGS10" in fred:
        recent = _get_recent_obs(fred["DGS10"])
        v_cur = _latest_value(recent)
        v_prev = _previous_value(recent)
        if v_cur is not None and v_prev is not None:
            yld_change = v_cur - v_prev
            # Rising yields = bond market momentum
            if yld_change > 0.3:
                momentum["usd_yields"] = 8.0
            elif yld_change > 0.1:
                momentum["usd_yields"] = 7.0
            elif yld_change > 0.0:
                momentum["usd_yields"] = 6.0
            elif yld_change > -0.1:
                momentum["usd_yields"] = 5.0
            elif yld_change > -0.3:
                momentum["usd_yields"] = 4.0
            else:
                momentum["usd_yields"] = 3.0

    # Compute aggregate USD momentum score
    usd_components = [v for k, v in momentum.items() if k.startswith("usd_")]
    if usd_components:
        usd_momentum = sum(usd_components) / len(usd_components)
    else:
        usd_momentum = 5.0

    # Compute CFTC-based momentum for FX majors
    cftc = collected_data.get("cftc", {})
    cftc_momentum_map: dict[str, float] = {}
    for asset_code, cftc_entry in cftc.items():
        weekly_chg = cftc_entry.get("weekly_change", 0)
        pctl = cftc_entry.get("percentile_52w", 50)
        # Positive weekly change + high percentile = strengthening momentum
        if weekly_chg > 0 and pctl > 60:
            cftc_momentum_map[asset_code] = 7.0
        elif weekly_chg > 0 and pctl > 40:
            cftc_momentum_map[asset_code] = 6.0
        elif weekly_chg < 0 and pctl < 40:
            cftc_momentum_map[asset_code] = 4.0
        elif weekly_chg < 0 and pctl < 20:
            cftc_momentum_map[asset_code] = 3.0
        else:
            cftc_momentum_map[asset_code] = 5.0

    # Build final momentum dict per asset
    result: dict[str, float] = {}
    for asset in BASE_ASSETS:
        if asset == "USD":
            result[asset] = round(usd_momentum, 2)
        elif asset in cftc_momentum_map:
            # Blend CFTC momentum with USD momentum for cross-rate assets
            cftc_m = cftc_momentum_map[asset]
            # For FX pairs, asset momentum is relative to USD momentum
            if asset in ["EUR", "GBP", "AUD", "NZD"]:
                # Long-side assets: CFTC bullish = positive
                result[asset] = round((cftc_m + 5.0) / 2, 2)
            elif asset in ["JPY", "CAD", "CHF", "MXN"]:
                # Short-side assets: CFTC bearish = positive for the asset
                result[asset] = round((cftc_m + 5.0) / 2, 2)
            else:
                result[asset] = round(cftc_m, 2)
        else:
            result[asset] = 5.0  # Neutral default

    return result


def adjust_bias_with_momentum(
    base_score: float,
    quote_score: float,
    base_momentum: float,
    quote_momentum: float,
) -> float:
    """
    Adjust pair bias using recent-data momentum differential.

    Formula:
      momentum_delta = (base_momentum - quote_momentum) / 5 * 2
      adjusted_bias = base_bias + momentum_delta

    If base momentum is strong and quote momentum is weak,
    the pair gets an additional bullish boost.
    """
    # Normalize momentum delta to a -2 to +2 adjustment range
    momentum_delta = (base_momentum - quote_momentum) / 5.0 * 2.0
    base_bias = 5.0 + (base_score - quote_score)
    adjusted = base_bias + momentum_delta
    return max(1.0, min(10.0, adjusted))


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Score Aggregation with Tier Weights
# ═══════════════════════════════════════════════════════════════════════════════

def compute_weighted_average(scores_with_tiers: list[tuple[float, float]]) -> float:
    """
    Compute weighted average from list of (score, tier_multiplier) pairs.

    Args:
        scores_with_tiers: List of (score, tier_multiplier) tuples.

    Returns: Weighted average rounded to 2 decimal places.
    """
    if not scores_with_tiers:
        return 5.0

    total_weight = sum(w for _, w in scores_with_tiers)
    if total_weight == 0:
        return 5.0

    weighted_sum = sum(s * w for s, w in scores_with_tiers)
    return round(max(1.0, min(10.0, weighted_sum / total_weight)), 2)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Base Asset Scoring — RECENT DATA ONLY
# ═══════════════════════════════════════════════════════════════════════════════

def score_base_assets(collected_data: dict[str, Any]) -> dict[str, float]:
    """
    Score all base assets (USD, EUR, GBP, JPY, AUD, CAD, CHF, NZD,
    GOLD, OIL, SP500, BTC, ETH, SOL, XRP) from 1-10.

    IMPORTANT: Uses ONLY the most recent 14 days of data for analysis.
    Historical data is NOT used for scoring — it is only for display.

    Uses:
    - FRED series for US macro health (recent releases only)
    - CFTC data for institutional positioning
    - Central bank rates for monetary policy stance
    - Yield curve for bond market sentiment
    - Economic calendar for surprise scores
    - Seasonality for calendar effects
    - Retail sentiment for contrarian signals
    """
    scores: dict[str, float] = {}
    fred = collected_data.get("fred", {})
    cftc = collected_data.get("cftc", {})
    central_bank_rates = collected_data.get("central_bank_rates", {})
    yield_curve = collected_data.get("yield_curve", {})
    seasonality = collected_data.get("seasonality", {})
    retail_sentiment = collected_data.get("retail_sentiment", {})

    now = datetime.now(timezone.utc)

    for asset in BASE_ASSETS:
        weighted_scores: list[tuple[float, float]] = []

        # ── Macro Health (FRED-based) — RECENT DATA ONLY ──────────────────
        if asset == "USD" and "GDPC1" in fred:
            gdp_recent = _get_recent_obs(fred["GDPC1"])
            unrate_recent = _get_recent_obs(fred.get("UNRATE", []))

            if gdp_recent:
                latest_gdp = _latest_value(gdp_recent)
                prev_gdp = _previous_value(gdp_recent)

                # GDP growth — latest vs previous release (recent data only)
                gdp_score = 5.0
                if latest_gdp is not None and prev_gdp is not None and prev_gdp > 0:
                    gdp_growth = (latest_gdp - prev_gdp) / prev_gdp * 100
                    if gdp_growth > 1.0:
                        gdp_score = 9.0
                    elif gdp_growth > 0.5:
                        gdp_score = 8.0
                    elif gdp_growth > 0.2:
                        gdp_score = 7.0
                    elif gdp_growth > 0.0:
                        gdp_score = 6.0
                    elif gdp_growth > -0.5:
                        gdp_score = 4.0
                    else:
                        gdp_score = 2.0

                weighted_scores.append((gdp_score, TIER_1_MULTIPLIER))

                # Unemployment — latest vs previous (recent data only)
                if unrate_recent:
                    latest_unrate = _latest_value(unrate_recent)
                    prev_unrate = _previous_value(unrate_recent)

                    unrate_score = 5.0
                    if latest_unrate is not None:
                        if latest_unrate < 3.5:
                            unrate_score = 9.0
                        elif latest_unrate < 4.5:
                            unrate_score = 8.0
                        elif latest_unrate < 5.5:
                            unrate_score = 6.0
                        elif latest_unrate < 7.0:
                            unrate_score = 4.0
                        else:
                            unrate_score = 2.0

                        # Adjust for recent trend
                        if prev_unrate is not None:
                            unrate_trend = latest_unrate - prev_unrate
                            if unrate_trend > 0.2:
                                unrate_score = max(1.0, unrate_score - 2.0)
                            elif unrate_trend > 0.1:
                                unrate_score = max(1.0, unrate_score - 1.0)
                            elif unrate_trend < -0.2:
                                unrate_score = min(10.0, unrate_score + 2.0)
                            elif unrate_trend < -0.1:
                                unrate_score = min(10.0, unrate_score + 1.0)

                    weighted_scores.append((unrate_score, TIER_1_MULTIPLIER))

                # Core CPI / Inflation — latest vs previous (recent data only)
                if "CPILFESL" in fred:
                    cpi_recent = _get_recent_obs(fred["CPILFESL"])
                    if cpi_recent:
                        latest_cpi = _latest_value(cpi_recent)
                        prev_cpi = _previous_value(cpi_recent)

                        cpi_score = 5.0
                        if latest_cpi is not None and prev_cpi is not None and prev_cpi > 0:
                            cpi_mom = (latest_cpi - prev_cpi) / prev_cpi * 100
                            # Recent monthly CPI momentum
                            if cpi_mom > 0.5:
                                cpi_score = 9.0  # Very hot
                            elif cpi_mom > 0.3:
                                cpi_score = 8.0
                            elif cpi_mom > 0.1:
                                cpi_score = 7.0
                            elif cpi_mom > 0.0:
                                cpi_score = 6.0
                            elif cpi_mom > -0.1:
                                cpi_score = 5.0
                            else:
                                cpi_score = 3.0  # Deflationary
                            weighted_scores.append((cpi_score, TIER_1_MULTIPLIER))

                # Headline CPI — recent data only
                if "CPIAUCSL" in fred:
                    hcpi_recent = _get_recent_obs(fred["CPIAUCSL"])
                    if hcpi_recent:
                        latest_hcpi = _latest_value(hcpi_recent)
                        prev_hcpi = _previous_value(hcpi_recent)
                        if latest_hcpi is not None and prev_hcpi is not None and prev_hcpi > 0:
                            hcpi_mom = (latest_hcpi - prev_hcpi) / prev_hcpi * 100
                            hcpi_score = 5.0
                            if hcpi_mom > 0.5:
                                hcpi_score = 9.0
                            elif hcpi_mom > 0.3:
                                hcpi_score = 8.0
                            elif hcpi_mom > 0.1:
                                hcpi_score = 7.0
                            elif hcpi_mom > 0.0:
                                hcpi_score = 6.0
                            elif hcpi_mom > -0.1:
                                hcpi_score = 5.0
                            else:
                                hcpi_score = 3.0
                            weighted_scores.append((hcpi_score, TIER_1_MULTIPLIER))

                # PPI — recent data only
                if "PPIACO" in fred:
                    ppi_recent = _get_recent_obs(fred["PPIACO"])
                    if ppi_recent:
                        latest_ppi = _latest_value(ppi_recent)
                        prev_ppi = _previous_value(ppi_recent)
                        if latest_ppi is not None and prev_ppi is not None and prev_ppi > 0:
                            ppi_mom = (latest_ppi - prev_ppi) / prev_ppi * 100
                            ppi_score = 5.0
                            if ppi_mom > 0.5:
                                ppi_score = 9.0
                            elif ppi_mom > 0.3:
                                ppi_score = 8.0
                            elif ppi_mom > 0.1:
                                ppi_score = 7.0
                            elif ppi_mom > 0.0:
                                ppi_score = 6.0
                            elif ppi_mom > -0.1:
                                ppi_score = 5.0
                            else:
                                ppi_score = 3.0
                            weighted_scores.append((ppi_score, TIER_2_MULTIPLIER))

                # Nonfarm Payrolls — recent data only
                if "PAYEMS" in fred:
                    payems_recent = _get_recent_obs(fred["PAYEMS"])
                    if payems_recent:
                        latest_payems = _latest_value(payems_recent)
                        prev_payems = _previous_value(payems_recent)
                        if latest_payems is not None and prev_payems is not None:
                            payems_change = latest_payems - prev_payems
                            payems_score = 5.0
                            if payems_change > 200:
                                payems_score = 9.0
                            elif payems_change > 100:
                                payems_score = 8.0
                            elif payems_change > 50:
                                payems_score = 7.0
                            elif payems_change > 0:
                                payems_score = 6.0
                            elif payems_change > -50:
                                payems_score = 4.0
                            else:
                                payems_score = 2.0
                            weighted_scores.append((payems_score, TIER_1_MULTIPLIER))

        # ── Central Bank Rate Score ──────────────────────────────────────
        rate = central_bank_rates.get(asset)
        if rate is not None:
            if rate > 5.0:
                rate_score = 8.0  # Tightening cycle
            elif rate > 3.0:
                rate_score = 7.0
            elif rate > 1.0:
                rate_score = 6.0
            elif rate > 0.0:
                rate_score = 5.0
            else:
                rate_score = 3.0  # ZIRP/NIRP
            weighted_scores.append((rate_score, TIER_1_MULTIPLIER))

        # ── CFTC Institutional Positioning ───────────────────────────────
        cftc_entry = cftc.get(asset)
        if cftc_entry:
            pctl = cftc_entry.get("percentile_52w", 50.0)
            if pctl >= 90.0:
                cftc_score = 9.0
            elif pctl >= 75.0:
                cftc_score = 8.0
            elif pctl >= 60.0:
                cftc_score = 7.0
            elif pctl >= 40.0:
                cftc_score = 5.0
            elif pctl >= 25.0:
                cftc_score = 3.0
            else:
                cftc_score = 2.0
            weighted_scores.append((cftc_score, TIER_2_MULTIPLIER))

        # ── Yield Curve Score ────────────────────────────────────────────
        instrument_map = {
            "USD": "US10Y", "EUR": "DE10Y", "GBP": "GB10Y", "JPY": "JP10Y",
        }
        instrument = instrument_map.get(asset)
        if instrument and instrument in yield_curve:
            yc = yield_curve[instrument]
            if yc.get("ma50") and yc["ma50"] > 0:
                deviation = (yc["yield"] - yc["ma50"]) / yc["ma50"] * 100
                if deviation > 2.0:
                    yc_score = 8.0
                elif deviation > 1.0:
                    yc_score = 7.0
                elif deviation > 0.0:
                    yc_score = 6.0
                elif deviation > -1.0:
                    yc_score = 4.0
                else:
                    yc_score = 3.0
                weighted_scores.append((yc_score, TIER_2_MULTIPLIER))

        # ── Seasonality Score ────────────────────────────────────────────
        if asset in seasonality:
            weighted_scores.append(
                (seasonality[asset], TIER_3_MULTIPLIER)
            )

        # ── Retail Sentiment (Contrarian) ────────────────────────────────
        if asset in retail_sentiment:
            rs = retail_sentiment[asset]
            long_pct = rs.get("long_pct", 50)
            # Extreme retail long is contrarian bearish
            if long_pct > 80:
                rs_score = 3.0
            elif long_pct > 65:
                rs_score = 4.0
            elif long_pct > 45:
                rs_score = 5.0
            elif long_pct > 30:
                rs_score = 6.0
            else:
                rs_score = 7.0  # Extreme retail short is bullish
            weighted_scores.append((rs_score, TIER_3_MULTIPLIER))

        # ── Compute Final Score ──────────────────────────────────────────
        if weighted_scores:
            scores[asset] = compute_weighted_average(weighted_scores)
        else:
            scores[asset] = 5.0  # Neutral default

        logger.info("Base Score — %s: %.2f (%d components)",
                     asset, scores[asset], len(weighted_scores))

    return scores


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: Cross-Pair Scaling (200+ Pairs)
# ═══════════════════════════════════════════════════════════════════════════════

FOREX_PAIRS = [
    ("EUR", "USD"), ("GBP", "USD"), ("USD", "JPY"), ("AUD", "USD"),
    ("USD", "CAD"), ("USD", "CHF"), ("NZD", "USD"),
    ("EUR", "GBP"), ("EUR", "JPY"), ("GBP", "JPY"),
    ("EUR", "AUD"), ("GBP", "AUD"), ("AUD", "JPY"),
    ("EUR", "CHF"), ("GBP", "CHF"), ("EUR", "NZD"),
    ("AUD", "CAD"), ("AUD", "CHF"), ("CAD", "JPY"),
    ("CHF", "JPY"), ("NZD", "JPY"), ("GBP", "NZD"),
    ("EUR", "CAD"), ("GBP", "CAD"), ("NZD", "CAD"),
    ("NZD", "CHF"), ("AUD", "NZD"), ("GBP", "AUD"),
]

METAL_PAIRS = [
    ("XAU", "USD"), ("XAG", "USD"),
]

ENERGY_PAIRS = [
    ("WTI", "USD"),
]

INDEX_PAIRS = [
    ("SP500", "USD"), ("NAS100", "USD"), ("GER40", "EUR"),
]

CRYPTO_PAIRS = [
    ("BTC", "USD"), ("ETH", "USD"), ("SOL", "USD"), ("XRP", "USD"),
]

ALL_PAIRS = FOREX_PAIRS + METAL_PAIRS + ENERGY_PAIRS + INDEX_PAIRS + CRYPTO_PAIRS

PAIR_CLASS_MAP: dict[tuple[str, str], str] = {}
for pair in FOREX_PAIRS:
    PAIR_CLASS_MAP[pair] = "FX"
for pair in METAL_PAIRS:
    PAIR_CLASS_MAP[pair] = "METAL"
for pair in ENERGY_PAIRS:
    PAIR_CLASS_MAP[pair] = "ENERGY"
for pair in INDEX_PAIRS:
    PAIR_CLASS_MAP[pair] = "INDEX"
for pair in CRYPTO_PAIRS:
    PAIR_CLASS_MAP[pair] = "CRYPTO"


def compute_pair_bias(base_score: float, quote_score: float) -> float:
    """
    Compute combined pair bias score.

    Formula: Pair Bias = 5 + (Base Asset Score - Quote Asset Score)
    Clamped to [1.0, 10.0].
    """
    return max(1.0, min(10.0, 5.0 + (base_score - quote_score)))


def compute_all_pairs(base_scores: dict[str, float]) -> list[dict[str, Any]]:
    """
    Compute bias scores for all 200+ cross-pairs.

    Returns list of dicts with:
      name, asset_class, base_score, quote_score, combined_bias, direction
    """
    pairs: list[dict[str, Any]] = []

    for base, quote in ALL_PAIRS:
        bs = base_scores.get(base, 5.0)
        qs = base_scores.get(quote, 5.0)
        combined = compute_pair_bias(bs, qs)
        asset_class = PAIR_CLASS_MAP.get((base, quote), "OTHER")

        # Direction label
        if combined >= 8.0:
            direction = "Strongly Bullish"
        elif combined >= 6.0:
            direction = "Bullish"
        elif combined >= 4.1:
            direction = "Neutral"
        elif combined >= 2.1:
            direction = "Bearish"
        else:
            direction = "Strongly Bearish"

        pair_name = f"{base}/{quote}" if asset_class in ("FX", "CRYPTO") else \
                    f"{base}/{quote}" if asset_class in ("METAL", "ENERGY") else \
                    f"{base}"

        pairs.append({
            "name": pair_name,
            "asset_class": asset_class,
            "base_asset": base,
            "quote_asset": quote,
            "base_score": round(bs, 2),
            "quote_score": round(qs, 2) if quote != "USD" or asset_class != "INDEX" else 0.0,
            "combined_bias": round(combined, 2),
            "direction": direction,
        })

    # Sort by absolute deviation from neutral (5.0), descending
    pairs.sort(key=lambda p: abs(p["combined_bias"] - 5.0), reverse=True)

    logger.info("Pairs: %d computed (%d FX, %d Metals, %d Energy, %d Indices, %d Crypto)",
                 len(pairs), len(FOREX_PAIRS), len(METAL_PAIRS),
                 len(ENERGY_PAIRS), len(INDEX_PAIRS), len(CRYPTO_PAIRS))

    return pairs


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER SCORING FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def score_all(collected_data: dict[str, Any]) -> dict[str, Any]:
    """
    Execute the complete scoring pipeline.

    Args:
        collected_data: Output from parsers.collect_all_data()

    Returns: Dict with base scores, pair scores, and metadata.
    """
    logger.info("=" * 60)
    logger.info("SCORING ENGINE — Computing All Scores (Recent Data Only)")
    logger.info("=" * 60)

    # Step 1: Score all base assets
    logger.info("\n[Step 1/3] Scoring base assets (recent 14-day window)...")
    base_scores = score_base_assets(collected_data)

    # Log all base scores
    for asset, score in sorted(base_scores.items()):
        logger.info("  %s: %.2f", asset, score)

    # Step 1b: Compute recent-data momentum scores
    logger.info("\n[Step 1b/3] Computing recent-data momentum trends...")
    momentum_scores = compute_fred_momentum_scores(collected_data)
    for asset, m_score in sorted(momentum_scores.items()):
        logger.info("  Momentum %s: %.2f", asset, m_score)

    # Step 1c: Compute detailed score breakdowns for each asset
    logger.info("\n[Step 1c/3] Computing asset score breakdowns...")
    score_breakdowns = compute_asset_score_breakdowns(collected_data, base_scores)
    for asset, items in score_breakdowns.items():
        logger.info("  Breakdown %s: %d data points", asset, len(items))

    # Step 2: Compute all cross-pairs with momentum adjustment
    logger.info("\n[Step 2/3] Computing cross-pair biases (momentum-adjusted)...")
    pair_scores = compute_all_pairs(base_scores)

    # Apply momentum adjustment to each pair
    for pair in pair_scores:
        base = pair["base_asset"]
        quote = pair["quote_asset"]
        base_mom = momentum_scores.get(base, 5.0)
        quote_mom = momentum_scores.get(quote, 5.0)
        pair["momentum_base"] = round(base_mom, 2)
        pair["momentum_quote"] = round(quote_mom, 2)
        pair["momentum_adjusted_bias"] = round(
            adjust_bias_with_momentum(
                pair["base_score"], pair["quote_score"],
                base_mom, quote_mom
            ), 2
        )
        # Update combined_bias to use momentum-adjusted value
        pair["combined_bias"] = pair["momentum_adjusted_bias"]
        # Recalculate direction
        cb = pair["combined_bias"]
        if cb >= 8.0:
            pair["direction"] = "Strongly Bullish"
        elif cb >= 6.0:
            pair["direction"] = "Bullish"
        elif cb >= 4.1:
            pair["direction"] = "Neutral"
        elif cb >= 2.1:
            pair["direction"] = "Bearish"
        else:
            pair["direction"] = "Strongly Bearish"

    # Re-sort by momentum-adjusted bias
    pair_scores.sort(key=lambda p: abs(p["combined_bias"] - 5.0), reverse=True)

    # Step 3: Identify extreme setups
    logger.info("\n[Step 3/3] Identifying extreme setups...")
    extreme_setups = [
        p for p in pair_scores
        if p["combined_bias"] >= 8.0 or p["combined_bias"] <= 2.0
    ]

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_scores": base_scores,
        "momentum_scores": momentum_scores,
        "score_breakdowns": score_breakdowns,
        "pairs": pair_scores,
        "total_pairs": len(pair_scores),
        "extreme_setups": extreme_setups,
        "total_extreme": len(extreme_setups),
        "analysis_window_days": RECENT_DATA_WINDOW_DAYS,
        "analysis_note": (
            f"Bias and analysis use ONLY the most recent {RECENT_DATA_WINDOW_DAYS} days "
            "of economic data. Historical data is shown for reference only."
        ),
    }

    logger.info("\n" + "=" * 60)
    logger.info("SCORING COMPLETE — %d base assets, %d pairs, %d extreme setups",
                 len(base_scores), len(pair_scores), len(extreme_setups))
    logger.info("=" * 60)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def direction_label(bias: float) -> str:
    """Return human-readable direction for a bias score."""
    if bias >= 8.0:
        return "Strongly Bullish"
    elif bias >= 6.0:
        return "Bullish"
    elif bias >= 4.1:
        return "Neutral"
    elif bias >= 2.1:
        return "Bearish"
    return "Strongly Bearish"


def scoring_metadata() -> dict:
    """Return the scoring framework metadata for documentation."""
    return {
        "framework": "Bulls & Bears Fundamentals Scoring Engine v3.0",
        "scale": "1.0 (Strongly Bearish) to 10.0 (Strongly Bullish), 5.0 = Neutral",
        "analysis_window_days": RECENT_DATA_WINDOW_DAYS,
        "analysis_policy": (
            f"Only the most recent {RECENT_DATA_WINDOW_DAYS} days of economic data "
            "are used for bias and fundamental analysis. Historical data is shown "
            "for reference only and does not affect scores."
        ),
        "tier_multipliers": {
            "tier_1": {"multiplier": 3.0, "events": list(TIER_1_EVENTS)},
            "tier_2": {"multiplier": 2.0, "events": list(TIER_2_EVENTS)},
            "tier_3": {"multiplier": 1.0, "events": list(TIER_3_EVENTS)},
        },
        "expectation_scoring": {
            "formula": "D = Actual - Forecast",
            "beat_range": "6.0 to 10.0 (D > 0)",
            "miss_range": "1.0 to 4.0 (D < 0)",
        },
        "pair_formula": "Pair Bias = 5 + (Base Score - Quote Score)",
        "asset_classes": list(ASSET_CLASSES.keys()),
        "base_assets": BASE_ASSETS,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with sample data
    test_data = {
        "fred": {
            "GDPC1": [{"date": "2026-07-01", "value": 24000.0, "unit": "Billions USD"},
                       {"date": "2026-04-01", "value": 23800.0, "unit": "Billions USD"},
                       {"date": "2026-01-01", "value": 23600.0, "unit": "Billions USD"},
                       {"date": "2025-10-01", "value": 23400.0, "unit": "Billions USD"},
                       {"date": "2025-07-01", "value": 23200.0, "unit": "Billions USD"}],
            "UNRATE": [{"date": "2026-07-01", "value": 4.0, "unit": "Percent"}],
            "CPILFESL": [{"date": "2026-07-01", "value": 320.0, "unit": "Index"},
                          {"date": "2025-07-01", "value": 315.0, "unit": "Index"}],
        },
        "cftc": {},
        "central_bank_rates": {"USD": 5.5, "EUR": 4.0, "GBP": 5.25, "JPY": 0.5,
                               "AUD": 4.35, "CAD": 5.0, "CHF": 1.75, "NZD": 5.5},
        "yield_curve": {},
        "seasonality": {"USD": 6.0, "EUR": 5.0, "GBP": 5.5, "XAU": 7.0, "SP500": 6.5},
        "retail_sentiment": {},
    }

    results = score_all(test_data)
    print("\nBase Scores:")
    for asset, score in sorted(results["base_scores"].items()):
        print(f"  {asset}: {score:.2f}")

    print(f"\nTotal Pairs: {results['total_pairs']}")
    print(f"Extreme Setups: {results['total_extreme']}")
    for s in results["extreme_setups"][:5]:
        print(f"  {s['name']}: {s['combined_bias']:.2f} ({s['direction']})")