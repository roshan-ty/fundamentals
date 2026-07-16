"""
Cross-Currency & Cross-Asset Pairing Math — Computes combined bias scores
for all FX pairs, metals, energy, and equity indices dynamically.
"""

import logging
from typing import Optional
from itertools import permutations

from backend.models.schemas import (
    CurrencyScores, PairBias, PairsData, TradeSetup, TradeSetupsData,
    clamp, direction_label,
)

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

# All FX currencies we track
FX_CURRENCIES = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "USD"]

# Special asset formulas
METALS = ["XAU", "XAG"]   # Gold, Silver
ENERGY = ["WTI"]          # Crude Oil
INDICES = ["SP500", "NAS100", "GER40"]

# FX pair naming
def fx_pair_name(base: str, quote: str) -> str:
    """Generate standard FX pair name."""
    return f"{base}/{quote}"


# ── Pair computation ──────────────────────────────────────────────────────────

def compute_pairs_bias(
    currency_scores: dict[str, CurrencyScores],
) -> PairsData:
    """
    Compute bias for all assets from individual currency scores.
    
    For FX pairs:
    Combined Pair Bias = 5 + (Base Avg Score - Quote Avg Score)
    Capped to [0, 10].
    
    For Metals:
    Metal Bias = 10 - USD Yield Score
    
    For Energy:
    Oil Bias = Global GDP Trend Score - (0.5 * USD Strength Score)
    
    For Indices:
    Equity Bias = GDP Score - (0.7 * Bond Yield Score)
    """
    pairs_data = PairsData()
    pairs_data.last_updated = ""

    # Build lookup: currency -> average_score
    avg_scores: dict[str, float] = {}
    macro_scores: dict[str, float] = {}
    yield_scores: dict[str, float] = {}

    for currency, cs in currency_scores.items():
        avg_scores[currency.upper()] = cs.average_score
        macro_scores[currency.upper()] = cs.macro_score
        yield_scores[currency.upper()] = cs.yield_momentum_score

    # ── 1. FX Pairs (all combinations) ───────────────────────────────────────
    for base, quote in permutations(FX_CURRENCIES, 2):
        base_score = avg_scores.get(base, 5.0)
        quote_score = avg_scores.get(quote, 5.0)

        combined = clamp(5.0 + (base_score - quote_score))
        direction = direction_label(combined)

        # Generate conclusion
        if direction in ("Strongly Bullish", "Bullish"):
            conclusion = (
                f"{base} fundamentals ({base_score:.1f}) significantly outrank "
                f"{quote} ({quote_score:.1f}). Bias favors long {base}/{quote}."
            )
        elif direction in ("Strongly Bearish", "Bearish"):
            conclusion = (
                f"{quote} fundamentals ({quote_score:.1f}) significantly outrank "
                f"{base} ({base_score:.1f}). Bias favors short {base}/{quote}."
            )
        else:
            conclusion = (
                f"{base} and {quote} fundamentals are balanced "
                f"({base_score:.1f} vs {quote_score:.1f}). Neutral bias."
            )

        pairs_data.pairs.append(
            PairBias(
                asset_class="FX",
                name=fx_pair_name(base, quote),
                base_currency=base,
                quote_currency=quote,
                base_score=round(base_score, 2),
                quote_score=round(quote_score, 2),
                combined_bias=round(combined, 2),
                direction=direction,
                conclusion=conclusion,
            )
        )

    # ── 2. Metals (Gold, Silver) ────────────────────────────────────────────
    usd_yield_score = yield_scores.get("USD", 5.0)
    for metal in METALS:
        metal_score = clamp(10.0 - usd_yield_score)
        direction = direction_label(metal_score)

        if direction in ("Strongly Bullish", "Bullish"):
            conclusion = f"Gold/Silver benefits from weak USD yield outlook. Favorable."
        elif direction in ("Strongly Bearish", "Bearish"):
            conclusion = f"High USD yields are pressuring metals. Unfavorable."
        else:
            conclusion = f"Neutral precious metals outlook relative to USD yields."

        pairs_data.pairs.append(
            PairBias(
                asset_class="METAL",
                name=f"XAU/USD" if metal == "XAU" else "XAG/USD",
                base_currency=metal,
                quote_currency="USD",
                base_score=round(metal_score, 2),
                quote_score=round(usd_yield_score, 2),
                combined_bias=round(metal_score, 2),
                direction=direction,
                conclusion=conclusion,
            )
        )

    # ── 3. Energy (Crude Oil) ────────────────────────────────────────────────
    usd_macro_score = macro_scores.get("USD", 5.0)
    usd_str = avg_scores.get("USD", 5.0)
    oil_score = clamp(usd_macro_score - (0.5 * usd_str))
    direction = direction_label(oil_score)

    if direction in ("Strongly Bullish", "Bullish"):
        conclusion = "Strong global GDP outlook and weak USD support crude oil."
    elif direction in ("Strongly Bearish", "Bearish"):
        conclusion = "Weak global GDP outlook and strong USD pressure crude oil."
    else:
        conclusion = "Crude oil outlook is neutral based on macro factors."

    pairs_data.pairs.append(
        PairBias(
            asset_class="ENERGY",
            name="WTI/USD",
            base_currency="WTI",
            quote_currency="USD",
            base_score=round(oil_score, 2),
            quote_score=round(usd_str, 2),
            combined_bias=round(oil_score, 2),
            direction=direction,
            conclusion=conclusion,
        )
    )

    # ── 4. Equity Indices ────────────────────────────────────────────────────
    for idx in INDICES:
        usd_gdp_score = macro_scores.get("USD", 5.0)
        usd_yld = yield_scores.get("USD", 5.0)
        idx_score = clamp(usd_gdp_score - (0.7 * usd_yld))
        direction = direction_label(idx_score)

        idx_name = {
            "SP500": "US500",
            "NAS100": "US100",
            "GER40": "GER40",
        }.get(idx, idx)

        if direction in ("Strongly Bullish", "Bullish"):
            conclusion = f"Strong GDP growth and low yields support {idx_name}."
        elif direction in ("Strongly Bearish", "Bearish"):
            conclusion = f"High yields compressing multiples for {idx_name}."
        else:
            conclusion = f"{idx_name} outlook is neutral."

        pairs_data.pairs.append(
            PairBias(
                asset_class="INDEX",
                name=idx_name,
                base_currency=idx,
                quote_currency="",
                base_score=round(idx_score, 2),
                quote_score=0.0,
                combined_bias=round(idx_score, 2),
                direction=direction,
                conclusion=conclusion,
            )
        )

    logger.info("Pairs: Computed %d pairs/assets.", len(pairs_data.pairs))
    return pairs_data


def compute_trade_setups(pairs_data: PairsData) -> TradeSetupsData:
    """
    Extract highest-probability setups where bias is extreme.
    Filters for Combined Bias >= 8.0 (Strongly Bullish) or <= 2.0 (Strongly Bearish).
    """
    setups_data = TradeSetupsData()
    setups_data.last_updated = pairs_data.last_updated

    for pair in pairs_data.pairs:
        if pair.combined_bias >= 8.0 or pair.combined_bias <= 2.0:
            direction = "LONG" if pair.combined_bias >= 8.0 else "SHORT"
            setups_data.setups.append(
                TradeSetup(
                    asset_name=pair.name,
                    direction=direction,
                    combined_bias=pair.combined_bias,
                    fundamental_consensus=pair.conclusion,
                )
            )

    # Sort by absolute distance from neutral (5.0), descending
    setups_data.setups.sort(
        key=lambda s: abs(s.combined_bias - 5.0),
        reverse=True,
    )

    logger.info("Trade Setups: %d high-probability setups found.", len(setups_data.setups))
    return setups_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from backend.models.schemas import CurrencyScores

    # Test with sample scores
    scores = {
        "EUR": CurrencyScores(currency="EUR", macro_score=4.0, event_surprise_score=5.0, yield_momentum_score=5.0, cftc_sentiment_score=6.0, average_score=5.0),
        "GBP": CurrencyScores(currency="GBP", macro_score=5.0, event_surprise_score=6.0, yield_momentum_score=6.0, cftc_sentiment_score=6.0, average_score=5.75),
        "JPY": CurrencyScores(currency="JPY", macro_score=5.0, event_surprise_score=4.0, yield_momentum_score=4.0, cftc_sentiment_score=3.0, average_score=4.0),
        "AUD": CurrencyScores(currency="AUD", macro_score=5.0, event_surprise_score=5.0, yield_momentum_score=5.0, cftc_sentiment_score=5.0, average_score=5.0),
        "CAD": CurrencyScores(currency="CAD", macro_score=5.0, event_surprise_score=5.0, yield_momentum_score=5.0, cftc_sentiment_score=5.0, average_score=5.0),
        "CHF": CurrencyScores(currency="CHF", macro_score=5.0, event_surprise_score=5.0, yield_momentum_score=5.0, cftc_sentiment_score=5.0, average_score=5.0),
        "USD": CurrencyScores(currency="USD", macro_score=7.0, event_surprise_score=7.0, yield_momentum_score=7.0, cftc_sentiment_score=7.0, average_score=7.0),
    }

    pairs = compute_pairs_bias(scores)
    print(f"Pairs: {len(pairs.pairs)} total.")
    for p in pairs.pairs[:5]:
        print(f"  {p.asset_class:7} {p.name:10} Bias={p.combined_bias:5.2f} {p.direction:20}")

    setups = compute_trade_setups(pairs)
    print(f"\nTrade Setups: {len(setups.setups)} high-probability.")
    for s in setups.setups[:5]:
        print(f"  {s.asset_name:10} {s.direction:6} Bias={s.combined_bias:5.2f}")