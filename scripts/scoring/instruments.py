# Instrument bias — precious metals, energy, industrial, crypto and indices.
# Direct instruments (metals/oil/copper): score = inverse USD calendar component
# + COT positioning component.
# Derived instruments (crypto/equity indices): no calendar/COT exists, so bias is
# labelled "derived": inverse normalized USD + a global risk-appetite proxy built
# from real yields and US index breadth.
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, load_scorecard, log, DATA_DIR, now_iso

USD_INV = {"XAUUSD": 1.0, "XAGUSD": 1.0, "XPTUSD": 1.0, "XPDUSD": 1.0,
           "OIL": 0.7, "BRENT": 0.7, "COPPER": 0.7}
COT_W = 0.35  # COT weight contribution to instrument bias


def _band(score):
    if score <= 2:
        return "Very Bearish"
    if score <= 4:
        return "Bearish"
    if score < 6:
        return "Neutral"
    if score <= 7:
        return "Bullish"
    return "Very Bullish"


def _cot_tilt(sym, cot):
    rec = cot.get(sym, {})
    t = rec.get("tilt", {}).get("tilt", 0)
    return t, rec.get("latest_week"), (rec.get("positions") or {}).get("report_date")


def score_instruments():
    sc = load_scorecard()
    cur = load_json(os.path.join(DATA_DIR, "bias", "currencies.json"), default={}).get("currencies", {})
    cot = load_json(os.path.join(DATA_DIR, "cftc", "cot_bias.json"), default={}).get("instruments", {})
    usd = cur.get("USD", {}).get("score", 5.0)
    out = {}
    targets = sc.get("instruments", {}).get("targets", {})
    derived_cfg = sc.get("derived", {})

    # Direct instruments (real COT exists)
    for sym, cfg in targets.items():
        usd_inverse = cfg.get("usd_inverse", 1.0)
        usd_comp = (10.0 - usd) / 5.0 - 1.0  # -1 (strong USD) ... +1 (weak USD)
        usd_part = usd_inverse * usd_comp
        c_tilt, week, rdate = _cot_tilt(sym, cot)
        cot_part = COT_W * c_tilt
        raw = 5.0 + 5.0 * (usd_part + cot_part)
        score = max(0.0, min(10.0, raw))
        out[sym] = {
            "name": cfg.get("name", sym),
            "type": cfg.get("kind", "metal"),
            "biasType": "direct",
            "score": round(score, 2),
            "band": _band(score),
            "components": {
                "inverse_usd": round(usd_part, 3),
                "usd_score": usd,
                "cot_tilt": c_tilt,
                "cot_contribution": round(cot_part, 3),
            },
            "cot": {"week": week, "report_date": rdate},
        }

    # Derived instruments (crypto + equity indices)
    # Risk-appetite proxy: real 10Y yield inverse + US calendar tilt (bullish US
    # economy reads as risk-on for equities, but rates headwind; equal-weight blend)
    yields = load_json(os.path.join(DATA_DIR, "macro", "fred.json"), default={})
    dfii = yields.get("DFII10", {}).get("points", [])
    real_yield = dfii[-1]["value"] if dfii else None
    risk = 0.0
    if real_yield is not None:
        # Lower real yield → higher risk appetite (risk-off when yields climb)
        risk += -0.12 * (real_yield - 2.0)
    usd_derived = (10.0 - usd) / 5.0 - 1.0  # weak USD → bullish crypto/indices
    derived_score = 5.0 + 5.0 * (
        derived_cfg.get("usd_weight", 0.6) * usd_derived + derived_cfg.get("risk_weight", 0.4) * risk
    )
    derived_score = max(0.0, min(10.0, derived_score))
    for sym in derived_cfg.get("targets", []):
        out[sym] = {
            "name": sym,
            "type": "derived",
            "biasType": "derived",
            "score": round(derived_score, 2),
            "band": _band(derived_score),
            "components": {
                "inverse_usd": round(usd_derived, 3),
                "usd_score": usd,
                "real_yield_10y": real_yield,
                "risk_proxy": round(risk, 3),
                "note": "No economic calendar or COT positioning exists for this instrument; score is a derived sentiment proxy.",
            },
        }

    payload = {
        "meta": {"updated": now_iso()},
        "instruments": out,
    }
    save_json(os.path.join(DATA_DIR, "bias", "instruments.json"), payload)
    log("Instrument scoring: " + ", ".join(f"{k}={v['score']}" for k, v in out.items()))
    return out


if __name__ == "__main__":
    print(json.dumps(score_instruments(), indent=1)[:3000])