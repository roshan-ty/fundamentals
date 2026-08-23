#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — AI Market Analysis Generator
Reads all fresh JSON endpoints (master_bias.json, calendar.json, cftc_report.json,
news.json) and generates smart, concise macroeconomic analysis notes for USD and
all major asset classes.

Synthesis Market Logic:
  1. USD Synthesis:
     - USD Score < 4.0: weakening growth/employment + cooling inflation + falling
       yields => strong bearish fundamental drag on USD.
     - USD Score > 6.0: hot inflation/employment or hawkish central bank => strong
       fundamental support for USD.
  2. Cross-Asset Tailwinds (Gold/XAU, Silver/XAG, EUR/USD):
     - USD weakness is a direct tailwind for Gold and EUR due to inverse dollar
       pricing mechanics and real interest rate differential shifts.
  3. Institutional CFTC Confluence:
     - If an asset has CFTC Long Ratio > 75% AND a Bullish Fundamental Score
       (> 6.0), generate a note highlighting strong institutional-fundamental
       confluence.

Output: public/data/ai_insights.json

Run:
  python scripts/generate_ai_notes.py            # generate ai_insights.json
  python scripts/generate_ai_notes.py --selftest # verify synthesis offline
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "public", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "ai_insights.json")

# ── Asset universe for analysis ────────────────────────────────────────────────
# Aligned with the canonical whitelist in scripts/config.py.
USD_COUNTER_ASSETS = ["XAU", "XAG", "EUR", "GBP", "AUD", "NZD", "BTC"]
MAJOR_PAIRS = [
    "EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD", "USD/JPY", "USD/CAD",
    "USD/CHF", "XAU/USD", "XAG/USD", "BTC/USD", "ETH/USD",
    "LTC/USD", "SOL/USD", "XRP/USD", "AVAX/USD", "SUI/USD", "XLM/USD",
    "COPPER/USD", "PALLADIUM/USD", "PLATINUM/USD", "BRENT/USD",
]


def _load_json(filename: str) -> Any:
    """Load a JSON file from the data directory."""
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Could not load %s: %s", filename, e)
        return {}


def _score_label(score: float) -> str:
    """Human-readable label for a 1-10 score."""
    if score >= 8.0:
        return "Strongly Bullish"
    if score >= 6.0:
        return "Bullish"
    if score >= 4.1:
        return "Neutral"
    if score >= 2.1:
        return "Bearish"
    return "Strongly Bearish"


def _build_usd_analysis(master_bias: dict, calendar: dict, cftc: dict, news: dict) -> dict:
    """Build a structured USD analysis note per the task's synthesis rules."""
    base_scores = master_bias.get("base_scores", {})
    usd_score = base_scores.get("USD", 5.0)

    # Calendar surprises
    cal_events = calendar if isinstance(calendar, list) else calendar.get("events", [])
    usd_surprises = [
        ev for ev in cal_events
        if ev.get("currency") == "USD" and ev.get("actual_num") is not None
        and ev.get("forecast_num") is not None
    ][:5]

    # CFTC
    cftc_data = cftc.get("data", {}) if isinstance(cftc, dict) else {}
    usd_cftc = cftc_data.get("USD", {})

    # News mentions
    news_articles = news.get("articles", []) if isinstance(news, dict) else []
    usd_news = [a for a in news_articles if "USD" in a.get("currency_tags", [])][:3]

    key_points = []
    for ev in usd_surprises:
        actual = ev.get("actual_num")
        forecast = ev.get("forecast_num")
        if actual is not None and forecast is not None:
            delta = actual - forecast
            direction = "beat" if delta > 0 else "miss"
            key_points.append(
                f"{ev.get('event', '')}: Actual {actual} vs Forecast {forecast} ({direction})"
            )

    # Narrative per task rules
    if usd_score < 4.0:
        narrative = (
            f"The US Dollar composite score is {usd_score:.1f}/10 ({_score_label(usd_score)}). "
            "Weakening growth/employment data combined with cooling inflation and falling "
            "Treasury yields creates a strong bearish fundamental drag on the US Dollar. "
            "Rate-cut expectations are building, which is bearish for USD and bullish for "
            "counter-assets (Gold, Silver, EUR, GBP, AUD, NZD, BTC)."
        )
    elif usd_score > 6.0:
        narrative = (
            f"The US Dollar composite score is {usd_score:.1f}/10 ({_score_label(usd_score)}). "
            "Hot inflation/employment metrics or hawkish central bank positioning provide "
            "strong fundamental support for USD. Rate expectations remain elevated, "
            "supporting capital flows into the dollar."
        )
    else:
        narrative = (
            f"The US Dollar composite score is {usd_score:.1f}/10 ({_score_label(usd_score)}). "
            "Mixed macro signals keep the dollar in a neutral-to-uncertain range."
        )

    return {
        "asset": "USD",
        "section": "USD Bias",
        "score": round(usd_score, 2),
        "direction": _score_label(usd_score),
        "summary": narrative,
        "key_data_points": key_points,
        "breakdown_items": [],
        "news_headlines": [a.get("headline") for a in usd_news],
    }


def _build_cross_asset_tailwind(master_bias: dict, usd_score: float) -> dict:
    """Build a cross-asset tailwind note for Gold/Silver/EUR per task rules."""
    base_scores = master_bias.get("base_scores", {})
    gold = base_scores.get("XAU", 5.0)
    silver = base_scores.get("XAG", 5.0)
    eur = base_scores.get("EUR", 5.0)

    if usd_score < 4.0:
        summary = (
            f"USD weakness (score {usd_score:.1f}/10) operates as a direct tailwind for "
            f"Gold ({gold:.1f}), Silver ({silver:.1f}), and EUR/USD ({eur:.1f}) due to "
            "inverse dollar pricing mechanics and real interest rate differential shifts. "
            "As US real yields fall, non-yielding metals and EUR become relatively more attractive."
        )
    elif usd_score > 6.0:
        summary = (
            f"USD strength (score {usd_score:.1f}/10) is a headwind for Gold ({gold:.1f}), "
            f"Silver ({silver:.1f}), and EUR/USD ({eur:.1f}) as rising real yields and a "
            "stronger dollar pressure inverse-priced assets."
        )
    else:
        summary = (
            f"With USD neutral ({usd_score:.1f}/10), Gold ({gold:.1f}), Silver ({silver:.1f}), "
            "and EUR/USD are driven more by their own macro fundamentals than dollar direction."
        )

    return {
        "asset": "CROSS_ASSET_TAILWINDS",
        "section": "Cross-Asset Tailwinds",
        "score": round(max(gold, silver, eur), 2),
        "direction": _score_label(max(gold, silver, eur)),
        "summary": summary,
        "key_data_points": [
            f"Gold (XAU): {gold:.1f}/10",
            f"Silver (XAG): {silver:.1f}/10",
            f"EUR/USD: {eur:.1f}/10",
        ],
        "breakdown_items": [],
        "news_headlines": [],
    }


def _build_cftc_confluence(master_bias: dict, cftc: dict) -> dict:
    """Build a CFTC institutional-fundamental confluence note per task rules."""
    base_scores = master_bias.get("base_scores", {})
    cftc_data = cftc.get("data", {}) if isinstance(cftc, dict) else {}

    confluence_assets = []
    for asset, entry in cftc_data.items():
        long_pct = entry.get("long_percentage", 0)
        # Map asset symbol to base_scores key (GOLD->XAU, SILVER->XAG, etc.)
        score_key = asset
        if asset == "GOLD":
            score_key = "XAU"
        elif asset == "SILVER":
            score_key = "XAG"
        elif asset == "OIL":
            score_key = "WTI"
        elif asset == "US500":
            score_key = "SP500"
        elif asset == "US100":
            score_key = "NAS100"
        elif asset == "GE40":
            score_key = "GER40"
        fundamental_score = base_scores.get(score_key, 5.0)

        # Confluence: Long Ratio > 75% AND Bullish Fundamental Score > 6.0
        if long_pct > 75.0 and fundamental_score > 6.0:
            confluence_assets.append({
                "asset": asset,
                "long_ratio": long_pct,
                "fundamental_score": fundamental_score,
            })

    if not confluence_assets:
        return {
            "asset": "CFTC_CONFLUENCE",
            "section": "Institutional Confluence",
            "score": 5.0,
            "direction": "Neutral",
            "summary": "No assets currently show strong institutional-fundamental confluence "
                       "(CFTC Long Ratio > 75% AND fundamental score > 6.0).",
            "key_data_points": [],
            "breakdown_items": [],
            "news_headlines": [],
        }

    lines = []
    for c in confluence_assets:
        lines.append(
            f"{c['asset']}: CFTC Long Ratio {c['long_ratio']:.1f}% with fundamental score "
            f"{c['fundamental_score']:.1f}/10 — strong institutional-fundamental confluence."
        )

    return {
        "asset": "CFTC_CONFLUENCE",
        "section": "Institutional Confluence",
        "score": round(max(c["fundamental_score"] for c in confluence_assets), 2),
        "direction": "Bullish",
        "summary": " ".join(lines),
        "key_data_points": [
            f"{c['asset']}: {c['long_ratio']:.1f}% long / {c['fundamental_score']:.1f} score"
            for c in confluence_assets
        ],
        "breakdown_items": [],
        "news_headlines": [],
    }


def _build_pair_analysis(master_bias: dict, pair_name: str) -> dict:
    """Build an analysis note for a specific currency pair."""
    pairs = master_bias.get("pairs", [])
    pair = next((p for p in pairs if p.get("name") == pair_name), None)
    if not pair:
        return {}

    base = pair.get("base_asset", "")
    quote = pair.get("quote_asset", "")
    combined = pair.get("combined_bias", 5.0)

    if quote == "USD" and base in USD_COUNTER_ASSETS:
        relationship = (
            f"{base} is the base asset and USD is the quote asset. "
            "Weak USD is bullish for this pair; strong USD is bearish."
        )
    elif base == "USD" and quote in ["JPY", "CAD"]:
        relationship = (
            f"USD is the base asset and {quote} is the quote asset. "
            "This pair has a DIRECT relationship with USD strength."
        )
    else:
        relationship = f"{base} vs {quote} relative fundamental strength."

    summary = (
        f"{pair_name} composite bias is {combined:.1f}/10 ({_score_label(combined)}). "
        f"Base score {pair.get('base_score', 5.0):.1f} vs quote score "
        f"{pair.get('quote_score', 5.0):.1f}. {relationship}"
    )

    return {
        "asset": pair_name,
        "section": "Pair Analysis",
        "score": round(combined, 2),
        "direction": _score_label(combined),
        "summary": summary,
        "key_data_points": [
            f"Base ({base}) score: {pair.get('base_score', 5.0):.1f}",
            f"Quote ({quote}) score: {pair.get('quote_score', 5.0):.1f}",
            f"Combined bias: {combined:.1f}/10",
        ],
        "breakdown_items": [],
        "news_headlines": [],
    }


def generate_ai_notes() -> dict:
    """Read all fresh JSON endpoints and generate structured analysis notes."""
    master_bias = _load_json("master_bias.json")
    calendar = _load_json("calendar.json")
    cftc = _load_json("cftc_report.json")
    news = _load_json("news.json")

    notes: list[dict] = []
    base_scores = master_bias.get("base_scores", {})
    usd_score = base_scores.get("USD", 5.0)

    # USD analysis
    usd_note = _build_usd_analysis(master_bias, calendar, cftc, news)
    if usd_note:
        notes.append(usd_note)

    # Cross-asset tailwinds (Gold/Silver/EUR)
    tailwind_note = _build_cross_asset_tailwind(master_bias, usd_score)
    notes.append(tailwind_note)

    # CFTC institutional-fundamental confluence
    confluence_note = _build_cftc_confluence(master_bias, cftc)
    notes.append(confluence_note)

    # Major pair analyses
    for pair_name in MAJOR_PAIRS:
        note = _build_pair_analysis(master_bias, pair_name)
        if note:
            notes.append(note)

    # Market breadth summary
    pairs = master_bias.get("pairs", [])
    bullish = sum(1 for p in pairs if p.get("combined_bias", 5) >= 6.0)
    bearish = sum(1 for p in pairs if p.get("combined_bias", 5) <= 4.0)
    total = max(1, len(pairs))

    breadth = {
        "asset": "MARKET_BREADTH",
        "section": "Market Breadth",
        "score": round((bullish / total) * 10, 2),
        "direction": "Bullish" if bullish > bearish else "Bearish" if bearish > bullish else "Neutral",
        "summary": (
            f"Across {total} tracked pairs, {bullish} are bullish ({bullish/total*100:.0f}%) "
            f"and {bearish} are bearish ({bearish/total*100:.0f}%). "
            f"USD composite: {usd_score:.1f}/10."
        ),
        "key_data_points": [
            f"Bullish signals: {bullish}",
            f"Bearish signals: {bearish}",
            f"Total pairs: {total}",
        ],
        "breakdown_items": [],
        "news_headlines": [],
    }
    notes.append(breadth)

    # Compose final analysis text (concise summary for the frontend)
    analysis_lines = []
    for note in notes:
        analysis_lines.append(
            f"{note['asset']} ({note['section']}): {note['summary']}"
        )
    analysis_text = "\n\n".join(analysis_lines)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "local-ai-notes",
        "provider": "Bulls & Bears Fundamentals AI Generator",
        "analysis": analysis_text,
        "notes": notes,
        "token_usage": {},
    }

    return result


def write_ai_insights(insights: dict, output_path: Optional[str] = None) -> str:
    """Write AI insights to public/data/ai_insights.json."""
    path = output_path or OUTPUT_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2, default=str)
    logger.info("AI Insights: Written %d notes to %s", len(insights.get("notes", [])), path)
    return path


def run_self_test() -> int:
    """Offline verification of the synthesis logic."""
    print("=" * 60)
    print(" BULLS & BEARS FUNDAMENTALS — AI NOTES SELF-TEST")
    print("=" * 60)

    # USD < 4.0 => bearish narrative
    master = {"base_scores": {"USD": 3.4, "XAU": 7.6, "XAG": 7.6, "EUR": 7.6}, "pairs": []}
    usd_note = _build_usd_analysis(master, [], {}, {})
    print(f"  [INFO] USD score 3.4 -> {usd_note['direction']}")
    assert usd_note["direction"] == "Bearish", "USD 3.4 should be Bearish"
    assert "bearish fundamental drag" in usd_note["summary"], "USD <4 should mention bearish drag"

    # USD > 6.0 => bullish narrative
    master2 = {"base_scores": {"USD": 7.2, "XAU": 3.8, "XAG": 3.8, "EUR": 3.8}, "pairs": []}
    usd_note2 = _build_usd_analysis(master2, [], {}, {})
    print(f"  [INFO] USD score 7.2 -> {usd_note2['direction']}")
    assert usd_note2["direction"] == "Bullish", "USD 7.2 should be Bullish"
    assert "fundamental support" in usd_note2["summary"], "USD >6 should mention support"

    # Cross-asset tailwind: USD weak => Gold/EUR bullish
    tailwind = _build_cross_asset_tailwind(master, 3.4)
    print(f"  [INFO] Cross-asset tailwind direction = {tailwind['direction']}")
    assert tailwind["direction"] == "Bullish", "Weak USD should be bullish for Gold/EUR"
    assert "inverse dollar pricing" in tailwind["summary"], "Should mention inverse dollar pricing"

    # CFTC confluence: Long Ratio > 75% AND score > 6.0
    cftc = {"data": {"GOLD": {"long_percentage": 88.0}}}
    master3 = {"base_scores": {"XAU": 7.6}, "pairs": []}
    confluence = _build_cftc_confluence(master3, cftc)
    print(f"  [INFO] CFTC confluence assets = {[c['asset'] for c in confluence['key_data_points']]}")
    assert confluence["direction"] == "Bullish", "GOLD 88% long + 7.6 score should be confluence"
    assert "GOLD" in confluence["summary"], "GOLD should appear in confluence summary"

    # No confluence when score <= 6.0
    cftc2 = {"data": {"GOLD": {"long_percentage": 88.0}}}
    master4 = {"base_scores": {"XAU": 5.5}, "pairs": []}
    confluence2 = _build_cftc_confluence(master4, cftc2)
    print(f"  [INFO] No-confluence direction = {confluence2['direction']}")
    assert confluence2["direction"] == "Neutral", "Score 5.5 should not trigger confluence"

    print("\nAll AI notes self-test assertions passed.")
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if "--selftest" in sys.argv:
        return run_self_test()

    insights = generate_ai_notes()
    write_ai_insights(insights)

    print(f"\nAI notes generation complete.")
    print(f"  Notes generated: {len(insights.get('notes', []))}")
    print(f"  Output: {OUTPUT_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())