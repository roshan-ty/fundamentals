#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Forex Factory News Scraper
Scrapes the latest financial news articles from Forex Factory
(https://www.forexfactory.com/news) with Cloudflare bypass.

Extracts: Headline, Timestamp, Currency Tags, Source Link, Short Snippet.
Exports to public/data/news.json.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

try:
    import cloudscraper
    _HAS_CLOUDSCRAPER = True
except ImportError:
    _HAS_CLOUDSCRAPER = False

try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:
    _HAS_CURL_CFFI = False

FF_NEWS_URL = "https://www.forexfactory.com/news"

# ForexLive RSS mirror — reliable fallback when Forex Factory HTML is
# blocked by Cloudflare. Same coverage: USD/EUR/GBP/JPY/AUD/CAD/CHF, gold etc.
FOREXLIVE_RSS_URL = "https://www.forexlive.com/feed/news"

# Currency tags we recognize in headlines
CURRENCY_TAGS = [
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD",
    "XAU", "XAG", "WTI", "BTC", "ETH", "SP500", "NAS100",
]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _fetch_html(url: str) -> Optional[str]:
    """Fetch HTML with Cloudflare bypass strategies."""
    if _HAS_CLOUDSCRAPER:
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
            resp = scraper.get(url, headers=BROWSER_HEADERS, timeout=45)
            if resp.status_code == 200 and len(resp.text) > 1000:
                logger.info("News: fetched via cloudscraper (%d bytes)", len(resp.text))
                return resp.text
        except Exception as e:
            logger.warning("News: cloudscraper failed: %s", e)

    if _HAS_CURL_CFFI:
        try:
            resp = curl_requests.get(
                url,
                headers=BROWSER_HEADERS,
                impersonate="chrome120",
                timeout=45,
            )
            if resp.status_code == 200 and len(resp.text) > 1000:
                logger.info("News: fetched via curl_cffi (%d bytes)", len(resp.text))
                return resp.text
        except Exception as e:
            logger.warning("News: curl_cffi failed: %s", e)

    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=45)
        if resp.status_code == 200 and len(resp.text) > 1000:
            logger.info("News: fetched via requests (%d bytes)", len(resp.text))
            return resp.text
    except Exception as e:
        logger.warning("News: requests failed: %s", e)

    return None


# Common natural-language aliases mapped to our currency tags.
# This lets the News Feed filter pills (USD/EUR/GBP/JPY/AUD/CAD/GOLD...) match
# headlines that use "dollar", "euro", "pound", "yen", "gold", "oil", etc.
CURRENCY_ALIASES: dict[str, list[str]] = {
    "USD": ["USD", "DOLLAR", "GREENBACK", "US TREASURY", "US YIELD", "FED", "FOMC", "US CPI", "US NFP", "UNITED STATES", "AMERICA"],
    "EUR": ["EUR", "EURO", "ECB", "EURUSD", "FRANCE", "GERMANY", "ITALY", "SPAIN", "EUROZONE", "EURO AREA"],
    "GBP": ["GBP", "POUND", "STERLING", "BOE", "GBPUSD", "UK ", "UNITED KINGDOM", "BRITAIN"],
    "JPY": ["JPY", "YEN", "BOJ", "USDJPY", "JAPAN"],
    "AUD": ["AUD", "AUSSIE", "RBA", "AUDUSD", "AUSTRALIA"],
    "CAD": ["CAD", "LOONIE", "USDCAD", "CANADA"],
    "CHF": ["CHF", "SWISSY", "FRANC", "SNB", "SWITZERLAND"],
    "NZD": ["NZD", "KIWI", "RBNZ", "NEW ZEALAND"],
    "XAU": ["XAU", "GOLD"],
    "XAG": ["XAG", "SILVER"],
    "WTI": ["WTI", "OIL", "CRUDE"],
    "BTC": ["BTC", "BITCOIN", "CRYPTO"],
    "ETH": ["ETH", "ETHEREUM"],
}


def _extract_currency_tags(text: str) -> list[str]:
    """Extract currency tags from a headline/snippet.

    Matches both literal currency codes (USD, EUR, ...) and common
    natural-language aliases (dollar, euro, pound, yen, gold, oil, ...)
    so the News Feed filter pills match real-world headlines.
    """
    tags = []
    upper = text.upper()
    for tag in CURRENCY_TAGS:
        aliases = CURRENCY_ALIASES.get(tag, [tag])
        for alias in aliases:
            # Match as standalone word or as part of a pair like EURUSD
            if re.search(rf"\b{re.escape(alias)}\b|{re.escape(alias)}(?=USD|EUR|GBP|JPY|AUD|CAD|CHF|NZD)", upper):
                tags.append(tag)
                break
    return tags


def _parse_forexlive_rss(xml_text: str) -> list[dict]:
    """
    Parse the ForexLive RSS feed into structured article dicts.

    This is a reliable fallback source when Forex Factory's HTML is
    blocked by Cloudflare. Items provide: title, link, pubDate, description.
    """
    articles: list[dict] = []
    soup = BeautifulSoup(xml_text, "xml")
    items = soup.find_all("item")

    for item in items:
        try:
            title_el = item.find("title")
            headline = title_el.get_text(strip=True) if title_el else ""
            if not headline:
                continue

            link_el = item.find("link")
            source_link = link_el.get_text(strip=True) if link_el else ""

            pub_el = item.find("pubDate")
            pub_text = pub_el.get_text(strip=True) if pub_el else ""
            timestamp = ""
            if pub_text:
                try:
                    # RFC 2822 format, e.g. "Wed, 21 Aug 2026 12:00:00 +0000"
                    parsed = datetime.strptime(pub_text, "%a, %d %b %Y %H:%M:%S %z")
                    timestamp = parsed.isoformat()
                except ValueError:
                    timestamp = pub_text

            desc_el = item.find("description")
            desc = desc_el.get_text(strip=True) if desc_el else ""
            # Strip any HTML tags from description snippet
            snippet = re.sub(r"<[^>]+>", "", desc)
            snippet = snippet[:200]

            currency_tags = _extract_currency_tags(headline)

            impact = "medium"
            upper = headline.upper()
            if any(kw in upper for kw in ["FED", "CPI", "NFP", "GDP", "PCE", "RATE", "INFLATION"]):
                impact = "high"
            elif any(kw in upper for kw in ["PMI", "RETAIL", "UNEMPLOYMENT", "TRADE"]):
                impact = "medium"

            articles.append({
                "headline": headline[:160],
                "timestamp": timestamp,
                "currency_tags": currency_tags,
                "impact": impact,
                "source_link": source_link,
                "snippet": snippet,
            })
        except Exception as e:
            logger.debug("News: Skipping RSS item: %s", e)
            continue

    # Deduplicate
    seen = set()
    unique = []
    for art in articles:
        key = art["headline"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(art)

    logger.info("News: %d unique articles parsed from ForexLive RSS", len(unique))
    return unique


def fetch_forexlive_news() -> list[dict]:
    """Fetch and parse the latest ForexLive RSS news feed."""
    try:
        resp = requests.get(FOREXLIVE_RSS_URL, headers=BROWSER_HEADERS, timeout=30)
        if resp.status_code == 200 and len(resp.text) > 1000:
            logger.info("News: fetched ForexLive RSS (%d bytes)", len(resp.text))
            return _parse_forexlive_rss(resp.text)
    except Exception as e:
        logger.warning("News: ForexLive RSS failed: %s", e)
    return []


def _parse_ff_news(html: str) -> list[dict]:
    """Parse Forex Factory news page into structured article dicts."""
    soup = BeautifulSoup(html, "html.parser")
    articles: list[dict] = []

    # Forex Factory news articles are typically <article> or div.news-item
    article_nodes = soup.find_all("article") or soup.find_all(
        "div", class_=re.compile("news-item|news__item|article")
    )

    for node in article_nodes:
        try:
            # Headline
            headline_el = node.find("h2") or node.find("h3") or node.find("a", class_=re.compile("title|headline"))
            headline = headline_el.get_text(strip=True) if headline_el else ""
            if not headline:
                continue

            # Source link
            link_el = headline_el if headline_el.name == "a" else node.find("a", href=True)
            source_link = link_el.get("href", "") if link_el else ""
            if source_link and source_link.startswith("/"):
                source_link = f"https://www.forexfactory.com{source_link}"

            # Timestamp
            time_el = node.find("time") or node.find("span", class_=re.compile("time|date"))
            timestamp = time_el.get("datetime", "") if time_el else ""
            if not timestamp and time_el:
                timestamp = time_el.get_text(strip=True)

            # Snippet — first paragraph or div with text
            snippet_el = node.find("p") or node.find("div", class_=re.compile("snippet|summary|content"))
            snippet = snippet_el.get_text(strip=True)[:200] if snippet_el else ""

            # Currency tags from headline + snippet
            currency_tags = _extract_currency_tags(f"{headline} {snippet}")

            # Impact guess: if headline contains "Fed", "CPI", "NFP", "GDP" etc → high
            impact = "medium"
            upper = headline.upper()
            if any(kw in upper for kw in ["FED", "CPI", "NFP", "GDP", "PCE", "RATE", "INFLATION"]):
                impact = "high"
            elif any(kw in upper for kw in ["PMI", "RETAIL", "UNEMPLOYMENT", "TRADE"]):
                impact = "medium"

            articles.append({
                "headline": headline[:160],
                "timestamp": timestamp,
                "currency_tags": currency_tags,
                "impact": impact,
                "source_link": source_link,
                "snippet": snippet,
            })
        except Exception as e:
            logger.debug("News: Skipping article: %s", e)
            continue

    # Deduplicate by headline
    seen = set()
    unique = []
    for art in articles:
        key = art["headline"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(art)

    logger.info("News: %d unique articles parsed", len(unique))
    return unique


def fetch_ff_news() -> list[dict]:
    """
    Fetch and parse the latest Forex Factory news.

    Falls back to the ForexLive RSS mirror when Forex Factory's HTML is
    blocked by Cloudflare (common on shared/datacenter IPs).
    """
    html = _fetch_html(FF_NEWS_URL)
    if html:
        articles = _parse_ff_news(html)
        if articles:
            return articles
        logger.warning("News: Forex Factory HTML parsed but 0 articles found.")

    # Fallback: ForexLive RSS mirror (reliable, no Cloudflare)
    logger.info("News: Falling back to ForexLive RSS mirror...")
    articles = fetch_forexlive_news()
    if articles:
        logger.info("News: Using %d articles from ForexLive RSS fallback.", len(articles))
        return articles

    logger.warning("News: Failed to fetch news from both Forex Factory and ForexLive.")
    return []


def export_news_json(articles: list[dict], output_path: str) -> str:
    """Write news articles to a JSON file."""
    payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "articles": articles,
        "total_articles": len(articles),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("News: Exported %d articles to %s", len(articles), output_path)
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    articles = fetch_ff_news()
    print(f"Fetched {len(articles)} news articles")
    for art in articles[:5]:
        print(f"  {art['headline']} | {art['currency_tags']} | {art['impact']}")