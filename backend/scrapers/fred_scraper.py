"""
Pipeline A: FRED API — Fetch macro-economic series (GDP, CPI, PCE, UNRATE, FEDFUNDS).
"""

import os
import json
import logging
from datetime import datetime, date, timezone
from typing import Optional
import requests

from backend.models.schemas import FredSeries, FredData

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

SERIES_MAP = {
    "GDPC1":       "Real Gross Domestic Product",
    "CPILFESL":    "Core CPI (All Items Less Food & Energy)",
    "PCEPILFE":    "Core PCE",
    "UNRATE":      "Unemployment Rate",
    "FEDFUNDS":    "Federal Funds Effective Rate",
}

UNIT_MAP: dict[str, str] = {
    "GDPC1":    "Billions of Chained 2017 Dollars",
    "CPILFESL": "Index 1982-1984=100",
    "PCEPILFE": "Index 2017=100",
    "UNRATE":   "Percent",
    "FEDFUNDS": "Percent",
}

# ── Main scraper ──────────────────────────────────────────────────────────────

def fetch_fred_data() -> FredData:
    """
    Fetch all configured FRED series from the API.
    Returns a FredData container.
    """
    fred_data = FredData()
    fred_data.last_updated = datetime.now(timezone.utc).isoformat()

    if not FRED_API_KEY:
        logger.error("FRED_API_KEY not set. Skipping FRED pipeline.")
        return fred_data

    for series_id, series_name in SERIES_MAP.items():
        try:
            params = {
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 120,  # ~10 years of monthly data
            }
            resp = requests.get(FRED_BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            observations = data.get("observations", [])
            for obs in observations:
                obs_date = obs.get("date", "")
                obs_value_str = obs.get("value", ".")
                if obs_value_str == "." or obs_value_str == "":
                    continue
                try:
                    obs_value = float(obs_value_str)
                except ValueError:
                    continue

                fred_data.series.append(
                    FredSeries(
                        series_id=series_id,
                        series_name=series_name,
                        date=obs_date,
                        value=obs_value,
                        unit=UNIT_MAP.get(series_id, ""),
                    )
                )

            logger.info("FRED: Fetched %d observations for %s", len(observations), series_id)

        except requests.RequestException as e:
            status_code = ""
            if hasattr(e, 'response') and e.response is not None:
                status_code = f" (HTTP {e.response.status_code})"
            logger.warning("FRED: Failed to fetch %s%s: %s", series_id, status_code, e)
            continue
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.warning("FRED: Failed to parse %s response: %s", series_id, e)
            continue

    return fred_data


def get_latest_fred_value(series_id: str, fred_data: FredData) -> Optional[float]:
    """
    Get the most recent value for a given series_id from fetched data.
    """
    for s in fred_data.series:
        if s.series_id == series_id:
            return s.value
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = fetch_fred_data()
    print(f"Fetched {len(data.series)} observations from FRED.")
    for s in data.series[:10]:
        print(f"  {s.series_id} | {s.date} | {s.value}")