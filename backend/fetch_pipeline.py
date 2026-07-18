#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Master Pipeline Orchestrator
Executed by GitHub Actions every 24 hours.

Pipeline Sequence:
  1. parsers.collect_all_data() — Fetch raw data from all 8+ sources
  2. scorer.score_all() — Compute base asset scores + 200+ cross-pairs
  3. ai_analyst.generate_macro_summary() — xAI macro summary
  4. Export all results to /public/data/ as static JSON files
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env for local development
try:
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
except ImportError:
    pass

from backend.parsers import collect_all_data
from backend.scorer import score_all
from backend.ai_analyst import generate_macro_summary

logger = logging.getLogger(__name__)

# ── Output Directory ───────────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "public", "data",
)


def ensure_output_dir() -> None:
    """Create output directory if it doesn't exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def write_json(filename: str, data: Any) -> str:
    """Write data to JSON file in the output directory."""
    ensure_output_dir()
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    size = os.path.getsize(filepath)
    logger.info("Written: %s (%d bytes)", filepath, size)
    return filepath


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

def run_pipeline() -> dict[str, Any]:
    """
    Execute the complete data pipeline:
    1. Collect raw data from all sources
    2. Compute scores for all assets and pairs
    3. Generate AI macro summary
    4. Export all results to /public/data/
    """
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 70)
    logger.info(" BULLS & BEARS FUNDAMENTALS — PIPELINE EXECUTION")
    logger.info("=" * 70)

    # ── Step 1: Data Collection ────────────────────────────────────────────────
    logger.info("\n[STEP 1/4] Collecting raw data from all sources...")
    collected_data = collect_all_data()
    logger.info("✓ Data collection complete: %d categories", len(collected_data))

    # ── Step 2: Scoring ────────────────────────────────────────────────────────
    logger.info("\n[STEP 2/4] Computing fundamental scores...")
    scoring_results = score_all(collected_data)
    logger.info("✓ Scoring complete: %d base assets, %d pairs",
                 len(scoring_results["base_scores"]),
                 scoring_results["total_pairs"])

    # ── Step 3: AI Analysis ────────────────────────────────────────────────────
    logger.info("\n[STEP 3/4] Generating AI macro summary...")
    ai_insights = generate_macro_summary(scoring_results, collected_data)
    logger.info("✓ AI analysis generated (provider: %s)", ai_insights["provider"])

    # ── Step 4: Export All ─────────────────────────────────────────────────────
    logger.info("\n[STEP 4/4] Exporting to /public/data/...")

    # 4a: Calendar data — economic events with surprise ratios
    calendar_events = _extract_calendar_events(collected_data)
    write_json("calendar.json", {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "events": calendar_events,
        "total_events": len(calendar_events),
    })

    # 4b: Macro data — FRED historical series
    macro_data = collected_data.get("fred", {})
    write_json("macro_data.json", {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "series": macro_data,
    })

    # 4c: CFTC report — institutional positioning
    cftc_data = collected_data.get("cftc", {})
    write_json("cftc_report.json", {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "positions": cftc_data,
        "total_markets": len(cftc_data),
    })

    # 4d: Master bias — complete scored matrix (200+ pairs)
    write_json("master_bias.json", {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "base_scores": scoring_results["base_scores"],
        "total_base_assets": len(scoring_results["base_scores"]),
        "pairs": scoring_results["pairs"],
        "total_pairs": scoring_results["total_pairs"],
        "extreme_setups": scoring_results["extreme_setups"],
        "total_extreme": scoring_results["total_extreme"],
        "summary": {
            "bullish_count": sum(1 for p in scoring_results["pairs"]
                                  if p["combined_bias"] >= 6.0),
            "bearish_count": sum(1 for p in scoring_results["pairs"]
                                  if p["combined_bias"] <= 4.0),
            "neutral_count": sum(1 for p in scoring_results["pairs"]
                                  if 4.0 < p["combined_bias"] < 6.0),
        },
    })

    # 4e: AI insights
    write_json("ai_insights.json", ai_insights)

    # ── Pipeline Summary ───────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info("\n" + "=" * 70)
    logger.info(" PIPELINE COMPLETE — %.2f seconds", elapsed)
    logger.info("=" * 70)
    logger.info(" Output files:")
    logger.info("   /public/data/calendar.json      — %d events", len(calendar_events))
    logger.info("   /public/data/macro_data.json     — %d series", len(macro_data))
    logger.info("   /public/data/cftc_report.json    — %d markets", len(cftc_data))
    logger.info("   /public/data/master_bias.json    — %d pairs", scoring_results["total_pairs"])
    logger.info("   /public/data/ai_insights.json    — 1 file")
    logger.info("=" * 70)

    return {
        "status": "success",
        "elapsed_seconds": round(elapsed, 2),
        "files_written": 5,
        "total_pairs": scoring_results["total_pairs"],
        "extreme_setups": scoring_results["total_extreme"],
    }


def _extract_calendar_events(collected_data: dict[str, Any]) -> list[dict]:
    """
    Extract and normalize calendar events from Forex Factory JSON feed.
    """
    events: list[dict] = []

    # From Forex Factory
    ff_events = collected_data.get("forex_factory_calendar", [])
    for ev in ff_events:
        try:
            events.append({
                "source": ev.get("source", "ForexFactory"),
                "date": ev.get("date", ""),
                "currency": ev.get("currency", ""),
                "event": ev.get("event", ""),
                "forecast": _safe_float(ev.get("forecast")),
                "actual": _safe_float(ev.get("actual")),
                "previous": _safe_float(ev.get("previous")),
                "impact": ev.get("impact", "low"),
            })
        except (KeyError, ValueError):
            continue

    # Sort by date descending, most recent first
    events.sort(key=lambda e: e.get("date", ""), reverse=True)

    logger.info("Calendar: %d events extracted from Forex Factory", len(events))
    return events


def _safe_float(val: Any) -> Optional[float]:
    """Safely convert a value to float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip().replace(",", "").replace("%", "").replace("$", "")
        if val in ("", "-", "N/A", "."):
            return None
        try:
            return float(val)
        except ValueError:
            return None
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    summary = run_pipeline()
    print(f"\nPipeline Status: {summary['status']}")
    print(f"Elapsed: {summary['elapsed_seconds']}s")
    print(f"Files Written: {summary['files_written']}")
    print(f"Total Pairs Scored: {summary['total_pairs']}")
    print(f"Extreme Setups: {summary['extreme_setups']}")