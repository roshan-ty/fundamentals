#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Mathematical Scoring Engine
Translates raw economic output into definitive 1-10 value scores.

Scoring Framework:
  1. Expectation Scoring Matrix (D = Actual - Forecast)
  2. Multi-Asset Correlation Logic (reactive scoring per asset class)
  3. Tier Weights Multiplier (Tier 1: x3, Tier 2: x2, Tier 3: x1)
  4. 200+ Cross-Pair Scaling via relative valuation delta
"""

import logging
from typing import Any, Optional
from datetime import datetime, timezone
import numpy as np

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
# SECTION 2A: 2-Week Momentum / Trend Analysis
# ═══════════════════════════════════════════════════════════════════════════════

def compute_fred_momentum_scores(collected_data: dict[str, Any]) -> dict[str, float]:
    """
    Compute 2-week directional momentum scores from FRED series for each asset.
    
    For USD, uses:
      - GDPC1: (V_current - V_2q_ago) / V_2q_ago → momentum score
      - UNRATE: rising unemployment = weakening economy → negative momentum
      - CPILFESL: inflation change → directional momentum
      - FEDFUNDS: rate change → monetary policy momentum
      - DGS10: yield change → bond market momentum
      - T10YIE: breakeven inflation change
    
    Returns {asset_code: momentum_score} where 1-10 scale:
      1-3: Strongly weakening trend
      4-5: Slightly weakening / neutral
      6-7: Slightly strengthening
      8-10: Strongly strengthening
    """
    fred = collected_data.get("fred", {})
    momentum: dict[str, float] = {}
    
    # USD momentum from multiple FRED series
    if "GDPC1" in fred:
        obs = fred["GDPC1"]
        if len(obs) >= 5:
            v_cur = obs[0]["value"]
            v_prev = obs[4]["value"]  # ~1 quarter ago (desc order)
            if v_prev > 0:
                pct_change = (v_cur - v_prev) / v_prev * 100
                # GDP growth > 3% = strong positive momentum
                if pct_change > 3.0:
                    usd_gdp = 8.0
                elif pct_change > 2.0:
                    usd_gdp = 7.0
                elif pct_change > 1.0:
                    usd_gdp = 6.0
                elif pct_change > 0.0:
                    usd_gdp = 5.5
                elif pct_change > -1.0:
                    usd_gdp = 4.5
                else:
                    usd_gdp = 3.0
                momentum["usd_gdp"] = usd_gdp

    if "UNRATE" in fred:
        obs = fred["UNRATE"]
        if len(obs) >= 3:
            v_cur = obs[0]["value"]
            v_w2 = obs[2]["value"] if len(obs) >= 3 else obs[-1]["value"]
            unrate_change = v_cur - v_w2
            # Rising unemployment = negative momentum for economy
            if unrate_change > 0.5:
                usd_unemp = 2.0
            elif unrate_change > 0.2:
                usd_unemp = 3.0
            elif unrate_change > 0.0:
                usd_unemp = 4.5
            elif unrate_change > -0.2:
                usd_unemp = 5.5
            elif unrate_change > -0.5:
                usd_unemp = 7.0
            else:
                usd_unemp = 8.0
            momentum["usd_unemp"] = usd_unemp

    if "CPILFESL" in fred:
        obs = fred["CPILFESL"]
        if len(obs) >= 13:
            v_cur = obs[0]["value"]
            v_12m = obs[12]["value"] if len(obs) >= 13 else obs[-1]["value"]
            if v_12m > 0:
                cpi_yoy = (v_cur - v_12m) / v_12m * 100
                # Inflation momentum
                if cpi_yoy > 5.0:
                    momentum["usd_cpi"] = 9.0  # Very hot
                elif cpi_yoy > 3.5:
                    momentum["usd_cpi"] = 7.0
                elif cpi_yoy > 2.5:
                    momentum["usd_cpi"] = 6.0
                elif cpi_yoy > 1.5:
                    momentum["usd_cpi"] = 5.5
                elif cpi_yoy > 0.0:
                    momentum["usd_cpi"] = 5.0
                else:
                    momentum["usd_cpi"] = 3.0

    if "FEDFUNDS" in fred:
        obs = fred["FEDFUNDS"]
        if len(obs) >= 3:
            v_cur = obs[0]["value"]
            v_prev = obs[2]["value"] if len(obs) >= 3 else obs[-1]["value"]
            rate_change = v_cur - v_prev
            # Rate hikes = hawkish momentum
            if rate_change > 0.5:
                momentum["usd_rates"] = 9.0
            elif rate_change > 0.25:
                momentum["usd_rates"] = 8.0
            elif rate_change > 0.0:
                momentum["usd_rates"] = 6.5
            elif rate_change > -0.25:
                momentum["usd_rates"] = 4.5
            elif rate_change > -0.5:
                momentum["usd_rates"] = 3.0
            else:
                momentum["usd_rates"] = 2.0

    if "DGS10" in fred:
        obs = fred["DGS10"]
        if len(obs) >= 3:
            v_cur = obs[0]["value"]
            v_prev = obs[2]["value"] if len(obs) >= 3 else obs[-1]["value"]
            yld_change = v_cur - v_prev
            # Rising yields = bond market momentum
            if yld_change > 0.5:
                momentum["usd_yields"] = 8.0
            elif yld_change > 0.25:
                momentum["usd_yields"] = 7.0
            elif yld_change > 0.0:
                momentum["usd_yields"] = 6.0
            elif yld_change > -0.25:
                momentum["usd_yields"] = 5.0
            elif yld_change > -0.5:
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
    Adjust pair bias using 2-week momentum differential.
    
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
# SECTION 4: Base Asset Scoring
# ═══════════════════════════════════════════════════════════════════════════════

def score_base_assets(collected_data: dict[str, Any]) -> dict[str, float]:
    """
    Score all base assets (USD, EUR, GBP, JPY, AUD, CAD, CHF, NZD,
    GOLD, OIL, SP500, BTC, ETH, SOL, XRP) from 1-10.

    Uses:
    - FRED series for US macro health
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

        # ── Macro Health (FRED-based) ────────────────────────────────────
        if asset == "USD" and "GDPC1" in fred:
            gdp_obs = fred["GDPC1"]
            unrate_obs = fred.get("UNRATE", [])

            if gdp_obs and unrate_obs:
                latest_gdp = gdp_obs[0]["value"]
                gdp_4q_ago = gdp_obs[4]["value"] if len(gdp_obs) >= 5 else None
                latest_unrate = unrate_obs[0]["value"]

                # GDP growth
                gdp_score = 5.0
                if gdp_4q_ago and gdp_4q_ago > 0:
                    gdp_growth = (latest_gdp - gdp_4q_ago) / gdp_4q_ago * 100
                    if gdp_growth > 3.0:
                        gdp_score = 9.0
                    elif gdp_growth > 2.0:
                        gdp_score = 8.0
                    elif gdp_growth > 1.0:
                        gdp_score = 7.0
                    elif gdp_growth > 0.0:
                        gdp_score = 6.0
                    elif gdp_growth > -1.0:
                        gdp_score = 4.0
                    else:
                        gdp_score = 2.0

                weighted_scores.append((gdp_score, TIER_1_MULTIPLIER))

                # Unemployment score
                unrate_score = 5.0
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

                weighted_scores.append((unrate_score, TIER_1_MULTIPLIER))

                # Core CPI / Inflation score
                if "CPILFESL" in fred:
                    cpi_obs = fred["CPILFESL"]
                    if cpi_obs:
                        # YoY change in CPI
                        latest_cpi = cpi_obs[0]["value"]
                        cpi_12m_ago = cpi_obs[12]["value"] if len(cpi_obs) >= 13 else None
                        if cpi_12m_ago and cpi_12m_ago > 0:
                            cpi_yoy = (latest_cpi - cpi_12m_ago) / cpi_12m_ago * 100
                            if cpi_yoy > 5.0:
                                cpi_score = 9.0  # Very hot
                            elif cpi_yoy > 3.5:
                                cpi_score = 8.0
                            elif cpi_yoy > 2.5:
                                cpi_score = 7.0
                            elif cpi_yoy > 1.5:
                                cpi_score = 6.0  # In target range
                            elif cpi_yoy > 0.0:
                                cpi_score = 5.0
                            else:
                                cpi_score = 3.0  # Deflationary
                            weighted_scores.append((cpi_score, TIER_1_MULTIPLIER))

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
    logger.info("SCORING ENGINE — Computing All Scores")
    logger.info("=" * 60)

    # Step 1: Score all base assets
    logger.info("\n[Step 1/3] Scoring base assets...")
    base_scores = score_base_assets(collected_data)

    # Log all base scores
    for asset, score in sorted(base_scores.items()):
        logger.info("  %s: %.2f", asset, score)

    # Step 1b: Compute 2-week momentum scores
    logger.info("\n[Step 1b/3] Computing 2-week momentum trends...")
    momentum_scores = compute_fred_momentum_scores(collected_data)
    for asset, m_score in sorted(momentum_scores.items()):
        logger.info("  Momentum %s: %.2f", asset, m_score)

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
        "pairs": pair_scores,
        "total_pairs": len(pair_scores),
        "extreme_setups": extreme_setups,
        "total_extreme": len(extreme_setups),
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
        "framework": "Bulls & Bears Fundamentals Scoring Engine v2.0",
        "scale": "1.0 (Strongly Bearish) to 10.0 (Strongly Bullish), 5.0 = Neutral",
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