#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Forex Factory Economic Calendar Scraper
Scrapes the full Forex Factory calendar while bypassing Cloudflare.

Uses cloudscraper + curl_cffi with browser impersonation, plus a
BeautifulSoup fallback. Exports normalized events to public/data/calendar.json.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Cloudflare bypass clients ──────────────────────────────────────────────────
try:
    import cloudscraper
    _HAS_CLOUDSCRAPER = True
except ImportError:
    _HAS_CLOUDSCRAPER = False

try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:
    _HAS_CURL_CFFI = False

FF_CALENDAR_URL = "https://www.forexfactory.com/calendar"

# Country code mapping from Forex Factory country names to our currency codes
FF_COUNTRY_MAP: dict[str, str] = {
    "USD": "USD", "EUR": "EUR", "GBP": "GBP", "JPY": "JPY",
    "AUD": "AUD", "CAD": "CAD", "CHF": "CHF", "NZD": "NZD",
    "CNY": "CNY", "HKD": "HKD", "SGD": "SGD", "MXN": "MXN",
    "NOK": "NOK", "SEK": "SEK", "TRY": "TRY", "ZAR": "ZAR",
    "INR": "INR", "BRL": "BRL", "RUB": "RUB", "KRW": "KRW",
}

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _safe_float(val: Any) -> Optional[float]:
    """Safely convert a value to float, handling K/M/B suffixes and symbols."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip().replace(",", "").replace("%", "").replace("$", "")
        if val in ("", "-", "N/A", ".", "--"):
            return None
        multiplier = 1.0
        if val and val[-1] in ("K", "k"):
            multiplier = 1_000.0
            val = val[:-1]
        elif val and val[-1] in ("M", "m"):
            multiplier = 1_000_000.0
            val = val[:-1]
        elif val and val[-1] in ("B", "b"):
            multiplier = 1_000_000_000.0
            val = val[:-1]
        try:
            return float(val) * multiplier
        except ValueError:
            return None
    return None


def _fetch_html(url: str) -> Optional[str]:
    """Fetch HTML with Cloudflare bypass strategies."""
    # Strategy 1: cloudscraper
    if _HAS_CLOUDSCRAPER:
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
            resp = scraper.get(url, headers=BROWSER_HEADERS, timeout=45)
            if resp.status_code == 200 and "calendar" in resp.text.lower():
                logger.info("Calendar: fetched via cloudscraper (%d bytes)", len(resp.text))
                return resp.text
        except Exception as e:
            logger.warning("Calendar: cloudscraper failed: %s", e)

    # Strategy 2: curl_cffi with browser impersonation
    if _HAS_CURL_CFFI:
        try:
            resp = curl_requests.get(
                url,
                headers=BROWSER_HEADERS,
                impersonate="chrome120",
                timeout=45,
            )
            if resp.status_code == 200 and "calendar" in resp.text.lower():
                logger.info("Calendar: fetched via curl_cffi (%d bytes)", len(resp.text))
                return resp.text
        except Exception as e:
            logger.warning("Calendar: curl_cffi failed: %s", e)

    # Strategy 3: plain requests with browser headers
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=45)
        if resp.status_code == 200 and "calendar" in resp.text.lower():
            logger.info("Calendar: fetched via requests (%d bytes)", len(resp.text))
            return resp.text
    except Exception as e:
        logger.warning("Calendar: requests failed: %s", e)

    return None


def _parse_impact(impact_class: str) -> str:
    """Map Forex Factory impact CSS class to high/med/low."""
    if "high" in impact_class:
        return "high"
    if "med" in impact_class or "medium" in impact_class:
        return "medium"
    return "low"


def _parse_ff_calendar(html: str) -> list[dict]:
    """Parse the Forex Factory calendar HTML table into normalized events."""
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []

    # Forex Factory uses a table with class 'calendar__table'
    table = soup.find("table", class_=re.compile("calendar__table"))
    if not table:
        logger.warning("Calendar: No calendar table found in HTML.")
        return events

    current_date = ""
    rows = table.find_all("tr", class_=re.compile("calendar__row"))

    for row in rows:
        try:
            # Date cell
            date_cell = row.find("td", class_=re.compile("calendar__date"))
            if date_cell:
                date_text = date_cell.get_text(strip=True)
                if date_text:
                    current_date = date_text

            # Time cell
            time_cell = row.find("td", class_=re.compile("calendar__time"))
            time_text = time_cell.get_text(strip=True) if time_cell else ""

            # Currency cell
            currency_cell = row.find("td", class_=re.compile("calendar__currency"))
            currency_text = currency_cell.get_text(strip=True) if currency_cell else ""
            currency = FF_COUNTRY_MAP.get(currency_text.upper(), "")

            # Event cell
            event_cell = row.find("td", class_=re.compile("calendar__event"))
            event_text = event_cell.get_text(strip=True) if event_cell else ""

            # Impact cell
            impact_cell = row.find("td", class_=re.compile("calendar__impact"))
            impact_class = impact_cell.get("class", []) if impact_cell else []
            impact = _parse_impact(" ".join(impact_class))

            # Actual / Forecast / Previous cells
            actual_cell = row.find("td", class_=re.compile("calendar__actual"))
            forecast_cell = row.find("td", class_=re.compile("calendar__forecast"))
            previous_cell = row.find("td", class_=re.compile("calendar__previous"))

            actual_text = actual_cell.get_text(strip=True) if actual_cell else ""
            forecast_text = forecast_cell.get_text(strip=True) if forecast_cell else ""
            previous_text = previous_cell.get_text(strip=True) if previous_cell else ""

            if not event_text or not currency:
                continue

            # Build ISO date
            event_date = current_date
            if time_text:
                event_date = f"{current_date} {time_text}"

            events.append({
                "source": "ForexFactory",
                "date": event_date,
                "currency": currency,
                "event": event_text[:120],
                "forecast": _safe_float(forecast_text),
                "actual": _safe_float(actual_text),
                "previous": _safe_float(previous_text),
                "impact": impact,
            })
        except Exception as e:
            logger.debug("Calendar: Skipping row: %s", e)
            continue

    logger.info("Calendar: %d events parsed from Forex Factory HTML", len(events))
    return events


def fetch_ff_calendar_html() -> list[dict]:
    """Fetch and parse the full Forex Factory calendar."""
    html = _fetch_html(FF_CALENDAR_URL)
    if not html:
        logger.warning("Calendar: Failed to fetch Forex Factory HTML.")
        return []
    return _parse_ff_calendar(html)


def export_calendar_json(events: list[dict], output_path: str) -> str:
    """Write calendar events to a JSON file."""
    payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "events": events,
        "total_events": len(events),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("Calendar: Exported %d events to %s", len(events), output_path)
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    events = fetch_ff_calendar_html()
    print(f"Fetched {len(events)} calendar events")
    for ev in events[:5]:
        print(f"  {ev['date']} | {ev['currency']} | {ev['event']} | {ev['impact']}")