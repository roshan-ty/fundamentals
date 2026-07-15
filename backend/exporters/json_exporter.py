"""
JSON Exporter — Serializes all data models to JSON files in the frontend/data/ directory.
"""

import json
import os
import logging
from dataclasses import asdict
from typing import Any

from backend.models.schemas import (
    FredData, CftcData, YieldData, CalendarData, NewsData,
    CurrencyScores, PairsData, TradeSetupsData,
)

logger = logging.getLogger(__name__)

# Output directory relative to project root
FRONTEND_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend", "data",
)


def _ensure_dir(path: str) -> None:
    """Ensure the output directory exists."""
    os.makedirs(path, exist_ok=True)


def _write_json(filename: str, data: Any) -> None:
    """Write data to a JSON file in the frontend data directory."""
    _ensure_dir(FRONTEND_DATA_DIR)
    filepath = os.path.join(FRONTEND_DATA_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info("Exported: %s (%d bytes)", filename, os.path.getsize(filepath))
    except (IOError, OSError) as e:
        logger.error("Failed to write %s: %s", filename, e)


def _dataclass_to_dict(obj: Any) -> dict:
    """Convert a dataclass instance to a dict, handling nested dataclasses."""
    return json.loads(json.dumps(asdict(obj), default=str))


# ── Individual exporters ──────────────────────────────────────────────────────

def export_fred_data(fred_data: FredData) -> None:
    """Export FRED data to JSON."""
    _write_json("fred_historical.json", _dataclass_to_dict(fred_data))


def export_cftc_data(cftc_data: CftcData) -> None:
    """Export CFTC data to JSON."""
    _write_json("cftc_historical.json", _dataclass_to_dict(cftc_data))


def export_yield_data(yield_data: YieldData) -> None:
    """Export yield data to JSON."""
    _write_json("yields.json", _dataclass_to_dict(yield_data))


def export_calendar_data(calendar_data: CalendarData) -> None:
    """Export calendar data to JSON."""
    _write_json("calendar_surprises.json", _dataclass_to_dict(calendar_data))


def export_news_data(news_data: NewsData) -> None:
    """Export news data to JSON."""
    _write_json("news_feed.json", _dataclass_to_dict(news_data))


def export_currency_scores(scores: dict[str, CurrencyScores]) -> None:
    """Export individual currency scores to JSON."""
    scores_dict = {
        currency: _dataclass_to_dict(cs)
        for currency, cs in scores.items()
    }
    _write_json("scores.json", scores_dict)


def export_pairs_bias(pairs_data: PairsData) -> None:
    """Export pairs bias data to JSON."""
    _write_json("pairs_bias.json", _dataclass_to_dict(pairs_data))


def export_trade_setups(setups_data: TradeSetupsData) -> None:
    """Export trade setups to JSON."""
    _write_json("trade_setups.json", _dataclass_to_dict(setups_data))


def export_usd_bias(currency_scores: dict[str, CurrencyScores]) -> None:
    """Export a simplified USD bias summary."""
    usd = currency_scores.get("USD")
    if usd:
        _write_json("usd_bias.json", {
            "currency": "USD",
            "average_score": usd.average_score,
            "macro_score": usd.macro_score,
            "event_surprise_score": usd.event_surprise_score,
            "yield_momentum_score": usd.yield_momentum_score,
            "cftc_sentiment_score": usd.cftc_sentiment_score,
            "updated_at": usd.updated_at,
        })


# ── Bulk export ───────────────────────────────────────────────────────────────

def export_all(
    fred_data: FredData,
    cftc_data: CftcData,
    yield_data: YieldData,
    calendar_data: CalendarData,
    news_data: NewsData,
    currency_scores: dict[str, CurrencyScores],
    pairs_data: PairsData,
    setups_data: TradeSetupsData,
) -> None:
    """Export all data to JSON files."""
    logger.info("Exporting all data to %s", FRONTEND_DATA_DIR)

    export_fred_data(fred_data)
    export_cftc_data(cftc_data)
    export_yield_data(yield_data)
    export_calendar_data(calendar_data)
    export_news_data(news_data)
    export_currency_scores(currency_scores)
    export_pairs_bias(pairs_data)
    export_trade_setups(setups_data)
    export_usd_bias(currency_scores)

    logger.info("Export complete. All files written to %s", FRONTEND_DATA_DIR)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test with empty data
    export_all(
        fred_data=FredData(),
        cftc_data=CftcData(),
        yield_data=YieldData(),
        calendar_data=CalendarData(),
        news_data=NewsData(),
        currency_scores={},
        pairs_data=PairsData(),
        setups_data=TradeSetupsData(),
    )
    print("Test export complete.")