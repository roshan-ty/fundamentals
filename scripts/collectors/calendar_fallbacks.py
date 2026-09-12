# Calendar fallbacks — secondary economic calendar sources used when the primary
# is unavailable. All sources are normalized to the same canonical event schema:
#   title, country (currency code), date_utc, impact, forecast, previous, actual
# TradingEconomics is the main fallback (no Cloudflare, carries actual values).
# TradingView / Investing.com / Myfxbook are attempted best-effort and degrade
# gracefully when blocked.
import os
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import log, HttpSession, save_json, DATA_DIR  # noqa: E402

# ISO-2 country -> currency for calibration to our scoring universe
COUNTRY_CURRENCY = {
    "US": "USD", "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR", "NL": "EUR",
    "BE": "EUR", "IE": "EUR", "PT": "EUR", "FI": "EUR", "AT": "EUR", "GR": "EUR",
    "SK": "EUR", "SI": "EUR", "LU": "EUR", "CY": "EUR", "MT": "EUR", "LV": "EUR",
    "LT": "EUR", "EE": "EUR", "HR": "EUR", "EU": "EUR", "GB": "GBP", "JP": "JPY",
    "AU": "AUD", "NZ": "NZD", "CA": "CAD", "CH": "CHF", "CN": "CNY", "MX": "MXN",
    "BR": "BRL", "SE": "SEK", "NO": "NOK", "PL": "PLN", "HU": "HUF", "CZ": "CZK",
    "DK": "DKK", "SG": "SGD", "HK": "HKD", "ZA": "ZAR", "TR": "TRY", "KR": "KRW",
}


def _clean_value(val):
    """Normalize numeric-ish snapshots: unicode dashes -> '-', strip stray glyphs."""
    txt = _clean(val)
    for ch in ("\u2212", "\u2013", "\u2014", "\uff0d", "\u2011"):
        txt = txt.replace(ch, "-")
    # keep only digits, signs, percent, dot, comma, $-units and letters
    txt = "".join(ch for ch in txt if ch.isalnum() or ch in "-+%.,$ ")
    return txt


def _clean(val):
    return " ".join(str(val or "").split())


def _parse_et_datetime(date_str, time_str):
    """TE times are America/New_York; convert to UTC ISO."""
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
        dt = dt.replace(tzinfo=ZoneInfo("America/New_York"))
        return dt.astimezone(timezone.utc).isoformat(timespec="minutes")
    except Exception:
        if date_str:
            return f"{date_str}T00:00:00+00:00"
        return None


def parse_tradingeconomics(html):
    """Parse the /calendar page (verified against a live capture)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    tb = soup.find("table", class_="table-condensed")
    if not tb:
        return []
    events = []
    for tr in tb.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue
        raw_date = tds[0].get("class") or []
        date_str = next((c for c in raw_date if re.match(r"^\d{4}-\d{2}-\d{2}$", c)), None)
        time_txt = _clean(tds[0].get_text(" ", strip=True))
        country_iso = _clean(tds[3].get_text(" ", strip=True)).upper()
        ev_name = _clean(tds[4].get_text(" ", strip=True))
        if not ev_name or ":" not in time_txt:
            continue
        actual = _clean_value(tds[5].get_text(" ", strip=True))
        previous = _clean_value(tds[6].get_text(" ", strip=True))
        consensus = _clean_value(tds[7].get_text(" ", strip=True))
        forecast = _clean_value(tds[8].get_text(" ", strip=True))
        currency = COUNTRY_CURRENCY.get(country_iso, country_iso)
        events.append({
            "title": ev_name,
            "country": currency,
            "date_utc": _parse_et_datetime(date_str, time_txt),
            "impact": "",
            "forecast": forecast if forecast and forecast != "-" else "",
            "previous": previous if previous and previous != "-" else "",
            "actual": actual if actual and actual != "-" else "",
            "source": "te",
        })
    return events


def fetch_tradingeconomics(http=None):
    """Fetch + parse TradingEconomics /calendar into canonical events."""
    http = http or HttpSession(timeout=45, max_retries=2)
    html = http.get("https://tradingeconomics.com/calendar", timeout=60).text
    return parse_tradingeconomics(html)


_COUNTRY_PAGES = ["australia", "new-zealand", "japan", "switzerland", "china",
                  "canada", "united-kingdom", "germany", "france", "united-states"]


def collect_year_calendar(days=365):
    """Fetch a ~1-year TradingEconomics window + per-country calendar pages so
    every data point has a recent released predecessor. Actual-bearing rows from
    per-country pages feed currencies that the main feed misses (AUD/NZD/JPY/
    CHF/CNY). Saved to data/calendar/year_events.json; the verdict engine
    consumes it via build_releases (not displayed directly)."""
    from datetime import timedelta
    today = datetime.utcnow()
    start = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    http = HttpSession(timeout=60, max_retries=2)
    seen = {}

    def merge_events(events):
        for ev in events:
            key = (ev.get("title"), ev.get("country"), (ev.get("date_utc") or "")[:16])
            seen[key] = ev

    try:
        html = http.get("https://tradingeconomics.com/calendar",
                        params={"from": start, "to": end}, timeout=90).text
        merge_events(parse_tradingeconomics(html))
    except Exception as exc:
        log(f"Year calendar fetch failed: {str(exc)[:100]}", "WARN")

    for slug in _COUNTRY_PAGES:
        try:
            chtml = http.get(f"https://tradingeconomics.com/{slug}/calendar",
                             timeout=60).text
            events = parse_tradingeconomics(chtml)
            merge_events(events)
            log(f"Country calendar {slug}: {len(events)} rows "
                f"({sum(1 for e in events if e.get('actual'))} actuals)")
        except Exception as exc:
            log(f"Country calendar {slug} failed: {str(exc)[:80]}", "WARN")

    events = list(seen.values())
    log(f"Year calendar (all countries): {len(events)} rows "
        f"({sum(1 for e in events if e.get('actual'))} released actuals)")
    if events:
        save_json(os.path.join(DATA_DIR, "calendar", "year_events.json"), events)
    return events
def fetch_tradingview():
    """Best-effort TradingView economic calendar data endpoint."""
    out = []
    http = HttpSession(timeout=25, max_retries=1)
    url = "https://scanner.tradingview.com/economic-calendar/scan"
    try:
        r = http.get(url, timeout=25)
        ct = r.headers.get("content-type", "")
        data = r.json() if "json" in ct else {}
        for row in (data.get("data") or [])[:200]:
            d = row.get("d", [])
            if len(d) >= 6:
                out.append({
                    "title": d[2], "country": d[1], "date_utc": None,
                    "impact": "", "forecast": d[4], "previous": d[5],
                    "actual": d[3], "source": "tv",
                })
    except Exception as exc:
        log(f"TradingView fallback unavailable: {str(exc)[:100]}", "WARN")
    return out


def try_investing_myfxbook():
    """Best-effort attempts for Investing.com + Myfxbook (often CF-challenged)."""
    http = HttpSession(timeout=25, max_retries=1)
    for name, url in (("investing", "https://www.investing.com/economic-calendar/"),
                      ("myfxbook", "https://www.myfxbook.com/forex-economic-calendar")):
        try:
            r = http.get(url, timeout=25)
            if r.status_code == 200:
                log(f"fallback {name} reachable ({len(r.text)} bytes)", "INFO")
            else:
                log(f"fallback {name} blocked (status {r.status_code})", "WARN")
        except Exception as exc:
            log(f"fallback {name} unavailable: {str(exc)[:90]}", "WARN")


_MOM = ("m/m", "mom", "m o m", "mm ")
_YOY = ("y/y", "yoy", "y o y", "yy ")
_QOQ = ("q/q", "qoq", "q o q", "qq ")
_STOP = set(("the", "a", "an", "of", "in", "for", "and", "or", "summary", "final",
             "revised", "flash", "prelim", "index", "jan", "feb", "mar", "apr", "may",
             "jun", "jul", "aug", "sep", "oct", "nov", "dec", "united", "states", "euro",
             "zone", "south", "africa", "national", "us", "au", "ca", "gb", "de", "fr",
             "ch", "nz", "jp", "cn", "mom", "yoy", "qoq", "mm", "yy", "qq", "m/m", "y/y", "q/q"))


def _signature(title):
    low = (title or "").lower()
    has_mom = any(w in low for w in _MOM)
    has_yoy = any(w in low for w in _YOY)
    has_qoq = any(w in low for w in _QOQ)
    words = re.findall(r"[a-z]{3,}", low)
    core = tuple(sorted(set(w for w in words if w not in _STOP))[:8])
    return (has_mom, has_yoy, has_qoq, core)


def merge_calendars(primary, fallback):
    """Enrich primary events with fallback actuals (match by country+day+signature),
    then append genuinely new events. Keeps the primary schedule as the base."""
    enriched = []
    index = {}  # (country, day) -> list of (signature, event)
    for ev in primary:
        key = (ev.get("country"), (ev.get("date_utc") or "")[:10])
        index.setdefault(key, []).append(ev)

    new_events = []
    for ev in fallback:
        if not ev.get("actual"):
            continue
        key = (ev.get("country"), (ev.get("date_utc") or "")[:10])
        sig = _signature(ev.get("title"))
        candidates = index.get(key) or []
        matched = None
        for cand in candidates:
            csig = _signature(cand.get("title"))
            if csig == sig:
                matched = cand
                break
        if matched:
            if not matched.get("actual"):
                matched["actual"] = ev.get("actual")
                matched["previous"] = ev.get("previous") or matched.get("previous")
                if not matched.get("forecast"):
                    matched["forecast"] = ev.get("forecast")
            continue
        new_events.append(ev)

    for ev in primary:
        enriched.append(ev)
    enriched.extend(new_events)
    # final dedupe by title+country+day
    by_key = {}
    for ev in enriched:
        k = (ev.get("title"), ev.get("country"), (ev.get("date_utc") or "")[:16])
        if k not in by_key or (ev.get("actual") and not by_key[k].get("actual")):
            by_key[k] = ev
    return list(by_key.values())


def collect_fallback_events(fallback_enabled=True):
    """Pull fallback calendars, prefer TradingEconomics (rich actuals)."""
    if not fallback_enabled:
        return []
    evs = []
    try:
        evs = fetch_tradingeconomics()
        log(f"TradingEconomics fallback: {len(evs)} events "
            f"({sum(1 for e in evs if e.get('actual'))} with actual)")
    except Exception as exc:
        log(f"TradingEconomics fallback failed: {str(exc)[:100]}", "WARN")
    if not evs:
        try_investing_myfxbook()
    return evs