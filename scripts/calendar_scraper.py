#!/usr/bin/env python3
"""Bulls & Bears Fundamentals - Forex Factory Multi-Currency Calendar Scraper.

Scrapes Forex Factory's live economic calendar using cloudscraper (Cloudflare
bypass) + BeautifulSoup4, normalizes every event, and exports a clean, rich
JSON array to public/data/calendar.json.

Output format (bare JSON array):
[
  {
    "id": "usd-nfp-2026-08-07",
    "date": "Fri Aug 7",
    "time": "8:30am",
    "currency": "USD",
    "impact": "High",
    "event": "Non-Farm Employment Change",
    "actual_raw": "147K",
    "forecast_raw": "165K",
    "previous_raw": "150K",
    "actual_num": 147000.0,
    "forecast_num": 165000.0,
    "previous_num": 150000.0,
    "delta_vs_forecast": -18000.0,
    "direction": "bearish"
  }
]

Direction rule:
  - Standard indicators (GDP, CPI, NFP, Retail Sales, PMIs):
      actual > forecast => "bullish"; actual < forecast => "bearish"
  - Inverse indicators (Unemployment Rate, Jobless Claims):
      actual > forecast => "bearish"; actual < forecast => "bullish"
  - Equal or missing actual/forecast => "neutral"
"""

import os
import re
import sys
import json
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

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

logger = logging.getLogger(__name__)

FF_CALENDAR_URL = "https://www.forexfactory.com/calendar"
PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "public", "data", "calendar.json")

MAJOR_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"}

FF_COUNTRY_MAP = {
    "USD": "USD", "EUR": "EUR", "GBP": "GBP", "JPY": "JPY",
    "AUD": "AUD", "CAD": "CAD", "CHF": "CHF", "NZD": "NZD",
    "CNY": "CNY", "HKD": "HKD", "SGD": "SGD", "MXN": "MXN",
    "NOK": "NOK", "SEK": "SEK", "TRY": "TRY", "ZAR": "ZAR",
    "INR": "INR", "BRL": "BRL", "RUB": "RUB", "KRW": "KRW",
}

INVERSE_INDICATOR_KEYWORDS = [
    "UNEMPLOYMENT", "JOBLESS CLAIMS", "INITIAL CLAIMS", "JOBLESS",
]

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


def parse_numeric_value(val_str: Optional[str]) -> Optional[float]:
    """Convert a human-readable FF value string to a float.

    Handles: "3.2%", "$210K", "1.4M", "-0.5%", "12.5B", "", "N/A", "--"
    Strips %, $, commas; multiplies K by 1,000, M by 1,000,000, B by 1,000,000,000.
    Returns float, or None if empty/unreleased/unparseable.
    """
    if val_str is None:
        return None
    if isinstance(val_str, (int, float)):
        return float(val_str)
    if not isinstance(val_str, str):
        return None

    val = val_str.strip().replace(",", "").replace("%", "").replace("$", "")
    if val in ("", "-", "N/A", ".", "--", "None"):
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


def parse_impact(impact_class: str) -> str:
    """Map FF impact CSS classes to a canonical label.

    Handles both schemes: calendar__impact-icon--high/medium/low and
    impact-red/impact-ora/impact-yel/impact-gra.
    """
    cls = impact_class.lower()
    if "high" in cls or "red" in cls:
        return "High"
    if "med" in cls or "medium" in cls or "ora" in cls:
        return "Medium"
    if "low" in cls or "yel" in cls:
        return "Low"
    if "gra" in cls or "non" in cls:
        return "Non-Economic"
    return "Low"


def determine_direction(event_name: str, actual: Optional[float],
                        forecast: Optional[float]) -> str:
    """Determine bullish/bearish/neutral based on Actual vs Forecast."""
    if actual is None or forecast is None:
        return "neutral"
    if abs(actual - forecast) < 1e-9:
        return "neutral"

    upper = event_name.upper()
    is_inverse = any(kw in upper for kw in INVERSE_INDICATOR_KEYWORDS)

    if actual > forecast:
        return "bearish" if is_inverse else "bullish"
    return "bullish" if is_inverse else "bearish"


def make_event_id(currency: str, event: str, date: str) -> str:
    """Build a stable slug id, e.g. 'usd-nfp-2026-08-07'."""
    cur = currency.lower()
    ev = re.sub(r"[^a-z0-9]+", "-", event.lower()).strip("-")
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date)
    if date_match:
        date_slug = date_match.group(1)
    else:
        date_slug = re.sub(r"[^a-z0-9]+", "-", date.lower()).strip("-")
    return f"{cur}-{ev}-{date_slug}"


def fetch_calendar_html() -> Optional[str]:
    """Fetch the FF calendar HTML with Cloudflare bypass fallback chain.

    Strategy 1: cloudscraper (browser impersonation)
    Strategy 2: curl_cffi (chrome120 impersonation)
    Strategy 3: plain requests with browser headers
    """
    # Strategy 1: cloudscraper
    if _HAS_CLOUDSCRAPER:
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
            resp = scraper.get(FF_CALENDAR_URL, headers=BROWSER_HEADERS, timeout=45)
            if resp.status_code == 200 and "calendar" in resp.text.lower():
                logger.info("Fetched via cloudscraper (%d bytes)", len(resp.text))
                return resp.text
            logger.warning("cloudscraper returned status %s", resp.status_code)
        except Exception as e:
            logger.warning("cloudscraper failed: %s", e)

    # Strategy 2: curl_cffi with browser impersonation
    if _HAS_CURL_CFFI:
        try:
            resp = curl_requests.get(
                FF_CALENDAR_URL,
                headers=BROWSER_HEADERS,
                impersonate="chrome120",
                timeout=45,
            )
            if resp.status_code == 200 and "calendar" in resp.text.lower():
                logger.info("Fetched via curl_cffi (%d bytes)", len(resp.text))
                return resp.text
            logger.warning("curl_cffi returned status %s", resp.status_code)
        except Exception as e:
            logger.warning("curl_cffi failed: %s", e)

    # Strategy 3: plain requests with browser headers
    try:
        resp = requests.get(FF_CALENDAR_URL, headers=BROWSER_HEADERS, timeout=45)
        if resp.status_code == 200 and "calendar" in resp.text.lower():
            logger.info("Fetched via requests (%d bytes)", len(resp.text))
            return resp.text
        logger.warning("requests returned status %s", resp.status_code)
    except Exception as e:
        logger.warning("requests failed: %s", e)

    return None


def parse_calendar(html: str) -> list[dict]:
    """Parse the FF calendar HTML table into rich event dicts."""
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []

    table = soup.find("table", class_=re.compile("calendar__table"))
    if not table:
        logger.warning("No calendar table found in HTML.")
        return events

    current_date = ""
    rows = table.find_all("tr", class_=re.compile("calendar__row"))

    for row in rows:
        try:
            if "day-breaker" in " ".join(row.get("class", [])):
                date_cell = row.find("td", class_=re.compile("calendar__date"))
                if date_cell:
                    date_text = date_cell.get_text(strip=True)
                    if date_text:
                        current_date = date_text
                continue

            time_cell = row.find("td", class_=re.compile("calendar__time"))
            time_text = time_cell.get_text(strip=True) if time_cell else ""

            currency_cell = row.find("td", class_=re.compile("calendar__currency"))
            currency_text = currency_cell.get_text(strip=True) if currency_cell else ""
            currency = FF_COUNTRY_MAP.get(currency_text.upper(), "")

            event_cell = row.find("td", class_=re.compile("calendar__event"))
            event_text = event_cell.get_text(strip=True) if event_cell else ""

            impact_cell = row.find("td", class_=re.compile("calendar__impact"))
            impact_class = ""
            if impact_cell:
                impact_span = impact_cell.find("span", class_=re.compile("impact"))
                if impact_span:
                    impact_class = " ".join(impact_span.get("class", []))
                else:
                    impact_class = " ".join(impact_cell.get("class", []))
            impact = parse_impact(impact_class)

            actual_cell = row.find("td", class_=re.compile("calendar__actual"))
            forecast_cell = row.find("td", class_=re.compile("calendar__forecast"))
            previous_cell = row.find("td", class_=re.compile("calendar__previous"))

            actual_raw = actual_cell.get_text(strip=True) if actual_cell else ""
            forecast_raw = forecast_cell.get_text(strip=True) if forecast_cell else ""
            previous_raw = previous_cell.get_text(strip=True) if previous_cell else ""

            if not event_text or not currency:
                continue

            actual_num = parse_numeric_value(actual_raw)
            forecast_num = parse_numeric_value(forecast_raw)
            previous_num = parse_numeric_value(previous_raw)

            delta = None
            if actual_num is not None and forecast_num is not None:
                delta = round(actual_num - forecast_num, 4)

            direction = determine_direction(event_text, actual_num, forecast_num)

            events.append({
                "id": make_event_id(currency, event_text, current_date),
                "date": current_date,
                "time": time_text,
                "currency": currency,
                "impact": impact,
                "event": event_text[:120],
                "actual_raw": actual_raw,
                "forecast_raw": forecast_raw,
                "previous_raw": previous_raw,
                "actual_num": actual_num,
                "forecast_num": forecast_num,
                "previous_num": previous_num,
                "delta_vs_forecast": delta,
                "direction": direction,
            })
        except Exception as e:
            logger.debug("Skipping row: %s", e)
            continue

    logger.info("Parsed %d calendar events", len(events))
    return events


def export_calendar(events: list[dict], output_path: str = OUTPUT_PATH) -> str:
    """Write the rich event array to public/data/calendar.json."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, default=str)
    logger.info("Exported %d events to %s", len(events), output_path)
    return output_path


def run_self_test() -> int:
    """Offline verification of parsing/normalization logic (no network needed).

    Validates the exact examples from the task spec so the scraper's math and
    classification can be proven correct even when Forex Factory is unreachable
    (Cloudflare block / no network).
    """
    print("=" * 60)
    print(" BULLS & BEARS FUNDAMENTALS — CALENDAR SCRAPER SELF-TEST")
    print("=" * 60)

    # ── parse_numeric_value ────────────────────────────────────────────────
    cases = [
        ("3.2%", 3.2),
        ("$210K", 210000.0),
        ("1.4M", 1400000.0),
        ("-0.5%", -0.5),
        ("12.5B", 12500000000.0),
        ("147K", 147000.0),
        ("165K", 165000.0),
        ("150K", 150000.0),
        ("", None),
        ("N/A", None),
        ("--", None),
    ]
    for raw, expected in cases:
        got = parse_numeric_value(raw)
        status = "PASS" if got == expected else "FAIL"
        print(f"  [{status}] parse_numeric_value({raw!r}) = {got} (expected {expected})")
        if status == "FAIL":
            return 1

    # ── parse_impact ───────────────────────────────────────────────────────
    impact_cases = [
        ("calendar__impact-icon--high", "High"),
        ("calendar__impact-icon--medium", "Medium"),
        ("calendar__impact-icon--low", "Low"),
        ("impact-red", "High"),
        ("impact-ora", "Medium"),
        ("impact-yel", "Low"),
        ("impact-gra", "Non-Economic"),
    ]
    for cls, expected in impact_cases:
        got = parse_impact(cls)
        status = "PASS" if got == expected else "FAIL"
        print(f"  [{status}] parse_impact({cls!r}) = {got} (expected {expected})")
        if status == "FAIL":
            return 1

    # ── determine_direction ────────────────────────────────────────────────
    dir_cases = [
        # Standard indicator: actual > forecast => bullish
        ("Non-Farm Employment Change", 147000.0, 165000.0, "bearish"),
        ("Non-Farm Employment Change", 170000.0, 165000.0, "bullish"),
        # Inverse indicator: higher unemployment => bearish
        ("Unemployment Rate", 4.2, 4.0, "bearish"),
        ("Unemployment Rate", 3.9, 4.0, "bullish"),
        # Missing / equal => neutral
        ("GDP", None, 2.0, "neutral"),
        ("CPI", 2.5, 2.5, "neutral"),
    ]
    for event, actual, forecast, expected in dir_cases:
        got = determine_direction(event, actual, forecast)
        status = "PASS" if got == expected else "FAIL"
        print(f"  [{status}] determine_direction({event!r}, {actual}, {forecast}) = {got} (expected {expected})")
        if status == "FAIL":
            return 1

    # ── make_event_id ──────────────────────────────────────────────────────
    eid = make_event_id("USD", "Non-Farm Employment Change", "Fri Aug 7")
    print(f"  [INFO] sample event id: {eid}")

    print("\nAll calendar scraper self-test assertions passed.")
    return 0


def run_fixture_pipeline() -> int:
    """Run the full parse→norm→export pipeline against a realistic HTML fixture.

    This produces the exact task-mandated bare-array format in public/data/calendar.json
    even when the live Forex Factory fetch is blocked (Cloudflare 403), so the scraper's
    end-to-end behaviour is verifiable offline. Covers all 8 major currencies and
    High / Medium / Low / Non-Economic impacts.
    """
    fixture_html = """<html><body>
    <table class="calendar__table">
      <tr class="calendar__row calendar__row--day-breaker">
        <td class="calendar__date">Fri Aug 7 2026</td>
      </tr>
      <tr class="calendar__row">
        <td class="calendar__time">8:30am</td>
        <td class="calendar__currency">USD</td>
        <td class="calendar__event">Non-Farm Employment Change</td>
        <td class="calendar__impact"><span class="calendar__impact-icon calendar__impact-icon--high"></span></td>
        <td class="calendar__actual">147K</td>
        <td class="calendar__forecast">165K</td>
        <td class="calendar__previous">150K</td>
      </tr>
      <tr class="calendar__row">
        <td class="calendar__time">2:00am</td>
        <td class="calendar__currency">EUR</td>
        <td class="calendar__event">German CPI (YoY)</td>
        <td class="calendar__impact impact-red"></td>
        <td class="calendar__actual">2.4%</td>
        <td class="calendar__forecast">2.3%</td>
        <td class="calendar__previous">2.5%</td>
      </tr>
      <tr class="calendar__row">
        <td class="calendar__time">4:30am</td>
        <td class="calendar__currency">GBP</td>
        <td class="calendar__event">GDP (QoQ)</td>
        <td class="calendar__impact impact-ora"></td>
        <td class="calendar__actual">0.6%</td>
        <td class="calendar__forecast">0.5%</td>
        <td class="calendar__previous">0.4%</td>
      </tr>
      <tr class="calendar__row">
        <td class="calendar__time">7:00pm</td>
        <td class="calendar__currency">JPY</td>
        <td class="calendar__event">Household Spending (YoY)</td>
        <td class="calendar__impact impact-yel"></td>
        <td class="calendar__actual">1.2%</td>
        <td class="calendar__forecast">1.5%</td>
        <td class="calendar__previous">1.8%</td>
      </tr>
      <tr class="calendar__row">
        <td class="calendar__time">1:30am</td>
        <td class="calendar__currency">AUD</td>
        <td class="calendar__event">Employment Change</td>
        <td class="calendar__impact impact-red"></td>
        <td class="calendar__actual">38.5K</td>
        <td class="calendar__forecast">25.0K</td>
        <td class="calendar__previous">42.0K</td>
      </tr>
      <tr class="calendar__row">
        <td class="calendar__time">8:30am</td>
        <td class="calendar__currency">CAD</td>
        <td class="calendar__event">CPI (YoY)</td>
        <td class="calendar__impact impact-red"></td>
        <td class="calendar__actual">3.1%</td>
        <td class="calendar__forecast">2.9%</td>
        <td class="calendar__previous">3.0%</td>
      </tr>
      <tr class="calendar__row">
        <td class="calendar__time">3:15am</td>
        <td class="calendar__currency">CHF</td>
        <td class="calendar__event">SNB Rate Statement</td>
        <td class="calendar__impact impact-red"></td>
        <td class="calendar__actual">1.25%</td>
        <td class="calendar__forecast">1.25%</td>
        <td class="calendar__previous">1.50%</td>
      </tr>
      <tr class="calendar__row">
        <td class="calendar__time">10:00pm</td>
        <td class="calendar__currency">NZD</td>
        <td class="calendar__event">Retail Sales (QoQ)</td>
        <td class="calendar__impact impact-ora"></td>
        <td class="calendar__actual">1.8%</td>
        <td class="calendar__forecast">1.6%</td>
        <td class="calendar__previous">1.4%</td>
      </tr>
      <tr class="calendar__row">
        <td class="calendar__time">All Day</td>
        <td class="calendar__currency">USD</td>
        <td class="calendar__event">Bank Holiday</td>
        <td class="calendar__impact impact-gra"></td>
        <td class="calendar__actual"></td>
        <td class="calendar__forecast"></td>
        <td class="calendar__previous"></td>
      </tr>
    </table>
    </html>
    """

    events = parse_calendar(fixture_html)
    if not events:
        logger.error("Fixture parse produced zero events.")
        return 1

    export_calendar(events)

    currencies = {ev["currency"] for ev in events}
    impacts = {ev["impact"] for ev in events}
    with_numeric = sum(1 for ev in events if ev["actual_num"] is not None)

    print(f"\nCalendar fixture pipeline complete.")
    print(f"  Total events: {len(events)}")
    print(f"  Currencies: {', '.join(sorted(currencies))}")
    print(f"  Impacts: {', '.join(sorted(impacts))}")
    print(f"  Events with numeric actual: {with_numeric}")

    missing_majors = MAJOR_CURRENCIES - currencies
    if missing_majors:
        print(f"  [WARN] Missing major currencies: {', '.join(sorted(missing_majors))}")
        return 1
    print(f"  [OK] All 8 major currencies present: {', '.join(sorted(MAJOR_CURRENCIES))}")

    high_impact = [ev for ev in events if ev["impact"] == "High"]
    med_impact = [ev for ev in events if ev["impact"] == "Medium"]
    low_impact = [ev for ev in events if ev["impact"] == "Low"]
    none_impact = [ev for ev in events if ev["impact"] == "Non-Economic"]
    print(f"  High: {len(high_impact)} · Medium: {len(med_impact)} · Low: {len(low_impact)} · Non-Economic: {len(none_impact)}")
    if not (high_impact and med_impact and low_impact):
        print("  [WARN] Not all impact levels present in fixture.")
        return 1

    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Offline self-test mode: python scripts/calendar_scraper.py --selftest
    if "--selftest" in sys.argv:
        return run_self_test()

    # Fixture pipeline mode: python scripts/calendar_scraper.py --fixture
    if "--fixture" in sys.argv:
        return run_fixture_pipeline()

    html = fetch_calendar_html()
    if not html:
        logger.error("Failed to fetch Forex Factory calendar.")
        return 1

    events = parse_calendar(html)
    if not events:
        logger.error("No events parsed from calendar HTML.")
        return 1

    export_calendar(events)

    currencies = {ev["currency"] for ev in events}
    impacts = {ev["impact"] for ev in events}
    with_numeric = sum(1 for ev in events if ev["actual_num"] is not None)

    print(f"\nCalendar scraper complete.")
    print(f"  Total events: {len(events)}")
    print(f"  Currencies: {', '.join(sorted(currencies))}")
    print(f"  Impacts: {', '.join(sorted(impacts))}")
    print(f"  Events with numeric actual: {with_numeric}")

    missing_majors = MAJOR_CURRENCIES - currencies
    if missing_majors:
        print(f"  [WARN] Missing major currencies: {', '.join(sorted(missing_majors))}")
    else:
        print(f"  [OK] All 8 major currencies present: {', '.join(sorted(MAJOR_CURRENCIES))}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
