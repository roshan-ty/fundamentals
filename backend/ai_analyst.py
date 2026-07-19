#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — AI Macro Analyst
Interfaces with xAI's chat completion API to generate quantitative
fundamental summaries of the macroeconomic landscape.
"""

import os
import json
import logging
from typing import Any, Optional
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
XAI_MODEL = "grok-2-latest"  # Current stable xAI model as of July 2026


def generate_macro_summary(scoring_results: dict[str, Any],
                           collected_data: dict[str, Any]) -> dict[str, Any]:
    """
    Send structured data to xAI and return the analysis.

    Args:
        scoring_results: Output from scorer.score_all()
        collected_data: Output from parsers.collect_all_data()

    Returns: Dict with AI-generated insights.
    """
    if not XAI_API_KEY:
        logger.warning("XAI_API_KEY not set. Using local synthesis fallback.")
        return _local_synthesis(scoring_results)

    # Prepare a concise prompt with the data
    prompt = _build_prompt(scoring_results, collected_data)

    try:
        response = requests.post(
            XAI_API_URL,
            headers={
                "Authorization": f"Bearer {XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": XAI_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an elite macroeconomic analyst for Bulls & Bears Fundamentals. "
                            "You provide concise, highly quantitative fundamental summaries. "
                            "Focus on: US Dollar bias, interest rate expectations, inflation trends, "
                            "institutional positioning (CFTC), and cross-asset implications. "
                            "Keep responses under 500 words. Use specific numbers and scores. "
                            "Format with clear sections: USD Bias, Key Themes, Asset Class Outlook."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "temperature": 0.3,  # Low temperature for factual analysis
                "max_tokens": 1024,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()

        ai_text = data["choices"][0]["message"]["content"]

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": XAI_MODEL,
            "provider": "xAI",
            "analysis": ai_text,
            "token_usage": data.get("usage", {}),
        }

        logger.info("AI Analysis generated (%d tokens)",
                     data.get("usage", {}).get("total_tokens", 0))
        return result

    except requests.RequestException as e:
        logger.error("xAI API call failed: %s", e)
        return _local_synthesis(scoring_results)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error("xAI response parse failed: %s", e)
        return _local_synthesis(scoring_results)


def _build_prompt(scoring_results: dict[str, Any],
                  collected_data: dict[str, Any]) -> str:
    """Build a structured prompt from the scoring data."""
    base_scores = scoring_results.get("base_scores", {})
    pairs = scoring_results.get("pairs", [])
    total_extreme = scoring_results.get("total_extreme", 0)

    # Extract key metrics
    usd_score = base_scores.get("USD", 5.0)
    eur_score = base_scores.get("EUR", 5.0)
    gbp_score = base_scores.get("GBP", 5.0)
    jpy_score = base_scores.get("JPY", 5.0)
    xau_score = base_scores.get("XAU", 5.0)
    btc_score = base_scores.get("BTC", 5.0)

    # Count bullish/bearish pairs
    bullish = sum(1 for p in pairs if p["combined_bias"] >= 6.0)
    bearish = sum(1 for p in pairs if p["combined_bias"] <= 4.0)
    neutral = sum(1 for p in pairs if 4.0 < p["combined_bias"] < 6.0)

    # Top directional moves
    top_long = [p for p in pairs if p["combined_bias"] >= 8.0][:5]
    top_short = [p for p in pairs if p["combined_bias"] <= 2.0][:5]

    # CFTC summary
    cftc_data = collected_data.get("cftc", {})

    prompt = f"""CURRENT FUNDAMENTAL SCORES (1-10 scale, 5=Neutral):

USD: {usd_score:.2f}
EUR: {eur_score:.2f}
GBP: {gbp_score:.2f}
JPY: {jpy_score:.2f}
Gold (XAU): {xau_score:.2f}
Bitcoin (BTC): {btc_score:.2f}

MARKET BREADTH:
Total Pairs Tracked: {len(pairs)}
Bullish Signals: {bullish} ({bullish/len(pairs)*100:.0f}%)
Bearish Signals: {bearish} ({bearish/len(pairs)*100:.0f}%)
Neutral: {neutral}
Extreme Setups: {total_extreme}

STRONGEST LONG SETUPS (Bias >= 8.0):
{chr(10).join(f"- {p['name']}: {p['combined_bias']:.2f} ({p['direction']})" for p in top_long[:5]) if top_long else "None"}

STRONGEST SHORT SETUPS (Bias <= 2.0):
{chr(10).join(f"- {p['name']}: {p['combined_bias']:.2f} ({p['direction']})" for p in top_short[:5]) if top_short else "None"}

CFTC INSTITUTIONAL POSITIONING (52-week percentile):
{chr(10).join(f"- {market}: {pos.get('percentile_52w', 'N/A')}%" for market, pos in list(cftc_data.items())[:10]) if cftc_data else "No CFTC data available"}

Analyze this data and provide:
1. USD Bias Assessment — Is the dollar fundamentally bullish or bearish? Rate expectations?
2. Key Macro Themes — What are the dominant narratives driving markets?
3. Asset Class Outlook — Specific calls on FX, Gold, Equities, Crypto
4. Institutional Flow Interpretation — What are smart money positions indicating?
Use quantitative evidence throughout."""
    return prompt


def _local_synthesis(scoring_results: dict[str, Any]) -> dict[str, Any]:
    """
    Fallback synthesis when xAI is unavailable.
    Generates a structured textual analysis from the scoring data.
    """
    base_scores = scoring_results.get("base_scores", {})
    pairs = scoring_results.get("pairs", [])
    cftc = scoring_results.get("cftc", {})

    usd_score = base_scores.get("USD", 5.0)
    eur_score = base_scores.get("EUR", 5.0)
    gbp_score = base_scores.get("GBP", 5.0)
    jpy_score = base_scores.get("JPY", 5.0)
    xau_score = base_scores.get("XAU", 5.0)
    btc_score = base_scores.get("BTC", 5.0)

    bullish = sum(1 for p in pairs if p["combined_bias"] >= 6.0)
    bearish = sum(1 for p in pairs if p["combined_bias"] <= 4.0)

    usd_assessment = "bullish" if usd_score >= 6.0 else \
                     "bearish" if usd_score <= 4.0 else "neutral"
    market_bias = "broadly bullish" if bullish > bearish * 1.5 else \
                  "broadly bearish" if bearish > bullish * 1.5 else \
                  "mixed with a slight positive tilt" if bullish > bearish else \
                  "mixed with a slight negative tilt"

    lines = [
        f"=== Bulls & Bears Fundamentals — Macro Synthesis ===",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"",
        f"USD BIAS: The US Dollar composite score is {usd_score:.1f}/10, indicating a {usd_assessment} stance. ",
        f"EUR/USD bias reflects euro fundamental score of {eur_score:.1f} vs dollar.",
        f"GBP/USD bias reflects pound fundamental score of {gbp_score:.1f}.",
        f"USD/JPY bias reflects yen fundamental score of {jpy_score:.1f}.",
        f"",
        f"KEY THEMES: The broader market is {market_bias}, with {bullish} bullish ",
        f"vs {bearish} bearish signals across {len(pairs)} tracked pairs.",
        f"Gold (XAU) scores {xau_score:.1f}/10, reflecting real yield and inflation dynamics.",
        f"Bitcoin (BTC) scores {btc_score:.1f}/10, reflecting global liquidity conditions.",
        f"",
    ]

    if cftc:
        net_long_markets = sum(
            1 for v in cftc.values() if v.get("net_speculative", 0) > 0
        )
        net_short_markets = sum(
            1 for v in cftc.values() if v.get("net_speculative", 0) < 0
        )
        lines.append(f"INSTITUTIONAL FLOWS: CFTC data shows {net_long_markets} markets " +
                     f"with net long speculative positions vs {net_short_markets} net short. ")

    lines.append(f"")
    lines.append(f"ASSET CLASS OUTLOOK: ")

    if usd_score >= 6.0:
        lines.append(f"FX: Favor USD-long pairs (short EUR/USD, GBP/USD). ")
    elif usd_score <= 4.0:
        lines.append(f"FX: Favor USD-short pairs (long EUR/USD, GBP/USD). ")
    else:
        lines.append(f"FX: USD outlook is neutral — look for relative value in crosses. ")

    if xau_score >= 6.0:
        lines.append(f"Gold: Favorable backdrop for longs. ")
    else:
        lines.append(f"Gold: Headwinds from real yields and USD. ")

    if btc_score >= 6.0:
        lines.append(f"Crypto: Bullish liquidity backdrop. ")
    else:
        lines.append(f"Crypto: Caution warranted in current macro environment. ")

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "local-synthesis",
        "provider": "local-fallback",
        "analysis": "".join(lines),
        "token_usage": {},
    }

    logger.info("Local synthesis generated")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with sample scoring results
    test_scores = {
        "base_scores": {
            "USD": 7.5, "EUR": 5.0, "GBP": 5.5, "JPY": 3.0,
            "XAU": 7.0, "BTC": 6.0, "ETH": 5.5,
        },
        "pairs": [
            {"name": "EUR/USD", "combined_bias": 3.5, "direction": "Bearish"},
            {"name": "GBP/USD", "combined_bias": 4.0, "direction": "Neutral"},
            {"name": "XAU/USD", "combined_bias": 7.0, "direction": "Bullish"},
        ],
        "total_pairs": 45,
        "total_extreme": 3,
        "extreme_setups": [
            {"name": "USD/JPY", "combined_bias": 8.5, "direction": "Strongly Bullish"},
        ],
        "cftc": {},
    }

    result = generate_macro_summary(test_scores, {"cftc": {}})
    print("\n" + result["analysis"])