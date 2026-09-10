# Live quotes collector — FX, metals, energy, crypto, indices.
# Providers used in priority order, each with its own rate-limiter so 24/7
# scheduling stays inside free-tier buckets:
#   TwelveData free:  8 req/min  -> budget 7/min, auto-wait
#   FMP free:        ~250 req/day-> hourly job only does a small global set
#   Finnhub free:     60 req/min -> used for crypto
#   MarketStack:      emergency FX fallback (rarely called)
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, load_symbols, log, DATA_DIR, now_iso, HttpSession

BASE_SNAPSHOT = os.path.join(DATA_DIR, "quotes", "latest.json")


class MinuteBudget:
    """Simple per-minute request budget for free-tier APIs."""

    def __init__(self, limit):
        self.limit = limit
        self.count = 0
        self.window_start = time.time()

    def wait(self):
        elapsed = time.time() - self.window_start
        if elapsed > 60:
            self.window_start = time.time()
            self.count = 0
        if self.count >= self.limit:
            time.sleep(max(0, 60 - elapsed) + 1)
            self.window_start = time.time()
            self.count = 0
        self.count += 1


def _td_symbol(sym, symbols):
    mapped = symbols.get("providerSymbols", {}).get("twelvedata", {}).get(sym)
    if mapped:
        return mapped
    fx = symbols.get("fx", {}).get(sym)
    if fx:
        return f"{fx['base']}/{fx['quote']}"
    return sym


def _fmp_symbol(sym, symbols):
    return symbols.get("providerSymbols", {}).get("fmp", {}).get(sym) or sym


def _finnhub_symbol(sym, symbols):
    return symbols.get("providerSymbols", {}).get("finnhub", {}).get(sym) or sym
def fetch_twelvedata(http, symbols, td_key, fx_set, metal_set, crypto_set):
    """Rate-limited Twelve Data price fetches."""
    out = {}
    budget = MinuteBudget(7)
    for sym in list(fx_set) + list(metal_set) + list(crypto_set):
        try:
            budget.wait()
            s = _td_symbol(sym, symbols)
            r = http.get_json("https://api.twelvedata.com/price",
                              params={"symbol": s, "apikey": td_key})
            if r.get("price"):
                out[sym] = {"price": float(r["price"]), "ts": now_iso(), "source": "td"}
            else:
                log(f"TD {sym}: no price ({str(r)[:80]})", "WARN")
        except Exception as exc:
            log(f"TD {sym} failed: {str(exc)[:80]}", "WARN")
    return out


def fetch_fmp(http, symbols, fmp_key, index_set, energy_set):
    """FMP quotes for global indices + energy futures."""
    out = {}
    budget = MinuteBudget(28)
    for sym in list(index_set) + list(energy_set):
        try:
            budget.wait()
            s = _fmp_symbol(sym, symbols)
            rows = http.get_json(f"https://financialmodelingprep.com/api/v3/quote/{s}",
                                 params={"apikey": fmp_key})
            if isinstance(rows, list) and rows and rows[0].get("price"):
                out[sym] = {"price": float(rows[0]["price"]), "ts": now_iso(), "source": "fmp"}
        except Exception as exc:
            log(f"FMP {sym} failed: {str(exc)[:80]}", "WARN")
    return out


def fetch_finnhub(http, symbols, fh_key, crypto_set):
    """Crypto quotes via Finnhub."""
    out = {}
    for sym in crypto_set:
        try:
            s = _finnhub_symbol(sym, symbols)
            r = http.get_json("https://finnhub.io/api/v1/quote",
                              params={"symbol": s, "token": fh_key})
            if r.get("c"):
                out[sym] = {"price": float(r["c"]), "ts": now_iso(), "source": "finnhub"}
        except Exception as exc:
            log(f"Finnhub {sym} failed: {str(exc)[:80]}", "WARN")
        time.sleep(0.15)
    return out


def fetch_marketstack(http, symbols, ms_key, missing_fx):
    """Emergency FX fallback (rare; small free quota)."""
    out = {}
    if not missing_fx:
        return out
    try:
        symbols_str = ",".join(missing_fx)
        r = http.get_json("https://api.marketstack.com/v2/eod/latest",
                          params={"access_key": ms_key, "symbols": symbols_str})
        for d in (r or {}).get("data", []):
            sym_raw = d.get("symbol", "")
            if d.get("close") and sym_raw in missing_fx:
                out[sym_raw] = {"price": float(d["close"]), "ts": now_iso(), "source": "marketstack"}
    except Exception as exc:
        log(f"MarketStack failed: {str(exc)[:80]}", "WARN")
    return out


def persist(snapshot):
    """Merge new snapshot into latest.json and append to history line."""
    prev = load_json(BASE_SNAPSHOT, default={})
    prev.update(snapshot)
    save_json(BASE_SNAPSHOT, prev)


def collect(env, scope="daily"):
    symbols = load_symbols()
    http = HttpSession(timeout=30, max_retries=1)

    # scope-dependent instrument sets
    if scope == "hourly":
        fx_set = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"}
        metal_set = {"XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"}
        crypto_set = {"BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"}
        index_set = {"US500", "US100", "US30", "GER40", "EU50", "GB100", "JP225"}
        energy_set = set()
    else:
        fx_set = set(symbols.get("fx", {}).keys())
        metal_set = set(symbols.get("metals", {}).keys())
        crypto_set = set(symbols.get("crypto", {}).keys())
        index_set = set(symbols.get("indices", {}).keys())
        energy_set = set(symbols.get("energy", {}).keys())

    snap = {}
    snap.update(fetch_twelvedata(http, symbols, env.get("TWELVEDATA_KEY", ""),
                                 fx_set, metal_set, crypto_set))
    snap.update(fetch_fmp(http, symbols, env.get("FMP_KEY", ""), index_set, energy_set))
    snap.update(fetch_finnhub(http, symbols, env.get("FINNHUB_KEY", ""), crypto_set))

    # MarketStack fallback only on the daily cycle for FX failures
    if scope == "daily":
        missing_fx = list(fx_set - set(snap.keys()))
        if missing_fx and env.get("MARKETSTACK_KEY"):
            fallback = fetch_marketstack(http, symbols, env.get("MARKETSTACK_KEY", ""), missing_fx)
            snap.update(fallback)

    persist(snap)
    log(f"Quotes[{scope}]: {len(snap)} instruments refreshed")
    return snap


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))
    env = {k: os.environ.get(k, "") for k in
           ("TWELVEDATA_KEY", "FMP_KEY", "FINNHUB_KEY", "MARKETSTACK_KEY")}
    out = collect(env, scope=os.environ.get("QUOTES_SCOPE", "hourly"))
    print(json.dumps({k: v for k, v in list(out.items())[:5]}, indent=1))