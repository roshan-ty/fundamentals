"""
Typed dataclasses for the Bulls & Bears Fundamentals scoring engine.
All scores are on a 0–10 scale unless otherwise noted.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import date


# ── FRED / Macro Data ──────────────────────────────────────────────────────────

@dataclass
class FredSeries:
    """A single FRED observation."""
    series_id: str
    series_name: str
    date: str          # ISO date string
    value: float
    unit: str = ""


@dataclass
class FredData:
    """Container for all fetched FRED series."""
    series: list[FredSeries] = field(default_factory=list)
    last_updated: str = ""


# ── CFTC / CoT Data ───────────────────────────────────────────────────────────

@dataclass
class CftcPosition:
    """Net speculative positioning for a single market."""
    market: str
    report_date: str
    noncomm_long: float
    noncomm_short: float
    net_speculative: float
    weekly_change: float
    percentile_52w: float   # 0–100
    last_updated: str = ""


@dataclass
class CftcData:
    """Container for all CFTC positions."""
    positions: list[CftcPosition] = field(default_factory=list)
    last_updated: str = ""


# ── Yield Curve Data ──────────────────────────────────────────────────────────

@dataclass
class YieldEntry:
    """Yield observation for a single instrument."""
    instrument: str        # e.g. "US10Y", "DE10Y", "GB10Y", "JP10Y"
    date: str
    yield_value: float     # percentage (e.g. 4.5 means 4.5%)
    yield_ma50: Optional[float] = None


@dataclass
class YieldData:
    entries: list[YieldEntry] = field(default_factory=list)
    last_updated: str = ""


# ── Economic Calendar / Event Surprise Data ───────────────────────────────────

@dataclass
class CalendarEvent:
    """A single high-impact economic event."""
    currency: str
    event_name: str
    date: str
    actual: float
    forecast: float
    previous: float
    surprise_ratio: float = 0.0


@dataclass
class CalendarData:
    events: list[CalendarEvent] = field(default_factory=list)
    last_updated: str = ""


# ── Scoring Data ──────────────────────────────────────────────────────────────

@dataclass
class CurrencyScores:
    """
    The four component scores plus the average for one currency.
    All scores 0–10.
    """
    currency: str                    # e.g. "USD"
    macro_score: float = 5.0
    event_surprise_score: float = 5.0
    yield_momentum_score: float = 5.0
    cftc_sentiment_score: float = 5.0
    average_score: float = 5.0
    updated_at: str = ""


@dataclass
class PairBias:
    """Bias for a single traded pair/asset."""
    asset_class: str       # "FX", "METAL", "ENERGY", "INDEX"
    name: str              # e.g. "EUR/USD", "XAU/USD", "US500"
    base_currency: str     # Base or primary asset
    quote_currency: str    # Quote or secondary (empty for singles)
    base_score: float
    quote_score: float
    combined_bias: float
    direction: str         # "Strongly Bullish" | "Bullish" | "Neutral" | "Bearish" | "Strongly Bearish"
    conclusion: str        # Short textual explanation


@dataclass
class PairsData:
    pairs: list[PairBias] = field(default_factory=list)
    last_updated: str = ""


@dataclass
class TradeSetup:
    """Highest-probability setup from extreme bias scores."""
    asset_name: str
    direction: str
    combined_bias: float
    fundamental_consensus: str


@dataclass
class TradeSetupsData:
    setups: list[TradeSetup] = field(default_factory=list)
    last_updated: str = ""


# ── News Feed Data ────────────────────────────────────────────────────────────

@dataclass
class NewsArticle:
    title: str
    source: str
    link: str
    published_at: str
    description: str = ""


@dataclass
class NewsData:
    articles: list[NewsArticle] = field(default_factory=list)
    last_updated: str = ""


# ── Utility ───────────────────────────────────────────────────────────────────

def clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    """Clamp a value between low and high inclusive."""
    return max(low, min(high, round(value, 2)))


def direction_label(bias: float) -> str:
    """Return a human-readable direction label for a combined bias score."""
    if bias >= 8.0:
        return "Strongly Bullish"
    elif bias >= 6.0:
        return "Bullish"
    elif bias >= 4.1:
        return "Neutral"
    elif bias >= 2.1:
        return "Bearish"
    else:
        return "Strongly Bearish"


def dict_factory(data):
    """Convert dataclass to dict, excluding None values."""
    return {k: v for k, v in data if v is not None}