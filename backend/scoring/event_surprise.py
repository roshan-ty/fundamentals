"""
High-Impact Event Surprise Score — Uses the last 5 high-impact releases
per currency to compute a surprise ratio and map to a 0–10 score.
"""

import logging
from typing import Optional
from collections import defaultdict

from backend.models.schemas import CalendarData, CalendarEvent, clamp

logger = logging.getLogger(__name__)


def compute_event_surprise_score(calendar_data: CalendarData) -> dict[str, float]:
    """
    Compute event surprise scores for each currency.
    
    For each currency, take the last 5 high-impact events and compute
    the cumulative surprise. Map to 0–10 score.
    
    Surprise Ratio = (Actual - Forecast) / |Forecast|
    
    Score mapping:
    - Consistently strong positive surprises (net cumulative > 1.0) = 8 to 10
    - Mixed or matching forecasts = 5
    - Consistently negative surprises (net cumulative < -1.0) = 0 to 2
    """
    if not calendar_data.events:
        logger.warning("Event Surprise: No calendar events available.")
        return {c: 5.0 for c in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF"]}

    # Group events by currency, sorted by date descending
    currency_events: dict[str, list[CalendarEvent]] = defaultdict(list)
    for event in calendar_data.events:
        currency_events[event.currency].append(event)

    scores: dict[str, float] = {}
    
    # Target currencies
    target_currencies = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF"]

    for currency in target_currencies:
        events = currency_events.get(currency, [])
        # Sort by date descending, take last 5
        events_sorted = sorted(events, key=lambda e: e.date, reverse=True)
        recent_events = events_sorted[:5]

        if not recent_events:
            scores[currency] = 5.0
            continue

        # Compute cumulative surprise
        cumulative_surprise = sum(e.surprise_ratio for e in recent_events)

        # Score mapping
        if cumulative_surprise >= 0.8:
            score = 8.0 + min(2.0, cumulative_surprise * 1.5)  # 8–10
        elif cumulative_surprise >= 0.3:
            score = 6.0 + (cumulative_surprise - 0.3) * 4.0  # 6–8
        elif cumulative_surprise >= -0.3:
            score = 5.0 + cumulative_surprise * 3.33  # ~4–6
        elif cumulative_surprise >= -0.8:
            score = 4.0 + (cumulative_surprise + 0.3) * 4.0  # 2–4
        else:
            score = max(0.0, 2.0 + (cumulative_surprise + 0.8) * 2.5)  # 0–2

        scores[currency] = clamp(score)
        logger.info(
            "Event Surprise — %s: cumulative=%.4f, score=%.2f",
            currency, cumulative_surprise, scores[currency],
        )

    return scores


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from backend.models.schemas import CalendarData, CalendarEvent

    cd = CalendarData()
    cd.events.append(CalendarEvent(currency="USD", event_name="CPI", date="2026-07-01", actual=3.2, forecast=3.0, previous=2.8, surprise_ratio=0.0667))
    cd.events.append(CalendarEvent(currency="USD", event_name="NFP", date="2026-07-01", actual=250, forecast=200, previous=180, surprise_ratio=0.25))
    cd.events.append(CalendarEvent(currency="USD", event_name="GDP", date="2026-06-15", actual=2.1, forecast=2.0, previous=1.9, surprise_ratio=0.05))

    scores = compute_event_surprise_score(cd)
    print(f"Event Surprise scores: {scores}")