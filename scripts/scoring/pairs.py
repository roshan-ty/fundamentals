# Pair bias — for every traded pair/instrument:
#   pair = 5 + (baseScore - 5) - (quoteScore - 5), clamped 0-10
#   (base bullish & quote bearish => pair bullish; the three EURUSD scenarios
#   from the spec emerge automatically).
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, load_symbols, log, DATA_DIR, now_iso


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


def _dir(score):
    if score > 5.2:
        return "Bullish"
    if score < 4.8:
        return "Bearish"
    return "Neutral"


def score_pairs():
    cur = load_json(os.path.join(DATA_DIR, "bias", "currencies.json"), default={}).get("currencies", {})
    inst = load_json(os.path.join(DATA_DIR, "bias", "instruments.json"), default={}).get("instruments", {})
    syms = load_symbols()
    pairs = []

    def lookup(code):
        if code in cur:
            return cur[code]["score"]
        if code in inst:
            return inst[code]["score"]
        return None

    for cls in ("fx", "crypto", "metals", "energy", "indices"):
        instruments = syms.get(cls, {})
        for sym, meta in instruments.items():
            if cls == "fx":
                base, quote = meta["base"], meta["quote"]
                b = lookup(base)
                q = lookup(quote)
                if b is None or q is None:
                    score, bias_type = None, "unscored"
                else:
                    score = 5.0 + (b - 5.0) - (q - 5.0)
                    score = max(0.0, min(10.0, score))
                    bias_type = "direct"
                pairs.append({
                    "symbol": sym, "name": f"{base}/{quote}", "class": "fx",
                    "biasType": bias_type, "score": round(score, 2) if score is not None else None,
                    "band": _band(score) if score is not None else "No Score",
                    "direction": _dir(score) if score is not None else "No Score",
                    "base_score": b, "quote_score": q,
                })
            elif cls in ("metals", "energy"):
                score = inst.get(sym, {}).get("score")
                pairs.append({
                    "symbol": sym, "name": inst.get(sym, {}).get("name", sym),
                    "class": cls, "biasType": inst.get(sym, {}).get("biasType", "direct"),
                    "score": score,
                    "band": _band(score) if score is not None else "No Score",
                    "direction": _dir(score) if score is not None else "No Score",
                    "base_score": inst.get(sym, {}).get("components", {}).get("usd_score"),
                    "quote_score": None,
                })
            elif cls == "crypto":
                score = inst.get(sym, {}).get("score")
                pairs.append({
                    "symbol": sym, "name": f"{meta.get('base', sym)} / USD",
                    "class": "crypto", "biasType": inst.get(sym, {}).get("biasType", "derived"),
                    "score": score,
                    "band": _band(score) if score is not None else "No Score",
                    "direction": _dir(score) if score is not None else "No Score",
                    "base_score": None, "quote_score": None,
                })
            elif cls == "indices":
                score = inst.get(sym, {}).get("score")
                pairs.append({
                    "symbol": sym, "name": meta.get("name", sym),
                    "class": "index", "biasType": inst.get(sym, {}).get("biasType", "derived"),
                    "score": score,
                    "band": _band(score) if score is not None else "No Score",
                    "direction": _dir(score) if score is not None else "No Score",
                    "base_score": None, "quote_score": None,
                })

    scored = [p for p in pairs if p["score"] is not None]
    total = len(pairs)
    save_json(os.path.join(DATA_DIR, "bias", "pairs.json"), {
        "meta": {"updated": now_iso(), "total": total, "scored": len(scored),
                 "note": "Pair bias derived from currency/instrument bias; yields & news confirm only."},
        "pairs": pairs,
    })
    log(f"Pair scoring: {len(scored)}/{total} scored")
    return pairs


if __name__ == "__main__":
    print(json.dumps(score_pairs(), indent=1)[:2500])