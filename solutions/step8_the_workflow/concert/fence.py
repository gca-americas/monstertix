"""Guards that run immediately before the agent spends money.

Module 4 is two separate failures that look like one:

  STALE   The agent held state["temp:seatmap"] across a forty-minute wait and
          bought from it. Those seats sold twelve minutes in. Nothing was
          missing from context — the wrong thing was *present*.

  REPEAT  The purchase committed, the response never arrived, and the runtime
          retried. ADK's own ResumabilityConfig docstring warns about this:
          "Tool call to resume needs to be idempotent because we only guarantee
          an at-least-once behavior once resumed." The platform will retry you.

The fix for the first is to re-fetch in the instant before acting. The fix for
the second is a key the venue can recognise.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import BaseTool, ToolContext

from . import venue

MAX_SNAPSHOT_AGE_SECONDS = 30.0


def refresh_before_purchase(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict | None:
    """Re-check live inventory before any purchase goes through.

    Returning a dict short-circuits the tool, so the agent never reaches the
    venue with a stale plan.
    """
    if tool.name != "purchase":
        return None

    event_id = args.get("event_id")
    section = args.get("section", "A")
    seats = int(args.get("seats", 2))
    if not event_id:
        return None

    live = venue.get(f"/events/{event_id}/seatmap")
    current = next(
        (s for s in live["sections"] if s["section"] == section),
        None,
    )
    if current is None:
        return {
            "error": True,
            "message": f"section {section} does not exist for {event_id}",
        }

    # What the agent *thought* was true, for a useful error message.
    snapshot = tool_context.state.get("temp:seatmap") or {}
    believed = next(
        (s for s in snapshot.get("sections", []) if s["section"] == section),
        None,
    )

    if current["available"] < seats:
        return {
            "error": True,
            "reason": "stale_plan",
            "message": (
                f"Section {section} has {current['available']} seats left, "
                f"{seats} requested. Re-read the seat map and pick again."
            ),
            "believed_available": believed.get("available") if believed else None,
            "actually_available": current["available"],
        }

    if believed and believed["price"] != current["price"]:
        return {
            "error": True,
            "reason": "price_moved",
            "message": (
                f"Price for section {section} moved from {believed['price']} to "
                f"{current['price']}. Confirm before buying."
            ),
        }

    # Fresh enough to act on. Hand the live price down to the tool.
    tool_context.state["temp:verified_price"] = current["price"]
    return None
