# COT component — positioning tilt from the Commitment of Traders report.
# For each instrument with COT coverage: the recent change in non-commercial
# (managed-money/large spec) net exposure vs the latest reading is turned into
# a +1 / -1 / 0 tilt, weighted lower than calendar data (COT is a secondary
# input to the bias score).
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, log, DATA_DIR, now_iso

# How this instrument's non-commercial positioning relates to bullish price bias,
# analogously to how central banks' reported positions tilt the underlying asset.
DIRECTIONS = {
    "EUR": "long_bullish", "GBP": "long_bullish", "JPY": "long_bullish",
    "CHF": "long_bullish", "CAD": "long_bullish", "AUD": "long_bullish",
    "NZD": "long_bullish", "MXN": "long_bullish", "BRL": "long_bullish",
    "CNY": "long_bullish", "XAUUSD": "long_bullish", "XAGUSD": "long_bullish",
    "XPTUSD": "long_bullish", "XPDUSD": "long_bullish", "OIL": "long_bullish",
    "BRENT": "long_bullish", "COPPER": "long_bullish",
    "US500": "long_bullish", "US100": "long_bullish", "JP225": "long_bullish",
}


def cot_tilt(sym, rec):
    """Return {'tilt': 1|-1|0, 'net': float, 'note': str} from COT history."""
    hist = rec.get("history", {})
    dates = sorted(hist.keys())
    if len(dates) < 2:
        return {"tilt": 0, "net": None, "note": "insufficient history"}
    last_d, prev_d = dates[-1], dates[-2]
    last, prev = hist[last_d], hist[prev_d]
    last_net = None
    if last.get("noncomm_long") is not None and last.get("noncomm_short") is not None:
        last_net = last["noncomm_long"] - last["noncomm_short"]
    prev_net = None
    if prev.get("noncomm_long") is not None and prev.get("noncomm_short") is not None:
        prev_net = prev["noncomm_long"] - prev["noncomm_short"]
    if last_net is None or prev_net is None:
        return {"tilt": 0, "net": last_net, "note": "missing positioning data"}
    delta = last_net - prev_net
    tilt = 1 if delta > 0 else (-1 if delta < 0 else 0)
    return {
        "tilt": tilt,
        "net": round(last_net, 0),
        "delta": round(delta, 0),
        "noncomm_long": last.get("noncomm_long"),
        "noncomm_short": last.get("noncomm_short"),
        "change_long": last.get("change_noncomm_long"),
        "change_short": last.get("change_noncomm_short"),
        "week": last_d,
        "note": "non-commercial net exposure " + ("expanded" if delta > 0 else ("shrank" if delta < 0 else "flat")),
    }


def collect():
    cot = load_json(os.path.join(DATA_DIR, "cftc", "cot_legacy.json"), default={}).get("markets", {})
    out = {}
    for sym, rec in cot.items():
        if sym not in DIRECTIONS:
            continue
        out[sym] = {
            "sym": sym,
            "market": rec.get("market"),
            "latest_week": rec.get("latest"),
            "tilt": cot_tilt(sym, rec),
            "positions": {
                "report_date": rec["history"].get(rec["latest"], {}).get("report_date") if rec.get("latest") else None,
                "long": rec["history"].get(rec["latest"], {}).get("noncomm_long") if rec.get("latest") else None,
                "short": rec["history"].get(rec["latest"], {}).get("noncomm_short") if rec.get("latest") else None,
            }
        }
    save_json(os.path.join(DATA_DIR, "cftc", "cot_bias.json"), {
        "meta": {"updated": now_iso(), "note": "COT positioning tilt (secondary bias input)"},
        "instruments": out,
    })
    log("COT bias: " + ", ".join(f"{k}={v['tilt']['tilt']:+d}({v['latest_week']})" for k, v in out.items()))
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(collect(), indent=1)[:3000])