# Core scoring engine — applies the Bulls & Bears rule:
#   Actual vs previous per scorecard direction → +1 / -1 / 0 scaled by weight.
#   Currency score = 5 + 5 * (netBuffWeight / totalEligibleWeight), clamped 0-10.
import os
import sys
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, load_scorecard, log, DATA_DIR, now_iso


def norm_num(text):
    """Parse numbers out of feed strings: '3.4%', '-1.4M', '2.48T', '805B'."""
    if text is None:
        return None
    t = str(text).replace(",", "").strip()
    m = re.search(r"[-+]?\d*\.?\d+", t)
    if not m:
        return None
    val = float(m.group(0))
    tup = t.upper()
    if "K" in tup:
        val *= 1_000
    elif "M" in tup:
        val *= 1_000_000
    elif "B" in tup:
        val *= 1_000_000_000
    elif "T" in tup:
        val *= 1_000_000_000_000
    return val


def decide(actual, previous, direction):
    """Golden rule: actual vs previous → +1 / -1 / 0."""
    a = norm_num(actual) if actual is not None else None
    p = norm_num(previous) if previous is not None else None
    if a is None or p is None or a == p:
        return 0
    if direction == "higher_is_bullish":
        return 1 if a > p else -1
    if direction == "lower_is_bullish":
        return 1 if a < p else -1
    return 0
# Currency -> indicator keyword matchers (feed titles → scorecard dataPoint)
_TITLE_MATCHERS = {
    "USD": {
        "us_fed_funds": ["Federal Funds Rate", "FOMC", "Fed Interest Rate", "Fed Funds"],
        "us_nfp": ["Non-Farm Employment Change", "Nonfarm", "Non-Farm Payrolls"],
        "us_unemployment": ["Unemployment Rate"],
        "us_ahe": ["Average Hourly Earnings"],
        "us_cpi": ["CPI m/m", "CPI y/y", "Core CPI m/m", "Core CPI y/y", "CPI x"],
        "us_pce": ["Core PCE", "PCE Price"],
        "us_gdp": ["GDP q/q", "GDP y/y", "Advance GDP", "Gross Domestic Product"],
        "us_ism": ["ISM Manufacturing", "ISM Services"],
        "us_retail": ["Retail Sales"],
        "us_adp": ["ADP Non-Farm Employment Change", "ADP Employment", "ADP Nonfarm"],
        "us_claims": ["Initial Jobless Claims", "Jobless Claims", "Unemployment Claims"],
        "us_ppi": ["PPI m/m", "PPI y/y", "Core PPI", "Producer Prices"],
        "us_confidence": ["CB Consumer Confidence", "Michigan Consumer Sentiment", "UoM Consumer Sentiment", "Consumer Confidence"],
        "us_housing": ["Building Permits", "Housing Starts", "New Home Sales", "Existing Home Sales"],
        "us_trade": ["Trade Balance"],
    },
    "EUR": {
        "eu_ecb_rate": ["ECB Interest Rate", "Main Refinancing", "ECB Press Conference", "ECB Monetary Policy", "ECB Rate", "ECB Statement"],
        "eu_cpi_flash": ["CPI Flash", "HICP"],
        "eu_de_pmi": ["German Flash Manufacturing PMI", "German Flash Services PMI", "German Manufacturing PMI", "German Services PMI", "German Flash Manufacturing", "German Flash Services"],
        "eu_ifo": ["IFO Business Climate", "IFO"],
        "eu_zew": ["ZEW Economic Sentiment"],
        "eu_gdp": ["Revised GDP q/q", "GDP q/q", "GDP y/y", "Gross Domestic Product", "Final GDP"],
        "eu_employment_change": ["Employment Change"],
        "eu_unemployment": ["Unemployment Rate"],
        "eu_de_indprod": ["German Industrial Production", "Industrial Production m/m"],
        "eu_retail": ["Retail Sales"],
    },
    "GBP": {
        "gb_bank_rate": ["Bank of England Bank Rate", "Official Bank Rate", "MPC", "BoE Interest Rate", "BoE Bank Rate"],
        "gb_cpi": ["CPI y/y", "Core CPI y/y", "CPI"],
        "gb_employment_change": ["Employment Change"],
        "gb_claimants": ["Claimant Count Change"],
        "gb_unemployment": ["Unemployment Rate"],
        "gb_average_earnings": ["Average Earnings Index", "Average Earnings"],
        "gb_gdp": ["GDP m/m", "GDP q/q", "GDP y/y", "Gross Domestic Product"],
        "gb_pmi": ["Flash Manufacturing PMI", "Flash Services PMI", "Flash Manufacturing", "Flash Services"],
        "gb_retail": ["Retail Sales"],
    },
    "AUD": {
        "au_cash_rate": ["RBA Interest Rate", "Cash Rate", "RBA Rate Statement", "RBA Monetary Policy", "RBA", "Official Cash Rate"],
        "au_cpi": ["CPI q/q", "CPI y/y", "Trimmed Mean CPI"],
        "au_employment": ["Employment Change"],
        "au_unemployment": ["Unemployment Rate"],
        "au_retail": ["Retail Sales"],
        "au_gdp": ["GDP q/q", "Gross Domestic Product"],
        "au_trade": ["Trade Balance"],
    },
    "NZD": {
        "nz_ocr": ["RBNZ", "OCR", "Official Cash Rate"],
        "nz_cpi": ["CPI q/q", "CPI y/y", "CPI"],
        "nz_employment": ["Employment Change"],
        "nz_unemployment": ["Unemployment Rate"],
        "nz_gdp": ["GDP q/q", "Gross Domestic Product"],
        "nz_gdt": ["GlobalDairyTrade", "GDT"],
    },
    "CAD": {
        "ca_overnight": ["BoC Interest Rate", "Overnight Rate", "Bank of Canada Rate", "BoC Rate", "BoC"],
        "ca_employment": ["Employment Change"],
        "ca_unemployment": ["Unemployment Rate"],
        "ca_cpi": ["CPI m/m", "CPI y/y", "Median CPI", "Trimmed CPI", "Core CPI"],
        "ca_gdp": ["GDP m/m", "Gross Domestic Product"],
        "ca_retail": ["Retail Sales"],
        "ca_trade": ["Trade Balance"],
    },
    "JPY": {
        "jp_boj": ["BoJ Policy Rate", "BoJ Interest Rate", "BoJ Monetary Policy", "BoJ Press Conference", "BoJ Rate"],
        "jp_core_cpi": ["Core CPI y/y", "Tokyo Core CPI", "Core CPI", "National Core CPI"],
        "jp_gdp": ["GDP q/q", "GDP y/y", "Final GDP", "Gross Domestic Product"],
        "jp_tankan": ["Tankan"],
        "jp_trade": ["Trade Balance"],
        "jp_cash_earnings": ["Average Cash Earnings"],
    },
    "CHF": {
        "ch_snb": ["SNB Policy Rate", "SNB Interest Rate", "SNB Monetary Policy", "SNB Rate", "Swiss National Bank"],
        "ch_cpi": ["CPI m/m", "CPI y/y", "CPI"],
        "ch_pmi": ["Manufacturing PMI", "Procure.ch", "SVME"],
        "ch_kof": ["KOF"],
        "ch_reserves": ["Foreign Currency Reserves"],
    },
    "CNY": {
        "cn_lpr": ["Loan Prime Rate", "LPR", "PBOC"],
        "cn_pmi": ["Manufacturing PMI", "NBS Manufact", "Caixin Manufact"],
        "cn_cpi_ppi": ["CPI y/y", "PPI y/y"],
        "cn_indprod": ["Industrial Production"],
        "cn_gdp": ["GDP q/q", "GDP y/y", "Gross Domestic Product"],
        "cn_trade": ["Trade Balance", "Exports", "Imports"],
    },
}


def match_data_point(sc, currency, title):
    """Map a calendar event title to a scorecard dataPoint for a currency."""
    idx = sc["currencies"].get(currency, {}).get("_index", {})
    matchers = _TITLE_MATCHERS.get(currency, {})
    tl = title.lower()
    for dp_id, keywords in matchers.items():
        for kw in keywords:
            if kw.lower() in tl:
                return idx.get(dp_id)
    return None


def _events():
    evs = load_json(os.path.join(DATA_DIR, "calendar", "events_current.json"), default=[])
    evs += load_json(os.path.join(DATA_DIR, "calendar", "fred_events.json"), default=[])
    return evs


def score_currencies():
    sc = load_scorecard()
    bands = sc.get("bands", {})
    out = {}
    detail = {}
    evs = _events()
    for event in evs:
        country = event.get("country")
        title = event.get("title", "")
        actual = event.get("actual")
        if country not in ("USD", "EUR", "GBP", "AUD", "NZD", "CAD", "JPY", "CHF", "CNY"):
            continue
        if not actual:
            continue
        dp = match_data_point(sc, country, title)
        if not dp:
            continue
        sign = decide(actual, event.get("previous"), dp["direction"])
        weight = dp["weight"]
        verdict = "neutral" if sign == 0 else ("bullish" if sign > 0 else "bearish")
        rec = {
            "event": title, "date": event.get("date_utc"), "impact": event.get("impact"),
            "actual": str(actual), "previous": str(event.get("previous", "")),
            "dataPoint": dp["name"], "direction": dp["direction"],
            "sign": sign, "weight": weight, "verdict": verdict,
        }
        detail.setdefault(country, []).append(rec)
    for currency, cur in sc["currencies"].items():
        scored = [d for d in detail.get(currency, []) if d["sign"] != 0]
        eligible = detail.get(currency, [])
        net = sum(d["sign"] * d["weight"] for d in scored)
        total_w = sum(d["weight"] for d in eligible) or 1.0
        ratio = net / total_w
        raw = 5.0 + 5.0 * ratio
        score = max(0.0, min(10.0, raw))
        out[currency] = {
            "score": round(score, 2),
            "band": _band_for(score, bands),
            "net": round(net, 2),
            "scored_points": len(scored),
            "eligible_points": len(eligible),
            "top_drivers": sorted(
                [{"event": d["event"], "verdict": d["verdict"],
                  "weighted": round(d["sign"] * d["weight"], 2), "date": d["date"]}
                 for d in scored],
                key=lambda x: abs(x["weighted"]), reverse=True)[:8],
        }
    payload = {
        "meta": {"updated": now_iso(), "method": "calendar + COT (calendar part)"},
        "currencies": out,
        "band_scale": bands,
        "detail": detail,
    }
    save_json(os.path.join(DATA_DIR, "bias", "currencies.json"), payload)
    log("Currency scoring: " + ", ".join(f"{c}={v['score']}({v['band']})" for c, v in out.items()))
    return out


def _band_for(score, bands=None):
    if score <= 2:
        return "Very Bearish"
    if score <= 4:
        return "Bearish"
    if score < 6:
        return "Neutral"
    if score <= 7:
        return "Bullish"
    return "Very Bullish"


if __name__ == "__main__":
    print(json.dumps(score_currencies(), indent=2))