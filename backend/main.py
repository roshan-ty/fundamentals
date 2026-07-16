#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Main Orchestrator
Runs all data pipelines, computes scores, and exports JSON databases.
"""

import os
import sys
import logging
from datetime import datetime, timezone

# Load .env file if present (local development)
try:
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        logging.info("Loaded .env from %s", dotenv_path)
except ImportError:
    logging.warning("python-dotenv not installed — relying on environment variables.")

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Imports ──────────────────────────────────────────────────────────────────

from backend.scrapers.fred_scraper import fetch_fred_data
from backend.scrapers.cftc_scraper import fetch_cftc_data
from backend.scrapers.yield_scraper import fetch_yield_data
from backend.scrapers.calendar_scraper import fetch_calendar_data
from backend.scrapers.news_scraper import fetch_news_data

from backend.scoring.macro_score import compute_macro_score
from backend.scoring.event_surprise import compute_event_surprise_score
from backend.scoring.yield_score import compute_yield_score
from backend.scoring.cftc_sentiment import compute_cftc_sentiment_score
from backend.scoring.pair_math import compute_pairs_bias, compute_trade_setups

from backend.models.schemas import CurrencyScores, clamp

from backend.exporters.json_exporter import export_all

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ── Constants ────────────────────────────────────────────────────────────────

TARGET_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF"]


# ── Pipeline Execution ───────────────────────────────────────────────────────

def run_pipeline() -> None:
    """
    Execute the full data pipeline:
    1. Fetch raw data from all sources
    2. Compute individual scores
    3. Compute pair biases and trade setups
    4. Export all to JSON
    """
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("Bulls & Bears Fundamentals — Pipeline Start")
    logger.info("=" * 60)

    # ── Step 1: Fetch raw data ───────────────────────────────────────────────
    logger.info("\n[Step 1/5] Fetching raw data...")

    fred_data = fetch_fred_data()
    logger.info("  ✓ FRED: %d observations", len(fred_data.series))

    cftc_data = fetch_cftc_data()
    logger.info("  ✓ CFTC: %d markets", len(cftc_data.positions))

    yield_data = fetch_yield_data()
    logger.info("  ✓ Yields: %d instruments", len(yield_data.entries))

    calendar_data = fetch_calendar_data()
    logger.info("  ✓ Calendar: %d events", len(calendar_data.events))

    news_data = fetch_news_data()
    logger.info("  ✓ News: %d articles", len(news_data.articles))

    # ── Step 2: Compute individual scores ────────────────────────────────────
    logger.info("\n[Step 2/5] Computing component scores...")

    macro_scores = compute_macro_score(fred_data)
    logger.info("  ✓ Macro scores computed")

    event_scores = compute_event_surprise_score(calendar_data)
    logger.info("  ✓ Event surprise scores computed")

    yield_scores_val = compute_yield_score(yield_data)
    logger.info("  ✓ Yield momentum scores computed")

    cftc_scores = compute_cftc_sentiment_score(cftc_data)
    # Derive USD CFTC score from inverse of non-USD currency positions
    # Since there is no "USD" futures contract, we take the average of
    # EUR, GBP, JPY, AUD, CAD, CHF scores and invert it (10 - avg)
    # A strong EUR/GBP/etc. bullish position = USD bearish sentiment
    non_usd_currencies = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF"]
    usd_cftc_derived = 5.0
    non_usd_scores = [cftc_scores.get(c, 5.0) for c in non_usd_currencies]
    if non_usd_scores:
        avg_non_usd = sum(non_usd_scores) / len(non_usd_scores)
        usd_cftc_derived = clamp(10.0 - avg_non_usd)
    cftc_scores["USD"] = usd_cftc_derived
    logger.info("  ✓ CFTC sentiment scores computed (USD derived from non-USD inverse: %.2f)", usd_cftc_derived)

    # ── Step 3: Aggregate into CurrencyScores ────────────────────────────────
    logger.info("\n[Step 3/5] Aggregating currency scores...")

    currency_scores: dict[str, CurrencyScores] = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for currency in TARGET_CURRENCIES:
        macro = macro_scores.get(currency, 5.0)
        event = event_scores.get(currency, 5.0)
        yld = yield_scores_val.get(currency, 5.0)
        cftc = cftc_scores.get(currency, 5.0)

        avg = clamp((macro + event + yld + cftc) / 4.0)

        currency_scores[currency] = CurrencyScores(
            currency=currency,
            macro_score=macro,
            event_surprise_score=event,
            yield_momentum_score=yld,
            cftc_sentiment_score=cftc,
            average_score=avg,
            updated_at=now_iso,
        )

        logger.info(
            "  %s: Macro=%.1f Event=%.1f Yield=%.1f CFTC=%.1f → Avg=%.2f",
            currency, macro, event, yld, cftc, avg,
        )

    # ── Step 4: Compute pairs and trade setups ───────────────────────────────
    logger.info("\n[Step 4/5] Computing pair biases and trade setups...")

    pairs_data = compute_pairs_bias(currency_scores)
    logger.info("  ✓ %d pairs/assets computed", len(pairs_data.pairs))
    pairs_data.last_updated = now_iso

    setups_data = compute_trade_setups(pairs_data)
    setups_data.last_updated = now_iso
    logger.info("  ✓ %d trade setups identified", len(setups_data.setups))

    # ── Step 5: Export to JSON ───────────────────────────────────────────────
    logger.info("\n[Step 5/5] Exporting to JSON...")

    export_all(
        fred_data=fred_data,
        cftc_data=cftc_data,
        yield_data=yield_data,
        calendar_data=calendar_data,
        news_data=news_data,
        currency_scores=currency_scores,
        pairs_data=pairs_data,
        setups_data=setups_data,
    )
    logger.info("  ✓ Export complete")

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info("\n" + "=" * 60)
    logger.info("Pipeline completed in %.2f seconds.", elapsed)
    logger.info("=" * 60)


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_pipeline()