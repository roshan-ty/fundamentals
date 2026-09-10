# News feed collector — merges a daily global feed with good intraday financial
# headlines, tags every story to the instruments it touches (keyword rules from
# config/news_rules.json) and keeps a rolling 7-day window.
import os
import sys
import json
import re
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, load_news_rules, log, DATA_DIR, now_iso, HttpSession

NEWS_FEED = os.path.join(DATA_DIR, "news", "feed.json")
META = os.path.join(DATA_DIR, "meta", "quota.json")


def _clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def fetch_newsdata(http, key, categories="business,technology,top"):
    """Daily global feed (free tier is small; called once per day)."""
    out = []
    try:
        r = http.get_json("https://newsdata.io/api/1/news",
                          params={"apikey": key, "language": "en", "category": categories, "size": 8})
        for a in r.get("results", []):
            out.append({
                "headline": _clean(a.get("title")),
                "snippet": _clean(a.get("description")),
                "url": a.get("url", ""),
                "source": "global",
                "published": a.get("pubDate", ""),
                "tags": [],
            })
    except Exception as exc:
        log(f"Newsdata failed: {str(exc)[:100]}", "WARN")
    return out


def fetch_finnhub_news(http, key, categories=("general",)):
    """Intraday financial + geopolitical headlines (free tier, 60/min)."""
    out = []
    for cat in categories:
        try:
            r = http.get_json("https://finnhub.io/api/v1/news",
                              params={"category": cat, "token": key})
            for a in (r if isinstance(r, list) else [])[:30]:
                dt = datetime.fromtimestamp(a.get("datetime", 0)).isoformat(timespec="minutes")
                out.append({
                    "headline": _clean(a.get("headline")),
                    "snippet": _clean(a.get("summary"))[:300],
                    "url": a.get("url", ""),
                    "source": "markets",
                    "published": dt,
                    "tags": [],
                })
        except Exception as exc:
            log(f"Finnhub news({cat}) failed: {str(exc)[:80]}", "WARN")
    return out


def _tag(headline, snippet, rules):
    text = (headline + " " + snippet).lower()
    tags = []
    for instrument, cfg in rules.get("rules", {}).items():
        inc = cfg.get("include", [])
        exc = cfg.get("exclude", [])
        if not inc:
            continue
        hit = any(k.lower() in text for k in inc)
        if hit and not any(k.lower() in text for k in exc):
            tags.append(instrument)
    return tags


def collect(env):
    http = HttpSession(timeout=30, max_retries=2)
    rules = load_news_rules()
    items = []
    items += fetch_newsdata(http, env.get("NEWSDATA_KEY", ""))
    items += fetch_finnhub_news(http, env.get("FINNHUB_KEY", ""))
    # Dedupe by url+headline
    seen = {}
    for it in items:
        if not it["headline"]:
            continue
        key = (it["headline"].lower(), it["url"])
        it["tags"] = _tag(it["headline"], it["snippet"], rules)
        it["collected_at"] = now_iso()
        seen[key] = it
    # Merge with prior window (keep 7 days)
    prev = load_json(NEWS_FEED, default=[])
    for it in prev:
        k = (it.get("headline", "").lower(), it.get("url", ""))
        if k not in seen:
            seen[k] = it
    cutoff = datetime.utcnow() - timedelta(days=7)
    items_out = []
    for it in seen.values():
        try:
            pub = datetime.fromisoformat((it.get("published") or "").replace("Z", "+00:00"))
            if pub.replace(tzinfo=None) < cutoff:
                continue
        except Exception:
            pass
        items_out.append(it)
    items_out.sort(key=lambda x: x.get("published", ""), reverse=True)
    save_json(NEWS_FEED, items_out[:400])
    log(f"News feed: {len(items_out)} stories retained")
    return {"stories": len(items_out)}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))
    env = {k: os.environ.get(k, "") for k in ("NEWSDATA_KEY", "FINNHUB_KEY")}
    print(collect(env))