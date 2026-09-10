# Actuals layer — matches economic calendar events to published actual values
# from official sources. Produces data/calendar/fred_events.json (US events with
# known actual vs previous) which the scoring engine consumes directly.
import os
import sys
import json
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, log, DATA_DIR, now_iso

US_INDICATORS = {
    # series_id: {name, kind, unit, direction-agnostic (scoring reads scorecard)}
    "CPIAUCSL": {"name": "CPI m/m", "kind": "mom_pct", "ref": "consumption inflation"},
    "CPILFESL": {"name": "Core CPI m/m", "kind": "mom_pct"},
    "PPIACO": {"name": "PPI m/m", "kind": "mom_pct"},
    "PPIFES": {"name": "Core PPI m/m", "kind": "mom_pct"},
    "PCEPILFE": {"name": "Core PCE Price Index m/m", "kind": "mom_pct"},
    "PAYEMS": {"name": "Non-Farm Employment Change", "kind": "level_chg", "unit_label": "K"},
    "UNRATE": {"name": "Unemployment Rate", "kind": "level"},
    "ICSA": {"name": "Initial Jobless Claims", "kind": "level"},
    "RSAFS": {"name": "Retail Sales m/m", "kind": "mom_pct"},
    "GDPC1": {"name": "GDP q/q annualized", "kind": "qoq_ann_pct"},
    "HOUST": {"name": "Housing Starts", "kind": "level"},
    "PERMIT": {"name": "Building Permits", "kind": "level"},
    "BOPGSTB": {"name": "Trade Balance", "kind": "level_signed"},
    "UMCSENT": {"name": "UoM Consumer Sentiment", "kind": "level"},
}


def _pct_change(prev, curr):
    if prev in (None, 0) or curr is None:
        return None
    return round((curr / prev - 1.0) * 100.0, 2)


def build_fred_events():
    """Derive dated US release 'events' with actual & previous from FRED series."""
    store = load_json(os.path.join(DATA_DIR, "macro", "fred.json"), default={})
    events = []
    for sid, meta in US_INDICATORS.items():
        sdata = store.get(sid)
        if not sdata or not sdata.get("points"):
            log(f"FRED actuals: missing series {sid}", "WARN")
            continue
        pts = sdata["points"]  # ascending by date
        vals = [(p["date"], p["value"]) for p in pts if p.get("value") is not None]
        kind = meta["kind"]
        # Build event per release: use latest observation for current, prior for previous
        for i in range(1, len(vals)):
            d_prev, v_prev = vals[i - 1]
            d_cur, v_cur = vals[i]
            if kind == "mom_pct":
                actual = _pct_change(v_prev, v_cur)
                prev_val = None
            elif kind == "qoq_ann_pct":
                if i >= 4:
                    actual = _pct_change(vals[i - 4][1], v_cur)
                    prev_val = None
                else:
                    continue
            elif kind == "level_chg":
                actual = round(v_cur - v_prev, 1)
                prev_val = None
            else:
                actual = v_cur
                prev_val = None
            if actual is None:
                continue
            events.append({
                "title": meta["name"],
                "country": "USD",
                "date_utc": d_cur + "T00:00:00+00:00",
                "impact": "High" if meta["name"] in (
                    "CPI m/m", "Core CPI m/m", "Non-Farm Employment Change",
                    "Unemployment Rate", "GDP q/q annualized") else "Medium",
                "actual": str(actual),
                "previous": str(prev_val) if prev_val is not None else (str(v_prev) if kind in ("level", "level_signed") else ""),
                "source_series": sid,
                "period": d_cur,
            })
    # Keep only the latest 2 releases per indicator
    by_title = {}
    for ev in events:
        by_title.setdefault(ev["title"], []).append(ev)
    latest = []
    for title, evs in by_title.items():
        evs.sort(key=lambda x: x["date_utc"])
        latest.extend(evs[-2:])
    latest.sort(key=lambda x: x["date_utc"])
    return latest


def collect():
    events = build_fred_events()
    save_json(os.path.join(DATA_DIR, "calendar", "fred_events.json"), events)
    log(f"FRED actuals: {len(events)} dated US events")
    return {"events": len(events), "titles": sorted({e['title'] for e in events})}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))