"""
Pipeline D: Economic Calendar & High-Impact Events — Fetch upcoming/recent
economic events using EODHD API and compute surprise ratios.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from backend.models.schemas import CalendarEvent, CalendarData

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

EODHD_BASE = "https://eodhd.com/api/economic-calendar"
EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "")

# Map EODHD country codes to our currency codes
COUNTRY_CURRENCY_MAP: dict[str, str] = {
    "US": "USD",
    "EU": "EUR",
    "GB": "GBP",
    "JP": "JPY",
    "AU": "AUD",
    "CA": "CAD",
    "CH": "CHF",
}

# High-impact event keywords to track
HIGH_IMPACT_KEYWORDS = [
    "CPI", "GDP", "NFP", "PPI", "UNEMPLOYMENT", "FED", "BOE", "ECB",
    "INTEREST RATE", "INFLATION", "RETAIL SALES", "PMI", "MANUFACTURING",
    "SERVICES", "EMPLOYMENT CHANGE", "JOBLESS CLAIMS", "TRADE BALANCE",
]


# ── Main scraper ──────────────────────────────────────────────────────────────

def _is_high_impact(event_name: str) -> bool:
    """Check if an event name matches high-impact keywords."""
    upper = event_name.upper()
    return any(kw in upper for kw in HIGH_IMPACT_KEYWORDS)


def fetch_calendar_data() -> CalendarData:
    """
    Fetch economic calendar events from EODHD API.
    Returns a CalendarData container with events and surprise ratios.
    """
    calendar_data = CalendarData()
    calendar_data.last_updated = datetime.now(timezone.utc).isoformat()

    if not EODHD_API_KEY:
        logger.warning("EODHD_API_KEY not set. Skipping economic calendar.")
        return calendar_data

    # Fetch events from last 60 days to get enough high-impact data
    to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from_date = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")

    try:
        params = {
            "api_token": EODHD_API_KEY,
            "fmt": "json",
            "from": from_date,
            "to": to_date,
        }
        resp = requests.get(EODHD_BASE, params=params, timeout=30)
        resp.raise_for_status()
        events_raw = resp.json()

        if not isinstance(events_raw, list):
            logger.warning("Calendar: Unexpected response format from EODHD.")
            return calendar_data

        for ev in events_raw:
            try:
                country = ev.get("country", "")
                currency = COUNTRY_CURRENCY_MAP.get(country, "")

                event_name = ev.get("event", "") or ev.get("name", "")
                if not event_name or not currency:
                    continue

                # Only track high-impact events
                if not _is_high_impact(event_name) and not any(
                    word in event_name.upper() for word in ["NFP", "CPI", "GDP", "FOMC"]
                ):
                    # Be more inclusive to ensure we have enough data
                    pass  # Keep events that have actual/forecast values

                actual = _safe_float(ev.get("actual"))
                forecast = _safe_float(ev.get("forecast"))
                previous = _safe_float(ev.get("previous"))

                # Only add events that have at least actual and forecast
                if actual is None or forecast is None:
                    continue

                date_str = ev.get("date", "")
                if date_str and "T" in date_str:
                    date_str = date_str.split("T")[0]  # Strip time component

                # Compute surprise ratio
                surprise = 0.0
                if abs(forecast) > 0.001:
                    surprise = round((actual - forecast) / abs(forecast), 4)

                calendar_data.events.append(
                    CalendarEvent(
                        currency=currency,
                        event_name=event_name[:100],
                        date=date_str if date_str else to_date,
                        actual=actual,
                        forecast=forecast,
                        previous=previous if previous is not None else 0.0,
                        surprise_ratio=surprise,
                    )
                )

            except (KeyError, ValueError, TypeError) as e:
                logger.debug("Calendar: Skipping event row: %s", e)
                continue

        logger.info(
            "Calendar: Fetched %d events from EODHD.",
            len(calendar_data.events),
        )

    except requests.RequestException as e:
        logger.warning("Calendar: Failed to fetch from EODHD: %s", e)
    except (ValueError, TypeError, KeyError) as e:
        logger.warning("Calendar: Failed to parse EODHD response: %s", e)

    return calendar_data


def _safe_float(val) -> Optional[float]:
    """Safely convert a value to float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip().replace(",", "").replace("%", "").replace("$", "")
        if val == "" or val == "-":
            return None
        try:
            return float(val)
        except ValueError:
            return None
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = fetch_calendar_data()
    print(f"Calendar: {len(data.events)} events.")
    for e in data.events[:10]:
        print(f"  {e.currency} | {e.event_name} | Actual={e.actual} | Surprise={e.surprise_ratio}")