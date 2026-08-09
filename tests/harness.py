"""Shared machinery for the step tests.

Every test here answers one question: **does this step still do what the
instructions say it does?** Not "does the code import" — that is table stakes —
but "if a student types what the codelab tells them to type, do they see what the
codelab shows them".

Two kinds of test, and the split matters because one kind is free and the other
is not:

    structural   no model calls. Does step 6 actually wrap join_queue in a
                 LongRunningFunctionTool? Is compaction on? Milliseconds.

    behavioural  drives the real agent against the real venue with the real
                 model. Slow (a minute or more each) and costs tokens, so they
                 are skipped unless you ask for them:

                     WORKSHOP_TEST_LIVE=1 pytest tests/

The venue must be running. Point at it with VENUE_URL; the default is the
scratch port so a test run never touches the venue a student has on :8080.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import pathlib
import sys
import warnings

import httpx
import pytest

warnings.filterwarnings("ignore")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOLUTIONS = ROOT / "solutions"
VENUE_URL = os.environ.get("VENUE_URL", "http://127.0.0.1:8099")
LIVE = os.environ.get("WORKSHOP_TEST_LIVE", "").lower() in ("1", "true", "yes")

needs_model = pytest.mark.skipif(
    not LIVE, reason="live test — set WORKSHOP_TEST_LIVE=1 (slow, costs tokens)"
)


# --- loading one step's package ------------------------------------------


def load_step(step: str):
    """Import `concert` from one solution folder, in isolation.

    Every step ships a package with the same name, so anything already imported
    has to go before the next one is loaded — otherwise step 7's test quietly
    asserts against step 6's code and passes for the wrong reason.
    """
    folder = ROOT / "solutions" / step
    assert folder.is_dir(), f"no solution folder {step}"

    for name in [m for m in sys.modules if m == "concert" or m.startswith("concert.")]:
        del sys.modules[name]
    sys.path = [p for p in sys.path if "solutions/" not in p]
    sys.path.insert(0, str(folder))

    os.environ.setdefault("MEMORY_DIR", str(ROOT / "memory"))
    os.environ["VENUE_URL"] = VENUE_URL
    return importlib.import_module("concert.agent")


def tool_names(agent) -> list[str]:
    return [getattr(t, "name", getattr(t, "__name__", str(t))) for t in agent.tools]


# --- the venue -----------------------------------------------------------


class Venue:
    """The buttons on the control panel, as a Python object."""

    def __init__(self, base: str = VENUE_URL):
        self.c = httpx.Client(base_url=base, timeout=20)

    def reset(self):
        self.c.post("/admin/reset")

    def skip_the_wait(self):
        self.c.post("/admin/advance-queue")

    def sell_out(self, section: str = "A", event_id: str = "ms-ams-01"):
        self.c.post("/admin/sellout", json={"event_id": event_id, "section": section})

    def break_next_purchase(self):
        self.c.post("/admin/hang-once")

    def state(self) -> dict:
        return self.c.get("/admin/state").json()

    @property
    def orders(self) -> int:
        return self.state()["order_count"]

    @property
    def tickets(self) -> int:
        return len(self.state()["queue"])


@pytest.fixture
def venue():
    v = Venue()
    try:
        v.reset()
    except Exception:  # noqa: BLE001
        pytest.skip(f"no venue at {VENUE_URL} — start it with `python -m venue`")
    return v


# --- driving an agent or a graph -----------------------------------------


class Transcript:
    """What happened, in a form a test can make assertions about."""

    def __init__(self):
        self.calls: list[str] = []
        self.said: list[str] = []
        self.interrupts: list[str] = []

    def called(self, name: str) -> bool:
        return name in self.calls

    def __repr__(self) -> str:
        return f"<calls={self.calls} said={len(self.said)} interrupts={len(self.interrupts)}>"


def drive(node, turns, *, session_state=None, venue=None, on_interrupt=None):
    """Run `node` through `turns`, answering interrupts as they come.

    turns          strings sent as ordinary messages
    on_interrupt   called with (message, transcript) each time the run parks;
                   return the text to answer with, or None to stop
    """
    from google.adk import Runner
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.sessions import InMemorySessionService
    from google.adk.workflow.utils._workflow_hitl_utils import (
        create_request_input_response,
        get_request_input_interrupt_ids,
    )
    from google.genai import types

    t = Transcript()

    async def run():
        ss = InMemorySessionService()
        await ss.create_session(app_name="t", user_id="user", session_id="s",
                                state=session_state or {})
        try:
            from concert import memory as mem
            memory_service = mem.memory_service
        except (ImportError, AttributeError):
            memory_service = None

        kwargs = dict(app_name="t", session_service=ss,
                      artifact_service=InMemoryArtifactService(),
                      memory_service=memory_service)
        from google.adk.workflow import Workflow
        runner = (Runner(node=node, **kwargs) if isinstance(node, Workflow)
                  else Runner(agent=node, **kwargs))

        queue = list(turns)
        msg = (types.Content(role="user", parts=[types.Part(text=queue.pop(0))])
               if queue else None)

        for _ in range(20):
            interrupt, asked = None, ""
            async for ev in runner.run_async(user_id="user", session_id="s",
                                             new_message=msg):
                ids = get_request_input_interrupt_ids(ev)
                if ids:
                    interrupt = ids[0]
                for part in (ev.content.parts if getattr(ev, "content", None) else []) or []:
                    fc = getattr(part, "function_call", None)
                    if fc and fc.name == "adk_request_input":
                        asked = str(fc.args.get("message", ""))
                        t.interrupts.append(asked)
                    elif fc:
                        t.calls.append(fc.name)
                    elif getattr(part, "text", None) and part.text.strip():
                        t.said.append(part.text.strip())

            if interrupt is not None:
                answer = on_interrupt(asked, t) if on_interrupt else (
                    queue.pop(0) if queue else None)
                if answer is None:
                    return
                msg = types.Content(
                    role="user",
                    parts=[create_request_input_response(interrupt, {"result": answer})])
                continue

            if not queue:
                return
            msg = types.Content(role="user", parts=[types.Part(text=queue.pop(0))])

    asyncio.run(run())
    return t
