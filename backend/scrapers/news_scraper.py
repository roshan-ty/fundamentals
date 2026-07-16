"""
Pipeline E: Live News Feed — Fetch global financial market headlines
from Newsdata.io API. Purely cosmetic — not fed into scoring engine.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

from backend.models.schemas import NewsArticle, NewsData

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

NEWSDATA_BASE = "https://newsdata.io/api/1/news"
NEWSDATA_API_KEY = os.environ.get("NEWSDATA_API_KEY", "")


# ── Main scraper ──────────────────────────────────────────────────────────────

def fetch_news_data() -> NewsData:
    """
    Fetch latest financial news from Newsdata.io.
    Returns a NewsData container.
    """
    news_data = NewsData()
    news_data.last_updated = datetime.now(timezone.utc).isoformat()

    if not NEWSDATA_API_KEY:
        logger.warning("NEWSDATA_API_KEY not set. Skipping news feed.")
        return news_data

    try:
        params = {
            "apikey": NEWSDATA_API_KEY,
            "category": "business",
            "country": "us,gb,eu,au,jp,ca,ch",
            "language": "en",
            "size": 25,
            "q": "forex OR stock OR oil OR gold OR treasury OR dollar OR euro OR pound OR yen OR market OR finance OR economy OR rate",
        }
        resp = requests.get(NEWSDATA_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        articles_raw = data.get("results", [])
        if not articles_raw:
            logger.warning("News: No articles returned from API.")
            return news_data

        for art in articles_raw:
            try:
                title = (art.get("title") or "").strip()
                if not title:
                    continue

                news_data.articles.append(
                    NewsArticle(
                        title=title[:300],
                        source=(art.get("source_id") or art.get("source") or "Unknown"),
                        link=(art.get("link") or ""),
                        published_at=(art.get("pubDate") or art.get("published_at") or ""),
                        description=((art.get("description") or "")[:500]),
                    )
                )
            except (KeyError, TypeError) as e:
                logger.debug("News: Skipping article: %s", e)
                continue

        # Limit to 50 articles max
        if len(news_data.articles) > 50:
            news_data.articles = news_data.articles[:50]

        logger.info("News: Fetched %d articles.", len(news_data.articles))

    except requests.RequestException as e:
        status_code = ""
        if hasattr(e, 'response') and e.response is not None:
            status_code = f" (HTTP {e.response.status_code})"
        logger.warning("News: Failed to fetch from Newsdata.io%s: %s", status_code, e)
    except (ValueError, KeyError, TypeError) as e:
        logger.warning("News: Failed to parse Newsdata.io response: %s", e)

    return news_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = fetch_news_data()
    print(f"News: {len(data.articles)} articles.")
    for a in data.articles[:5]:
        print(f"  [{a.source}] {a.title}")