"""MODULE 1 tools — search and look at seats. Nothing that waits, nothing that buys.

The agent is genuinely good at this. That is the point: it plans the trip
beautifully and is still asleep when the presale drops.
"""

from __future__ import annotations

from . import venue


def search_events(city: str = "", weekday: str = "") -> dict:
    """List tour dates. Call with no arguments to see the whole tour.

    This venue sells one artist and one tour, so there is nothing to search by
    name — never ask the user which artist they mean.

    Args:
        city: Optional. Filter to one city, e.g. "Amsterdam".
        weekday: Optional. Filter to one weekday, e.g. "Saturday".

    Returns:
        Tour dates with venue, city, date and weekday.
    """
    return venue.get("/events", city=city, weekday=weekday)


def get_seatmap(event_id: str) -> dict:
    """Look up current sections, prices and availability for one show.

    Args:
        event_id: The event id from search_events, e.g. "ms-ams-01".

    Returns:
        Sections with tier, price and seats available, plus a captured_at
        timestamp recording when this snapshot was taken.
    """
    return venue.get(f"/events/{event_id}/seatmap")


def purchase(event_id: str, section: str, seats: int) -> dict:
    """Buy seats. Spends real money.

    Only call this when you know which show, which section, and how many — and
    when the person has actually asked for it. Never guess on someone's behalf.

    Args:
        event_id: The show to buy for, e.g. "ms-ams-01".
        section: Section letter — "A" lower bowl, "B" upper, "C" general.
        seats: How many seats.

    Returns:
        The order, or an error explaining why it did not go through.
    """
    return venue.post(
        "/purchase",
        {"event_id": event_id, "section": section, "seats": seats},
    )
