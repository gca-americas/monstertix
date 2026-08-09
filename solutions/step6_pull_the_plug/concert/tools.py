"""MODULE 4 tools — the agent learns to wait.

join_queue is the one that matters. It returns *immediately* with a pending
status and a ticket, and the invocation parks. The agent is not running during
the forty minutes that follow. It is gone. Something external brings it back.

Nothing is looping and nothing holds a connection open. When somebody asks the
agent again — you, or a scheduler — it picks up where it stopped, because the
session was written to disk before it parked.
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


def join_queue(event_id: str, tool_context: ToolContext) -> dict:
    """Join the on-sale waiting room for a show.

    Returns immediately with a queue position. Reaching the front takes about
    forty minutes of venue time. Do not poll in a loop — call check_queue when
    somebody asks, and not otherwise.

    Args:
        event_id: The event id to queue for, e.g. "ms-ams-01".

    Returns:
        The queue ticket and current position.
    """
    result = venue.post("/queue/join", {"event_id": event_id})
    if result.get("error"):
        return result

    tool_context.state["queue_ticket"] = result["ticket"]
    tool_context.state["queue_event_id"] = event_id
    return {
        "status": "waiting",
        "ticket": result["ticket"],
        "position": result["position"],
        "estimated_wait_seconds": result["real_seconds_remaining"],
        "note": "You are queued. Stop here; check again when asked.",
    }


def check_queue(tool_context: ToolContext, ticket: str = "") -> dict:
    """Check whether a queue ticket has reached the front.

    Args:
        ticket: The ticket id. Defaults to the one stored in state.

    Returns:
        Current position and whether it is your turn.
    """
    ticket = ticket or tool_context.state.get("queue_ticket", "")
    if not ticket:
        return {"error": True, "message": "no queue ticket in state"}
    return venue.get(f"/queue/{ticket}")


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
