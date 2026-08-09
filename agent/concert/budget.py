"""MODULE 5 — what the person agreed to spend, in their own words.

The tempting design is a schema:

    {"max_per_seat": 250}                      one number
    {"lower_bowl": 250, "upper_bowl": 100}     one number per tier

Both are wrong the first time somebody says something you did not anticipate:

    "About a hundred for the cheap seats, two-fifty if they're good ones —
     and I'd go higher for a Saturday."

Now you need a weekday dimension. Then a per-city one. Then "not more than $400
total, whatever you do". Every schema you write is a bet about what people are
allowed to care about, and you lose that bet in the first conversation.

So do not model it. Store the sentence.

    budget = ("Up to $100 for upper bowl or general admission, up to $250 "
                   "for lower bowl, and up to $300 for a Saturday show.")

The agent reads it and applies it, which is a thing agents are good at and
schemas are not.

SESSION STATE, NOT `user:`. This is a decision worth making on purpose. A budget
is agreed for one booking, not forever — "two-fifty if they're the good ones"
was about that band, that night. Put it under `user:` and it silently governs
every run this person ever makes, including ones where they would have said
something different, and they will never be asked again. So every new session
starts with no budget and has to agree one.

The cost of that choice is real: an unattended run gets a fresh session, so it
has nothing agreed and falls back to a default. That is the honest trade — a
limit that has to be re-agreed, against a limit that quietly outlives the
conversation it came from.
"""

from __future__ import annotations

import contextvars
import os

# --- is anybody there? -----------------------------------------------------
#
# `agree_budget` stops the run and asks a person what they will spend. That is
# right when somebody is reading, and fatal at 3am: Pub/Sub delivers a message,
# the graph parks on a question, nobody answers, nothing is bought, and nothing
# looks broken.
#
# The obvious fix is an environment variable, and it is the WRONG SHAPE. "Is a
# person here?" is a fact about one REQUEST, not about the process. The deployed
# service handles both kinds: a browser, where somebody is plainly waiting, and a
# Pub/Sub push, where nobody is. One variable set at boot cannot tell them apart,
# so a browser gets the unattended path and the person is never asked.
#
# So the default is a variable — unattended, the safe assumption for a service
# that a scheduler can reach — and a request that KNOWS a person is driving says
# so, for the duration of that request only. A ContextVar is scoped to the
# asyncio task, which in FastAPI is exactly one request.
_UNATTENDED_BY_DEFAULT = os.environ.get("UNATTENDED", "").lower() in (
    "1", "true", "yes",
)
_attended = contextvars.ContextVar("attended", default=None)


def mark_attended(value: bool = True) -> None:
    """Say a person is on the other end of THIS request.

    Called by the `/wake` route, which only ever runs because somebody typed
    into MonsterTix. The Pub/Sub trigger never calls it, so it keeps the default.
    """
    _attended.set(value)


def someone_is_there() -> bool:
    """Can this run stop and ask a question and expect an answer?"""
    marked = _attended.get()
    if marked is not None:
        return marked
    return not _UNATTENDED_BY_DEFAULT


def load(state) -> str:
    """What they agreed, verbatim. Empty string means nobody has said."""
    return str(state.get("budget") or "")


def describe(agreed: str) -> str:
    """The budget as one line, for a prompt or a log.

    This string is exactly what the unattended run is handed at 3am, and it is
    the only form of the budget it ever sees.
    """
    return agreed or "nothing agreed yet"

