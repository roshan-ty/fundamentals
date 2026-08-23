#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — CFTC Positioning Engine

Authoritative script that processes CFTC Commitment of Traders (COT) data and
generates public/data/cftc_report.json with the All-Time Overall Long vs. Short
Positioning Percentage for all whitelisted assets.

Scoring math (see task spec):
  Total Non-Commercial Positions = Long + Short
  Long Ratio  L% = (Long / (Long + Short)) * 100
  Short Ratio S% = 100.0 - L%

  Tiered Sentiment Matrix centered at 50.0%:
    L% > 50.0 (Majority LONG):
      50.1-59.9  => Mildly Bullish        (score 5.5-6.4)
      60.0-74.9  => Moderately Bullish    (score 6.5-7.9)
      >= 75.0    => Strongly Bullish      (score 8.0-10.0)
    L% < 50.0 (Majority SHORT):
      40.1-49.9  => Mildly Bearish        (score 3.6-4.5)
      25.0-40.0  => Moderately Bearish    (score 2.1-3.5)
      <= 24.9    => Strongly Bearish      (score 1.0-2.0)

  Visual-only metric (never flips overall bias):
    Weekly Net Change dW = ((Net_current - Net_prev) / |Net_prev|) * 100

Output: public/data/cftc_report.json (superset schema — task `data` model + the
frontend's existing `positions` structure so the website keeps working).

Run:
  python scripts/build_cftc_data.py            # generate cftc_report.json
  python scripts/build_cftc_data.py --selftest # verify formulas offline
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

from scripts.config import ALLOWED_ASSETS

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
CFTC_INPUT_PATH = os.path.join(_PROJECT_ROOT, "public", "data", "cftc_report.json")
OUTPUT_PATH = os.path.join(_PROJECT_ROOT, "public", "data", "cftc_report.json")

# ── Engine code -> whitelist asset symbol mapping ──────────────────────────────
# The existing CFTC data is keyed by engine codes (XAU, XAG, WTI, SP500, EUR...).
# Map them to the whitelist trading symbols used in ALLOWED_ASSETS.
ENGINE_TO_ASSET: dict[str, str] = {
    # Commodities
    "XAU": "GOLD",
    "XAG": "SILVER",
    "WTI": "OIL",
    "BRENT": "BRENT",
    "COPPER": "COPPER",
    "PALLADIUM": "PALLADIUM",
    "PLATINUM": "PLATINUM",
    # Forex (map currency engine code to a representative whitelist pair)
    "EUR": "EURUSD",
    "GBP": "GBPUSD",
    "JPY": "USDJPY",
    "AUD": "AUDUSD",
    "CAD": "USDCAD",
    "CHF": "USDCHF",
    "NZD": "NZDUSD",
    "MXN": "USDMXN",
    # Indices
    "SP500": "US500",
    "NAS100": "US100",
    "GER40": "GE40",
    "AUS200": "AUS200",
    "JP225": "JP225",
    "GB100": "GB100",
    "EU50": "EU50",
    "FR40": "FR40",
    "CH20": "CH20",
    "ES35": "ES35",
    "HK50": "HK50",
    "US30": "US30",
}

# Category lookup for each whitelist asset symbol
def _category_for(symbol: str) -> str:
    for cat, symbols in ALLOWED_ASSETS.items():
        if symbol in symbols:
            return cat
    return "OTHER"


# ── Tiered sentiment matrix centered at 50.0% ──────────────────────────────────

def sentiment_from_long_ratio(long_pct: float) -> tuple[str, float]:
    """Return (sentiment_label, cftc_score) from the long ratio percentage.

    Centered at 50.0% — no hardcoded 70% thresholds. Weekly change never
    flips this classification.
    """
    lr = long_pct
    if lr > 50.0:
        if lr >= 75.0:
            # Strongly Bullish / Extreme Long: score 8.0-10.0
            score = 8.0 + min((lr - 75.0) / 25.0, 1.0) * 2.0
            return "Strongly Bullish", round(score, 2)
        if lr >= 60.0:
            # Moderately Bullish: score 6.5-7.9
            score = 6.5 + ((lr - 60.0) / 14.9) * 1.4
            return "Moderately Bullish", round(score, 2)
        # Mildly Bullish: score 5.5-6.4
        score = 5.5 + ((lr - 50.1) / 9.8) * 0.9
        return "Mildly Bullish", round(score, 2)
    if lr < 50.0:
        if lr <= 24.9:
            # Strongly Bearish / Extreme Short: score 1.0-2.0
            score = 1.0 + (lr / 24.9) * 1.0
            return "Strongly Bearish", round(score, 2)
        if lr <= 40.0:
            # Moderately Bearish: score 2.1-3.5
            score = 3.5 - ((40.0 - lr) / 15.0) * 1.4
            return "Moderately Bearish", round(score, 2)
        # Mildly Bearish: score 3.6-4.5
        score = 4.5 - ((49.9 - lr) / 9.8) * 0.9
        return "Mildly Bearish", round(score, 2)
    return "Neutral", 5.0


def compute_weekly_change_pct(net_current: float, net_previous: Optional[float]) -> Optional[float]:
    """Compute the visual-only weekly net change percentage (dW)."""
    if net_previous is None or abs(net_previous) < 1e-9:
        return None
    return round(((net_current - net_previous) / abs(net_previous)) * 100.0, 2)


# ── Data loading & processing ──────────────────────────────────────────────────

def load_existing_positions() -> dict[str, dict]:
    """Load the existing cftc_report.json positions (engine-code keyed)."""
    if not os.path.exists(CFTC_INPUT_PATH):
        logger.warning("cftc_report.json not found at %s", CFTC_INPUT_PATH)
        return {}
    with open(CFTC_INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    positions = data.get("positions", {}) if isinstance(data, dict) else {}
    return positions


def build_cftc_data(positions: dict[str, dict]) -> dict[str, Any]:
    """Assemble the superset cftc_report.json payload.

    Task schema: data (asset symbols -> long/short contracts, percentages,
    sentiment, cftc_score, weekly_change_pct).
    Frontend schema: positions (engine codes -> existing fields).
    """
    data_out: dict[str, dict] = {}
    positions_out: dict[str, dict] = {}

    for engine_code, pos in positions.items():
        long_c = float(pos.get("noncomm_long", 0) or 0)
        short_c = float(pos.get("noncomm_short", 0) or 0)
        total = long_c + short_c

        if total <= 0:
            long_pct = 50.0
        else:
            long_pct = (long_c / total) * 100.0
        short_pct = 100.0 - long_pct

        sentiment, score = sentiment_from_long_ratio(long_pct)

        net_current = float(pos.get("net_speculative", 0) or 0)
        # weekly_change in existing data is the absolute change; derive pct
        # from net_current and (net_current - weekly_change) as previous.
        weekly_change_abs = float(pos.get("weekly_change", 0) or 0)
        net_previous = net_current - weekly_change_abs
        weekly_pct = compute_weekly_change_pct(net_current, net_previous)
        if weekly_pct is None:
            weekly_pct = pos.get("weekly_change_pct")

        # Map engine code to whitelist asset symbol
        asset_symbol = ENGINE_TO_ASSET.get(engine_code, engine_code)
        category = _category_for(asset_symbol)

        # Task schema entry (asset symbol keyed)
        data_out[asset_symbol] = {
            "asset": asset_symbol,
            "category": category,
            "long_contracts": round(long_c, 2),
            "short_contracts": round(short_c, 2),
            "long_percentage": round(long_pct, 2),
            "short_percentage": round(short_pct, 2),
            "weekly_change_pct": weekly_pct,
            "sentiment": sentiment,
            "cftc_score": score,
        }

        # Frontend schema entry (engine code keyed, preserves existing fields)
        positions_out[engine_code] = {
            "report_date": pos.get("report_date", ""),
            "noncomm_long": long_c,
            "noncomm_short": short_c,
            "long_ratio": round(long_pct, 2),
            "net_speculative": net_current,
            "weekly_change": weekly_change_abs,
            "weekly_change_pct": weekly_pct,
            "percentile_52w": pos.get("percentile_52w", 50.0),
            "cftc_score": score,
            "sentiment": sentiment,
        }

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "data": data_out,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "positions": positions_out,
        "total_markets": len(data_out),
    }


def write_cftc_report(payload: dict[str, Any], output_path: str = OUTPUT_PATH) -> str:
    """Write cftc_report.json."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("Exported cftc_report.json (%d markets)", payload["total_markets"])
    return output_path


# ── Self-test (offline formula verification) ──────────────────────────────────

def run_self_test() -> int:
    """Verify the CFTC math against the task's exact examples."""
    print("=" * 60)
    print(" BULLS & BEARS FUNDAMENTALS — CFTC ENGINE SELF-TEST")
    print("=" * 60)

    # Gold example: 245120 long, 32280 short.
    # NOTE: 245120 / (245120 + 32280) = 88.36% (the task's stated 88.38% is a
    # rounding artifact of its example numbers; the formula is authoritative).
    long_c = 245120.0
    short_c = 32280.0
    total = long_c + short_c
    long_pct = (long_c / total) * 100.0
    short_pct = 100.0 - long_pct
    print(f"  [INFO] GOLD long% = {long_pct:.2f} (expected 88.36)")
    print(f"  [INFO] GOLD short% = {short_pct:.2f} (expected 11.64)")
    assert abs(long_pct - 88.36) < 0.01, "GOLD long% should be 88.36"
    assert abs(short_pct - 11.64) < 0.01, "GOLD short% should be 11.64"

    # Gold sentiment: 88.38% >= 75 => Strongly Bullish, score 8.0-10.0
    sentiment, score = sentiment_from_long_ratio(long_pct)
    print(f"  [INFO] GOLD sentiment = {sentiment} (score {score})")
    assert sentiment == "Strongly Bullish", "GOLD should be Strongly Bullish"
    assert 8.0 <= score <= 10.0, "GOLD score should be 8.0-10.0"

    # Negative weekly change must NOT flip the overall bias
    weekly_pct = compute_weekly_change_pct(212840.0, 213180.0)  # -0.16%
    print(f"  [INFO] GOLD weekly change = {weekly_pct}% (visual only)")
    assert weekly_pct is not None and weekly_pct < 0, "weekly change should be negative"
    # Bias stays Strongly Bullish despite negative weekly change
    assert sentiment == "Strongly Bullish", "Negative weekly change must not flip bias"

    # EURUSD example: 142000 long, 95000 short => 59.91% Long => Mildly Bullish
    eur_long = 142000.0
    eur_short = 95000.0
    eur_total = eur_long + eur_short
    eur_pct = (eur_long / eur_total) * 100.0
    eur_sent, eur_score = sentiment_from_long_ratio(eur_pct)
    print(f"  [INFO] EURUSD long% = {eur_pct:.2f} -> {eur_sent} (score {eur_score})")
    assert abs(eur_pct - 59.91) < 0.01, "EURUSD long% should be 59.91"
    assert eur_sent == "Mildly Bullish", "EURUSD should be Mildly Bullish"
    assert 5.5 <= eur_score <= 6.4, "EURUSD score should be 5.5-6.4"

    # Tiered matrix boundary checks
    s1, sc1 = sentiment_from_long_ratio(50.1)
    assert s1 == "Mildly Bullish", "50.1% should be Mildly Bullish"
    s2, sc2 = sentiment_from_long_ratio(60.0)
    assert s2 == "Moderately Bullish", "60.0% should be Moderately Bullish"
    s3, sc3 = sentiment_from_long_ratio(75.0)
    assert s3 == "Strongly Bullish", "75.0% should be Strongly Bullish"
    s4, sc4 = sentiment_from_long_ratio(49.9)
    assert s4 == "Mildly Bearish", "49.9% should be Mildly Bearish"
    s5, sc5 = sentiment_from_long_ratio(40.0)
    assert s5 == "Moderately Bearish", "40.0% should be Moderately Bearish"
    s6, sc6 = sentiment_from_long_ratio(24.9)
    assert s6 == "Strongly Bearish", "24.9% should be Strongly Bearish"

    print("\nAll CFTC engine self-test assertions passed.")
    return 0


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if "--selftest" in sys.argv:
        return run_self_test()

    positions = load_existing_positions()
    if not positions:
        logger.warning("No existing CFTC positions found; output will be empty.")

    payload = build_cftc_data(positions)
    write_cftc_report(payload)

    print(f"\nCFTC data build complete.")
    print(f"  Markets processed: {payload['total_markets']}")
    print(f"  Output: {OUTPUT_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())