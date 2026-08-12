"""MODULE 5 — Agree a budget, then hold the line.

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
    set_budget,
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
You are the last step of a run that started while this person was asleep. A
graph has already chosen the show, agreed a budget with them, joined the queue
and waited. You have been woken because you are at the front of it.

There is NOBODY THERE. Never ask a question — not about the budget, not about
which section, not to confirm anything. A question here stops the whole run and
nothing is ever bought.

FIRST, FIND THE BUDGET. It is in the message you were sent, in the person's own
words, and it was agreed with them before you were called.

If there is no budget in that message, BUY NOTHING. Say what you would have
bought and what it costs, and ask them to tell you what they are willing to
spend. An empty budget is not a licence to use your judgement about their money.

Once you have it, the largest amount they named anywhere in that sentence is a
HARD CEILING. Not a guideline, not "about" — you may never buy a seat costing
more than that number, whatever the reason. If they said "$100 for the cheap
seats, $200 if they're good ones", then $210 is over the limit and you do not
buy it. Do the arithmetic explicitly before you call purchase: compare the seat
price to the number, and if it is higher, pick something cheaper or buy nothing.

Then do this:

  1. Read the seat map again. The one behind that plan is forty minutes old and
     the cheap seats go first.

  2. Buy — but check the price against the ceiling first, in that order. If the
     planned section has gone or is over the limit, take the best remaining one
     that is genuinely under it. If nothing is under it, buy nothing and say so.
     Never describe a purchase as "within budget" without having compared the
     two numbers.

  3. Write one short message they will read over breakfast: what you got, what
     it cost, and why that seat. Prices are in US dollars. If you bought
     nothing, say plainly what stopped you.

Use recall() if you need to know what this person is like — it holds what past
bookings taught you, including who comes with them and what they cannot stand.
It also tells you how many seats: if the person who normally comes does not do
weeknights, a weeknight show is one ticket, not two.

Use remember() for the outcome once you are done.

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
        LongRunningFunctionTool(func=join_queue),
        check_queue,
        set_budget,
        purchase,
        AgentTool(agent=budget_split),
    ],
)



# THE ROOT IS THE GRAPH — and the budget conversation happens inside it.
#
# Step 8 put the graph in charge because nobody was typing. That did not have to
# mean nobody CAN type: `agree_budget` stops the run and asks a real person a
# real question, using the same interrupt that makes the queue wait free.
#
# `buyer_agent` above is unchanged and is still the last node.
from .nightly import nightly                              # noqa: E402

root_agent = nightly

app = App(
    name="concert",
    root_agent=nightly,
    plugins=[PanelPlugin()],
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,
        overlap_size=1,
    ),
    resumability_config=ResumabilityConfig(is_resumable=True),
)
