# Core scoring engine v2 — applies the Bulls & Bears rule:
#   A data point is scored ONLY when published actual differs from previous
#   (unchanged = 0). Sign comes from actual-vs-previous per scorecard direction;
#   magnitude is scaled by impact weight, recency decay and (when a forecast
#   exists) forecast confirmation. COT positioning blends into core currencies.
#   Currency score = 5 + 5 * (netWeight / fullConfiguredWeight), plus a thin-data
#   momentum guard, clamped 0-10. A coverage % is reported alongside every score.
import os
import sys
import json
import re
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, load_scorecard, log, DATA_DIR, now_iso

DECAY_BASE = 0.92      # weekly decay factor
MIN_DECAY = 0.25       # floor so older prints still count a little
THIN_COVERAGE = 0.35   # below this coverage we add the momentum guard
COT_CURRENCY_WEIGHT = 0.3


def _parse_decimal(s):
    """Handle European numeric formatting (2,5 / 1.234,56 / (1,2)) for sources
    like Eurostat/German data, plus standard 1,234.56. Operates on the numeric
    body only so trailing units ('%', 'B') never break the conversion."""
    s = str(s).replace("\u00a0", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    m = re.search(r"[-+]?\d[\d.,]*", s)
    if not m:
        return s
    body = m.group(0)
    if "," in body and "." not in body:
        if re.match(r"^-?\d+,\d{1,2}$", body):          # European decimal 2,5
            body = body.replace(",", ".")
        else:                                            # thousands 1,234,567
            body = body.replace(",", "")
    elif "," in body and "." in body:
        if re.match(r"^-?\d{1,3}(\.\d{3})+(,\d{1,2})$", body):  # 1.234,56 -> 1234.56
            body = body.replace(".", "").replace(",", ".")
        else:                                            # 1,234.56 -> 1234.56
            body = body.replace(",", "")
    return s[:m.start()] + body + s[m.end():]


def norm_num(text):
    """Parse numbers out of feed strings: '3.4%', '-1.4M', '2.48T', '805B', '2,5%'."""
    if text is None or str(text).strip() in ("", "-"):
        return None
    t = _parse_decimal(str(text))
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


def _weeks_old(date_utc):
    try:
        d = datetime.fromisoformat((date_utc or "").replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - d).days / 7.0)
    except Exception:
        return 0.0


def _decay(weeks):
    return max(MIN_DECAY, DECAY_BASE ** weeks)


def _forecast_factor(actual, forecast, direction, sign):
    """Forecast confirmation — modulates magnitude, never flips the sign.
    Beat previous AND beat/align forecast = full weight; beat previous but MISS
    forecast = 0.7x (surprise was less clean)."""
    if sign == 0 or not forecast:
        return 1.0
    a = norm_num(actual)
    f = norm_num(forecast)
    if a is None or f is None:
        return 1.0
    if sign > 0:
        return 1.0 if a >= f else 0.7
    return 1.0 if a <= f else 0.7


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
# Currency -> indicator keyword matchers (calendar titles → scorecard dataPoint)
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
        "eu_cpi_flash": ["CPI Flash", "HICP", "Euro Zone CPI", "EU CPI"],
        "eu_de_pmi": ["German Flash Manufacturing PMI", "German Flash Services PMI", "German Manufacturing PMI", "German Services PMI", "German Flash Manufacturing", "German Flash Services"],
        "eu_ifo": ["IFO Business Climate", "IFO"],
        "eu_zew": ["ZEW Economic Sentiment"],
        "eu_gdp": ["Revised GDP q/q", "GDP q/q", "GDP y/y", "Gross Domestic Product", "Final GDP", "Euro Zone GDP"],
        "eu_employment_change": ["Employment Change"],
        "eu_unemployment": ["Unemployment Rate"],
        "eu_de_indprod": ["German Industrial Production", "Industrial Production m/m", "Euro Zone Industrial"],
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
        "jp_core_cpi": ["Core CPI y/y", "Tokyo Core CPI", "Core CPI", "National Core CPI", "Japan CPI"],
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
        "cn_cpi_ppi": ["CPI y/y", "PPI y/y", "China CPI", "Chinese CPI"],
        "cn_indprod": ["Industrial Production"],
        "cn_gdp": ["GDP q/q", "GDP y/y", "Gross Domestic Product"],
        "cn_trade": ["Trade Balance", "Exports", "Imports"],
    },
    "MXN": {"mx_rate": ["Interest Rate Decision", "Banxico", "Mexican Interest Rate", "Overnight Rate"],
            "mx_cpi": ["CPI y/y", "CPI"], "mx_gdp": ["GDP q/q", "Gross Domestic Product"],
            "mx_trade": ["Trade Balance"], "mx_unemployment": ["Unemployment Rate"]},
    "BRL": {"br_rate": ["Selic", "Brazilian Interest Rate", "COPOM", "Interest Rate Decision"],
            "br_cpi": ["CPI y/y", "IPCA", "Brazilian CPI"], "br_gdp": ["GDP q/q", "Gross Domestic Product"],
            "br_trade": ["Trade Balance"], "br_unemployment": ["Unemployment Rate"]},
    "TRY": {"tr_rate": ["Interest Rate Decision", "CBRT", "Turkish Interest Rate", "One-Week Repo"],
            "tr_cpi": ["CPI y/y", "CPI"], "tr_gdp": ["GDP q/q", "Gross Domestic Product"],
            "tr_trade": ["Trade Balance"]},
    "ZAR": {"za_rate": ["Repo Rate", "South African Interest Rate", "SARB", "Interest Rate Decision"],
            "za_cpi": ["CPI y/y", "CPI"], "za_gdp": ["GDP q/q", "Gross Domestic Product"],
            "za_trade": ["Trade Balance"], "za_unemployment": ["Unemployment Rate"]},
    "PLN": {"pl_rate": ["Interest Rate Decision", "Polish Interest Rate", "Reference Rate"],
            "pl_cpi": ["CPI y/y", "CPI"], "pl_gdp": ["GDP q/q", "Gross Domestic Product"],
            "pl_trade": ["Trade Balance"]},
    "HUF": {"hu_rate": ["Interest Rate Decision", "Hungarian Interest Rate", "Base Rate"],
            "hu_cpi": ["CPI y/y", "CPI"], "hu_gdp": ["GDP q/q", "Gross Domestic Product"]},
    "CZK": {"cz_rate": ["Interest Rate Decision", "Czech Interest Rate", "Repo Rate"],
            "cz_cpi": ["CPI y/y", "CPI"], "cz_gdp": ["GDP q/q", "Gross Domestic Product"]},
    "DKK": {"dk_rate": ["Interest Rate Decision", "Danish Interest Rate", "Certificate of Deposit"],
            "dk_cpi": ["CPI y/y", "CPI"], "dk_gdp": ["GDP q/q", "Gross Domestic Product"]},
    "NOK": {"no_rate": ["Interest Rate Decision", "Norwegian Interest Rate", "Overnight Deposit"],
            "no_cpi": ["CPI y/y", "CPI"], "no_gdp": ["GDP q/q", "Gross Domestic Product"],
            "no_trade": ["Trade Balance"]},
    "SEK": {"se_rate": ["Interest Rate Decision", "Swedish Interest Rate", "Repo Rate"],
            "se_cpi": ["CPI y/y", "CPIF", "Swedish CPI"], "se_gdp": ["GDP q/q", "Gross Domestic Product"],
            "se_trade": ["Trade Balance"]},
    "SGD": {"sg_rate": ["MAS", "Monetary Policy Statement", "Singapore Interest"],
            "sg_cpi": ["CPI y/y", "CPI"], "sg_gdp": ["GDP q/q", "Gross Domestic Product", "Advance GDP"],
            "sg_trade": ["Trade Balance"]},
    "HKD": {"hk_cpi": ["CPI y/y", "CPI"], "hk_gdp": ["GDP q/q", "Gross Domestic Product"],
            "hk_trade": ["Trade Balance"], "hk_retail": ["Retail Sales"]},
}
def _normalize_title(title):
    """Unify calendar title styles: 'GDP MoM JUL' -> 'GDP m/m jul' so keyword
    matchers written against 'm/m' also catch sources using 'MoM'/'YoY'."""
    t = (title or "").lower()
    t = re.sub(r"\bmom\b", "m/m", t)
    t = re.sub(r"\byoy\b", "y/y", t)
    t = re.sub(r"\booq\b", "q/q", t)
    return t


def match_data_point(sc, currency, title):
    """Map a calendar event title to a scorecard dataPoint for a currency."""
    idx = sc["currencies"].get(currency, {}).get("_index", {})
    matchers = _TITLE_MATCHERS.get(currency, {})
    tl = _normalize_title(title)
    for dp_id, keywords in matchers.items():
        for kw in keywords:
            if kw.lower() in tl:
                return idx.get(dp_id)
    return None


def _events():
    evs = load_json(os.path.join(DATA_DIR, "calendar", "events_current.json"), default=[])
    evs += load_json(os.path.join(DATA_DIR, "calendar", "fred_events.json"), default=[])
    return evs


def _cot_tilt_for_currency(currency):
    """Load COT tilt for a currency from the CFTC bias file (secondary input)."""
    cot = load_json(os.path.join(DATA_DIR, "cftc", "cot_bias.json"), default={})
    ins = (cot.get("instruments") or {}).get(currency, {})
    tilt = (ins.get("tilt") or {}).get("tilt", 0)
    return float(tilt or 0)


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
        if country not in sc["currencies"]:
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
            "forecast": str(event.get("forecast", "")), "revision": str(event.get("revision", "")),
            "dataPoint": dp["name"], "direction": dp["direction"],
            "sign": sign, "weight": weight, "verdict": verdict,
        }
        detail.setdefault(country, []).append(rec)

    for currency, cur in sc["currencies"].items():
        cfg_points = cur.get("dataPoints", [])
        total_cfg = sum(p.get("weight", 0) for p in cfg_points) or 1.0
        pts = detail.get(currency, [])
        contribs = []
        for d in pts:
            if d["sign"] == 0:
                continue
            w = d["weight"]
            decay = _decay(_weeks_old(d.get("date")))
            factor = _forecast_factor(d.get("actual"), d.get("forecast"), d["direction"], d["sign"])
            contribs.append((d["sign"] * w * decay * factor, d))
        net = sum(c for c, _ in contribs)
        # COT positioning (secondary input) for currencies with CFTC coverage
        cot_tilt = _cot_tilt_for_currency(currency)
        net += COT_CURRENCY_WEIGHT * cot_tilt

        eligible_weight = sum(d["weight"] for d in pts)
        coverage = min(1.0, eligible_weight / total_cfg)
        ratio = net / total_cfg
        raw = 5.0 + 5.0 * ratio
        # thin-data momentum guard: show direction without saturating
        if coverage < THIN_COVERAGE and eligible_weight > 0:
            elig_ratio = net / eligible_weight
            raw += max(-0.5, min(0.5, 0.5 * elig_ratio))
        score = max(0.0, min(10.0, raw))
        out[currency] = {
            "score": round(score, 2),
            "band": _band_for(score, bands),
            "net": round(net, 2),
            "coverage": round(coverage * 100, 1),
            "total_configured_weight": round(total_cfg, 2),
            "scored_points": len([c for c, _ in contribs if c != 0]),
            "eligible_points": len(pts),
            "cot_tilt": cot_tilt,
            "top_drivers": sorted(
                [{"event": d["event"], "verdict": d["verdict"],
                  "weighted": round(c, 2), "date": d["date"]}
                 for c, d in contribs],
                key=lambda x: abs(x["weighted"]), reverse=True)[:8],
        }
    payload = {
        "meta": {"updated": now_iso(), "method": "calendar + COT (v2: decay + forecast confirmation + full-weight normalization)"},
        "currencies": out,
        "band_scale": bands,
        "detail": detail,
    }
    save_json(os.path.join(DATA_DIR, "bias", "currencies.json"), payload)
    log("Currency scoring: " + ", ".join(f"{c}={v['score']}({v['band']}, cov{v['coverage']}%)" for c, v in out.items()))
    return out


def attach_event_verdicts():
    """Attach bullish/bearish/neutral verdict per released calendar event so the
    Calendar + Data tabs display the direction the scoring engine derives."""
    sc = load_scorecard()
    path = os.path.join(DATA_DIR, "calendar", "events_current.json")
    evs = load_json(path, default=[])
    changed = 0
    for ev in evs:
        if not ev.get("actual") or not ev.get("previous"):
            continue
        dp = match_data_point(sc, ev.get("country"), ev.get("title"))
        if not dp:
            continue
        sign = decide(ev.get("actual"), ev.get("previous"), dp["direction"])
        verdict = "neutral" if sign == 0 else ("bullish" if sign > 0 else "bearish")
        if ev.get("verdict") != verdict:
            ev["verdict"] = verdict
            changed += 1
    save_json(path, evs)
    log(f"Event verdicts: {changed} updated/{len(evs)} events")
    return changed


if __name__ == "__main__":
    print(json.dumps(score_currencies(), indent=1)[:2000])