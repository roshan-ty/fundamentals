"""
Pipeline C: Yield Curve & Yield Spreads — Fetch Treasury yields from AlphaVantage
and global bond yields from Yahoo Finance via yfinance.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
import yfinance as yf

from backend.models.schemas import YieldEntry, YieldData

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

ALPHAVANTAGE_BASE = "https://www.alphavantage.co/query"
ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")

# Instruments to track via yfinance
YFINANCE_TICKERS: dict[str, str] = {
    "^TNX":  "US10Y",   # US 10-Year Treasury Note (yield proxy)
    "^GD10": "DE10Y",   # German 10-Year Bund
    "^UMG":  "GB10Y",   # UK 10-Year Gilt
    "^YT10": "JP10Y",   # Japan 10-Year JGB
}


# ── AlphaVantage Treasury Yields ──────────────────────────────────────────────

def fetch_av_treasury_yield(maturity: str = "10year") -> Optional[float]:
    """
    Fetch latest US Treasury yield from AlphaVantage.
    maturity: "10year" or "2year"
    Returns the latest yield percentage or None.
    """
    if not ALPHAVANTAGE_KEY:
        logger.warning("ALPHAVANTAGE_API_KEY not set. Skipping AV yield fetch.")
        return None

    try:
        params = {
            "function": "TREASURY_YIELD",
            "interval": "daily",
            "maturity": maturity,
            "apikey": ALPHAVANTAGE_KEY,
        }
        resp = requests.get(ALPHAVANTAGE_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Navigate the response structure
        for key in data:
            if "Treasury Yield" in key:
                values = data[key]
                if isinstance(values, list) and len(values) > 0:
                    latest = values[-1]
                    yield_str = latest.get("value", "")
                    if yield_str and yield_str != ".":
                        return float(yield_str)
        logger.warning("AV: No yield data found for %s", maturity)
        return None

    except (requests.RequestException, KeyError, ValueError, IndexError) as e:
        logger.warning("AV: Failed to fetch %s yield: %s", maturity, e)
        return None


def fetch_av_treasury_spread() -> dict[str, Optional[float]]:
    """
    Fetch both 10Y and 2Y yields from AV and compute spread.
    Returns dict with 'y10', 'y2', 'spread'.
    """
    y10 = fetch_av_treasury_yield("10year")
    y2 = fetch_av_treasury_yield("2year")
    spread = (y10 - y2) if (y10 is not None and y2 is not None) else None
    return {"y10": y10, "y2": y2, "spread": spread}


# ── Yahoo Finance Global Yields ───────────────────────────────────────────────

def fetch_yfinance_yields() -> list[YieldEntry]:
    """
    Fetch global bond yields via yfinance.
    Returns a list of YieldEntry objects.
    """
    entries: list[YieldEntry] = []
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for ticker, instrument in YFINANCE_TICKERS.items():
        try:
            bond = yf.Ticker(ticker)
            hist = bond.history(period="3mo")
            if hist.empty:
                logger.warning("YF: No data for %s (%s)", ticker, instrument)
                continue

            # Latest close price is the yield
            latest_yield = float(hist["Close"].iloc[-1])
            # 50-day moving average
            ma50 = float(hist["Close"].rolling(window=50).mean().iloc[-1]) if len(hist) >= 50 else None

            entries.append(
                YieldEntry(
                    instrument=instrument,
                    date=today_iso,
                    yield_value=round(latest_yield, 4),
                    yield_ma50=round(ma50, 4) if ma50 is not None else None,
                )
            )
            logger.info(
                "YF: %s (%s) = %.4f (MA50: %s)",
                ticker, instrument, latest_yield,
                f"{ma50:.4f}" if ma50 else "N/A",
            )

        except Exception as e:
            logger.warning("YF: Failed to fetch %s (%s): %s", ticker, instrument, e)
            continue

    return entries


# ── Main entry point ──────────────────────────────────────────────────────────

def fetch_yield_data() -> YieldData:
    """
    Fetch all yield data (US Treasuries from AV, global bonds from YF).
    US10Y is fetched via yfinance (^TNX) to get the 50-day MA for scoring.
    AlphaVantage is used for US2Y and as a fallback for US10Y.
    """
    yield_data = YieldData()
    yield_data.last_updated = datetime.now(timezone.utc).isoformat()
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Global bonds from yfinance (includes US10Y via ^TNX with MA50)
    yf_entries = fetch_yfinance_yields()
    has_us10y_from_yf = any(e.instrument == "US10Y" for e in yf_entries)
    yield_data.entries.extend(yf_entries)

    # US2Y from AlphaVantage (yfinance has no direct 2Y ticker)
    us_2y = fetch_av_treasury_yield("2year")
    if us_2y is not None:
        yield_data.entries.append(
            YieldEntry(instrument="US2Y", date=today_iso, yield_value=round(us_2y, 4))
        )
        logger.info("Yields: US2Y = %.4f", us_2y)

    # Fallback: if yfinance failed for US10Y, try AlphaVantage
    if not has_us10y_from_yf:
        us_10y = fetch_av_treasury_yield("10year")
        if us_10y is not None:
            yield_data.entries.append(
                YieldEntry(instrument="US10Y", date=today_iso, yield_value=round(us_10y, 4))
            )
            logger.info("Yields: US10Y (AV fallback) = %.4f", us_10y)

    return yield_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = fetch_yield_data()
    print(f"Yields: {len(data.entries)} instruments fetched.")
    for e in data.entries:
        print(f"  {e.instrument}: {e.yield_value} (MA50: {e.yield_ma50})")