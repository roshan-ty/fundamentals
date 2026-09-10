# Orchestrator — single entrypoint for scheduled runs.
#   python scripts/orchestrator.py all             # full daily pipeline
#   python scripts/orchestrator.py quotes_news     # intraday quotes + news
#   python scripts/orchestrator.py scoring         # scoring only (uses stored data)
# Reads API keys from environment (GitHub Actions Secrets or local .env).
import os
import sys
import json
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from common.utils import log, now_iso, save_json, DATA_DIR  # noqa: E402


def env():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    keys = ("FRED_KEY", "ALPHAVANTAGE_KEY1", "ALPHAVANTAGE_KEY2", "FINNHUB_KEY",
            "TWELVEDATA_KEY", "FMP_KEY", "NEWSDATA_KEY", "EODHD_KEY", "MARKETSTACK_KEY")
    return {k: os.environ.get(k, "") for k in keys}


def run(fn, name):
    t0 = time.time()
    try:
        res = fn()
        log(f"{name}: OK in {time.time() - t0:.1f}s")
        return res
    except Exception as exc:
        log(f"{name}: FAILED — {exc}", "ERROR")
        return None


def meta_write(pipeline, stages):
    meta_path = os.path.join(DATA_DIR, "meta", "last_update.json")
    m = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as fh:
            m = json.load(fh)
    m[pipeline] = {"updated": now_iso(), "stages": {k: {"ok": v is not None} for k, v in stages.items()}}
    save_json(meta_path, m)


def all_pipeline():
    e = env()
    from collectors import fred, forexfactory, national_actuals, cftc, quotes, news
    stages = {}
    stages["fred"] = run(lambda: fred.collect(e.get("FRED_KEY", "")), "fred")
    stages["calendar"] = run(lambda: forexfactory.collect(), "calendar")
    stages["actuals"] = run(lambda: national_actuals.collect(), "actuals")
    stages["cftc"] = run(lambda: cftc.collect(), "cftc")
    stages["quotes"] = run(lambda: quotes.collect(e, scope="daily"), "quotes")
    stages["news"] = run(lambda: news.collect(e), "news")
    # scoring depends on the collected data
    scoring_pipeline()
    meta_write("daily", stages)
    return stages


def scoring_pipeline():
    from scoring import score, cot, instruments, pairs, narrative, setups
    stages = {}
    stages["currencies"] = run(score.score_currencies, "currency scoring")
    stages["cot"] = run(cot.collect, "cot scoring")
    stages["instruments"] = run(instruments.score_instruments, "instrument scoring")
    stages["pairs"] = run(pairs.score_pairs, "pair scoring")
    stages["narratives"] = run(narrative.collect, "narratives")
    stages["setups"] = run(setups.collect, "setups")
    meta_write("scoring", stages)
    return stages


def quotes_news_pipeline():
    e = env()
    from collectors import quotes, news
    stages = {}
    stages["quotes"] = run(lambda: quotes.collect(e, scope="hourly"), "quotes")
    stages["news"] = run(lambda: news.collect(e), "news")
    meta_write("intraday", stages)
    return stages


def main():
    task = sys.argv[1] if len(sys.argv) > 1 else "all"
    if task == "all":
        res = all_pipeline()
    elif task == "scoring":
        res = scoring_pipeline()
    elif task in ("quotes", "quotes_news", "intraday"):
        res = quotes_news_pipeline()
    else:
        log(f"Unknown task: {task}", "ERROR")
        sys.exit(2)
    # Fail loudly if the data pipeline itself failed entirely
    if isinstance(res, dict) and res and all(v is None for v in res.values()):
        sys.exit(1)
    log("orchestrator complete")


if __name__ == "__main__":
    main()