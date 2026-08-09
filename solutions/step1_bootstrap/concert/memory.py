"""Memory as a file you can read.

ADK's MemoryService is an interface with exactly two methods —
`add_session_to_memory` and `search_memory` — and Memory Bank is one
implementation of it. This is another, deliberately made of plain text.

The point is not that Markdown scales. It doesn't. The point is that memory
stops being a managed service you take on faith and becomes a file a student
can open, read, edit, and argue with. Delete "Sam bails on weeknights", ask
again, and watch the agent book Tuesday.

Production swap lives in the closing slide: VertexAiMemoryBankService, which
needs an Agent Engine resource — the one component that doesn't run on a laptop.
"""

from __future__ import annotations

import os
import pathlib

MEMORY_DIR = pathlib.Path(os.environ.get("MEMORY_DIR", "./memory"))
MEMORY_USER = os.environ.get("MEMORY_USER", "userx")


def _path() -> pathlib.Path:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    return MEMORY_DIR / f"{MEMORY_USER}.md"


def recall() -> dict:
    """Read everything learned about this person from previous bookings.

    Call this before recommending a show. It holds preferences and past
    bookings that are not in the current conversation.

    Returns:
        The stored memory as text.
    """
    path = _path()
    if not path.exists():
        return {"memory": "", "note": "nothing remembered yet"}
    return {"memory": path.read_text(), "source": str(path)}


def remember(fact: str) -> dict:
    """Record a durable fact worth keeping after this conversation ends.

    Use this for preferences and outcomes, not for passing details. "Sam bails
    on weeknights" belongs here. "Row F costs $210 right now" does not.

    Args:
        fact: One sentence, written so it still makes sense months later.

    Returns:
        Confirmation and the file written to.
    """
    path = _path()
    existing = path.read_text() if path.exists() else f"# Memory — {MEMORY_USER}\n"
    if "## Preferences" not in existing:
        existing += "\n## Preferences\n"
    lines = existing.rstrip().splitlines()
    idx = lines.index("## Preferences")
    lines.insert(idx + 1, f"- {fact.strip()}")
    path.write_text("\n".join(lines) + "\n")
    return {"remembered": fact, "file": str(path)}
