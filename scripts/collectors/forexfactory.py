# Economic calendar collector — primary: Forex Factory calendar HTML (embedded state
# contains the full week incl. actual/forecast/previous for every currency).
# The calendar page is served by Cloudflare; a layered, polite bypass is attempted
# only when a challenge is detected (cloudscraper -> curl_cffi TLS impersonation ->
# playwright headless, import-guarded). On hard failure we fall back to the
# companion schedule feed (forecast/previous, no JS).
# No credentials required. Results saved to data/calendar/events_current.json.
import os
import sys
import json
import re
import time
import requests
from datetime import datetime, timedelta, timezone
from http.cookiejar import MozillaCookieJar

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, log, DATA_DIR, now_iso  # noqa: E402

CALENDAR_URL = "https://www.forexfactory.com/calendar"
FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
COOKIE_FILE = os.path.join(DATA_DIR, "meta", "ff_cookies.txt")
SOURCE_META = os.path.join(DATA_DIR, "meta", "calendar_source.json")
CHALLENGE_MARKERS = ("cf-challenge", "challenge-platform", "just a moment",
                     "checking your browser", "cf-mitigated", "__cf_chl")

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.forexfactory.com/",
}


def _load_cookies(session):
    try:
        jar = MozillaCookieJar(COOKIE_FILE)
        if os.path.exists(COOKIE_FILE):
            jar.load(ignore_discard=True, ignore_expires=True)
        session.cookies.update(jar)
    except Exception as exc:
        log(f"Cookie load failed: {exc}", "WARN")


def _save_cookies(session):
    try:
        os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
        jar = MozillaCookieJar(COOKIE_FILE)
        for c in session.cookies:
            jar.set_cookie(c)
        jar.save(ignore_discard=True, ignore_expires=True)
        log("Cookie jar saved", "INFO")
    except Exception as exc:
        log(f"Cookie save failed: {exc}", "WARN")


def _fetch_plain(retries=6):
    """Fetch the calendar page with plain requests + persistent cookies."""
    session = requests.Session()
    session.headers.update(_HEADERS)
    _load_cookies(session)
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(CALENDAR_URL, timeout=60, allow_redirects=True)
            _save_cookies(session)
            if r.status_code == 200:
                return r.text
            log(f"plain fetch HTTP {r.status_code}", "WARN")
            if r.status_code == 429:
                time.sleep(15)
        except Exception as exc:
            last = str(exc)[:140]
            log(f"plain fetch retry {attempt}: {last}", "WARN")
            time.sleep(4 * attempt)
    raise RuntimeError(f"Plain fetch failed: {last}")


def _is_challenge(text):
    low = (text or "").lower()
    return any(m in low for m in CHALLENGE_MARKERS) and "calendarComponentStates" not in low
def _fetch_via_cloudscraper():
    try:
        import cloudscraper
    except Exception as exc:
        log(f"cloudscraper unavailable: {exc}", "WARN")
        return None
    try:
        sc = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
        r = sc.get(CALENDAR_URL, headers=_HEADERS, timeout=60)
        if r.status_code == 200 and not _is_challenge(r.text) and "calendarComponentStates" in r.text:
            return r.text
        log(f"cloudscraper status {r.status_code}", "WARN")
    except Exception as exc:
        log(f"cloudscraper failed: {str(exc)[:140]}", "WARN")
    return None


def _fetch_via_curl_cffi():
    try:
        from curl_cffi import requests as cf_req
    except Exception as exc:
        log(f"curl_cffi unavailable: {exc}", "WARN")
        return None
    try:
        r = cf_req.get(CALENDAR_URL, headers=_HEADERS, impersonate="chrome", timeout=60)
        if r.status_code == 200 and not _is_challenge(r.text) and "calendarComponentStates" in r.text:
            return r.text
        log(f"curl_cffi status {r.status_code}", "WARN")
    except Exception as exc:
        log(f"curl_cffi failed: {str(exc)[:140]}", "WARN")
    return None


def _fetch_via_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        log(f"playwright unavailable: {exc}", "WARN")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=_HEADERS["User-Agent"], locale="en-US")
            page = ctx.new_page()
            page.goto(CALENDAR_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            html = page.content()
            browser.close()
            if "calendarComponentStates" in html:
                return html
            log("playwright returned page without calendar state", "WARN")
    except Exception as exc:
        log(f"playwright failed: {str(exc)[:140]}", "WARN")
    return None


def fetch_html():
    """Best-effort page fetch honoring the balanced bypass tier.
    Escalates when plain fetch is challenged, 403/blocked, or errors out."""
    # Tier 1: plain requests
    try:
        html = _fetch_plain()
        if not _is_challenge(html):
            return html, "ff-html"
        log("Cloudflare challenge detected — escalating bypass", "INFO")
    except Exception as exc:
        log(f"Plain fetch unavailable/blocked ({str(exc)[:100]}) — escalating bypass", "WARN")
    # Tiers 2-4: cloudscraper -> curl_cffi -> playwright (import-guarded)
    for name, fn in (("cloudscraper", _fetch_via_cloudscraper),
                     ("curl_cffi", _fetch_via_curl_cffi),
                     ("playwright", _fetch_via_playwright)):
        try:
            html = fn()
            if html:
                log(f"bypass via {name} succeeded", "INFO")
                return html, f"ff-html-{name}"
        except Exception as exc:
            log(f"bypass tier {name} raised: {str(exc)[:100]}", "WARN")
    raise RuntimeError("All bypass tiers failed (calendar page challenged/blocked)")


def _extract_state_events(html):
    """Parse window.calendarComponentStates[1] -> days -> list of canonical events."""
    m = re.search(r'window\.calendarComponentStates\[1\] = (\{.*?\});', html, re.S)
    if not m:
        return []
    raw = m.group(1)
    # The days array is the first value; find its closing bracket by balance.
    start = raw.index("days:") + len("days:")
    i, depth = start, 0
    while i < len(raw):
        if raw[i] == "[":
            depth += 1
        elif raw[i] == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    days_raw = raw[start:i + 1]
    fixed = re.sub(r'([{,]\s*)([A-Za-z_$][\w$]*)(\s*:)', r'\1"\2"\3', days_raw)
    fixed = re.sub(r'\bundefined\b', 'null', fixed)
    days = json.loads(fixed)
    out = []
    for day in days:
        for ev in day.get("events", []):
            out.append(_canonical_event(ev))
    return out


def _canonical_event(ev):
    impact = (ev.get("impactName") or "").lower()
    impact_map = {"high": "High", "medium": "Medium", "low": "Low",
                  "holiday": "Holiday", "none": "Low"}
    country = ev.get("currency") or ev.get("country") or ""
    if country.upper() == "ALL":
        country = "Global"
    dl = ev.get("dateline")
    dt_utc = datetime.fromtimestamp(dl, tz=timezone.utc).isoformat(timespec="minutes") if dl else None
    return {
        "title": ev.get("name") or ev.get("soloTitle") or "",
        "country": (country or "").upper(),
        "date_utc": dt_utc,
        "impact": impact_map.get(impact, "Low"),
        "forecast": str(ev.get("forecast") or "").strip(),
        "previous": str(ev.get("previous") or "").strip(),
        "actual": str(ev.get("actual") or "").strip(),
        "revision": str(ev.get("revision") or "").strip(),
        "dateline": dl,
        "source": "ff-html",
    }
def _iso_to_utc(date_str):
    """Convert companion-feed timestamps (e.g. '2026-09-10T08:30:00-04:00') to UTC ISO."""
    if not date_str:
        return None
    try:
        m = re.match(r"(.+?)([+-]\d{2}):(\d{2})$", date_str)
        if not m:
            return date_str
        base, oh, om = m.group(1), int(m.group(2)), int(m.group(3))
        dt = datetime.fromisoformat(base)
        dt_utc = dt - timedelta(hours=oh, minutes=om)
        return dt_utc.replace(tzinfo=timezone.utc).isoformat(timespec="minutes")
    except Exception:
        return date_str


def _fetch_feed(max_attempts=8):
    """Companion no-JS feed fallback (forecast/previous only)."""
    last = None
    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.get(FEED_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
            data = r.json()
            if isinstance(data, list) and data:
                out = []
                for e in data:
                    country = (e.get("country") or "").upper().strip()
                    out.append({
                        "title": (e.get("title") or "").strip(),
                        "country": "Global" if country == "ALL" else country,
                        "date_utc": _iso_to_utc(e.get("date")),
                        "impact": (e.get("impact") or ""),
                        "forecast": str(e.get("forecast") or "").strip(),
                        "previous": str(e.get("previous") or "").strip(),
                        "actual": "",
                        "revision": "",
                        "source": "ff-feed",
                    })
                return out
        except Exception as exc:
            last = str(exc)[:120]
        time.sleep(4 * attempt)
    raise RuntimeError(f"Calendar feed failed after {max_attempts} attempts: {last}")


def _merge(events):
    """Merge new events with prior storage, keyed by title+date, keep 45-day window."""
    path = os.path.join(DATA_DIR, "calendar", "events_current.json")
    prior = load_json(path, default=[])
    prior_map = {}
    for ev in prior:
        k = (ev.get("title"), ev.get("date_utc"), ev.get("country"))
        prior_map[k] = ev
    for ev in events:
        k = (ev.get("title"), ev.get("date_utc"), ev.get("country"))
        if k in prior_map:
            # keep the more informative version (source with actual wins on tie)
            old = prior_map[k]
            if not old.get("actual") and ev.get("actual"):
                prior_map[k] = ev
        else:
            prior_map[k] = ev
    # keep events within +-45 days
    now = datetime.utcnow()
    window = []
    for ev in prior_map.values():
        try:
            dt = datetime.fromisoformat((ev.get("date_utc") or "").replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if abs((dt.astimezone(timezone.utc).replace(tzinfo=None) - now).days) <= 45:
                window.append(ev)
        except Exception:
            window.append(ev)
    return sorted(window, key=lambda x: x.get("date_utc") or "")


def collect():
    """Fetch the full calendar (FF HTML preferred, feed + fallbacks backup) and merge."""
    events, source_used = [], "none"
    try:
        html, source_used = fetch_html()
        events = _extract_state_events(html)
        if len(events) < 10:
            log(f"Only {len(events)} events parsed from FF HTML — using feed + fallbacks", "WARN")
            events, source_used = _fetch_feed(), "ff-feed"
    except Exception as exc:
        log(f"FF HTML path failed ({exc}) — using feed + fallbacks", "WARN")
        try:
            events, source_used = _fetch_feed(), "ff-feed"
        except Exception as exc2:
            log(f"Feed fallback failed: {exc2}", "ERROR")
            events = []

    # Enrich / substitute with fallback calendars (TradingEconomics carries actuals)
    if not events or sum(1 for e in events if e.get("actual")) < 10:
        try:
            from collectors.calendar_fallbacks import collect_fallback_events, merge_calendars
            fallback_evs = collect_fallback_events()
            if fallback_evs:
                before = sum(1 for e in events if e.get("actual"))
                events = merge_calendars(events, fallback_evs)
                after = sum(1 for e in events if e.get("actual"))
                if after > before:
                    source_used = f"{source_used}+te"
                    log(f"Fallback added {after - before} actual-bearing events", "INFO")
        except Exception as exc:
            log(f"Fallback chain failed: {str(exc)[:120]}", "WARN")

    merged = _merge(events)
    save_json(os.path.join(DATA_DIR, "calendar", "events_current.json"), merged)
    save_json(SOURCE_META, {"updated": now_iso(), "source": source_used,
                            "events": len(merged), "with_actual": sum(1 for e in merged if e.get("actual"))})
    high = sum(1 for e in merged if e.get("impact") == "High")
    log(f"Calendar: {len(merged)} events (source={source_used}, High={high}, actuals={sum(1 for e in merged if e.get('actual'))})")
    return {"events": len(merged), "source": source_used, "high": high}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))