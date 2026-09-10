# Economic calendar collector — Forex Factory companion feed
# The schedule/forecast/previous feed is provided by the calendar's own
# public data service and requires no credentials. Scores are derived only
# when published actuals are matched from official economic sources.
import os
import sys
import json
import re
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, log, DATA_DIR, now_iso, HttpSession

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Currencies tracked by the FF feed (country codes they use)
CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNY"}


def _fetch_feed(http, max_attempts=8):
    """FF host is rate-flaky; retry with increasing backoff."""
    last = None
    for attempt in range(1, max_attempts + 1):
        try:
            r = http.get(FEED, timeout=60)
            data = r.json()
            if isinstance(data, list) and data:
                return data
            last = f"Unexpected payload: {str(data)[:120]}"
        except Exception as exc:
            last = str(exc)[:120]
        time.sleep(4 * attempt)
    raise RuntimeError(f"Calendar feed failed after {max_attempts} attempts: {last}")


def _iso_to_utc(date_str):
    """Convert FF timestamps (e.g. '2026-09-10T08:30:00-04:00') to UTC ISO."""
    if not date_str:
        return None
    try:
        from datetime import datetime, timedelta, timezone
        m = re.match(r"(.+?)([+-]\d{2}):(\d{2})$", date_str)
        if not m:
            return date_str
        base, oh, om = m.group(1), int(m.group(2)), int(m.group(3))
        dt = datetime.fromisoformat(base)
        dt_utc = dt - timedelta(hours=oh, minutes=om)  # signed hours: -04:00 => add 4h
        return dt_utc.replace(tzinfo=timezone.utc).isoformat(timespec="minutes")
    except Exception:
        return date_str


def collect():
    """Fetch the weekly calendar feed → data/calendar/events_current.json (merged)."""
    http = HttpSession(timeout=60, max_retries=1)
    raw = _fetch_feed(http)
    events = []
    for e in raw:
        title = (e.get("title") or "").strip()
        country = (e.get("country") or "").upper().strip()
        if country == "ALL":
            country = "Global"
        events.append({
            "title": title,
            "country": country,
            "date_utc": _iso_to_utc(e.get("date")),
            "impact": e.get("impact"),
            "forecast": (e.get("forecast") or "").strip(),
            "previous": (e.get("previous") or "").strip(),
            "actual": "",
        })
    # Merge with previously collected events (idempotent, keyed by title+time+country)
    path = os.path.join(DATA_DIR, "calendar", "events_current.json")
    prior = load_json(path, default=[])
    prior_map = {(x["title"], x["date_utc"], x["country"]): x for x in prior}
    for ev in events:
        key = (ev["title"], ev["date_utc"], ev["country"])
        old = prior_map.get(key)
        if old:
            ev["actual"] = old.get("actual", "") or ev.get("actual", "")
        prior_map[key] = ev
    merged = list(prior_map.values())
    # Keep only events in a +/- 45 day window to keep the dataset lean
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    window = []
    for ev in merged:
        try:
            dt = datetime.fromisoformat((ev.get("date_utc") or "").replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=None)
            if abs((dt.replace(tzinfo=None) - now).days) <= 45:
                window.append(ev)
        except Exception:
            window.append(ev)
    save_json(path, window)
    high = sum(1 for e in window if e["impact"] == "High")
    log(f"Calendar: {len(window)} events (High={high}), merged with prior actuals")
    return {"events": len(window), "high": high}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))