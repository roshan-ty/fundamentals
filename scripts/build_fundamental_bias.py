#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Fundamental Scoring Engine & Cross-Asset Relative Strength

Authoritative script that computes:
  1. Per-currency Fundamental Strength Score S_c in [1.0, 10.0] for the 8 major
     currencies (USD, EUR, GBP, JPY, AUD, CAD, CHF, NZD) using the Latest Release
     Delta Scoring model over public/data/calendar.json.
  2. All-pair & cross-asset relative strength for every whitelisted asset in
     scripts/config.py ALLOWED_ASSETS.

Output: public/data/master_bias.json (superset schema — task data model + the
frontend's existing base_scores/pairs/score_breakdowns structure so the website
keeps working).

Scoring math (see task spec):
  Event Deviation:  delta = (Actual - Forecast) / (|Forecast| + eps)
  Normalized d in [-1, +1] (sign flipped for Unemployment / Jobless Claims)
  Weight w: High=1.0, Medium=0.5, Low=0.2
  Z_c = sum(d_i * w_i) / sum(w_i)
  S_c = clamp(5.0 + Z_c * 4.0, 1.0, 10.0)

Pair / cross-asset formulas:
  Direct USD (USD/XXX):        S = S_USD
  Inverse USD (XXX/USD):       S = 11.0 - S_USD
  Non-USD cross (BASE/QUOTE):  S = clamp(5.0 + (S_BASE - S_QUOTE), 1, 10)
  Commodities & Crypto:        S = 11.0 - S_USD
  Indices:                     growth/rate-based (bullish >6, bearish <4)

Run:
  python scripts/build_fundamental_bias.py            # generate master_bias.json
  python scripts/build_fundamental_bias.py --selftest # verify formulas offline
"""

import os
import sys
import json
import math
import logging
from datetime import datetime, timezone
from typing import Any, Optional

# Ensure project root is importable
_PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.config import (
    ALLOWED_ASSETS,
    CURRENCY_ASSIGNMENT,
    ALLOWED_DISPLAY_PAIRS,
    ALLOWED_BASE_ASSETS,
    symbol_to_code,
)

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
CALENDAR_PATH = os.path.join(_PROJECT_ROOT, "public", "data", "calendar.json")
OUTPUT_PATH = os.path.join(_PROJECT_ROOT, "public", "data", "master_bias.json")

# ── Constants ──────────────────────────────────────────────────────────────────
MAJOR_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]

# Impact weights per the task spec
IMPACT_WEIGHTS = {
    "High": 1.0,
    "Medium": 0.5,
    "Low": 0.2,
    "Non-Economic": 0.0,
}

# Inverse distress indicators: higher actual => bearish
INVERSE_KEYWORDS = ["UNEMPLOYMENT", "JOBLESS CLAIMS", "INITIAL CLAIMS", "JOBLESS"]

# PMI benchmark: >50 expansion, <50 contraction
PMI_KEYWORDS = ["PMI", "MANUFACTURING PMI", "SERVICES PMI", "COMPOSITE PMI"]

# Index home currency (for index growth/rate logic)
INDEX_HOME_CURRENCY = {
    "AUS200": "AUD", "CH20": "CHF", "ES35": "EUR", "EU50": "EUR",
    "FR40": "EUR", "GB100": "GBP", "GE40": "EUR", "HK50": "HKD",
    "JP225": "JPY", "US100": "USD", "US30": "USD", "US500": "USD",
}


def _clamp(score: float, lo: float = 1.0, hi: float = 10.0) -> float:
    """Clamp a score strictly to [lo, hi]."""
    return max(lo, min(hi, score))


def _bias_label(score: float) -> str:
    """Map a 1-10 score to a directional bias label."""
    if score >= 7.0:
        return "Strongly Bullish"
    if score >= 6.0:
        return "Bullish"
    if score >= 4.1:
        return "Neutral"
    if score >= 2.1:
        return "Bearish"
    return "Strongly Bearish"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Latest Release Delta Scoring (per currency)
# ═══════════════════════════════════════════════════════════════════════════════

def _is_inverse(event_name: str) -> bool:
    upper = event_name.upper()
    return any(kw in upper for kw in INVERSE_KEYWORDS)


def _is_pmi(event_name: str) -> bool:
    upper = event_name.upper()
    return any(kw in upper for kw in PMI_KEYWORDS)


def event_deviation(actual: float, forecast: Optional[float],
                    previous: Optional[float], event_name: str) -> Optional[float]:
    """Compute the bounded normalized delta d in [-1, +1] for one event.

    delta = (Actual - Forecast) / (|Forecast| + eps)
    Sign is flipped for inverse indicators (Unemployment / Jobless Claims).
    PMI contraction (<50) is treated as bearish.
    """
    if actual is None:
        return None

    # Prefer forecast; fall back to previous if forecast missing
    ref = forecast if forecast is not None else previous
    if ref is None:
        return None

    eps = 1e-9
    delta = (actual - ref) / (abs(ref) + eps)

    # Normalize to [-1, +1] via tanh
    d = math.tanh(delta)

    # Inverse indicators: higher actual => bearish (flip sign)
    if _is_inverse(event_name):
        d = -d

    # PMI contraction (<50) => bearish regardless of delta
    if _is_pmi(event_name) and actual < 50.0:
        d = min(d, -0.1)

    return _clamp(d, -1.0, 1.0)


def score_currency_from_events(events: list[dict], currency: str) -> float:
    """Aggregate weighted sentiment for a currency into S_c in [1, 10]."""
    weighted_sum = 0.0
    weight_total = 0.0

    for ev in events:
        if ev.get("currency") != currency:
            continue
        impact = ev.get("impact", "Low")
        w = IMPACT_WEIGHTS.get(impact, 0.0)
        if w <= 0.0:
            continue

        actual = ev.get("actual_num")
        forecast = ev.get("forecast_num")
        previous = ev.get("previous_num")
        event_name = ev.get("event", "")

        d = event_deviation(actual, forecast, previous, event_name)
        if d is None:
            continue

        weighted_sum += d * w
        weight_total += w

    if weight_total <= 0.0:
        return 5.0  # neutral default

    z = weighted_sum / weight_total
    return round(_clamp(5.0 + z * 4.0), 2)


def compute_currency_scores(events: list[dict]) -> dict[str, float]:
    """Compute S_c for all 8 major currencies."""
    scores: dict[str, float] = {}
    for c in MAJOR_CURRENCIES:
        scores[c] = score_currency_from_events(events, c)
    return scores


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: All-Pair & Cross-Asset Relative Strength
# ═══════════════════════════════════════════════════════════════════════════════

def compute_asset_scores(currency_scores: dict[str, float]) -> dict[str, dict]:
    """Compute the relative strength score for every whitelisted asset.

    Returns {asset_symbol: {"score": float, "bias": str, "category": str}}.
    """
    usd = currency_scores.get("USD", 5.0)
    assets: dict[str, dict] = {}

    # ── Forex pairs ────────────────────────────────────────────────────────
    for symbol in ALLOWED_ASSETS.get("FOREX", []):
        if len(symbol) != 6:
            continue
        base, quote = symbol[:3], symbol[3:]
        sb = currency_scores.get(base, 5.0)
        sq = currency_scores.get(quote, 5.0)

        if base == "USD":
            # Direct USD pair (USD/XXX): S = S_USD
            score = usd
        elif quote == "USD":
            # Inverse USD pair (XXX/USD): S = 11.0 - S_USD
            score = 11.0 - usd
        else:
            # Non-USD cross (BASE/QUOTE): S = clamp(5 + (S_BASE - S_QUOTE))
            score = _clamp(5.0 + (sb - sq))

        assets[symbol] = {
            "score": round(score, 2),
            "bias": _bias_label(score),
            "category": "FOREX",
        }

    # ── Commodities (priced in USD, inverse to USD) ────────────────────────
    for symbol in ALLOWED_ASSETS.get("COMMODITIES", []):
        score = 11.0 - usd
        assets[symbol] = {
            "score": round(score, 2),
            "bias": _bias_label(score),
            "category": "COMMODITIES",
        }

    # ── Crypto (high-beta risk-on, priced in USD) ──────────────────────────
    for symbol in ALLOWED_ASSETS.get("CRYPTO", []):
        score = 11.0 - usd
        assets[symbol] = {
            "score": round(score, 2),
            "bias": _bias_label(score),
            "category": "CRYPTO",
        }

    # ── Global Equity Indices (growth/rate-based) ──────────────────────────
    for symbol in ALLOWED_ASSETS.get("INDICES", []):
        home = INDEX_HOME_CURRENCY.get(symbol, "USD")
        shome = currency_scores.get(home, 5.0)
        # Soft home currency (weak rates) => bullish; hawkish => bearish
        # Base 5.0, adjusted by home-currency weakness (11 - S_home) and USD
        # strength. Indices thrive on soft rates + expansion.
        score = 5.0 + (11.0 - shome) * 0.5 - (usd - 5.0) * 0.3
        score = _clamp(score)
        assets[symbol] = {
            "score": round(score, 2),
            "bias": _bias_label(score),
            "category": "INDICES",
        }

    return assets


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Frontend-compatible pair matrix (keeps website working)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_pair_matrix(currency_scores: dict[str, float]) -> list[dict]:
    """Build the frontend's `pairs` array from ALLOWED_DISPLAY_PAIRS.

    Each pair: {name, asset_class, base_asset, quote_asset, base_score,
                quote_score, combined_bias, direction}.
    """
    pairs: list[dict] = []
    for spec in ALLOWED_DISPLAY_PAIRS:
        base = spec["base"]
        quote = spec["quote"]
        bs = currency_scores.get(base, 5.0)
        qs = currency_scores.get(quote, 5.0)

        if base == "USD":
            combined = bs
        elif quote == "USD":
            combined = 11.0 - bs
        else:
            combined = _clamp(5.0 + (bs - qs))

        pairs.append({
            "name": f"{base}/{quote}",
            "asset_class": spec.get("asset_class", "OTHER"),
            "base_asset": base,
            "quote_asset": quote,
            "base_score": round(bs, 2),
            "quote_score": round(qs, 2),
            "combined_bias": round(combined, 2),
            "direction": _bias_label(combined),
        })

    pairs.sort(key=lambda p: abs(p["combined_bias"] - 5.0), reverse=True)
    return pairs


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Master JSON Generation
# ═══════════════════════════════════════════════════════════════════════════════

def load_calendar_events() -> list[dict]:
    """Load the canonical bare-array calendar.json."""
    if not os.path.exists(CALENDAR_PATH):
        logger.warning("calendar.json not found at %s", CALENDAR_PATH)
        return []
    with open(CALENDAR_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("events", [])
    return data


def build_master_bias(events: list[dict]) -> dict[str, Any]:
    """Assemble the superset master_bias.json payload."""
    currency_scores = compute_currency_scores(events)
    asset_scores = compute_asset_scores(currency_scores)
    pairs = compute_pair_matrix(currency_scores)

    # Task schema: currencies + assets
    currencies_out = {
        c: {"score": currency_scores[c], "bias": _bias_label(currency_scores[c])}
        for c in MAJOR_CURRENCIES
    }
    assets_out = {
        sym: {"score": a["score"], "bias": a["bias"], "category": a["category"]}
        for sym, a in asset_scores.items()
    }

    # Frontend schema: base_scores + pairs + summary + extreme_setups
    base_scores = dict(currency_scores)
    for sym, a in asset_scores.items():
        base_scores[sym] = a["score"]

    summary = {
        "bullish_count": sum(1 for p in pairs if p["combined_bias"] >= 6.0),
        "bearish_count": sum(1 for p in pairs if p["combined_bias"] <= 4.0),
        "neutral_count": sum(1 for p in pairs if 4.0 < p["combined_bias"] < 6.0),
    }
    extreme_setups = [
        p for p in pairs
        if p["combined_bias"] >= 8.0 or p["combined_bias"] <= 2.0
    ]

    return {
        # Task data model
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "currencies": currencies_out,
        "assets": assets_out,
        # Frontend data model (keeps website running)
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "base_scores": base_scores,
        "total_base_assets": len(base_scores),
        "momentum_scores": {},
        "score_breakdowns": {},
        "analysis_window_days": 14,
        "analysis_note": (
            "Latest Release Delta Model: per-currency scores from calendar "
            "events (Actual vs Forecast), weighted by impact. Cross-asset "
            "relative strength derived from currency differentials."
        ),
        "pairs": pairs,
        "total_pairs": len(pairs),
        "extreme_setups": extreme_setups,
        "total_extreme": len(extreme_setups),
        "summary": summary,
    }


def write_master_bias(payload: dict[str, Any], output_path: str = OUTPUT_PATH) -> str:
    """Write master_bias.json."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("Exported master_bias.json (%d assets, %d pairs)",
                len(payload["assets"]), payload["total_pairs"])
    return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: Self-Test (offline formula verification)
# ═══════════════════════════════════════════════════════════════════════════════

def run_self_test() -> int:
    """Verify the scoring formulas against the task's exact examples."""
    print("=" * 60)
    print(" BULLS & BEARS FUNDAMENTALS — SCORING ENGINE SELF-TEST")
    print("=" * 60)

    # ── Latest Release Delta Scoring ───────────────────────────────────────
    # NFP miss: actual 147K vs forecast 165K => bearish (negative d)
    d = event_deviation(147000.0, 165000.0, 150000.0, "Non-Farm Employment Change")
    print(f"  [INFO] NFP miss delta = {d:.4f} (expected negative)")
    assert d is not None and d < 0, "NFP miss should be bearish (negative delta)"

    # Unemployment rise: actual 4.2 vs forecast 4.0 => bearish (inverse flip)
    d2 = event_deviation(4.2, 4.0, 4.1, "Unemployment Rate")
    print(f"  [INFO] Unemployment rise delta = {d2:.4f} (expected negative)")
    assert d2 is not None and d2 < 0, "Unemployment rise should be bearish"

    # PMI contraction: actual 48 vs forecast 50 => bearish
    d3 = event_deviation(48.0, 50.0, 49.0, "Manufacturing PMI")
    print(f"  [INFO] PMI contraction delta = {d3:.4f} (expected negative)")
    assert d3 is not None and d3 < 0, "PMI contraction should be bearish"

    # ── Currency score aggregation ─────────────────────────────────────────
    # A single bullish event (actual > forecast) should push S_c above 5.0
    events = [
        {"currency": "USD", "impact": "High", "event": "Non-Farm Employment Change",
         "actual_num": 170000.0, "forecast_num": 165000.0, "previous_num": 150000.0},
    ]
    s = score_currency_from_events(events, "USD")
    print(f"  [INFO] USD score from single bullish NFP = {s}")
    assert s > 5.0, "Bullish event should push score above 5.0"

    # ── Cross-asset relative strength ──────────────────────────────────────
    # Inverse USD: S = 11.0 - S_USD
    cs = {"USD": 3.4, "EUR": 6.8, "GBP": 5.2, "JPY": 5.0, "AUD": 5.0,
          "CAD": 5.0, "CHF": 5.0, "NZD": 5.0}
    assets = compute_asset_scores(cs)
    print(f"  [INFO] S_USD=3.4 -> GOLD = {assets['GOLD']['score']} (expected 7.6)")
    assert abs(assets["GOLD"]["score"] - 7.6) < 0.01, "GOLD should be 11.0 - 3.4 = 7.6"
    assert abs(assets["BTCUSD"]["score"] - 7.6) < 0.01, "BTCUSD should be 7.6"

    # Non-USD cross: EURGBP = 5 + (S_EUR - S_GBP) = 5 + (6.8 - 5.2) = 6.6
    print(f"  [INFO] EURGBP = {assets['EURGBP']['score']} (expected 6.6)")
    assert abs(assets["EURGBP"]["score"] - 6.6) < 0.01, "EURGBP should be 6.6"

    # Direct USD: USDJPY = S_USD = 3.4
    print(f"  [INFO] USDJPY = {assets['USDJPY']['score']} (expected 3.4)")
    assert abs(assets["USDJPY"]["score"] - 3.4) < 0.01, "USDJPY should be 3.4"

    # Inverse USD: EURUSD = 11.0 - 3.4 = 7.6
    print(f"  [INFO] EURUSD = {assets['EURUSD']['score']} (expected 7.6)")
    assert abs(assets["EURUSD"]["score"] - 7.6) < 0.01, "EURUSD should be 7.6"

    # ── Whitelist coverage ─────────────────────────────────────────────────
    expected_count = sum(len(v) for v in ALLOWED_ASSETS.values())
    print(f"  [INFO] Whitelist assets = {expected_count}, generated = {len(assets)}")
    assert len(assets) == expected_count, "All whitelist assets must be scored"

    print("\nAll scoring engine self-test assertions passed.")
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if "--selftest" in sys.argv:
        return run_self_test()

    events = load_calendar_events()
    if not events:
        logger.warning("No calendar events found; using neutral scores (5.0).")

    payload = build_master_bias(events)
    write_master_bias(payload)

    print(f"\nFundamental bias build complete.")
    print(f"  Currencies scored: {len(payload['currencies'])}")
    print(f"  Assets scored: {len(payload['assets'])}")
    print(f"  Pairs computed: {payload['total_pairs']}")
    print(f"  Extreme setups: {payload['total_extreme']}")
    print(f"  Output: {OUTPUT_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())