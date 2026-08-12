"""MODULE 5 — the graph, now inside the same budget.

Nothing here replaces what you built. It surrounds it.

    START ─► open ─► pick_show ──► queue_up ──► check_front ──► buy_it
             (fn)     (agent)       (function)    (function)      (agent)
             reads memory  joins once,   at the front?   buys, using
             picks a show  keeps ticket    no → PAUSE    the seat map
                                           yes ↓          it re-reads
             ─ runs once ─────────────┘    │
                                           └─ every wake-up re-checks

The shape of that graph is the whole lesson, and it is not "replace the agent
with a script". Two nodes are agents, because choosing a show and reacting to a
seat map that moved are judgement. Two nodes are functions, because joining a
queue and asking "am I at the front yet" are rules, and a rule should not be a
coin flip at 3am.

WHAT HAPPENS WHEN IT IS NOT AT THE FRONT

`check_front` returns a `RequestInput`. That is ADK's interrupt: the graph stops
where it stands and the invocation is written to the session store. Nothing
loops, nothing sleeps, nothing holds a connection open. The process can die.

Waking it up runs `check_front` again — and only `check_front`:

    @node(rerun_on_resume=False)     pick_show, queue_up
        already done. Resuming does not redo them, so the agent does not pick a
        second show and you do not take a second queue ticket.

    @node(rerun_on_resume=True)      check_front
        the whole point. Every wake-up asks the venue where you are, and either
        stops again or falls through to the purchase.

So the run ends in exactly one place: tickets bought. It just might take all
night and several wake-ups to get there, and it costs nothing in between.

Run it by hand:
    python -m concert.nightly

It will stop at #14,203. Press SKIP THE WAIT on the panel, and it wakes itself
to show you the loop. In Module 6 the thing doing the waking is Cloud Scheduler.
"""

from __future__ import annotations

import asyncio
import warnings

from google.adk import Event, Runner, Workflow
from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.artifacts import InMemoryArtifactService
from google.adk.events.request_input import RequestInput
from google.adk.sessions import DatabaseSessionService
from google.adk.workflow import START, node
from google.adk.workflow.utils._workflow_hitl_utils import (
    create_request_input_response,
    get_request_input_interrupt_ids,
)
from google.genai import types
from pydantic import BaseModel

from . import budget, memory, venue
from .agent import buyer_agent
from .config import MODEL
from .memory import recall
from .tools import get_seatmap, search_events

warnings.filterwarnings("ignore", message=r".*\[EXPERIMENTAL\].*")

# A fallback for the very first unattended run, before anyone has agreed
# anything. Once set_budget has been called the graph uses that instead — the
# limit you agree in chat is the limit that runs tonight.
# Only used if nobody has agreed anything yet. The moment set_budget has been
# called the graph runs on THAT — what you confirmed in the chat is what gets
# spent tonight, conditions and all.
DEFAULT_BUDGET = "up to $250 per seat"


class Plan(BaseModel):
    """What pick_show decides, and what every node after it works from."""

    event_id: str
    city: str
    section: str
    seats: int
    reason: str


# --- node 0: say what tonight is for ---------------------------------------


@node(rerun_on_resume=False)
def open_the_night(node_input, ctx: Context) -> Event:
    """Give the picker something to answer, and tell it what it may spend.

    Two jobs. An agent node responds to its input, and first in the graph with no
    user message there is nothing to respond to — so this says the sentence a
    person would have said.

    The other job is the budget. It is read from `user:` state, which is where
    `set_budget` put it when somebody confirmed a number in conversation. That
    is the join between the two halves of this module: the limit is agreed by a
    person while they are awake, and spent by a graph while they are not.
    """
    agreed = budget.load(ctx.state) or DEFAULT_BUDGET
    asked = str(ctx.state.get("request") or "").strip()
    print(f"  [open]        3am. Nobody is awake. Budget: {budget.describe(agreed)}")
    if asked:
        print(f"  [open]        they asked for: {asked[:70]}")
    return Event(output=(
        "Choose tonight's show and section, and buy nothing yet.\n\n"
        f"What this person asked for, in their own words:\n\n"
        f"    {asked or '(nothing said this time. Use what recall() tells you.)'}"
        f"\n\nThe budget they agreed to, in their words:\n\n"
        f"    {agreed}\n\n"
        "Apply all of it, including any conditions about cities, days, how many "
        "are coming, or which sections. If nothing on the tour fits, choose "
        "nothing and say so."
    ))


# --- node 1: agree a budget, in the graph, with a real human ---------------


def what_they_asked_for(ctx) -> str:
    """Everything this person typed, joined, in their own words.

    The same argument `budget.py` makes about money applies to the rest of the
    ask. The tempting design is fields — city, party_size, weekends_only — and it
    breaks on the first sentence you did not anticipate ("I have 10 people coming
    with me, but two of them might drop out"). So do not model it. Keep the text
    and let the picker read it.

    Only `text` parts count, which quietly does the right thing: answers to an
    interrupt arrive as function_responses, so the budget conversation does not
    get echoed back in here. What is left is what they freely said.
    """
    said = []
    for event in (ctx.session.events or []):
        if event.author != "user":
            continue
        for part in (event.content.parts if event.content else []) or []:
            text = (getattr(part, "text", None) or "").strip()
            if text and text not in said:
                said.append(text)
    return "\n".join(said)


ASK_BUDGET = "budget:ask"
CONFIRM_BUDGET = "budget:confirm"


@node(rerun_on_resume=True)
def agree_budget(node_input, ctx: Context):
    """Stop the run and ask what they will spend. Read it back. Then store it.

    Three things make this work, and you need all three:

      @node(rerun_on_resume=True)
          the node runs again each time the graph is woken, instead of being
          skipped as already-done.

      a STABLE interrupt_id
          not the random one you get by default. It is the key you look the
          answer up by, so it has to be the same string on the run that asks and
          the run that reads.

      ctx.resume_inputs[interrupt_id]
          where the answer actually arrives. Not the return value of the
          RequestInput — ADK iterates a node rather than sending into it, so
          there is no value coming back that way.

    Two interrupts, not one, and the second is the point. The first answer is
    what somebody said. The second is what they agreed to.
    """
    answers = getattr(ctx, "resume_inputs", None) or {}

    # Do this on every run, not just the first. The node reruns on resume, so a
    # correction typed later ("actually there are only five of us now") is picked
    # up here rather than lost.
    ctx.state["request"] = what_they_asked_for(ctx)

    if budget.load(ctx.state):
        return Event(output=budget.load(ctx.state))

    if not budget.someone_is_there():
        # Nobody to ask. Run on what was agreed the last time somebody was
        # awake, and if that is nothing, on the default — but never stop here,
        # because stopping here means never buying anything.
        print(f"  [agree_budget] unattended. Using: {DEFAULT_BUDGET}")
        return Event(output=DEFAULT_BUDGET)

    said = str(answers.get(ASK_BUDGET) or "").strip()
    if not said:
        print("  [agree_budget] nothing agreed yet. Asking.")
        return RequestInput(
            interrupt_id=ASK_BUDGET,
            message=(
                "Before I book anything: what are you willing to spend? Say it "
                "however you like — a different price for the good seats, more "
                "for a weekend, a total you will not go past."
            ),
        )

    reply = str(answers.get(CONFIRM_BUDGET) or "").strip()
    if not reply:
        print(f"  [agree_budget] reading back: {said}")
        return RequestInput(
            interrupt_id=CONFIRM_BUDGET,
            message=f"So: {said}. Have I got that right?",
        )

    if not reply.lower().lstrip().startswith(
        ("yes", "yep", "correct", "that's right", "thats right", "confirmed", "right")
    ):
        # They corrected it rather than agreeing. Take the correction as the
        # agreement — they have now said it twice and been shown it once.
        said = reply

    ctx.state["budget"] = said
    print(f"  [agree_budget] agreed: {said}")
    return Event(output=said)


# --- node 2: choose a show. Judgement, so an agent. -----------------------

picker = Agent(
    name="pick_show",
    model=MODEL,
    tools=[recall, search_events, get_seatmap],
    output_schema=Plan,
    instruction=f"""
Choose one show and one section to buy.

THERE IS NOBODY THERE. It is 3am and the person is asleep. You cannot ask a
question, because nothing will answer it and the run will simply stop. Never end
your turn with a question. Never offer to do something and wait for a yes — just
do it. Work through the tools until you have a plan, then return the plan.

Call recall() first. It holds what previous bookings taught you about this
person — who they go with, what they cannot stand, what they are willing to
spend. Those preferences are the whole basis for the choice.

Then search_events. Then get_seatmap for the show you settled on — do not ask
whether to look at it, just look.

The budget is in the message you were sent, written the way the person said it.
Apply all of it — the prices, and any conditions about which sections or days.

The largest amount they named anywhere in that sentence is a HARD CEILING. Check
each section's price against it before you choose: if the price is higher than
that number, that section is not an option, no matter how well it fits the rest
of what they said. "$200 if they're the good ones" means a $210 seat is out.

How many seats to buy is in that same message, in their words. "I have 10 people
coming with me" is eleven seats, not ten and not two. If they never say, buy two.
Whatever number you settle on, put it in `seats`, and the section must have that
many available right now. If nothing is both available and under the ceiling,
choose nothing.

The city and the days are in there too. A person who says they live in New York
and can only do weekends has ruled out every weekday show and every other city,
even when a cheaper seat exists somewhere they cannot go.

Return the plan. Put the reason in one sentence, in terms of what you know about
this person — not "section A is the best seats".
""",
)


# `rerun_on_resume=False` is what stops this from picking a second show every
# time the queue is checked. It runs once, on the first invocation.
pick_show = node(picker, rerun_on_resume=False)


# --- node 2: get in line. A rule, so a function. --------------------------


@node(rerun_on_resume=False)
def queue_up(node_input, ctx: Context) -> Event:
    """Take a queue ticket. Exactly once, however many times this is woken.

    A second ticket would put you at the back of the line again, forty minutes
    behind where you already were. `rerun_on_resume=False` is doing real work
    here — it is not an optimisation.

    The ticket goes two places, and both matter:

      the node output    so check_front and brief can use it. This is how a
                         graph moves data — along an edge.

      session state      under the SAME key `join_queue` uses. The last node is
                         your agent, with all its tools, and `check_queue`
                         defaults to `state["queue_ticket"]`. Leave that unset
                         and the agent gets "no queue ticket in state" if it
                         ever looks — a bug that only appears when the model
                         happens to check.
    """
    plan = Plan(**node_input)
    ticket = venue.post("/queue/join", {"event_id": plan.event_id})
    if "ticket" not in ticket:
        raise RuntimeError(
            f"Failed to join queue for event {plan.event_id!r}: {ticket}. "
            "Please ensure the venue is running and press 'RESET THE VENUE' on the control panel."
        )
    ctx.state["queue_ticket"] = ticket["ticket"]
    ctx.state["queue_event_id"] = plan.event_id
    print(f"  [queue_up]    {plan.event_id} section {plan.section} — "
          f"ticket {ticket['ticket']} at #{ticket['position']:,}")
    return Event(output={**plan.model_dump(), "ticket": ticket["ticket"]})


# --- node 3: the wait, as an interrupt rather than a sleep ----------------


@node(rerun_on_resume=True)
def check_front(node_input):
    """Are we at the front yet? If not, stop the run and wait to be woken.

    Returning a `RequestInput` suspends the whole graph. Compare that with the
    obvious version:

        while not ready:          # never do this
            time.sleep(1)

    The loop keeps a process alive for forty minutes to achieve nothing, dies
    with the terminal, and cannot be resumed. The interrupt costs nothing, lives
    in the session store, and survives the machine going away.
    """
    status = venue.get(f"/queue/{node_input['ticket']}")

    # The ticket can cease to exist. A place at the front is only held for so
    # long, and the venue gives it away — so the thing you were waiting for is
    # gone, not merely late. Without this the run parks forever on a `ready` key
    # that will never appear, which looks exactly like patience.
    if status.get("error"):
        print(f"  [check_front] ticket gone: {status.get('message', 'unknown')}")
        return Event(output={**node_input, "ticket": "", "lost": True})

    if not status.get("ready"):
        print(f"  [check_front] #{status.get('position', 0):,} — not yet. Pausing.")
        return RequestInput(
            message=f"Still in the queue at #{status.get('position', 0):,}. "
                    "Wake me again and I will check."
        )
    print("  [check_front] at the front")
    return Event(output=node_input)


# --- node 4: buy. Judgement again, so the agent you built. ----------------


def brief(node_input, ctx: Context) -> Event:
    """Turn the plan into the sentence you would have typed.

    A node hands its output to the next node, and when the next node is an
    agent that output arrives as the message it wakes up to. This is where
    "go ahead and buy them" comes from when nobody is awake to say it.
    """
    if node_input.get("lost"):
        return Event(output=(
            "The queue place expired before anything could be bought — the venue "
            "only holds the front of the line for so long. Tell me that in one or "
            "two sentences, as a message I will read over breakfast. Buy nothing."
        ))

    plan = Plan(**{k: v for k, v in node_input.items()
                   if k not in ("ticket", "lost")})
    return Event(output=(
        f"You are at the front of the queue for {plan.event_id} in {plan.city}. "
        f"The plan is {plan.seats} seats in section {plan.section}, chosen "
        f"because: {plan.reason}\n\n"
        f"The budget this person agreed to, in their words:\n\n"
        f"    {budget.load(ctx.state) or DEFAULT_BUDGET}\n\n"
        "Buy them now. The seat map you are working from is forty minutes old, "
        "so read it again first — if that section has gone, take the best "
        "remaining one inside the same budget. Then write me one "
        "short message I will read over breakfast, saying what you got and what "
        "it cost. Prices are in US dollars."
    ))


# The last node is `buyer_agent` itself: the agent from step 7, imported and not
# modified. Its tools, its before_tool_callback, its idempotency key — all of it
# comes along, because there is only one of it.

nightly = Workflow(
    name="concert_nightly",
    description="The unattended presale run: judgement, rules, judgement.",
    edges=[(START, agree_budget, open_the_night, pick_show, queue_up, check_front, brief, buyer_agent)],
)


# --- running it from a terminal -------------------------------------------


async def main() -> None:
    """Run the graph once and stop wherever it gets to.

    There is deliberately no loop here. If the queue is not ready this exits
    with the run parked in `nightly.db`, and nothing is running until something
    outside calls it again. That something is you, for now — Module 6 replaces
    you with Cloud Scheduler and nothing else changes.
    """
    session_service = DatabaseSessionService(db_url="sqlite+aiosqlite:///nightly.db")
    if not await session_service.get_session(
        app_name="concert_nightly", user_id="user", session_id="tonight"
    ):
        await session_service.create_session(
            app_name="concert_nightly", user_id="user", session_id="tonight"
        )
    runner = Runner(
        node=nightly,
        app_name="concert_nightly",
        session_service=session_service,
        artifact_service=InMemoryArtifactService(),
        memory_service=memory.memory_service,
    )

    # A parked run is resumed by answering its interrupt, not by sending a new
    # message — a plain message starts a fresh invocation and replays the graph.
    session = await session_service.get_session(
        app_name="concert_nightly", user_id="user", session_id="tonight"
    )
    pending = None
    for event in reversed(session.events or []):
        ids = get_request_input_interrupt_ids(event)
        if ids:
            pending = ids[0]
            break

    message = None
    if pending:
        print("=== waking a run that was already parked ===")
        message = types.Content(
            role="user",
            parts=[create_request_input_response(pending, {"checked": True})],
        )
    else:
        print("=== presale run — nobody is awake ===")

    parked = False
    async for event in runner.run_async(
        user_id="user", session_id="tonight", new_message=message
    ):
        if get_request_input_interrupt_ids(event):
            parked = True
        for part in (event.content.parts if getattr(event, "content", None) else []) or []:
            if getattr(part, "function_call", None) and part.function_call.name != "adk_request_input":
                print(f"  [buy_it]      calls {part.function_call.name}")
            elif getattr(part, "text", None) and part.text.strip():
                print(f"\n📱 {part.text.strip()}\n")

    if parked:
        print("\n  Parked. Nothing is running.")
        print("  Press SKIP THE WAIT on the panel, then run this again:")
        print("      python -m concert.nightly\n")
    else:
        print("=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
