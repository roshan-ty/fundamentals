#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — AI Market Analysis Generator
Reads all fresh JSON endpoints (macro_data.json, calendar.json, cftc_report.json,
news.json, master_bias.json) and generates smart, concise macroeconomic analysis
notes for USD and all major asset pairs.

Output: public/data/ai_insights.json
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "public", "data")

# ── Asset universe for analysis ────────────────────────────────────────────────
# Aligned with the canonical whitelist in scripts/config.py.
# Only whitelisted symbols are analyzed — synthetic assets (WTI, SP500,
# NAS100, GER40, ...) are excluded from the traded universe.
USD_COUNTER_ASSETS = ["XAU", "XAG", "EUR", "GBP", "AUD", "NZD", "BTC"]
MAJOR_PAIRS = [
    "EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD", "USD/JPY", "USD/CAD",
    "USD/CHF", "XAU/USD", "XAG/USD", "BTC/USD", "ETH/USD",
    "LTC/USD", "SOL/USD", "XRP/USD", "AVAX/USD", "SUI/USD", "XLM/USD",
    "COPPER/USD", "PALLADIUM/USD", "PLATINUM/USD", "BRENT/USD",
]


def _load_json(filename: str) -> dict:
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


def _build_usd_analysis(master_bias: dict, macro_data: dict,
                        calendar: dict, cftc: dict, news: dict) -> dict:
    """Build a structured USD analysis note."""
    base_scores = master_bias.get("base_scores", {})
    usd_score = base_scores.get("USD", 5.0)
    breakdowns = master_bias.get("score_breakdowns", {}).get("USD", [])

    # Key data points
    fred_series = macro_data.get("series", {})
    gdp = fred_series.get("GDPC1", [{}])[0].get("value")
    unrate = fred_series.get("UNRATE", [{}])[0].get("value")
    cpi = fred_series.get("CPILFESL", [{}])[0].get("value")
    fed = fred_series.get("FEDFUNDS", [{}])[0].get("value")
    dgs10 = fred_series.get("DGS10", [{}])[0].get("value")

    # Calendar surprises
    cal_events = calendar.get("events", [])
    usd_surprises = [
        ev for ev in cal_events
        if ev.get("currency") == "USD" and ev.get("actual") is not None
        and ev.get("forecast") is not None
    ][:5]

    # CFTC
    usd_cftc = cftc.get("positions", {}).get("USD", {})

    # News mentions
    news_articles = news.get("articles", [])
    usd_news = [a for a in news_articles if "USD" in a.get("currency_tags", [])][:3]

    key_points = []
    if gdp is not None:
        key_points.append(f"Real GDP: ${gdp/1000:.1f}T")
    if unrate is not None:
        key_points.append(f"Unemployment: {unrate:.1f}%")
    if cpi is not None:
        key_points.append(f"Core CPI: {cpi:.1f}")
    if fed is not None:
        key_points.append(f"Fed Funds: {fed:.2f}%")
    if dgs10 is not None:
        key_points.append(f"10Y Yield: {dgs10:.2f}%")

    for ev in usd_surprises:
        actual = ev.get("actual")
        forecast = ev.get("forecast")
        if actual is not None and forecast is not None:
            delta = actual - forecast
            direction = "beat" if delta > 0 else "miss"
            key_points.append(
                f"{ev.get('event', '')}: Actual {actual} vs Forecast {forecast} ({direction})"
            )

    # Narrative
    if usd_score >= 6.0:
        narrative = (
            f"The US Dollar composite score is {usd_score:.1f}/10 ({_score_label(usd_score)}). "
            "Strong macro releases and/or elevated yields are supporting capital flows "
            "into the dollar. Rate expectations remain hawkish."
        )
    elif usd_score <= 4.0:
        narrative = (
            f"The US Dollar composite score is {usd_score:.1f}/10 ({_score_label(usd_score)}). "
            "Weak GDP momentum, soft inflation, rising unemployment, and/or falling yields "
            "are pressuring the dollar. Rate-cut expectations are building, which is "
            "bearish for USD and bullish for counter-assets (Gold, Silver, EUR, GBP, AUD, NZD, BTC)."
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
        "breakdown_items": [
            {"indicator": b.get("indicator"), "score": b.get("score"),
             "direction": b.get("direction")}
            for b in breakdowns[:6]
        ],
        "news_headlines": [a.get("headline") for a in usd_news],
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

    # Inverse-USD relationship logic
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
    """
    Read all fresh JSON endpoints and generate structured analysis notes.
    """
    master_bias = _load_json("master_bias.json")
    macro_data = _load_json("macro_data.json")
    calendar = _load_json("calendar.json")
    cftc = _load_json("cftc_report.json")
    news = _load_json("news.json")

    notes: list[dict] = []

    # USD analysis
    usd_note = _build_usd_analysis(master_bias, macro_data, calendar, cftc, news)
    if usd_note:
        notes.append(usd_note)

    # Major pair analyses
    for pair_name in MAJOR_PAIRS:
        note = _build_pair_analysis(master_bias, pair_name)
        if note:
            notes.append(note)

    # Market breadth summary
    base_scores = master_bias.get("base_scores", {})
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
            f"USD composite: {base_scores.get('USD', 5.0):.1f}/10."
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
    path = output_path or os.path.join(DATA_DIR, "ai_insights.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2, default=str)
    logger.info("AI Insights: Written %d notes to %s", len(insights.get("notes", [])), path)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    insights = generate_ai_notes()
    write_ai_insights(insights)
    print(f"Generated {len(insights.get('notes', []))} AI notes")
    for note in insights.get("notes", [])[:3]:
        print(f"  {note['asset']}: {note['summary'][:80]}...")