"""MODULE 4 — Pull the plug.

Two new pieces, and between them they are what "long-running" actually means.

  LongRunningFunctionTool(func=join_queue)
      The tool returns immediately with a ticket, and the invocation parks.
      The agent is NOT running for the next forty minutes. It is gone.

  ResumabilityConfig(is_resumable=True)
      Lets the app pause on that long-running call and resume from the last
      event afterwards. Read the library's own docstring for it — it states
      this workshop's thesis better than any slide:

          "1. pause an invocation upon a long-running function call.
           2. resume an invocation from the last event, if it's paused or
              failed midway through.
           Note: ADK resumes in a best-effort manner:
           1. Tool call to resume needs to be idempotent because we only
              guarantee an at-least-once behavior once resumed.
           2. Any temporary / in-memory state will be lost upon resumption."

      Point 1 is Module 4's second half. Point 2 is why temp:seatmap is a trap.

RUN IT WITH A REAL SESSION STORE, or none of this survives:

    adk web --session_service_uri="sqlite:///sessions.db" \
            --artifact_service_uri="file://./artifacts" .

Then kill the agent mid-queue, start it again, and look:

    sqlite3 sessions.db "select * from events limit 5"
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.apps.app import App, EventsCompactionConfig, ResumabilityConfig
from google.adk.tools import LongRunningFunctionTool
from google.adk.tools.agent_tool import AgentTool

from .config import MODEL
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
this person from past bookings. It is not in this conversation.

The queue comes first. The moment you know which show, call join_queue — you do
not need a section or a price to join. Do not ask permission first.

Having joined, say what position you landed at and stop there. Do not look up
seats, prices or sections unless you are asked for them.

If you are asked about seats or prices while you wait, read the seat map and
answer with the real numbers. Once you and the user have settled on a section,
that is the plan: when you are woken, carry it out.

Do not poll check_queue in a loop. But NEVER quote a queue position from memory
either — a position you were told earlier is already out of date, the line moves
while you talk, and somebody may have sent you to the front. Call check_queue
immediately before you state a position, and immediately before any purchase
attempt. If the user says they are at the front and you believe otherwise, they
are looking at the venue and you are looking at a memory: check, then answer.

Use note_companion for who is coming and what limits them. Use remember() for
preferences and outcomes, never for prices or availability.

For arithmetic across several shows, call budget_split. It cannot see this
conversation, so include everything it needs.

Be concrete and brief.
"""

root_agent = Agent(
    name="concert",
    model=MODEL,
    instruction=INSTRUCTION,
    tools=[
        search_events,
        get_seatmap,
        purchase,
        note_companion,
        recall,
        remember,
        LongRunningFunctionTool(func=join_queue),
        check_queue,
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
