"""MODULE 4 — Acting on old news.

The agent can finally buy. Which is when both failures show up.

STALE
    It comes back from a forty-minute wait holding state["temp:seatmap"] and
    buys from it. Those seats sold twelve minutes in. Nothing was missing from
    context — the wrong thing was present.

    Fix: before_tool_callback=refresh_before_purchase. It re-reads live
    inventory in the instant before the purchase and short-circuits the tool if
    the plan has gone stale.

REPEAT
    The order commits, the response never arrives, the runtime retries, and now
    you own four tickets. Press HANG ONCE on the control panel to watch it.

    Fix: an Idempotency-Key derived from session + event + section + seats, so a
    retry of the same purchase produces the same key and the venue returns the
    original order.

Neither bug is written by the student. The platform causes the second one on its
own — ADK's ResumabilityConfig guarantees at-least-once on resume, and that is a
promise, not a warning.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.apps.app import App, EventsCompactionConfig, ResumabilityConfig
from google.adk.tools import LongRunningFunctionTool
from google.adk.tools.agent_tool import AgentTool

from .config import MODEL
from .fence import refresh_before_purchase
from .memory import recall, remember
from .panel import PanelPlugin
from .tools import (
    check_queue,
    get_seatmap,
    join_queue,
    note_companion,
    purchase,
    search_events,
)

budget_split = Agent(
    name="budget_split",
    model=MODEL,
    include_contents="none",
    instruction="""
You do ticket arithmetic and nothing else.

Given a per-person budget, a number of people, and a list of sections with
prices, work out which sections fit and what the total is. Show the numbers.

You have no conversation history and do not need any. Everything you need is in
the request.
""",
    output_key="budget_plan",
)

INSTRUCTION = """
You help someone buy tickets to see a band on tour.

Before recommending anything, call recall() to read what you already know about
this person from past bookings.

The queue comes first. The moment you know which show, call join_queue — you do
not need a section or a price to join. Say what position you landed at, and read
the seat map while you wait if it helps you plan.

Do not poll check_queue in a loop. Call it when you are woken, or if the user
asks where they are in line.

When you are woken, do not trust anything you looked up before the wait. Read
the seat map again, then purchase.

If a purchase comes back with reason "stale_plan" or "price_moved", the world
moved while you were waiting. Re-read the seat map, tell the user what changed,
and pick again — never retry the same purchase blindly.

Use note_companion for who is coming. Use remember() for preferences and
outcomes, never for prices or availability.

Be concrete and brief.
"""

root_agent = Agent(
    name="concert",
    model=MODEL,
    instruction=INSTRUCTION,
    # Runs in the instant before any purchase reaches the venue.
    before_tool_callback=refresh_before_purchase,
    tools=[
        search_events,
        get_seatmap,
        note_companion,
        recall,
        remember,
        LongRunningFunctionTool(func=join_queue),
        check_queue,
        purchase,
        AgentTool(agent=budget_split),
    ],
)

app = App(
    name="concert",
    root_agent=root_agent,
    plugins=[PanelPlugin()],
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,
        overlap_size=1,
    ),
    resumability_config=ResumabilityConfig(is_resumable=True),
)
