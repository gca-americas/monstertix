"""MODULE 3 — Open the box.

Same agent, but now it writes to four different places, and students go find
each one in the dev UI:

    State tab      user:prefs           survives everything
                   temp:seatmap         survives nothing
    Artifacts tab  seatmap_*.json       never enters the prompt
    memory/*.md    past bookings        not in this session at all

Then they write down which of those survive a restart, and you restart.
"""

from __future__ import annotations

from google.adk.agents import Agent

from .config import MODEL
from .memory import recall, remember
from .tools import get_seatmap, note_companion, purchase, search_events

INSTRUCTION = """
You help someone plan a trip to see a band on tour.

Before recommending anything, call recall() to read what you already know about
this person from past bookings. It is not in this conversation.

Use note_companion when someone mentions who is coming and what limits them.
Use remember() for facts that should outlive this conversation — preferences and
outcomes, never prices or availability.

Be concrete: name the show, the city, the section, and the price. Keep answers
to two or three sentences unless asked for more.
"""

root_agent = Agent(
    name="concert",
    model=MODEL,
    instruction=INSTRUCTION,
    tools=[search_events, get_seatmap, purchase, note_companion, recall, remember],
)
