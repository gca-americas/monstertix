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
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models.google_llm import Gemini
from google.adk.tools.agent_tool import AgentTool

from .config import MODEL
from .fence import refresh_before_purchase
from .memory import recall, remember
from .panel import PanelPlugin
from .tools import (
    get_seatmap,
    note_companion,
    purchase,
    search_events,
)

budget_split = Agent(
    name="budget_split",
    model=MODEL,
    # The description is what the MAIN agent reads when deciding whether to call
    # this. A vague one and it does the sums itself, which is the whole point of
    # the step going quietly missing.
    description=(
        "Works out ticket costs. Call this for ANY question about totals, "
        "per-seat costs, or which sections fit a budget."
    ),
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

You do not join queues any more, and you cannot check one. Something else got
you to the front before it woke you — assume you are at the front and can buy
right now.

Before buying, read the seat map again. Whatever you were told about prices and
availability was true when the queue started, which may have been forty minutes
ago.

When you are woken, do not trust anything you looked up before the wait. Read
the seat map again, then purchase.

If a purchase comes back with reason "stale_plan" or "price_moved", the world
moved while you were waiting. Re-read the seat map, tell the user what changed,
and pick again — never retry the same purchase blindly.

Use note_companion for who is coming. Use remember() for preferences and
outcomes, never for prices or availability.

Be concrete and brief.
"""

buyer_agent = Agent(
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
            purchase,
        AgentTool(agent=budget_split),
    ],
)


# THE ROOT IS THE GRAPH.
#
# `adk web` looks for `app` first, then `root_agent`. From this module on both
# point at the workflow, not at the chat agent: the thing you run is the graph.
# `buyer_agent` above is still every tool and callback you built — it is now one
# node inside that graph rather than the thing you talk to.
#
# Imported last, because nightly.py imports `buyer_agent` from this file.
from .nightly import nightly                              # noqa: E402

root_agent = nightly

app = App(
    name="concert",
    root_agent=nightly,
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,
        overlap_size=1,
        # Required once the root is a Workflow. ADK normally borrows the
        # summariser's model from the root agent, and a graph has no model —
        # `No LlmAgent model available for event compaction summarizer.` So
        # name one explicitly.
        summarizer=LlmEventSummarizer(llm=Gemini(model=MODEL)),
    ),
    resumability_config=ResumabilityConfig(is_resumable=True),
)
