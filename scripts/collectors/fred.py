# FRED (US Federal Reserve) collector — US macro indicators + Treasury yields
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import HttpSession, load_json, save_json, log, DATA_DIR, now_iso

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

FRED_SERIES = {
    # Interest rates / policy
    "FEDFUNDS": {"name": "Federal Funds Effective Rate", "category": "rate", "unit": "percent"},
    "DFF": {"name": "Federal Funds Target Range Upper Limit", "category": "rate", "unit": "percent"},
    # Treasury yields (confirmation/visuals only — never scored)
    "DGS3MO": {"name": "3-Month Treasury Yield", "category": "yield", "unit": "percent"},
    "DGS2": {"name": "2-Year Treasury Yield", "category": "yield", "unit": "percent"},
    "DGS5": {"name": "5-Year Treasury Yield", "category": "yield", "unit": "percent"},
    "DGS10": {"name": "10-Year Treasury Yield", "category": "yield", "unit": "percent"},
    "DGS30": {"name": "30-Year Treasury Yield", "category": "yield", "unit": "percent"},
    "DFII10": {"name": "10-Year Constant Maturity Real Yield", "category": "yield", "unit": "percent"},
    # Inflation
    "CPIAUCSL": {"name": "CPI All Urban Consumers", "category": "inflation", "unit": "index", "freq": "monthly"},
    "CPILFESL": {"name": "Core CPI (ex food & energy)", "category": "inflation", "unit": "index", "freq": "monthly"},
    "PCEPI": {"name": "PCE Price Index", "category": "inflation", "unit": "index", "freq": "monthly"},
    "PCEPILFE": {"name": "Core PCE Price Index", "category": "inflation", "unit": "index", "freq": "monthly"},
    "PPIACO": {"name": "PPI All Commodities", "category": "inflation", "unit": "index", "freq": "monthly"},
    "PPIFES": {"name": "Core PPI (ex food & energy)", "category": "inflation", "unit": "index", "freq": "monthly"},
    # Labor
    "PAYEMS": {"name": "All Employees Total Nonfarm", "category": "labor", "unit": "thousands", "freq": "monthly"},
    "UNRATE": {"name": "Civilian Unemployment Rate", "category": "labor", "unit": "percent", "freq": "monthly"},
    "ICSA": {"name": "Initial Claims Seasonally Adjusted", "category": "labor", "unit": "thousands", "freq": "weekly"},
    # Consumption / industry / growth / trade / housing / sentiment
    "RSAFS": {"name": "Retail Sales: Total", "category": "consumption", "unit": "millions", "freq": "monthly"},
    "GDPC1": {"name": "Real GDP", "category": "growth", "unit": "billions", "freq": "quarterly"},
    "BOPGSTB": {"name": "Balance on Goods & Services", "category": "trade", "unit": "millions", "freq": "monthly"},
    "HOUST": {"name": "Housing Starts: New Privately Owned", "category": "housing", "unit": "thousands", "freq": "monthly"},
    "PERMIT": {"name": "Building Permits: New Privately Owned", "category": "housing", "unit": "thousands", "freq": "monthly"},
    "UMCSENT": {"name": "University of Michigan Consumer Sentiment", "category": "sentiment", "unit": "index", "freq": "monthly"},
    "INDPRO": {"name": "Industrial Production Index", "category": "industry", "unit": "index", "freq": "monthly"},
    "M2SL": {"name": "M2 Money Stock", "category": "liquidity", "unit": "billions", "freq": "monthly"},
    # International (OECD-MEI) — fresh series feeding non-US currency scoring
    "LRHUTTTTGBM156S": {"name": "UK Unemployment Rate", "category": "international", "unit": "percent", "freq": "monthly"},
    "LRHUTTTTDEM156S": {"name": "Germany Unemployment Rate", "category": "international", "unit": "percent", "freq": "monthly"},
    "LRHUTTTTJPM156S": {"name": "Japan Unemployment Rate", "category": "international", "unit": "percent", "freq": "monthly"},
    "LRHUTTTTCAM156S": {"name": "Canada Unemployment Rate", "category": "international", "unit": "percent", "freq": "monthly"},
}


def _clean_value(value):
    """FRED returns strings like '.', '' or numbers — normalize to float or None."""
    if value is None:
        return None
    value = str(value).strip()
    if value in ("", ".", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_series(http, api_key, series_id, observation_start=None, observation_end=None, limit=None):
    params = {"series_id": series_id, "api_key": api_key, "file_type": "json", "sort_order": "asc"}
    if observation_start:
        params["observation_start"] = observation_start
    if observation_end:
        params["observation_end"] = observation_end
    if limit:
        params["limit"] = limit
    data = http.get_json(FRED_BASE, params=params)
    points = []
    for obs in data.get("observations", []):
        val = _clean_value(obs.get("value"))
        if val is not None:
            points.append({"date": obs["date"], "value": val})
    return points
def collect(api_key):
    """Fetch all configured FRED series → data/macro/fred.json. Returns summary dict."""
    http = HttpSession(timeout=60, max_retries=3)
    path = os.path.join(DATA_DIR, "macro", "fred.json")
    store = load_json(path, default={})
    summary = {}
    for series_id, meta in FRED_SERIES.items():
        try:
            points = fetch_series(http, api_key, series_id)
            if not points:
                log(f"FRED {series_id}: no data", "WARN")
                continue
            dedup = {}
            for p in points:
                dedup[p["date"]] = p["value"]
            cleaned = [{"date": d, "value": v} for d, v in sorted(dedup.items())]
            # Cap history: keep the most recent 2600 observations per series.
            # This keeps the repo database lean while retaining years of depth
            # (daily yields ~10y, monthly CPI ~216y, weekly claims ~50y).
            if len(cleaned) > 2600:
                cleaned = cleaned[-2600:]
            store[series_id] = {"meta": meta, "points": cleaned, "updated": now_iso()}
            summary[series_id] = {"points": len(cleaned), "last": cleaned[-1]}
            log(f"FRED {series_id}: {len(cleaned)} points, last={cleaned[-1]['date']} val={cleaned[-1]['value']}")
        except Exception as exc:
            log(f"FRED {series_id} failed: {exc}", "ERROR")
    save_json(path, store)
    return {"collected": len(summary), "series": summary}


if __name__ == "__main__":
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    load_dotenv(env_path)
    key = os.environ.get("FRED_KEY", "")
    if not key:
        log("FRED_KEY not set", "ERROR")
        sys.exit(1)
    print(json.dumps(collect(key), indent=2)[:2000])