"""MODULE 1 — You cannot prompt your way to autonomy.

A good agent. It searches the tour, reads seat maps, reasons about budget and
company, and gives genuinely useful answers.

It also runs only when someone types. At 10:00 on Tuesday, when the presale
opens, this file does nothing at all — because nothing calls it.

That is the whole of Module 1. Every later module is about fixing it.
"""

from __future__ import annotations

from google.adk.agents import Agent

from .config import MODEL
from .tools import get_seatmap, purchase, search_events

INSTRUCTION = """
You help someone plan a trip to see a band on tour.

You can search tour dates and read seat maps. Be concrete: name the show, the
city, the section, and the price. When someone mentions who they're going with
or what they can spend, use it.

Keep answers short. Two or three sentences unless asked for more.
"""

# ── The second half of step 2 ────────────────────────────────────────────
# The obvious fix, when you notice the agent slept through the on-sale, is to
# tell it not to. Swap the instruction below, restart, and wait.
#
# Nothing happens. Not because this wording is bad — because no wording can
# invoke a function. "Monitor", "watch", "act on your own" describe behaviour
# the model has no mechanism to perform. It is read only at the moment someone
# sends a message, and it says nothing about who sends one.
#
# That is the point of step 2, and it is worth failing at yourself once.

PROACTIVE_INSTRUCTION = """
You are a proactive ticket-buying assistant.

Monitor the presale for The Midnight Signal. The moment it opens at 10:00 on
Tuesday, buy two tickets for the Amsterdam Saturday show — do not wait to be
asked, and do not wait for me to say anything. Act on your own.

Keep checking until the tickets are bought.
"""

root_agent = Agent(
    name="concert",
    model=MODEL,
    instruction=INSTRUCTION,           # ← swap to PROACTIVE_INSTRUCTION, then restart
    tools=[search_events, get_seatmap, purchase],
)
