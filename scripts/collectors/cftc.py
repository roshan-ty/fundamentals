# CFTC COT collector — Legacy (currencies, metals, energy, indices) + Disaggregated + TFF
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, log, DATA_DIR, now_iso, HttpSession

BASE = "https://publicreporting.cftc.gov/resource/{dataset}.json"
LEGACY_ALL = "srt6-5q2f"
DISAGG_ALL = "rxbv-e226"
TFF_ALL = "udgc-27he"

# Instrument -> (field, match substrings) on the Legacy COT report
MARKETS = {
    "EUR": {"field": "contract_market_name", "match": ["EURO FX"]},
    "GBP": {"field": "contract_market_name", "match": ["BRITISH POUND"]},
    "JPY": {"field": "contract_market_name", "match": ["JAPANESE YEN"]},
    "CHF": {"field": "contract_market_name", "match": ["SWISS FRANC"]},
    "CAD": {"field": "contract_market_name", "match": ["CANADIAN DOLLAR"]},
    "AUD": {"field": "contract_market_name", "match": ["AUSTRALIAN DOLLAR"]},
    "NZD": {"field": "contract_market_name", "match": ["NEW ZEALAND"]},
    "MXN": {"field": "contract_market_name", "match": ["MEXICAN PESO"]},
    "BRL": {"field": "contract_market_name", "match": ["BRAZILIAN REAL"]},
    "CNY": {"field": "contract_market_name", "match": ["RENMINBI"]},
    "XAUUSD": {"field": "contract_market_name", "match": ["GOLD"], "exclude": ["MICRO", "PAX"]},
    "XAGUSD": {"field": "contract_market_name", "match": ["SILVER"], "exclude": ["MICRO"]},
    "XPTUSD": {"field": "contract_market_name", "match": ["PLATINUM"]},
    "XPDUSD": {"field": "contract_market_name", "match": ["PALLADIUM"]},
    "OIL": {"field": "contract_market_name", "match": ["CRUDE OIL, LIGHT SWEET-WTI"]},
    "BRENT": {"field": "contract_market_name", "match": ["BRENT LAST DAY"]},
    "COPPER": {"field": "contract_market_name", "match": ["COPPER- #1"]},
    "US500": {"field": "contract_market_name", "match": ["E-MINI S&P 500 INDEX"], "exclude": ["MICRO"]},
    "US100": {"field": "contract_market_name", "match": ["NASDAQ-100 Consolidated"]},
    "JP225": {"field": "contract_market_name", "match": ["NIKKEI STOCK AVERAGE YEN DENOM"]},
}


def _flt(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_date(ts):
    try:
        return str(ts)[:10]
    except Exception:
        return None
def _query(http, dataset, params, retries=6):
    url = BASE.format(dataset=dataset)
    last = None
    for attempt in range(retries):
        try:
            return http.get(url, params={"$limit": "40000", **params}, timeout=180).json()
        except Exception as exc:  # CFTC host is TLS-flaky; manual backoff
            last = exc
            log(f"CFTC retry {attempt + 1}/{retries}: {str(exc)[:100]}", "WARN")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"CFTC query failed: {last}")


def fetch_legacy(http):
    """Fetch latest Legacy COT rows filtered to our instruments; keep per-instrument history."""
    q_clauses = []
    for sym, cfg in MARKETS.items():
        for token in cfg["match"]:
            q_clauses.append(f"({cfg['field']} like '%{token}%')")
    where = " or ".join(q_clauses)
    rows = _query(http, LEGACY_ALL, {
        "$where": where,
        "$order": "report_date_as_yyyy_mm_dd DESC",
    })
    out = {}
    for row in rows:
        date = _to_date(row.get("report_date_as_yyyy_mm_dd"))
        if not date:
            continue
        name = (row.get("contract_market_name") or "").upper()
        for sym, cfg in MARKETS.items():
            if not any(token in name for token in cfg["match"]):
                continue
            if any(ex in name for ex in cfg.get("exclude", [])):
                continue
            rec = out.setdefault(sym, {"market": name, "history": {}, "_exact": {}})
            exact_hit = any(name == token.upper() for token in cfg["match"])
            existing = rec["history"].get(date)
            if existing and existing.get("_exact") and not exact_hit:
                continue  # keep the exact-name contract for this date
            rec["history"][date] = {
                "report_date": date,
                "_exact": exact_hit,
                "open_interest": _flt(row.get("open_interest_all")),
                "noncomm_long": _flt(row.get("noncomm_positions_long_all")),
                "noncomm_short": _flt(row.get("noncomm_positions_short_all")),
                "noncomm_spread": _flt(row.get("noncomm_postions_spread_all") or row.get("noncomm_positions_spread")),
                "comm_long": _flt(row.get("comm_positions_long_all")),
                "comm_short": _flt(row.get("comm_positions_short_all")),
                "nonreport_long": _flt(row.get("nonrept_positions_long_all")),
                "nonreport_short": _flt(row.get("nonrept_positions_short_all")),
                "change_oi": _flt(row.get("change_in_open_interest_all")),
                "change_noncomm_long": _flt(row.get("change_in_noncomm_long_all")),
                "change_noncomm_short": _flt(row.get("change_in_noncomm_short_all")),
                "change_comm_long": _flt(row.get("change_in_comm_long_all")),
                "change_comm_short": _flt(row.get("change_in_comm_short_all")),
            }
    # sort history ascending, clean helper flags, set latest
    for sym, rec in out.items():
        rec["_exact"].clear()
        for date, item in rec["history"].items():
            item.pop("_exact", None)
        rec["history"] = dict(sorted(rec["history"].items()))
        rec["latest"] = list(rec["history"].keys())[-1] if rec["history"] else ""
    return out


def collect():
    """Fetch COT legacy report → data/cftc/cot_legacy.json + summary."""
    http = HttpSession(timeout=180, max_retries=1)  # manual retry loop handles TLS flakiness
    result = fetch_legacy(http)
    payload = {
        "meta": {"updated": now_iso(), "note": "Commitment of Traders, legacy format"},
        "markets": result,
    }
    save_json(os.path.join(DATA_DIR, "cftc", "cot_legacy.json"), payload)
    counts = {sym: len(rec["history"]) for sym, rec in result.items()}
    latest_dates = {sym: rec["latest"] for sym, rec in result.items()}
    log(f"CFTC COT: {len(result)} instruments; latest dates: {latest_dates}")
    return {"instruments": len(result), "per_instrument_records": counts, "latest_dates": latest_dates}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2)[:2000])