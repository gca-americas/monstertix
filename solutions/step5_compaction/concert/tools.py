"""MODULE 3 tools — now the agent leaves a trail worth inspecting.

Three things land in three different places, and Module 3 is students finding
each one in the dev UI:

  the seat map JSON     -> an artifact, out of the prompt entirely
  a short summary       -> state["temp:seatmap"], which does NOT survive
  who you're going with -> state["user:prefs"], which does

Most people guess wrong about temp:. That guess is Module 4's bug.
"""

from __future__ import annotations

import json
import time

from google.adk.tools import ToolContext
from google.genai import types

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


async def get_seatmap(event_id: str, tool_context: ToolContext) -> dict:
    """Look up current sections, prices and availability for one show.

    Args:
        event_id: The event id from search_events, e.g. "ms-ams-01".

    Returns:
        A short summary of sections and prices. The full seat map is saved as
        an artifact rather than returned, so it never enters the prompt.
    """
    seatmap = venue.get(f"/events/{event_id}/seatmap")

    # The venue returns errors as data, so check before indexing into it. A
    # model that invents an event id — ms-tko-01 for Tokyo, when the real one is
    # ms-tyo-01 — gets a 404 here, and without this guard the KeyError below
    # takes down the whole run instead of letting the agent look the id up.
    if seatmap.get("error"):
        return {
            "error": True,
            "event_id": event_id,
            "message": f"no show with id {event_id!r}. "
                       "Call search_events to get the real ids, and use one of those.",
        }

    # The full map is bulky and mostly noise to the model. Park it as a file
    # and hand back a filename.
    part = types.Part(
        inline_data=types.Blob(
            mime_type="application/json",
            data=json.dumps(seatmap, indent=2).encode(),
        )
    )
    filename = f"seatmap_{event_id}.json"
    await tool_context.save_artifact(filename, part)

    summary = {
        "event_id": event_id,
        "venue": seatmap["venue"],
        "city": seatmap["city"],
        "date": seatmap["date"],
        "weekday": seatmap["weekday"],
        "sections": [
            {"section": s["section"], "price": s["price"], "available": s["available"]}
            for s in seatmap["sections"]
        ],
        "captured_at": seatmap["captured_at"],
        "artifact": filename,
    }

    # temp: is not persisted. An agent that comes back to this after a long
    # wait is holding a snapshot, and the snapshot is a lie.
    tool_context.state["temp:seatmap"] = summary
    tool_context.state["temp:seatmap_captured"] = time.strftime(
        "%H:%M:%S", time.localtime(seatmap["captured_at"])
    )
    return summary


def note_companion(name: str, constraint: str, tool_context: ToolContext) -> dict:
    """Record who is coming and any constraint they have.

    Args:
        name: Who is coming, e.g. "Sam".
        constraint: What limits them, e.g. "cannot do weeknights".

    Returns:
        The updated companion list.
    """
    prefs = dict(tool_context.state.get("user:prefs", {}))
    prefs[name] = constraint
    tool_context.state["user:prefs"] = prefs
    return {"companions": prefs}


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
