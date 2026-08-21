#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Fundamental Scoring Engine
Translates raw economic output into definitive 1-10 value scores.

Scoring Framework:
  1. Latest Release Delta Model — evaluate ONLY the single most recent
     data release for each macro indicator (Actual vs Forecast/Previous).
  2. Expectation Scoring (D = Actual - Forecast)
  3. Multi-Asset Correlation / Cross-Asset Spillover Logic
  4. Tier Weights Multiplier (Tier 1: x3, Tier 2: x2, Tier 3: x1)
  5. CFTC Long-Ratio tiered scoring
  6. 200+ Cross-Pair Scaling via relative valuation delta

LATEST RELEASE POLICY:
  No multi-week historical averaging. Scoring uses ONLY the single most
  recent release per indicator. All historical data remains available for
  display (charts, tables) but is NOT used for bias computation. This
  guarantees maximum score sensitivity to the newest economic prints.
"""

import math
import logging
from typing import Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.parsers import RECENT_DATA_WINDOW_DAYS

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

# Counter-assets that move INVERSE to the US Dollar:
# Weak USD => Bullish, Strong USD => Bearish
USD_COUNTER_ASSETS = ["XAU", "XAG", "EUR", "GBP", "AUD", "NZD", "BTC"]

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

INFLATION_KEYWORDS = ["CPI", "PCE", "INFLATION", "PPI"]
GROWTH_KEYWORDS = ["GDP", "NFP", "EMPLOYMENT", "RETAIL SALES", "PMI",
                   "INDUSTRIAL PRODUCTION"]
LABOR_KEYWORDS = ["UNEMPLOYMENT", "JOBLESS CLAIMS", "JOLTS", "ADP"]


def _clamp(score: float) -> float:
    """Clamp a score to the [1.0, 10.0] range."""
    return max(1.0, min(10.0, score))


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
# SECTION 0: Macroeconomic Indicator Sensitivity & Financial Logic Primer
# ═══════════════════════════════════════════════════════════════════════════════

# Indicators where a HIGHER actual is BULLISH for USD (hotter = stronger USD)
#   - Inflation (CPI/PPI/PCE): hotter inflation => hawkish Fed => BULLISH USD
#   - Growth (GDP/Retail Sales): stronger growth => BULLISH USD
#   - Labor (NFP/ADP/JOLTS): hotter labor => wage pressure => BULLISH USD
BULLISH_ON_HIGH_KEYWORDS = [
    "CPI", "PCE", "INFLATION", "PPI", "GDP", "RETAIL SALES",
    "NFP", "EMPLOYMENT CHANGE", "ADP", "JOLTS", "PAYROLL",
]

# Indicators where a HIGHER actual is BEARISH for USD (inverse logic)
#   - Unemployment Rate: rising unemployment => economic distress => BEARISH USD
#   - Jobless Claims: rising claims => labor market weakness => BEARISH USD
BEARISH_ON_HIGH_KEYWORDS = [
    "UNEMPLOYMENT", "JOBLESS CLAIMS", "INITIAL CLAIMS", "JOBLESS",
]

# PMI indicators have a baseline threshold of 50.0
#   > 50.0 = Expansion, < 50.0 = Contraction
PMI_KEYWORDS = ["PMI", "MANUFACTURING PMI", "SERVICES PMI", "COMPOSITE PMI"]

# Sovereign bond yield indicators (US 2Y & 10Y Treasury)
YIELD_KEYWORDS = ["YIELD", "TREASURY", "T-NOTE", "TNOTE", "BOND"]


@dataclass
class IndicatorSensitivity:
    """Describes how a macro indicator affects USD bias."""
    direction: str  # "bullish_on_high" | "bearish_on_high"
    is_pmi: bool = False
    is_yield: bool = False


def classify_indicator(event_name: str) -> IndicatorSensitivity:
    """
    Classify an economic indicator by its fundamental impact on the USD.

    Returns an IndicatorSensitivity describing:
      - direction: whether a higher actual is bullish or bearish for USD
      - is_pmi: whether this is a PMI (50.0 expansion/contraction threshold)
      - is_yield: whether this is a sovereign bond yield
    """
    upper = event_name.upper()

    # PMI check first (contains "PMI" in the name)
    is_pmi = any(kw in upper for kw in PMI_KEYWORDS)
    is_yield = any(kw in upper for kw in YIELD_KEYWORDS)

    # Inverse indicators take precedence (unemployment, claims)
    if any(kw in upper for kw in BEARISH_ON_HIGH_KEYWORDS):
        return IndicatorSensitivity("bearish_on_high", is_pmi, is_yield)

    # Default: bullish on high (inflation, growth, labor)
    return IndicatorSensitivity("bullish_on_high", is_pmi, is_yield)


def deviation_score(actual: float, forecast: Optional[float],
                    previous: Optional[float]) -> float:
    """
    Calculate the weighted deviation of Actual vs Forecast and Previous.

    Formula:
        Deviation = (A - F)/|F| * 0.6 + (A - P)/|P| * 0.4

    Returns a value in [-1.0, +1.0] via tanh normalization:
      - +1.0 = Strongly Bullish (actual well above forecast & previous)
      -  0.0 = Neutral
      - -1.0 = Strongly Bearish (actual well below forecast & previous)
    """
    f_term = 0.0
    if forecast is not None and abs(forecast) > 1e-9:
        f_term = (actual - forecast) / abs(forecast)

    p_term = 0.0
    if previous is not None and abs(previous) > 1e-9:
        p_term = (actual - previous) / abs(previous)

    raw = f_term * 0.6 + p_term * 0.4
    return math.tanh(raw)


def deviation_to_score(dev: float) -> float:
    """
    Map a deviation in [-1.0, +1.0] to a 1-10 score.
      0.0  -> 5.0 (neutral)
      +1.0 -> 9.5
      -1.0 -> 0.5
    """
    return _clamp(5.0 + dev * 4.5)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Latest Release Delta Scoring
# ═══════════════════════════════════════════════════════════════════════════════

def score_latest_release(actual: float, forecast: Optional[float],
                         previous: Optional[float],
                         event_name: str) -> Optional[float]:
    """
    Score the SINGLE most recent data release using the Latest Release Delta Model.

    Returns a 1-10 score (5 = neutral) or None if not enough information.

    Finance Logic Primer mapping:
      - Inflation (CPI/PPI/PCE): Actual > Forecast => BULLISH USD; < => BEARISH
      - Growth (GDP/PMIs):       Actual > Forecast => BULLISH USD; < => BEARISH
      - Labor (NFP/ADP/JOLTS):   Actual > Forecast => BULLISH USD; < => BEARISH
      - Labor (Unemployment/Claims): Actual > Forecast => BEARISH USD (inverted)
      - Sovereign Yields:         Rising => BULLISH USD; Falling => BEARISH
    """
    if forecast is None and previous is None:
        return None

    sensitivity = classify_indicator(event_name)
    dev = deviation_score(actual, forecast, previous)

    # Apply direction: inverse indicators flip the deviation
    if sensitivity.direction == "bearish_on_high":
        dev = -dev

    score = deviation_to_score(dev)

    # PMI threshold logic: < 50.0 = contraction = BEARISH USD
    if sensitivity.is_pmi and actual is not None:
        if actual < 50.0:
            # Contraction: cap at 4.0 (bearish)
            score = min(score, 4.0)
        elif actual >= 50.0 and dev > 0:
            # Expansion + beat: boost
            score = max(score, 6.0)

    return _clamp(score)


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

    if std_dev and std_dev > 0:
        z_score = delta / std_dev
        if z_score > 0:
            score = 6.0 + min(z_score, 2.0) * 2.0
        else:
            score = 4.0 + max(z_score, -2.0) * 2.0
    else:
        if abs(forecast) > 0.001:
            pct_dev = delta / abs(forecast) * 100
            if pct_dev > 0:
                score = 6.0 + min(pct_dev / 5.0, 4.0)
            else:
                score = 4.0 + max(pct_dev / 5.0, -3.0)
        else:
            score = 5.0

    return _clamp(score)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: CFTC Long-Ratio Tiered Scoring
# ═══════════════════════════════════════════════════════════════════════════════

def compute_long_ratio(long_positions: float, short_positions: float) -> Optional[float]:
    """
    Compute the institutional Long Ratio:
        Long Ratio = (Long / (Long + Short)) * 100
    """
    total = (long_positions or 0) + (short_positions or 0)
    if total <= 0:
        return None
    return (long_positions / total) * 100.0


def cftc_score_from_long_ratio(long_ratio: float) -> float:
    """
    Tiered CFTC bias scoring centered at 50.0%.

    Long Ratio > 50.0% => BULLISH
      50.1% - 59.9%  => Mildly Bullish (score 6.0)
      60.0% - 74.9%  => Moderately Bullish (score 7-8)
      >= 75.0%       => Strongly Bullish / Extreme Long (score 9-10)

    Long Ratio < 50.0% => BEARISH
      49.9% - 40.1%  => Mildly Bearish (score 4.0)
      40.0% - 25.0%  => Moderately Bearish (score 2-3)
      <= 24.9%       => Strongly Bearish / Extreme Short (score 1)
    """
    lr = long_ratio
    if lr > 50.0:
        if lr >= 75.0:
            return 8.0 + min((lr - 75.0) / 25.0, 1.0) * 2.0
        if lr >= 60.0:
            return 6.5 + ((lr - 60.0) / 14.9) * 1.4
        return 5.5 + ((lr - 50.1) / 9.8) * 0.9
    elif lr < 50.0:
        if lr <= 24.9:
            return 1.0 + (lr / 24.9) * 1.0
        if lr <= 40.0:
            return 3.5 - ((40.0 - lr) / 15.0) * 1.4
        return 4.5 - ((49.9 - lr) / 9.8) * 0.9
    return 5.0  # Exactly 50.0 -> neutral


def cftc_sentiment_label(long_ratio: float) -> str:
    """Return the tiered sentiment label for a given long ratio percentage."""
    lr = long_ratio
    if lr > 50.0:
        if lr >= 75.0:
            return "Strongly Bullish / Extreme Long"
        if lr >= 60.0:
            return "Moderately Bullish"
        return "Mildly Bullish"
    if lr < 50.0:
        if lr <= 24.9:
            return "Strongly Bearish / Extreme Short"
        if lr <= 40.0:
            return "Moderately Bearish"
        return "Mildly Bearish"
    return "Neutral"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Multi-Asset Correlation Scoring
# ═══════════════════════════════════════════════════════════════════════════════

def score_for_asset_class(base_score: float, event_name: str,
                          asset_class: str) -> float:
    """Apply correlation logic: the same economic print affects asset classes differently."""
    upper = event_name.upper()
    is_inflation = any(kw in upper for kw in INFLATION_KEYWORDS)
    is_growth = any(kw in upper for kw in GROWTH_KEYWORDS)

    adjusted = base_score

    if asset_class == "FOREX":
        if is_inflation or is_growth:
            adjusted = 5.0 + (base_score - 5.0) * 1.2
    elif asset_class == "INDICES":
        if is_inflation:
            adjusted = 5.0 - (base_score - 5.0) * 1.3
        elif is_growth:
            adjusted = 5.0 + (base_score - 5.0) * 1.2
    elif asset_class == "COMMODITIES":
        if is_inflation:
            adjusted = 5.0 + (base_score - 5.0) * 1.4
        elif is_growth:
            adjusted = 5.0 + (base_score - 5.0) * 1.1
    elif asset_class == "CRYPTO":
        if is_inflation:
            adjusted = 5.0 - (base_score - 5.0) * 1.5
        elif is_growth:
            adjusted = 5.0 + (base_score - 5.0) * 0.8

    return _clamp(adjusted)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Latest-Release Helpers (no multi-week averaging)
# ═══════════════════════════════════════════════════════════════════════════════

def _latest_value(observations: list[dict]) -> Optional[float]:
    """Get the single most recent value (descending-ordered list)."""
    if not observations:
        return None
    return observations[0]["value"]


def _latest_date(observations: list[dict]) -> Optional[str]:
    if not observations:
        return None
    return observations[0].get("date", "")


def _previous_value(observations: list[dict]) -> Optional[float]:
    """Second-most-recent value (previous release)."""
    if len(observations) < 2:
        return None
    return observations[1]["value"]


def _pct_change(current: float, previous: float) -> Optional[float]:
    if previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Score Aggregation with Tier Weights
# ═══════════════════════════════════════════════════════════════════════════════

def compute_weighted_average(scores_with_tiers: list[tuple[float, float]]) -> float:
    """Weighted average from (score, tier_multiplier) pairs, clamped to 1-10."""
    if not scores_with_tiers:
        return 5.0
    total_weight = sum(w for _, w in scores_with_tiers)
    if total_weight == 0:
        return 5.0
    weighted_sum = sum(s * w for s, w in scores_with_tiers)
    return round(_clamp(weighted_sum / total_weight), 2)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Base Asset Scoring — LATEST RELEASE ONLY
# ═══════════════════════════════════════════════════════════════════════════════

def score_base_assets(collected_data: dict[str, Any]) -> dict[str, float]:
    """
    Score all base assets from 1-10 using ONLY the single latest release
    per macro indicator. No 14-day historical averaging.
    """
    scores: dict[str, float] = {}
    fred = collected_data.get("fred", {})
    cftc = collected_data.get("cftc", {})
    central_bank_rates = collected_data.get("central_bank_rates", {})
    yield_curve = collected_data.get("yield_curve", {})
    seasonality = collected_data.get("seasonality", {})
    retail_sentiment = collected_data.get("retail_sentiment", {})
    calendar_events = collected_data.get("calendar_events", [])

    for asset in BASE_ASSETS:
        weighted_scores: list[tuple[float, float]] = []

        # ── USD Macro Health — single LATEST release only ────────────────
        if asset == "USD":
            gdp_obs = fred.get("GDPC1", [])
            unrate_obs = fred.get("UNRATE", [])
            cpi_obs = fred.get("CPILFESL", [])
            hcpi_obs = fred.get("CPIAUCSL", [])
            ppi_obs = fred.get("PPIACO", [])
            payems_obs = fred.get("PAYEMS", [])
            fedfunds_obs = fred.get("FEDFUNDS", [])
            pce_obs = fred.get("PCEPILFE", [])
            dgs10_obs = fred.get("DGS10", [])

            # GDP — latest vs previous release, EXACT
            latest_gdp = _latest_value(gdp_obs)
            prev_gdp = _previous_value(gdp_obs)
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

            # Unemployment (latest release; rising = bearish USD)
            latest_unrate = _latest_value(unrate_obs)
            prev_unrate = _previous_value(unrate_obs)
            if latest_unrate is not None:
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
                if prev_unrate is not None:
                    trend = latest_unrate - prev_unrate
                    if trend > 0.2:
                        unrate_score = max(1.0, unrate_score - 2.0)
                    elif trend > 0.1:
                        unrate_score = max(1.0, unrate_score - 1.0)
                    elif trend < -0.2:
                        unrate_score = min(10.0, unrate_score + 2.0)
                    elif trend < -0.1:
                        unrate_score = min(10.0, unrate_score + 1.0)
                weighted_scores.append((unrate_score, TIER_1_MULTIPLIER))

            # Core CPI — latest release vs previous (soft = bearish USD)
            latest_cpi = _latest_value(cpi_obs)
            prev_cpi = _previous_value(cpi_obs)
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
                weighted_scores.append((cpi_score, TIER_1_MULTIPLIER))

            # Core PCE — latest release
            latest_pce = _latest_value(pce_obs)
            prev_pce = _previous_value(pce_obs)
            if latest_pce is not None and prev_pce is not None and prev_pce > 0:
                pce_mom = (latest_pce - prev_pce) / prev_pce * 100
                if pce_mom > 0.4:
                    pce_score = 8.0
                elif pce_mom > 0.1:
                    pce_score = 6.0
                elif pce_mom > 0.0:
                    pce_score = 5.5
                elif pce_mom > -0.1:
                    pce_score = 4.5
                else:
                    pce_score = 3.0
                weighted_scores.append((pce_score, TIER_1_MULTIPLIER))

            # Headline CPI
            latest_hcpi = _latest_value(hcpi_obs)
            prev_hcpi = _previous_value(hcpi_obs)
            if latest_hcpi is not None and prev_hcpi is not None and prev_hcpi > 0:
                hcpi_mom = (latest_hcpi - prev_hcpi) / prev_hcpi * 100
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

            # PPI
            latest_ppi = _latest_value(ppi_obs)
            prev_ppi = _previous_value(ppi_obs)
            if latest_ppi is not None and prev_ppi is not None and prev_ppi > 0:
                ppi_mom = (latest_ppi - prev_ppi) / prev_ppi * 100
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

            # Nonfarm Payrolls — latest release
            latest_pay = _latest_value(payems_obs)
            prev_pay = _previous_value(payems_obs)
            if latest_pay is not None and prev_pay is not None:
                pay_change = latest_pay - prev_pay
                if pay_change > 200:
                    pay_score = 9.0
                elif pay_change > 100:
                    pay_score = 8.0
                elif pay_change > 50:
                    pay_score = 7.0
                elif pay_change > 0:
                    pay_score = 6.0
                elif pay_change > -50:
                    pay_score = 4.0
                else:
                    pay_score = 2.0
                weighted_scores.append((pay_score, TIER_1_MULTIPLIER))

            # Fed Funds Rate
            latest_rate = _latest_value(fedfunds_obs)
            prev_rate = _previous_value(fedfunds_obs)
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
                if prev_rate is not None:
                    rate_change = latest_rate - prev_rate
                    if rate_change > 0.1:
                        rate_score = min(10.0, rate_score + 1.0)
                    elif rate_change < -0.1:
                        rate_score = max(1.0, rate_score - 1.0)
                weighted_scores.append((rate_score, TIER_1_MULTIPLIER))

            # 10Y Yield — falling yields = capital flees USD = BEARISH
            latest_yld = _latest_value(dgs10_obs)
            prev_yld = _previous_value(dgs10_obs)
            if latest_yld is not None and prev_yld is not None:
                yld_delta = latest_yld - prev_yld
                if yld_delta > 0.3:
                    yld_score = 8.0
                elif yld_delta > 0.1:
                    yld_score = 7.0
                elif yld_delta > 0.0:
                    yld_score = 6.0
                elif yld_delta > -0.1:
                    yld_score = 5.0
                elif yld_delta > -0.3:
                    yld_score = 4.0
                else:
                    yld_score = 3.0
                weighted_scores.append((yld_score, TIER_2_MULTIPLIER))

            # Calendar-derived deltas (Actual vs Forecast) for USD events
            usd_cal_deltas = [
                ev for ev in calendar_events
                if ev.get("currency") == "USD"
                and ev.get("actual") is not None
                and (ev.get("forecast") is not None or ev.get("previous") is not None)
            ]
            for ev in usd_cal_deltas[:4]:
                cal_score = score_latest_release(
                    float(ev["actual"]),
                    ev.get("forecast"),
                    ev.get("previous"),
                    ev.get("event", ""),
                )
                if cal_score is not None:
                    tier = get_event_tier(ev.get("event", ""))
                    weighted_scores.append((cal_score, tier))

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
            weighted_scores.append((rate_score, TIER_1_MULTIPLIER))

        # ── CFTC Institutional Positioning — LONG-RATIO based ────────────
        cftc_entry = cftc.get(asset)
        if cftc_entry:
            long_r = cftc_entry.get("long_ratio")
            if long_r is None:
                long_r = compute_long_ratio(
                    cftc_entry.get("noncomm_long", 0),
                    cftc_entry.get("noncomm_short", 0),
                )
            if long_r is not None:
                cftc_score = cftc_score_from_long_ratio(long_r)
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
            weighted_scores.append((seasonality[asset], TIER_3_MULTIPLIER))

        # ── Retail Sentiment (Contrarian) ────────────────────────────────
        if asset in retail_sentiment:
            long_pct = retail_sentiment[asset].get("long_pct", 50)
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
            weighted_scores.append((rs_score, TIER_3_MULTIPLIER))

        # ── Compute Final Score ──────────────────────────────────────────
        scores[asset] = (
            compute_weighted_average(weighted_scores)
            if weighted_scores else 5.0
        )
        logger.info("Base Score — %s: %.2f (%d components)",
                     asset, scores[asset], len(weighted_scores))

    return scores


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4A: Cross-Asset USD Spillover
# ═══════════════════════════════════════════════════════════════════════════════

# Assets that move INVERSE to the US Dollar (weak USD => Bullish):
#   Gold/XAU, Silver/XAG, EUR/USD, GBP/USD, AUD/USD, NZD/USD, BTC/USD
#   Asset Bias Score = 11.0 - S_USD
INVERSE_USD_ASSETS = ["XAU", "XAG", "EUR", "GBP", "AUD", "NZD", "BTC"]

# Assets that move DIRECTLY with the US Dollar (USD/JPY, USD/CAD, USD/CHF):
#   Asset Bias Score = S_USD
DIRECT_USD_ASSETS = ["JPY", "CAD", "CHF"]


def apply_cross_asset_spillover(scores: dict[str, float]) -> dict[str, float]:
    """
    Cross-Asset Spillover Matrix — derive counter-asset scores from the
    final USD Bias Score S_USD using the exact inverse relationship:

      Inverse USD Assets (XAU, XAG, EUR, GBP, AUD, NZD, BTC):
          Asset Bias Score = 11.0 - S_USD

      Direct USD Assets (JPY, CAD, CHF):
          Asset Bias Score = S_USD

    Example: If S_USD = 3.2 (Bearish USD), then:
        Gold/EUR score = 11.0 - 3.2 = 7.8 (Strongly Bullish)
    """
    usd = scores.get("USD", 5.0)
    spill = dict(scores)

    # Inverse USD assets: weak USD => Bullish
    for asset in INVERSE_USD_ASSETS:
        if asset in spill:
            spill[asset] = round(_clamp(11.0 - usd), 2)

    # Direct USD assets: move in lockstep with USD
    for asset in DIRECT_USD_ASSETS:
        if asset in spill:
            spill[asset] = round(_clamp(usd), 2)

    logger.info(
        "Cross-asset spillover: S_USD=%.2f -> inverse assets=%.2f, direct assets=%.2f",
        usd, _clamp(11.0 - usd), usd,
    )

    return spill


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: Score Breakdowns (per asset)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_asset_score_breakdowns(
    collected_data: dict[str, Any],
    base_scores: dict[str, float],
) -> dict[str, list[dict]]:
    """
    Build a detailed contribution list for every base asset.
    """
    fred = collected_data.get("fred", {})
    cftc = collected_data.get("cftc", {})
    central_bank_rates = collected_data.get("central_bank_rates", {})
    yield_curve = collected_data.get("yield_curve", {})
    seasonality = collected_data.get("seasonality", {})
    retail_sentiment = collected_data.get("retail_sentiment", {})

    def _append(items: list[dict], indicator: str, value: Any, unit: str,
                date: Optional[str], score: float, tier: str, weight: float):
        items.append({
            "indicator": indicator,
            "value": round(value, 3) if isinstance(value, float) else value,
            "unit": unit,
            "date": date,
            "score": round(score, 2),
            "tier": tier,
            "weight": weight,
            "direction": "bullish" if score >= 6 else "bearish" if score <= 4 else "neutral",
            "contribution": round(score * weight, 2),
        })

    breakdowns: dict[str, list[dict]] = {}

    for asset in BASE_ASSETS:
        items: list[dict] = []

        if asset == "USD":
            # Latest value monitoring (single latest release)
            gdp_growth = None
            latest_gdp = _latest_value(fred.get("GDPC1", []))
            prev_gdp = _previous_value(fred.get("GDPC1", []))
            if latest_gdp and prev_gdp:
                gdp_growth = (latest_gdp - prev_gdp) / prev_gdp * 100
            if gdp_growth is not None:
                s = 9.0 if gdp_growth > 1 else 8.0 if gdp_growth > 0.5 else \
                    7.0 if gdp_growth > 0.2 else 6.0 if gdp_growth > 0 else \
                    4.0 if gdp_growth > -0.5 else 2.0
                _append(items, "GDP Growth (Latest vs Previous)", gdp_growth,
                        "%", _latest_date(fred.get("GDPC1", [])), s, "Tier 1", TIER_1_MULTIPLIER)

            latest_unemp = _latest_value(fred.get("UNRATE", []))
            prev_unemp = _previous_value(fred.get("UNRATE", []))
            if latest_unemp is not None:
                s = 9.0 if latest_unemp < 3.5 else 8.0 if latest_unemp < 4.5 else \
                    6.0 if latest_unemp < 5.5 else 4.0 if latest_unemp < 7.0 else 2.0
                if prev_unemp is not None:
                    t = latest_unemp - prev_unemp
                    if t > 0.2: s = max(1.0, s - 2.0)
                    elif t > 0.1: s = max(1.0, s - 1.0)
                    elif t < -0.2: s = min(10.0, s + 2.0)
                    elif t < -0.1: s = min(10.0, s + 1.0)
                _append(items, "Unemployment Rate (Latest Release)", latest_unemp,
                        "%", _latest_date(fred.get("UNRATE", [])), s, "Tier 1", TIER_1_MULTIPLIER)

            latest_cpi = _latest_value(fred.get("CPILFESL", []))
            prev_cpi = _previous_value(fred.get("CPILFESL", []))
            if latest_cpi and prev_cpi:
                cpi_mom = (latest_cpi - prev_cpi) / prev_cpi * 100
                s = 9.0 if cpi_mom > 0.5 else 8.0 if cpi_mom > 0.3 else \
                    7.0 if cpi_mom > 0.1 else 6.0 if cpi_mom > 0 else \
                    5.0 if cpi_mom > -0.1 else 3.0
                _append(items, "Core CPI Change (Latest vs Previous)", cpi_mom,
                        "%", _latest_date(fred.get("CPILFESL", [])), s, "Tier 1", TIER_1_MULTIPLIER)

            latest_pay = _latest_value(fred.get("PAYEMS", []))
            prev_pay = _previous_value(fred.get("PAYEMS", []))
            if latest_pay is not None and prev_pay is not None:
                chg = latest_pay - prev_pay
                s = 9.0 if chg > 200 else 8.0 if chg > 100 else \
                    7.0 if chg > 50 else 6.0 if chg > 0 else \
                    4.0 if chg > -50 else 2.0
                _append(items, "Nonfarm Payrolls Change (Latest vs Previous)",
                        chg, "K jobs", _latest_date(fred.get("PAYEMS", [])),
                        s, "Tier 1", TIER_1_MULTIPLIER)

            latest_fed = _latest_value(fred.get("FEDFUNDS", []))
            if latest_fed is not None:
                s = 8.0 if latest_fed > 5 else 7.0 if latest_fed > 3 else \
                    6.0 if latest_fed > 1 else 5.0 if latest_fed > 0 else 3.0
                _append(items, "Fed Funds Rate (Latest)", latest_fed, "%",
                        _latest_date(fred.get("FEDFUNDS", [])), s, "Tier 1", TIER_1_MULTIPLIER)

            latest_yld = _latest_value(fred.get("DGS10", []))
            prev_yld = _previous_value(fred.get("DGS10", []))
            if latest_yld is not None and prev_yld is not None:
                yd = latest_yld - prev_yld
                s = 8.0 if yd > 0.3 else 7.0 if yd > 0.1 else \
                    6.0 if yd > 0 else 5.0 if yd > -0.1 else \
                    4.0 if yd > -0.3 else 3.0
                _append(items, "10Y Treasury Yield Change", yd, "%p",
                        _latest_date(fred.get("DGS10", [])), s, "Tier 2", TIER_2_MULTIPLIER)

        # CFTC
        cftc_entry = cftc.get(asset)
        if cftc_entry:
            lr = cftc_entry.get("long_ratio") or compute_long_ratio(
                cftc_entry.get("noncomm_long", 0),
                cftc_entry.get("noncomm_short", 0),
            )
            if lr is not None:
                s = cftc_score_from_long_ratio(lr)
                _append(items, f"CFTC Long Ratio ({asset})", lr, "%",
                        cftc_entry.get("report_date"), s, "Tier 2", TIER_2_MULTIPLIER)

        # Central bank rate
        rate = central_bank_rates.get(asset)
        if rate is not None:
            s = 8.0 if rate > 5 else 7.0 if rate > 3 else \
                6.0 if rate > 1 else 5.0 if rate > 0 else 3.0
            _append(items, f"{asset} Central Bank Rate", rate, "%",
                    None, s, "Tier 1", TIER_1_MULTIPLIER)

        # Yield curve
        instrument_map = {"USD": "US10Y", "EUR": "DE10Y", "GBP": "GB10Y", "JPY": "JP10Y"}
        inst = instrument_map.get(asset)
        if inst and inst in yield_curve:
            yc = yield_curve[inst]
            if yc.get("ma50") and yc["ma50"] > 0:
                dev = (yc["yield"] - yc["ma50"]) / yc["ma50"] * 100
                s = 8.0 if dev > 2 else 7.0 if dev > 1 else \
                    6.0 if dev > 0 else 4.0 if dev > -1 else 3.0
                _append(items, f"{inst} Yield vs 50-Day MA", dev, "%", None,
                        s, "Tier 2", TIER_2_MULTIPLIER)

        # Seasonality + Retail
        if asset in seasonality:
            _append(items, "Seasonality", seasonality[asset], "score",
                    None, seasonality[asset], "Tier 3", TIER_3_MULTIPLIER)
        if asset in retail_sentiment:
            long_pct = retail_sentiment[asset].get("long_pct", 50)
            s = 3.0 if long_pct > 80 else 4.0 if long_pct > 65 else \
                5.0 if long_pct > 45 else 6.0 if long_pct > 30 else 7.0
            _append(items, "Retail Sentiment (Contrarian)", long_pct,
                    "% long", None, s, "Tier 3", TIER_3_MULTIPLIER)

        if items:
            breakdowns[asset] = items

    return breakdowns


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: Cross-Pair Universe (200+ pairs)
# ═══════════════════════════════════════════════════════════════════════════════

FX_MAJORS = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
METALS = ["XAU", "XAG"]
ENERGY = ["WTI"]
INDICES = ["SP500", "NAS100", "GER40"]
CRYPTOS = ["BTC", "ETH", "SOL", "XRP"]

ALL_PAIRS = [(b, q) for b in BASE_ASSETS for q in BASE_ASSETS if b != q]

BASE_CLASS_MAP: dict[str, str] = {}
for a in FX_MAJORS: BASE_CLASS_MAP[a] = "FX"
for a in METALS:    BASE_CLASS_MAP[a] = "METAL"
for a in ENERGY:    BASE_CLASS_MAP[a] = "ENERGY"
for a in INDICES:   BASE_CLASS_MAP[a] = "INDEX"
for a in CRYPTOS:   BASE_CLASS_MAP[a] = "CRYPTO"

PAIR_CLASS_MAP = {(b, q): BASE_CLASS_MAP[b] for b, q in ALL_PAIRS}


def compute_pair_bias(base_score: float, quote_score: float) -> float:
    """Pair Bias = 5 + (Base - Quote), clamped [1, 10]."""
    return _clamp(5.0 + (base_score - quote_score))


def compute_all_pairs(base_scores: dict[str, float]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for base, quote in ALL_PAIRS:
        bs = base_scores.get(base, 5.0)
        qs = base_scores.get(quote, 5.0)
        combined = compute_pair_bias(bs, qs)
        asset_class = PAIR_CLASS_MAP.get((base, quote), "OTHER")

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

        pairs.append({
            "name": f"{base}/{quote}",
            "asset_class": asset_class,
            "base_asset": base,
            "quote_asset": quote,
            "base_score": round(bs, 2),
            "quote_score": round(qs, 2),
            "combined_bias": round(combined, 2),
            "direction": direction,
        })

    pairs.sort(key=lambda p: abs(p["combined_bias"] - 5.0), reverse=True)
    logger.info("Pairs: %d computed", len(pairs))
    return pairs


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER SCORING FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def score_all(collected_data: dict[str, Any]) -> dict[str, Any]:
    """
    Execute the complete scoring pipeline.
    """
    logger.info("=" * 60)
    logger.info("SCORING ENGINE (LATEST RELEASE DELTA MODEL)")
    logger.info("=" * 60)

    # Step 1: Base assets using ONLY latest releases
    base_scores = score_base_assets(collected_data)
    for asset, s in sorted(base_scores.items()):
        logger.info("  %s: %.2f", asset, s)

    # Step 2: Cross-asset USD spillover
    base_scores = apply_cross_asset_spillover(base_scores)
    logger.info("Post-spillover scores: %s", base_scores)

    # Step 3: Score breakdowns
    score_breakdowns = compute_asset_score_breakdowns(collected_data, base_scores)

    # Step 4: Pairs
    pair_scores = compute_all_pairs(base_scores)

    extreme_setups = [
        p for p in pair_scores
        if p["combined_bias"] >= 8.0 or p["combined_bias"] <= 2.0
    ]

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_scores": base_scores,
        "score_breakdowns": score_breakdowns,
        "pairs": pair_scores,
        "total_pairs": len(pair_scores),
        "extreme_setups": extreme_setups,
        "total_extreme": len(extreme_setups),
        "analysis_window_days": RECENT_DATA_WINDOW_DAYS,
        "analysis_note": (
            "Latest Release Delta Model: Only the single most recent data "
            "release per macro indicator is scored (Actual vs Forecast/Previous). "
            "No multi-week historical averaging. Historical data is shown for "
            "reference only and does not affect scores."
        ),
    }

    logger.info("SCORING COMPLETE — %d base assets, %d pairs, %d extreme setups",
                len(base_scores), len(pair_scores), len(extreme_setups))
    return result


def direction_label(bias: float) -> str:
    if bias >= 8.0:
        return "Strongly Bullish"
    if bias >= 6.0:
        return "Bullish"
    if bias >= 4.1:
        return "Neutral"
    if bias >= 2.1:
        return "Bearish"
    return "Strongly Bearish"


def scoring_metadata() -> dict:
    return {
        "framework": "Bulls & Bears Fundamentals Scoring Engine v4.0",
        "scale": "1.0 (Strongly Bearish) to 10.0 (Strongly Bullish), 5.0 = Neutral",
        "model": "Latest Release Delta Model",
        "analysis_policy": (
            "Only the single most recent release per macro indicator determines "
            "bias. No multi-week averaging. Historical data is display-only."
        ),
        "tier_multipliers": {
            "tier_1": {"multiplier": TIER_1_MULTIPLIER, "events": list(TIER_1_EVENTS)},
            "tier_2": {"multiplier": TIER_2_MULTIPLIER, "events": list(TIER_2_EVENTS)},
            "tier_3": {"multiplier": TIER_3_MULTIPLIER, "events": list(TIER_3_EVENTS)},
        },
        "pair_formula": "Pair Bias = 5 + (Base Score - Quote Score)",
        "asset_classes": list(ASSET_CLASSES.keys()),
        "cross_asset_spillover": "USD < 4.0 -> XAU/XAG/EUR/GBP/AUD/NZD/BTC bullish",
        "base_assets": BASE_ASSETS,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_data = {
        "fred": {
            "GDPC1": [{"date": "2026-07-01", "value": 24000.0},
                       {"date": "2026-04-01", "value": 23800.0}],
            "UNRATE": [{"date": "2026-07-01", "value": 4.0},
                        {"date": "2026-06-01", "value": 4.1}],
            "CPILFESL": [{"date": "2026-07-01", "value": 320.0},
                          {"date": "2026-06-01", "value": 319.0}],
            "FEDFUNDS": [{"date": "2026-07-01", "value": 5.25}],
        },
        "cftc": {},
        "central_bank_rates": {"USD": 5.25},
        "yield_curve": {},
        "seasonality": {},
        "retail_sentiment": {},
        "calendar_events": [],
    }
    results = score_all(test_data)
    print("\nBase Scores:", results["base_scores"])
    print("Pairs:", results["total_pairs"])
