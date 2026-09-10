# Top Setups — ranks instruments by bias magnitude and data confidence.
# Confidence = how many scored data points + COT availability; higher coverage
# produces higher-confidence setups.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, load_scorecard, log, DATA_DIR, now_iso


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


def collect(top_n=12):
    pairs = load_json(os.path.join(DATA_DIR, "bias", "pairs.json"), default={}).get("pairs", [])
    currencies = load_json(os.path.join(DATA_DIR, "bias", "currencies.json"), default={}).get("currencies", {})
    analyses = load_json(os.path.join(DATA_DIR, "analysis", "pairs.json"), default={}).get("analyses", {})
    setups = []
    for p in pairs:
        if p.get("score") is None:
            continue
        how_far = abs(p["score"] - 5.0)
        # confidence from scored calendar points of involved currencies
        conf = 0.5
        if p["class"] == "fx":
            bc = p["symbol"][:3]
            qc = p["symbol"][3:]
            for code in (bc, qc):
                cc = currencies.get(code, {})
                conf += 0.1 * min(5, cc.get("eligible_points", 0))
        else:
            cc = currencies.get("USD", {})
            conf += 0.1 * min(5, cc.get("eligible_points", 0))
        conf = min(conf, 1.0)
        setups.append({
            "symbol": p["symbol"],
            "name": p["name"],
            "score": p["score"],
            "band": p["band"],
            "direction": "Buy" if p["score"] > 5.2 else ("Sell" if p["score"] < 4.8 else "Hold"),
            "magnitude": round(how_far, 2),
            "confidence": round(conf, 2),
            "biasType": p.get("biasType", "direct"),
            "drivers": [t["event"] for t in currencies.get(p["symbol"][:3], {}).get("top_drivers", [])][:3] if p["class"] == "fx" else [],
            "rationale": analyses.get(p["symbol"], {}).get("summary", ""),
        })
    # Rank: strong bias + high confidence first
    setups.sort(key=lambda x: (x["magnitude"] * x["confidence"]), reverse=True)
    top = setups[:top_n]
    save_json(os.path.join(DATA_DIR, "setups", "top.json"), {
        "meta": {"updated": now_iso(), "note": "Top setups ranked by bias magnitude x data confidence"},
        "setups": top,
    })
    log("Top setups: " + ", ".join(f"{s['symbol']}={s['direction']}({s['score']},{s['confidence']})" for s in top[:8]))
    return top


if __name__ == "__main__":
    import json
    print(json.dumps(collect(), indent=1)[:2500])