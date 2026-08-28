#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Relative Strength & Differential Fundamental Scoring Engine

Authoritative script that computes:

  STEP 1 — Individual Currency Strength Scores S_c ∈ [1.0, 10.0]
  ---------------------------------------------------------------
  For each major currency (USD, EUR, GBP, JPY, AUD, CAD, CHF, NZD):

    d_i = Direction_Multiplier × clamp( (Actual − Forecast) / (|Forecast| + ε), −1.0, 1.0 )

    Impact weights:              High = 1.0 · Medium = 0.5 · Low = 0.2
    Weighted aggregate sentiment: Z_c = Σ(d_i · w_i) / Σ(w_i)
    Currency strength:           S_c = clamp(5.0 + Z_c × 4.0, 1.0, 10.0)

    Direction multipliers:
      Standard growth/inflation (GDP, CPI, PPI, Retail, NFP, PMI):  +1 (beat = bullish)
      Distress/employment (Unemployment, Jobless Claims):           −1 (rise = bearish)

  STEP 2 — Pair Relative Strength Differential Scores
  ---------------------------------------------------
  Forex currency pairs (EURUSD, GBPUSD, EURGBP, GBPJPY, AUDCAD, USDJPY, ...)
    Pair Score = clamp(5.0 + (S_BASE − S_QUOTE), 1.0, 10.0)
    => EURUSD with S_EUR=5.5, S_USD=8.0  → 5.0 + (5.5 − 8.0) = 2.5  (Strongly Bearish)
    => USDJPY with S_USD=8.0, S_JPY=3.0  → 5.0 + (8.0 − 3.0) = 10.0 (Extremely Bullish)

  Precious metals / crypto / equity indices (non-yielding, USD-priced)
    Asset Score = 11.0 − S_USD
    => S_USD=8.0 (bullish USD)  →  Gold = 3.0  (bearish Gold)

Output: public/data/master_bias.json
    Superset schema: task data model (currencies, assets, pairs) + the frontend's
    existing base_scores / pairs / event_breakdowns structure so the website and
    the "Analyze" modal keep working.

Run:
  python scripts/build_fundamental_bias.py            # generate master_bias.json
  python scripts/build_fundamental_bias.py --selftest # verify formulas offline
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

# Ensure project root is importable
_PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.config import (
    ALLOWED_ASSETS,
    ALLOWED_DISPLAY_PAIRS,
    symbol_to_code,
    _COMMODITY_METALS,
    _COMMODITY_ENERGY,
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

# Inverse distress indicators: higher actual => bearish (flip sign)
INVERSE_KEYWORDS = ["UNEMPLOYMENT", "JOBLESS CLAIMS", "INITIAL CLAIMS", "JOBLESS"]


def _clamp(value: float, lo: float = 1.0, hi: float = 10.0) -> float:
    """Clamp a value strictly to [lo, hi]."""
    return max(lo, min(hi, value))


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


def _is_inverse(event_name: str) -> bool:
    """True for distress indicators where a higher actual is bearish."""
    upper = event_name.upper()
    return any(kw in upper for kw in INVERSE_KEYWORDS)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Normalized event score & per-currency aggregation
# ═══════════════════════════════════════════════════════════════════════════════

def event_deviation(actual: Optional[float], forecast: Optional[float],
                    previous: Optional[float], event_name: str) -> Optional[float]:
    """Normalized event deviation d_i ∈ [−1, +1] per the task spec.

    d_i = Direction_Multiplier × clamp((Actual − Forecast) / (|Forecast| + ε), −1, 1)

    Falls back to Previous when Forecast is missing so released events with no
    consensus estimate still contribute.
    """
    if actual is None:
        return None

    ref = forecast if forecast is not None else previous
    if ref is None:
        return None

    eps = 1e-9
    raw = (actual - ref) / (abs(ref) + eps)

    # Linear clamp to [-1, +1] (not tanh — task spec mandates hard clamp)
    d = _clamp(raw, -1.0, 1.0)

    # Distress indicators: higher actual => bearish (Direction_Multiplier = −1)
    if _is_inverse(event_name):
        d = -d

    return d


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
# STEP 2 — Cross-asset relative strength & pair differential scores
# ═══════════════════════════════════════════════════════════════════════════════

def compute_asset_scores(currency_scores: dict[str, float]) -> dict[str, dict]:
    """Compute per-asset scores for commodities, crypto and equity indices.

    Non-yielding USD-priced assets (precious metals, crypto, equity indices)
    carry the inverse-USD score:  Asset Score = 11.0 − S_USD
    """
    usd = currency_scores.get("USD", 5.0)
    inverse = _clamp(11.0 - usd)

    assets: dict[str, dict] = {}

    for asset_class in ("COMMODITIES", "CRYPTO", "INDICES"):
        for symbol in ALLOWED_ASSETS.get(asset_class, []):
            code = symbol_to_code(symbol)
            if asset_class == "COMMODITIES":
                category = (
                    "METAL" if code in _COMMODITY_METALS
                    else "ENERGY" if code in _COMMODITY_ENERGY
                    else "COMMODITY"
                )
            else:
                category = asset_class  # CRYPTO | INDICES

            assets[code] = {
                "score": round(inverse, 2),
                "bias": _bias_label(inverse),
                "category": category,
            }

    return assets


def compute_pair_matrix(base_scores: dict[str, float]) -> list[dict]:
    """Build the frontend `pairs` array from ALLOWED_DISPLAY_PAIRS.

    Forex pairs (both legs are currencies):
        Pair Score = clamp(5.0 + (S_BASE − S_QUOTE), 1, 10)
    Assets priced in USD (metals / crypto / indices / energy):
        Pair Score = asset's own score (= 11.0 − S_USD)

    Each pair: {name, asset_class, base_asset, quote_asset, base_score,
                quote_score, net_differential, combined_bias, direction}.
    """
    pairs: list[dict] = []
    for spec in ALLOWED_DISPLAY_PAIRS:
        base = spec["base"]
        quote = spec["quote"]
        asset_class = spec.get("asset_class", "OTHER")
        bs = base_scores.get(base, 5.0)
        qs = base_scores.get(quote, 5.0)

        if asset_class == "FX":
            # Relative strength differential — compare BASE vs QUOTE currency
            combined = _clamp(5.0 + (bs - qs))
        else:
            # Non-yielding USD-priced asset — its score already encodes 11 − S_USD
            combined = _clamp(bs)

        pairs.append({
            "name": spec.get("name", f"{base}/{quote}"),
            "asset_class": asset_class,
            "base_asset": base,
            "quote_asset": quote,
            "base_score": round(bs, 2),
            "quote_score": round(qs, 2),
            "net_differential": round(bs - qs, 2),
            "combined_bias": round(combined, 2),
            "direction": _bias_label(combined),
        })

    pairs.sort(key=lambda p: abs(p["combined_bias"] - 5.0), reverse=True)
    return pairs


# ═══════════════════════════════════════════════════════════════════════════════
# Event-level breakdowns (drives the frontend "Analyze" modal)
# ═══════════════════════════════════════════════════════════════════════════════

def build_event_breakdowns(events: list[dict]) -> dict[str, list[dict]]:
    """Group every released calendar event by currency with full analytics.

    One record per event for each major currency:
      date, time, event, impact, actual/forecast/previous (raw + numeric),
      deviation (Actual − Forecast), d_score (normalized d_i), weight, direction.
    """
    breakdowns: dict[str, list[dict]] = {c: [] for c in MAJOR_CURRENCIES}

    for ev in events:
        currency = ev.get("currency")
        if currency not in breakdowns:
            continue

        actual = ev.get("actual_num")
        forecast = ev.get("forecast_num")
        previous = ev.get("previous_num")
        event_name = ev.get("event", "")
        impact = ev.get("impact", "Low")
        w = IMPACT_WEIGHTS.get(impact, 0.0)

        d = event_deviation(actual, forecast, previous, event_name)

        deviation = None
        if actual is not None and forecast is not None:
            deviation = round(actual - forecast, 4)

        direction = "neutral"
        if d is not None:
            direction = "bullish" if d > 0 else "bearish" if d < 0 else "neutral"

        breakdowns[currency].append({
            "date": ev.get("date", ""),
            "time": ev.get("time", ""),
            "event": event_name,
            "impact": impact,
            "actual_raw": ev.get("actual_raw", ""),
            "forecast_raw": ev.get("forecast_raw", ""),
            "previous_raw": ev.get("previous_raw", ""),
            "actual_num": actual,
            "forecast_num": forecast,
            "previous_num": previous,
            "deviation": deviation,
            "d_score": None if d is None else round(d, 4),
            "weight": w,
            "direction": direction,
        })

    return breakdowns


def build_score_breakdowns(breakdowns: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Derive the legacy per-indicator score breakdown shape for HomeTab cards."""
    out: dict[str, list[dict]] = {}
    for currency, items in breakdowns.items():
        rows = []
        for it in items:
            if it["d_score"] is None:
                continue
            score = round(_clamp(5.0 + it["d_score"] * 4.0), 2)
            rows.append({
                "indicator": it["event"],
                "value": it["actual_num"],
                "unit": "",
                "date": it["date"],
                "score": score,
                "tier": it["impact"],
                "weight": it["weight"],
                "direction": it["direction"],
                "contribution": round(it["d_score"] * it["weight"], 4),
})
        out[currency] = rows
    return out
# ═══════════════════════════════════════════════════════════════════════════════
# Master JSON Generation
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

    # base_scores = 8 majors + every whitelisted non-currency asset
    base_scores: dict[str, float] = dict(currency_scores)
    for code, a in asset_scores.items():
        base_scores[code] = a["score"]

    pairs = compute_pair_matrix(base_scores)

    currencies_out = {
        c: {"score": currency_scores[c], "bias": _bias_label(currency_scores[c])}
        for c in MAJOR_CURRENCIES
    }
    assets_out = {
        sym: {"score": a["score"], "bias": a["bias"], "category": a["category"]}
        for sym, a in asset_scores.items()
    }

    event_breakdowns = build_event_breakdowns(events)
    score_breakdowns = build_score_breakdowns(event_breakdowns)

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
        "event_breakdowns": event_breakdowns,
        "score_breakdowns": score_breakdowns,
        "analysis_window_days": 14,
        "analysis_note": (
            "Relative Strength & Differential Model: per-currency scores from "
            "calendar events (Actual vs Forecast, /|Forecast| normalized, impact-"
            "weighted). Forex pairs = 5 + (S_BASE − S_QUOTE); USD-priced assets "
            "(metals/crypto/indices) = 11 − S_USD."
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
# Self-Test (offline formula verification against the task's worked examples)
# ═══════════════════════════════════════════════════════════════════════════════

def run_self_test() -> int:
    """Verify the scoring formulas against the task's exact examples."""
    print("=" * 60)
    print(" BULLS & BEARS FUNDAMENTALS — SCORING ENGINE SELF-TEST")
    print("=" * 60)

    # ── Step 1: normalized event deviation ──────────────────────────────────
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

    # ── Currency score aggregation ───────────────────────────────────────────
    events = [
        {"currency": "USD", "impact": "High", "event": "Non-Farm Employment Change",
         "actual_num": 170000.0, "forecast_num": 165000.0, "previous_num": 150000.0},
    ]
    s = score_currency_from_events(events, "USD")
    print(f"  [INFO] USD score from single bullish NFP = {s}")
    assert s > 5.0, "Bullish event should push score above 5.0"

    # ── Step 2: Worked Example 1 — EURUSD = 5 + (S_EUR − S_USD) = 2.5 ───────
    cs = {"USD": 8.0, "EUR": 5.5, "GBP": 5.0, "JPY": 3.0, "AUD": 5.0,
          "CAD": 5.0, "CHF": 5.0, "NZD": 5.0}
    base_scores = dict(cs)
    for code, a in compute_asset_scores(cs).items():
        base_scores[code] = a["score"]

    pairs_map = {p["name"]: p for p in compute_pair_matrix(base_scores)}
    eurusd = pairs_map["EUR/USD"]["combined_bias"]
    print(f"  [INFO] EUR/USD = {eurusd} (expected 2.5)")
    assert abs(eurusd - 2.5) < 0.01, "EURUSD should be 5 + (5.5 − 8.0) = 2.5"

    # ── Worked Example 2 — USDJPY = 5 + (S_USD − S_JPY) = 10.0 ───────────────
    cs2 = dict(cs)
    cs2["JPY"] = 3.0
    base_scores2 = dict(cs2)
    for code, a in compute_asset_scores(cs2).items():
        base_scores2[code] = a["score"]
    pairs_map2 = {p["name"]: p for p in compute_pair_matrix(base_scores2)}
    usdjpy = pairs_map2["USD/JPY"]["combined_bias"]
    print(f"  [INFO] USD/JPY = {usdjpy} (expected 10.0)")
    assert abs(usdjpy - 10.0) < 0.01, "USDJPY should be 5 + (8.0 − 3.0) = 10.0"

    # ── Precious metals & crypto: 11 − S_USD ─────────────────────────────────
    assets = compute_asset_scores(cs)
    print(f"  [INFO] S_USD=8.0 -> XAU = {assets['XAU']['score']} (expected 3.0)")
    assert abs(assets["XAU"]["score"] - 3.0) < 0.01, "GOLD should be 11 − 8.0 = 3.0"
    assert abs(assets["XAG"]["score"] - 3.0) < 0.01, "SILVER should be 3.0"
    assert abs(assets["BTC"]["score"] - 3.0) < 0.01, "BTC should be 3.0"
    assert abs(assets["SP500"]["score"] - 3.0) < 0.01, "US500 should be 3.0"
    assert abs(assets["NAS100"]["score"] - 3.0) < 0.01, "US100 should be 3.0"

    # Weak USD => bullish Gold
    cs_weak = dict(cs)
    cs_weak["USD"] = 3.4
    assets_weak = compute_asset_scores(cs_weak)
    print(f"  [INFO] S_USD=3.4 -> XAU = {assets_weak['XAU']['score']} (expected 7.6)")
    assert abs(assets_weak["XAU"]["score"] - 7.6) < 0.01, "GOLD should be 11 − 3.4 = 7.6"

    # ── Event breakdowns & whitelist coverage ────────────────────────────────
    breakdowns = build_event_breakdowns(events)
    assert "USD" in breakdowns and len(breakdowns["USD"]) >= 1
    assert breakdowns["USD"][0]["d_score"] is not None

    expected_assets = (len(ALLOWED_ASSETS["COMMODITIES"]) +
                       len(ALLOWED_ASSETS["CRYPTO"]) +
                       len(ALLOWED_ASSETS["INDICES"]))
    print(f"  [INFO] Non-FX whitelist assets = {expected_assets}, generated = {len(assets)}")
    assert len(assets) == expected_assets, "All non-FX whitelist assets must be scored"

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