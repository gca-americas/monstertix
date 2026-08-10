"""MODULE 3 — What the summary throws away.

Two lines carry this module.

1. App(events_compaction_config=...) turns on the thing every runtime now does
   automatically: once enough turns have gone by, older events are replaced
   with an LLM summary. Summaries keep the gist and drop the exceptions, and
   "Sam bails on weeknights" is an exception. The agent then books Tuesday and
   explains its reasoning perfectly.

2. include_contents='none' on the budget_split sub-agent. It does arithmetic on
   ticket prices. It has no business reading four hours of group chat, and with
   this flag it doesn't — its prompt is the request and nothing else.

The fix for (1) is not "compact less". It's to stop leaving load-bearing facts
in the transcript at all: note_companion writes to user:prefs, remember() writes
to the memory file, and neither is something a summarizer can paraphrase away.

NOTE ON THE INTERVAL: compaction_interval counts *user-initiated invocations*,
not raw events. 3 is tuned for a workshop, so students see it fire within a few
turns. Production values are much larger — or use token_threshold instead.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.tools.agent_tool import AgentTool

from .config import MODEL
from .memory import recall, remember
from .tools import get_seatmap, note_companion, purchase, search_events

# --- the isolated sub-agent ----------------------------------------------

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
    # THE LINE. Without it this agent inherits the whole conversation.
    include_contents="none",
    instruction="""
You do ticket arithmetic and nothing else.

Given a per-person budget, a number of people, and a list of sections with
prices, work out which sections fit and what the total is. Show the numbers.

You have no conversation history and do not need any. Everything you need is in
the request.
""",
    # The result lands in state instead of being left loose in the transcript.
    output_key="budget_plan",
)

# --- the root agent -------------------------------------------------------

INSTRUCTION = """
You help someone plan a trip to see a band on tour.

Before recommending anything, call recall() to read what you already know about
this person from past bookings. It is not in this conversation.

Use note_companion when someone mentions who is coming and what limits them —
that fact needs to outlive this chat. Use remember() for preferences and
outcomes, never for prices or availability.

NEVER do ticket arithmetic yourself. The moment a question involves a total, a
per-seat cost, or which sections fit a budget, call budget_split — even when the
sum looks trivial and even when you are confident you could do it.

Call it with the budget, the party size, and the sections with prices. It cannot
see this conversation, so include everything it needs. If nobody has named a
budget yet, ask for one before you start comparing prices.

Be concrete: name the show, the city, the section, and the price. Keep answers
to two or three sentences unless asked for more.
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
        AgentTool(agent=budget_split),
    ],
)

# adk web looks for `app` before `root_agent`, so this is what actually runs.
app = App(
    name="concert",
    root_agent=root_agent,
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,
        overlap_size=1,
    ),
)
