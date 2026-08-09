"""MODULE 1 — Asleep at 10am.

A good agent. It searches the tour, reads seat maps, reasons about budget and
company, and gives genuinely useful answers.

It also runs only when someone types. At 10:00 on Tuesday, when the presale
opens, this file does nothing at all — because nothing calls it.

That is the whole of Module 1. Every later module is about fixing it.
"""

from __future__ import annotations

from google.adk.agents import Agent

from .config import MODEL
from .tools import get_seatmap, search_events

INSTRUCTION = """
You help someone plan a trip to see a band on tour.

You can search tour dates and read seat maps. Be concrete: name the show, the
city, the section, and the price. When someone mentions who they're going with
or what they can spend, use it.

Keep answers short. Two or three sentences unless asked for more.
"""

root_agent = Agent(
    name="concert",
    model=MODEL,
    instruction=INSTRUCTION,
    tools=[search_events, get_seatmap],
)
