"""THE TRIGGER — a web server with a Runner behind it.

    python -m monstertix.server                 (Ctrl-C to stop)
    python -m monstertix.server --ephemeral     sessions in memory, nothing survives

This is your own server, not `adk web`. `adk web` is a development UI that
happens to be able to run an agent; this is the part underneath it.

Something has to be listening before anything can call it. That is all a trigger
is: an endpoint, and a Runner behind the endpoint.

    POST /wake  {"message": "..."}   →   run the agent, return what it said

It builds its services the same way `adk web` does, from the same URIs, using
ADK's own factory functions. Every flag you pass to `adk web` has a matching
argument on `Runner`, and this file is where you can see that they are the same
decision:

    adk web --session_service_uri=X   ≡   Runner(session_service=<built from X>)

In the last module this same shape is what `get_fast_api_app(trigger_sources=…)`
gives you on Cloud Run, with Pub/Sub doing the POSTing.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import uuid
import warnings

warnings.filterwarnings("ignore", message=r".*\[EXPERIMENTAL\].*")

WORKSHOP = pathlib.Path(os.environ.get("WORKSHOP", pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(WORKSHOP / "agent"))

import uvicorn                                                        # noqa: E402
from fastapi import Body, FastAPI                                     # noqa: E402
from fastapi.responses import FileResponse                            # noqa: E402
from google.adk.cli.utils.service_factory import (                    # noqa: E402
    create_artifact_service_from_options,
    create_session_service_from_options,
)
from google.adk.runners import Runner                                 # noqa: E402
from google.adk.workflow.utils._workflow_hitl_utils import (          # noqa: E402
    create_request_input_response,
    get_request_input_interrupt_ids,
)
from google.adk.sessions import InMemorySessionService                # noqa: E402
from google.genai import types                                        # noqa: E402

from concert.agent import root_agent

from . import handlers                                  # noqa: E402

try:
    from concert.memory import memory_service                         # noqa: E402
except ImportError:
    memory_service = None          # earlier modules have no memory service yet

APP_NAME = "concert"
USER_ID = os.environ.get("MEMORY_USER", "userx")
PORT = int(os.environ.get("TRIGGER_PORT", "8090"))

# The same two URIs you pass to `adk web`. Same files, same data — start this
# server and the dev UI together and they see each other's sessions.
SESSION_URI = os.environ.get(
    "SESSION_SERVICE_URI", f"sqlite+aiosqlite:///{WORKSHOP}/sessions.db"
)
ARTIFACT_URI = os.environ.get("ARTIFACT_SERVICE_URI", f"file://{WORKSHOP}/artifacts")

_args = argparse.ArgumentParser(add_help=False)
_args.add_argument("--ephemeral", action="store_true",
                   help="keep sessions in memory; nothing survives a restart")
OPTS, _ = _args.parse_known_args()

if OPTS.ephemeral:
    # What you get when nobody configures a session store. Every wake starts
    # from nothing. Worth seeing once, deliberately.
    session_service = InMemorySessionService()
    SESSION_DESC = "in memory — nothing survives a restart"
else:
    session_service = create_session_service_from_options(
        base_dir=WORKSHOP / "agent", session_service_uri=SESSION_URI
    )
    SESSION_DESC = SESSION_URI

artifact_service = create_artifact_service_from_options(
    base_dir=WORKSHOP / "agent", artifact_service_uri=ARTIFACT_URI
)

# THE RUNNER. This is what `adk web` has been doing for you: an agent, a name,
# and somewhere to keep sessions, artifacts and memory.
runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
    artifact_service=artifact_service,
    # A memory service belongs here. `adk web` cannot take an instance — it only
    # builds services from a URI at startup — but a Runner you construct
    # yourself takes the object directly.
    memory_service=memory_service,
)

app = FastAPI(title="Trigger")

# The page sits next to the server that serves it. One folder, one thing to
# deploy: MonsterTix is the endpoint AND the front door, and in Module 6 both
# move to Cloud Run together.
STATIC = pathlib.Path(__file__).parent


@app.get("/")
def chat_ui():
    """The frontend.

    `adk web` is a development UI. It is excellent for looking inside a run —
    the State tab, the event stream, the graph — and it is not what you ship. It
    does not exist on Cloud Run, and you would not point a customer at it if it
    did.

    So this is the other surface: a page that knows nothing about ADK, talks to
    /wake over HTTP, and would work against any endpoint that answers the same
    way. It is served from the same process as the Runner purely so there is one
    thing to start in a workshop.
    """
    return FileResponse(STATIC / "index.html")


@app.post("/wake")
async def wake(payload: dict = Body(default={})):
    """Run the agent once. The work is in handlers.py, shared with step 10."""
    # A person is on the other end of this one. Says so for the duration of
    # this request only, so `agree_budget` asks instead of assuming a default.
    # The Pub/Sub trigger route never runs this, which is the whole point.
    try:
        from concert import budget                                # noqa: PLC0415
        budget.mark_attended()
    except ImportError:                                           # pragma: no cover
        pass                      # steps before the budget exists

    return await handlers.wake(
        runner, session_service, APP_NAME, USER_ID,
        message=payload.get("message") or "The presale just opened.",
        session_id=payload.get("session_id"),
        log=lambda m: print(m, flush=True),
    )


@app.post("/session/new")
def new_session():
    """Hand the page a fresh session id. Nothing is deleted."""
    return {"session_id": handlers.new_session_id()}


@app.post("/admin/wipe")
async def wipe(payload: dict = Body(default={})):
    """Delete every session and the memory file. Irreversible."""
    return await handlers.wipe(
        session_service, APP_NAME, USER_ID, log=lambda m: print(m, flush=True)
    )


@app.get("/health")
def health():
    # A Workflow has no .model — the model calls live in its agent nodes — so
    # this reports the shape rather than assuming an LlmAgent.
    return {
        "ok": True,
        "agent": root_agent.name,
        "kind": type(root_agent).__name__,
        "model": getattr(root_agent, "model", None),
        "sessions": SESSION_DESC,
        "memory": os.environ.get("MEMORY_DIR", "./memory"),
    }


if __name__ == "__main__":
    # From Module 5 on, root_agent is a Workflow rather than an LlmAgent, and a
    # graph has no model of its own — the model calls live in its agent nodes.
    kind = type(root_agent).__name__
    detail = getattr(root_agent, "model", None) or f"{kind} graph"
    # Fail here, not on the first tool call. venue.py has no localhost fallback
    # any more, so without this the server starts happily, the agent runs, and
    # the purchase raises somewhere deep in a tool — which reads as "the agent
    # is broken" rather than "this terminal never sourced set_env.sh".
    if not os.environ.get("VENUE_URL"):
        print("[server] ✗ VENUE_URL is not set, so there is no venue to buy from.",
              flush=True)
        print("[server]   In this terminal:  . ./set_env.sh", flush=True)
        print("[server]   No venue yet?      ./deploy-venue.sh", flush=True)
        raise SystemExit(1)

    print(f"[server] agent    {root_agent.name} · {detail}", flush=True)
    print(f"[server] venue    {os.environ['VENUE_URL']}", flush=True)
    print(f"[server] sessions {SESSION_DESC}", flush=True)
    print(f"[server] memory   {type(memory_service).__name__ if memory_service else 'none'}", flush=True)
    print(f"[server] listening on http://127.0.0.1:{PORT}/wake", flush=True)
    print("[server] nothing will happen until something calls it. Ctrl-C to stop.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
