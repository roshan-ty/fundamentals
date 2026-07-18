#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Data Parsers
Extracts 30 global macroeconomic data points across 8+ data sources.
All functions return structured dicts for the scoring engine.

Data Point Index:
  1-6, 11, 12, 20-22, 29: Economic Indicators & Labor (FMP + Finnhub)
  7-10, 23, 24: PMIs & Inflation Trends (AlphaVantage + FRED)
  13-19, 25: Central Bank & Policy Rates (FRED + FMP + BS4)
  26, 28: CFTC Institutional Positioning (CFTC.gov ZIP → Pandas)
  27: Retail Sentiment (DailyFX/Oanda BS4 scraping)
  30: Seasonality (yfinance 15-year monthly closes)
"""

import os
import io
import re
import json
import zipfile
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import yfinance as yf

logger = logging.getLogger(__name__)

# ── API Key Configuration ──────────────────────────────────────────────────────
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "")
NEWSDATA_API_KEY = os.environ.get("NEWSDATA_API_KEY", "")

# ── Constants ──────────────────────────────────────────────────────────────────
TARGET_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
TARGET_CRYPTO = ["BTC", "ETH", "SOL", "XRP"]

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: FRED Macro Series (Points 7-10, 13-16, 23-24)
# ═══════════════════════════════════════════════════════════════════════════════

FRED_SERIES = {
    "GDPC1":    {"name": "Real GDP", "unit": "Billions USD"},
    "CPILFESL": {"name": "Core CPI", "unit": "Index 1982-1984=100"},
    "PCEPILFE": {"name": "Core PCE", "unit": "Index 2017=100"},
    "UNRATE":   {"name": "Unemployment Rate", "unit": "Percent"},
    "FEDFUNDS": {"name": "Fed Funds Rate", "unit": "Percent"},
    "DFII10":   {"name": "10Y TIPS Yield", "unit": "Percent"},
    "T10YIE":   {"name": "10Y Breakeven Inflation", "unit": "Percent"},
    "M2SL":     {"name": "M2 Money Supply", "unit": "Billions USD"},
    "INDPRO":   {"name": "Industrial Production", "unit": "Index 2017=100"},
    "CPIAUCSL": {"name": "Headline CPI", "unit": "Index 1982-1984=100"},
    "PPIACO":   {"name": "PPI All Commodities", "unit": "Index 1982=100"},
    "PAYEMS":   {"name": "Nonfarm Payrolls", "unit": "Thousands"},
    "DGS10":    {"name": "10Y Treasury Yield", "unit": "Percent"},
    "DGS2":     {"name": "2Y Treasury Yield", "unit": "Percent"},
}


def fetch_fred_series() -> dict[str, list[dict]]:
    """Fetch all configured FRED series. Returns {series_id: [observations]}."""
    if not FRED_API_KEY:
        logger.warning("FRED_API_KEY not set. Skipping FRED data.")
        return {}

    base_url = "https://api.stlouisfed.org/fred/series/observations"
    results: dict[str, list[dict]] = {}

    for series_id, meta in FRED_SERIES.items():
        try:
            params = {
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 120,
            }
            resp = requests.get(base_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            observations = data.get("observations", [])

            parsed = []
            for obs in observations:
                val_str = obs.get("value", ".")
                if val_str in (".", "", None):
                    continue
                try:
                    val = float(val_str)
                except (ValueError, TypeError):
                    continue
                parsed.append({
                    "date": obs.get("date", ""),
                    "value": val,
                    "unit": meta["unit"],
                })

            results[series_id] = parsed
            logger.info("FRED: %s → %d observations", series_id, len(parsed))

        except requests.RequestException as e:
            logger.warning("FRED: Failed %s: %s", series_id, e)
            continue

    return results


def get_latest_fred(results: dict[str, list[dict]], series_id: str) -> Optional[float]:
    """Get the most recent value for a FRED series."""
    obs = results.get(series_id, [])
    return obs[0]["value"] if obs else None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: FMP Economic Indicators (Points 1-6, 11, 12, 20-22, 29)
# ═══════════════════════════════════════════════════════════════════════════════

FMP_BASE = "https://financialmodelingprep.com/api/v3"


def fetch_fmp_economic_calendar() -> list[dict]:
    """Fetch economic calendar events from FMP."""
    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY not set. Skipping FMP calendar.")
        return []

    try:
        url = f"{FMP_BASE}/economic_calendar"
        params = {"apikey": FMP_API_KEY}
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        events = resp.json()
        logger.info("FMP Calendar: %d events fetched", len(events))
        return events if isinstance(events, list) else []
    except Exception as e:
        logger.warning("FMP Calendar failed: %s", e)
        return []


def fetch_fmp_forex_data() -> list[dict]:
    """Fetch major forex pair quotes from FMP."""
    if not FMP_API_KEY:
        return []
    try:
        url = f"{FMP_BASE}/forex"
        params = {"apikey": FMP_API_KEY}
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json() if isinstance(resp.json(), list) else []
    except Exception as e:
        logger.warning("FMP Forex failed: %s", e)
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Finnhub Economic Calendar (Points 1-6, 11, 12)
# ═══════════════════════════════════════════════════════════════════════════════

FINNHUB_BASE = "https://finnhub.io/api/v1"


def fetch_finnhub_calendar() -> list[dict]:
    """Fetch economic calendar from Finnhub."""
    if not FINNHUB_API_KEY:
        logger.warning("FINNHUB_API_KEY not set. Skipping Finnhub calendar.")
        return []

    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = f"{FINNHUB_BASE}/calendar/economic"
        params = {"token": FINNHUB_API_KEY, "from": today, "to": today}
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        events = data.get("economicCalendar", [])
        logger.info("Finnhub Calendar: %d events", len(events))
        return events
    except Exception as e:
        logger.warning("Finnhub Calendar failed: %s", e)
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: AlphaVantage Economic Indicators (Points 7-10, 23, 24)
# ═══════════════════════════════════════════════════════════════════════════════

AV_BASE = "https://www.alphavantage.co/query"


def fetch_av_economic_indicator(function: str) -> Optional[dict]:
    """Fetch an economic indicator from AlphaVantage."""
    if not ALPHAVANTAGE_API_KEY:
        return None
    try:
        params = {
            "function": function,
            "apikey": ALPHAVANTAGE_API_KEY,
        }
        resp = requests.get(AV_BASE, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("AlphaVantage %s failed: %s", function, e)
        return None


def fetch_av_real_gdp() -> Optional[float]:
    """Fetch latest real GDP from AlphaVantage."""
    data = fetch_av_economic_indicator("REAL_GDP")
    if not data:
        return None
    try:
        for key in data:
            if "data" in key.lower():
                return float(data[key][-1]["value"])
    except (KeyError, IndexError, ValueError):
        pass
    return None


def fetch_av_cpi() -> Optional[float]:
    """Fetch latest CPI from AlphaVantage."""
    data = fetch_av_economic_indicator("CPI")
    if not data:
        return None
    try:
        for key in data:
            if "data" in key.lower():
                return float(data[key][-1]["value"])
    except (KeyError, IndexError, ValueError):
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: CFTC Commitments of Traders (Points 26, 28)
# ═══════════════════════════════════════════════════════════════════════════════

CFTC_BASE_URL = "https://www.cftc.gov/files/dea/history/deahist{year}.zip"

CFTC_TARGET_MARKETS: dict[str, str] = {
    "EURO CURRENCY":                "EUR",
    "BRITISH POUND STERLING":       "GBP",
    "JAPANESE YEN":                 "JPY",
    "CANADIAN DOLLAR":              "CAD",
    "SWISS FRANC":                  "CHF",
    "AUSTRALIAN DOLLAR":            "AUD",
    "MEXICAN PESO":                 "MXN",
    "NEW ZEALAND DOLLAR":           "NZD",
    "GOLD":                         "XAU",
    "SILVER":                       "XAG",
    "CRUDE OIL, LIGHT SWEET":       "WTI",
    "S&P 500 STOCK INDEX":          "SP500",
    "NASDAQ-100 STOCK INDEX MINI":  "NAS100",
    "E-MINI S&P 500":               "ES",
    "U.S. TREASURY BOND":           "USB",
    "10 YEAR U.S. TREASURY NOTE":   "UST10Y",
}

CFTC_COL_MARKET = "Market_and_Exchange_Names"
CFTC_COL_DATE = "Report_Date_as_MM_DD_YYYY"
CFTC_COL_ASST_MANAGER_LONG = "Asset_Mgr_Positions_Long_All"
CFTC_COL_ASST_MANAGER_SHORT = "Asset_Mgr_Positions_Short_All"
CFTC_COL_LEV_FUNDS_LONG = "Lev_Money_Positions_Long_All"
CFTC_COL_LEV_FUNDS_SHORT = "Lev_Money_Positions_Short_All"
CFTC_COL_NONCOMM_LONG = "Non_Commercial_Positions_Long_All"
CFTC_COL_NONCOMM_SHORT = "Non_Commercial_Positions_Short_All"


def _download_cftc_zip(year: int) -> Optional[bytes]:
    """Download CFTC legacy ZIP for a given year."""
    url = CFTC_BASE_URL.format(year=year)
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        logger.info("CFTC: Downloaded %s (%d bytes)", url, len(resp.content))
        return resp.content
    except requests.RequestException as e:
        logger.warning("CFTC: Failed %s: %s", url, e)
        return None


def _parse_cftc_zip(content: bytes) -> pd.DataFrame:
    """Extract CSV from CFTC ZIP archive into a DataFrame."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            csv_files = [n for n in zf.namelist() if n.endswith((".csv", ".txt"))]
            if not csv_files:
                logger.error("CFTC: No CSV/TXT in ZIP.")
                return pd.DataFrame()
            with zf.open(csv_files[0]) as f:
                raw = f.read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
                return pd.read_csv(io.StringIO(text), low_memory=False)
    except Exception as e:
        logger.error("CFTC: ZIP parse failed: %s", e)
        return pd.DataFrame()


def fetch_cftc_data() -> dict[str, dict]:
    """
    Download and parse CFTC data. Returns structured dict per market:
    {
      "EUR": {
        "report_date": "2026-07-15",
        "noncomm_long": 200000, "noncomm_short": 100000,
        "asset_mgr_long": 80000, "asset_mgr_short": 40000,
        "lev_funds_long": 60000, "lev_funds_short": 30000,
        "net_speculative": 100000,
        "percentile_52w": 82.5,
        "weekly_change": 5000
      }, ...
    }
    """
    result: dict[str, dict] = {}
    current_year = datetime.now().year

    for year in [current_year, current_year - 1, 2025]:
        content = _download_cftc_zip(year)
        if content is None:
            continue

        df = _parse_cftc_zip(content)
        if df.empty:
            continue

        df.columns = df.columns.str.strip()

        # Check required columns exist
        required = [CFTC_COL_MARKET, CFTC_COL_DATE]
        if not all(c in df.columns for c in required):
            logger.warning("CFTC: Missing required columns in %d data", year)
            continue

        # Filter to target markets
        market_names = list(CFTC_TARGET_MARKETS.keys())
        df_filtered = df[
            df[CFTC_COL_MARKET].str.strip().str.upper().isin(
                [m.upper() for m in market_names]
            )
        ].copy()

        if df_filtered.empty:
            continue

        # Parse dates
        df_filtered.loc[:, CFTC_COL_DATE] = pd.to_datetime(
            df_filtered[CFTC_COL_DATE], format="%m/%d/%Y", errors="coerce"
        )
        df_filtered = df_filtered.dropna(subset=[CFTC_COL_DATE])

        # Convert numeric columns
        numeric_cols = []
        for col in [CFTC_COL_NONCOMM_LONG, CFTC_COL_NONCOMM_SHORT,
                     CFTC_COL_ASST_MANAGER_LONG, CFTC_COL_ASST_MANAGER_SHORT,
                     CFTC_COL_LEV_FUNDS_LONG, CFTC_COL_LEV_FUNDS_SHORT]:
            if col in df_filtered.columns:
                numeric_cols.append(col)
                df_filtered.loc[:, col] = (
                    pd.to_numeric(df_filtered[col], errors="coerce").fillna(0).astype(float)
                )

        # Compute net speculative
        if CFTC_COL_NONCOMM_LONG in df_filtered.columns:
            df_filtered.loc[:, "net_spec"] = (
                df_filtered[CFTC_COL_NONCOMM_LONG] - df_filtered[CFTC_COL_NONCOMM_SHORT]
            )

        df_filtered = df_filtered.sort_values([CFTC_COL_MARKET, CFTC_COL_DATE])

        for market_name, short_code in CFTC_TARGET_MARKETS.items():
            market_df = df_filtered[
                df_filtered[CFTC_COL_MARKET].str.strip().str.upper() == market_name.upper()
            ].copy()

            if market_df.empty:
                continue

            # Weekly change
            market_df["weekly_change"] = market_df["net_spec"].diff().fillna(0.0)

            # 52-week percentile
            window = min(52, len(market_df))
            if window > 1:
                market_df["percentile_52w"] = (
                    market_df["net_spec"]
                    .rolling(window=window, min_periods=1)
                    .apply(
                        lambda x: (
                            (x.iloc[-1] - x.min()) / (x.max() - x.min()) * 100
                            if x.max() != x.min()
                            else 50.0
                        ),
                        raw=False,
                    )
                )
            else:
                market_df["percentile_52w"] = 50.0

            latest = market_df.iloc[-1]

            entry = {
                "report_date": latest[CFTC_COL_DATE].strftime("%Y-%m-%d"),
                "noncomm_long": float(latest.get(CFTC_COL_NONCOMM_LONG, 0)),
                "noncomm_short": float(latest.get(CFTC_COL_NONCOMM_SHORT, 0)),
                "net_speculative": float(latest["net_spec"]),
                "weekly_change": float(latest["weekly_change"]),
                "percentile_52w": round(float(latest["percentile_52w"]), 2),
            }

            if CFTC_COL_ASST_MANAGER_LONG in latest:
                entry["asset_mgr_long"] = float(latest[CFTC_COL_ASST_MANAGER_LONG])
                entry["asset_mgr_short"] = float(latest[CFTC_COL_ASST_MANAGER_SHORT])
            if CFTC_COL_LEV_FUNDS_LONG in latest:
                entry["lev_funds_long"] = float(latest[CFTC_COL_LEV_FUNDS_LONG])
                entry["lev_funds_short"] = float(latest[CFTC_COL_LEV_FUNDS_SHORT])

            result[short_code] = entry
            logger.info(
                "CFTC: %s — Net: %.0f, Pctl: %.1f%%",
                short_code, entry["net_speculative"], entry["percentile_52w"],
            )

        if len(result) >= 5:
            break

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: Retail Sentiment (Point 27) — DailyFX Scraper
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_retail_sentiment() -> dict[str, dict]:
    """
    Scrape retail sentiment data from DailyFX.
    Returns {currency: {"long_pct": float, "short_pct": float}}.
    """
    result: dict[str, dict] = {}
    try:
        url = "https://www.dailyfx.com/sentiment"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for sentiment data in script tags or tables
        scripts = soup.find_all("script")
        for script in scripts:
            if script.string and "sentiment" in script.string.lower():
                # Try to extract JSON-like data
                matches = re.findall(
                    r'\{[^}]*"currency"[^}]*"long"[^}]*\}',
                    script.string
                )
                for match in matches:
                    try:
                        data = json.loads(match)
                        curr = data.get("currency", "")
                        if curr in TARGET_CURRENCIES:
                            result[curr] = {
                                "long_pct": float(data.get("long", 50)),
                                "short_pct": float(data.get("short", 50)),
                            }
                    except (json.JSONDecodeError, ValueError):
                        continue

        logger.info("Retail Sentiment: %d currencies parsed", len(result))
    except Exception as e:
        logger.warning("Retail Sentiment scrape failed: %s", e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: Seasonality (Point 30) — yfinance 15-year monthly closes
# ═══════════════════════════════════════════════════════════════════════════════

SEASONALITY_TICKERS = {
    "DX-Y.NYB": "USD",   # Dollar Index
    "EURUSD=X": "EUR",
    "GBPUSD=X": "GBP",
    "JPY=X":    "JPY",
    "AUDUSD=X": "AUD",
    "USDCAD=X": "CAD",
    "USDCHF=X": "CHF",
    "GC=F":     "XAU",   # Gold
    "CL=F":     "WTI",   # Crude Oil
    "^GSPC":    "SP500", # S&P 500
    "BTC-USD":  "BTC",
    "ETH-USD":  "ETH",
}


def fetch_seasonality() -> dict[str, float]:
    """
    Calculate historical % of positive monthly closes for the current month
    using 15 years of data. Returns {asset: score_1_to_10}.
    Score: % positive mapped to 1-10 scale (5 = 50%).
    """
    result: dict[str, float] = {}
    current_month = datetime.now().month

    for ticker, asset in SEASONALITY_TICKERS.items():
        try:
            data = yf.download(ticker, period="15y", interval="1mo",
                               progress=False, auto_adjust=True)
            if data.empty:
                continue

            # Filter to current month only
            monthly = data[data.index.month == current_month].copy()
            if len(monthly) < 3:
                continue

            # Calculate monthly returns - handle MultiIndex columns
            close_col = monthly["Close"] if isinstance(monthly["Close"], pd.Series) else monthly["Close"].iloc[:, 0]
            monthly_returns = close_col.pct_change() * 100
            positive_months = (monthly_returns > 0).sum()
            total_months = len(monthly_returns.dropna())

            if total_months == 0:
                continue

            pct_positive = positive_months / total_months * 100

            # Map to 1-10 score: 0% = 1, 50% = 5, 100% = 10
            score = 1.0 + (pct_positive / 100.0) * 9.0
            result[asset] = round(max(1.0, min(10.0, score)), 2)

            logger.info(
                "Seasonality: %s (%s) — %.0f%% positive → %.1f",
                asset, ticker, pct_positive, result[asset],
            )

        except Exception as e:
            logger.warning("Seasonality failed for %s: %s", ticker, e)
            continue

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: Central Bank Policy Rates (Points 13-19, 25)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_central_bank_rates() -> dict[str, float]:
    """
    Fetch official benchmark interest rates for major central banks.
    Uses FRED for Fed Funds, plus FMP for other central banks.
    Returns {currency_code: rate_percent}.
    """
    rates: dict[str, float] = {}

    # Fed Funds Rate from FRED
    fred_data = fetch_fred_series()
    fed_rate = get_latest_fred(fred_data, "FEDFUNDS")
    if fed_rate is not None:
        rates["USD"] = fed_rate

    # Other central bank rates from FMP
    if FMP_API_KEY:
        try:
            url = f"{FMP_BASE}/central_bank_rates"
            params = {"apikey": FMP_API_KEY}
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                for entry in data:
                    country = entry.get("country", "").upper()
                    rate = entry.get("rate")
                    if rate is not None:
                        try:
                            rate_val = float(rate)
                            currency_map = {
                                "EUROPEAN UNION": "EUR",
                                "UNITED KINGDOM": "GBP",
                                "JAPAN": "JPY",
                                "AUSTRALIA": "AUD",
                                "CANADA": "CAD",
                                "SWITZERLAND": "CHF",
                                "NEW ZEALAND": "NZD",
                            }
                            curr = currency_map.get(country)
                            if curr:
                                rates[curr] = rate_val
                        except (ValueError, TypeError):
                            continue
        except Exception as e:
            logger.warning("Central bank rates fetch failed: %s", e)

    logger.info("Central Bank Rates: %s", rates)
    return rates


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9: Yield Curve Data (Points 13-19 supplement)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_yield_curve() -> dict[str, dict]:
    """
    Fetch global bond yields via yfinance.
    Returns {instrument: {"yield": float, "ma50": float}}.
    """
    yield_tickers = {
        "^TNX":  "US10Y",
        "^GD10": "DE10Y",
        "^UMG":  "GB10Y",
        "^YT10": "JP10Y",
    }
    result: dict[str, dict] = {}

    for ticker, instrument in yield_tickers.items():
        try:
            bond = yf.Ticker(ticker)
            hist = bond.history(period="3mo")
            if hist.empty:
                continue

            latest_yield = float(hist["Close"].iloc[-1])
            ma50 = (
                float(hist["Close"].rolling(window=50).mean().iloc[-1])
                if len(hist) >= 50 else None
            )

            result[instrument] = {
                "yield": round(latest_yield, 4),
                "ma50": round(ma50, 4) if ma50 else None,
            }
            logger.info("Yield: %s = %.4f (MA50: %s)", instrument, latest_yield,
                        f"{ma50:.4f}" if ma50 else "N/A")
        except Exception as e:
            logger.warning("Yield fetch failed for %s: %s", ticker, e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER COLLECTOR: Gather all 30 data points into one structured dict
# ═══════════════════════════════════════════════════════════════════════════════

def collect_all_data() -> dict[str, Any]:
    """
    Execute all data parsers and return a unified data dictionary
    for the scoring engine.
    """
    logger.info("=" * 60)
    logger.info("COLLECTING ALL 30 DATA POINTS")
    logger.info("=" * 60)

    data: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # FRED Macro Series (Points 7-10, 13-16, 23-24)
    logger.info("\n[1/8] FRED Macro Series...")
    data["fred"] = fetch_fred_series()

    # FMP Economic Calendar (Points 1-6, 11, 12, 20-22, 29)
    logger.info("\n[2/8] FMP Economic Calendar...")
    data["fmp_calendar"] = fetch_fmp_economic_calendar()

    # Finnhub Calendar (Points 1-6, 11, 12)
    logger.info("\n[3/8] Finnhub Calendar...")
    data["finnhub_calendar"] = fetch_finnhub_calendar()

    # AlphaVantage Indicators (Points 7-10, 23, 24)
    logger.info("\n[4/8] AlphaVantage Indicators...")
    data["av_gdp"] = fetch_av_real_gdp()
    data["av_cpi"] = fetch_av_cpi()

    # CFTC Institutional Positioning (Points 26, 28)
    logger.info("\n[5/8] CFTC CoT Data...")
    data["cftc"] = fetch_cftc_data()

    # Retail Sentiment (Point 27)
    logger.info("\n[6/8] Retail Sentiment...")
    data["retail_sentiment"] = fetch_retail_sentiment()

    # Seasonality (Point 30)
    logger.info("\n[7/8] Seasonality...")
    data["seasonality"] = fetch_seasonality()

    # Central Bank Rates & Yields (Points 13-19, 25)
    logger.info("\n[8/8] Central Bank Rates & Yields...")
    data["central_bank_rates"] = fetch_central_bank_rates()
    data["yield_curve"] = fetch_yield_curve()

    logger.info("\n" + "=" * 60)
    logger.info("DATA COLLECTION COMPLETE")
    logger.info("=" * 60)

    return data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collected = collect_all_data()
    print(f"\nCollected {len(collected)} data categories.")
    for key, val in collected.items():
        if isinstance(val, dict):
            print(f"  {key}: {len(val)} items")
        elif isinstance(val, list):
            print(f"  {key}: {len(val)} entries")
        else:
            print(f"  {key}: {val}")