"""MODULE 6 — one container, two front doors.

This is the only file that differs between what you ran on your laptop and what
runs in Google Cloud, and none of it is about the agent.

    ┌─ Cloud Run: concert-you ─────────────────────────────────────┐
    │                                                              │
    │   /                          MonsterTix, for a person        │
    │   /wake                      what that page posts to         │
    │   /apps/concert/trigger/     what Pub/Sub posts to           │
    │        pubsub                                                │
    │                                                              │
    │            one Runner, one session store, one graph          │
    └──────────────────────────────────────────────────────────────┘

`get_fast_api_app` does the heavy half: it discovers every agent package in
AGENTS_DIR, builds the session and artifact services from the same two URIs you
have been passing to `adk web` since Module 3, and mounts a Pub/Sub endpoint per
app. It returns an ordinary FastAPI, so the MonsterTix routes bolt straight onto
it.

Why one service and not two: the page and the agent are the same process, so the
browser calls `/wake` on its own origin. No CORS, no second deployment, no
service-to-service authentication, no network hop between them. Deploying them
apart would mean solving all four for no benefit.

Run it locally, exactly as the container will:

    uvicorn main:app --port 8080

Deploy it:

    ./deploy-agent.sh
"""

from __future__ import annotations

import os
import pathlib
import warnings

warnings.filterwarnings("ignore", message=r".*\[EXPERIMENTAL\].*")

from fastapi import Body                                          # noqa: E402
from fastapi.middleware.cors import CORSMiddleware                # noqa: E402
from fastapi.responses import FileResponse                        # noqa: E402
from google.adk.cli.fast_api import get_fast_api_app              # noqa: E402
from google.adk.cli.utils.service_factory import (                # noqa: E402
    create_artifact_service_from_options,
    create_session_service_from_options,
)
from google.adk.runners import Runner                             # noqa: E402

from concert.agent import root_agent                              # noqa: E402
from monstertix import handlers                                   # noqa: E402

try:
    from concert.memory import memory_service                      # noqa: E402
except ImportError:                                                # pragma: no cover
    memory_service = None

HERE = pathlib.Path(__file__).parent
APP_NAME = "concert"
USER_ID = os.environ.get("MEMORY_USER", "userx")

# The same two URIs as `adk web`. On Cloud Run these are a Cloud SQL connection
# string and a gs:// bucket — set by setup-cloud-state.sh, passed by
# deploy-agent.sh. The defaults below are for running this file on your laptop.
#
# Set them. Trigger sessions default to in-memory, which means a 3am run that
# joins a queue has forgotten the ticket by the time anything wakes it.
SESSION_URI = os.environ.get(
    "SESSION_SERVICE_URI", f"sqlite+aiosqlite:///{HERE}/sessions.db"
)
ARTIFACT_URI = os.environ.get("ARTIFACT_SERVICE_URI", f"file://{HERE}/artifacts")

app = get_fast_api_app(
    agents_dir=str(HERE),
    web=False,                        # no dev UI in production
    session_service_uri=SESSION_URI,
    artifact_service_uri=ARTIFACT_URI,
    trigger_sources=["pubsub"],       # ← mounts /apps/<app>/trigger/pubsub
    allow_origins=["*"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The same services, built from the same URIs, using ADK's own factories.
#
# `get_fast_api_app` does not hand its services back, so this builds a second
# object against the SAME database and bucket. That is fine and not a trick: a
# session service is a client, not a cache — two of them pointed at one Cloud
# SQL instance see identical data. What would NOT be fine is importing
# monstertix/server.py to get one, because that module builds its own from
# ITS defaults, which on a container means SQLite on a filesystem that is
# destroyed when the instance goes away.
session_service = create_session_service_from_options(
    base_dir=HERE, session_service_uri=SESSION_URI
)
artifact_service = create_artifact_service_from_options(
    base_dir=HERE, artifact_service_uri=ARTIFACT_URI
)

runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
    artifact_service=artifact_service,
    memory_service=memory_service,
)

MONSTERTIX = pathlib.Path(
    os.environ.get("MONSTERTIX_DIR", HERE / "monstertix")
)


@app.get("/")
def chat_ui():
    """MonsterTix. The surface that survives leaving your laptop."""
    return FileResponse(MONSTERTIX / "index.html")


@app.post("/wake")
async def wake(payload: dict = Body(default={})):
    """What the page posts to. Identical logic to Module 3's server."""
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
    )


@app.post("/trigger/wake")
async def scheduled_wake(payload: dict = Body(default={})):
    """What Cloud Scheduler reaches, via Pub/Sub push.

    ADK ships a trigger endpoint at /apps/<app>/trigger/pubsub, and for this
    workshop it is the wrong one. Read its source and you find:

        session_id = str(uuid.uuid4())               a brand new session
        user_id    = subscription.replace("/", "--") a different user

    That is correct for "fire an agent at something", and useless for "go and
    finish the thing you started". A fresh session has no queue ticket, no
    budget, and no memory of the conversation, so it books a second set of
    tickets rather than completing the first.

    This route does the opposite: it finds the session that is already waiting
    and answers the question it parked on.
    """
    listing = await session_service.list_sessions(app_name=APP_NAME, user_id=USER_ID)
    if not listing.sessions:
        return {"woke": None, "reason": "no sessions to resume"}

    # Newest first. A parked run is almost always the most recent thing here,
    # and anything older has either finished or been abandoned.
    for session in sorted(listing.sessions, key=lambda x: x.last_update_time,
                          reverse=True):
        parked = await handlers.pending_interrupt(
            session_service, APP_NAME, USER_ID, session.id
        )
        if parked:
            result = await handlers.wake(
                runner, session_service, APP_NAME, USER_ID,
                message=payload.get("message") or "Checking on your behalf.",
                session_id=session.id,
            )
            return {"woke": session.id, **result}

    return {"woke": None, "reason": "nothing is waiting"}


@app.get("/session/{session_id}/messages")
async def session_messages(session_id: str, since: float = 0.0):
    """Everything the agent has said in this session since `since`.

    The page polls this. Without it a scheduled run completes on the server and
    the browser goes on showing a queue position for ever — the work finished
    and the only person who cared never found out.
    """
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    if not session:
        return {"said": [], "awaiting_input": False, "now": 0.0}

    said, awaiting, latest = [], False, since
    for event in session.events or []:
        stamp = getattr(event, "timestamp", 0.0) or 0.0
        if stamp <= since:
            continue
        latest = max(latest, stamp)
        for part in (event.content.parts if event.content else []) or []:
            call = getattr(part, "function_call", None)
            if call and call.name == "adk_request_input":
                awaiting = True
                asked = (call.args or {}).get("message")
                if asked:
                    said.append(str(asked))
            elif getattr(part, "text", None) and event.author != "user":
                said.append(part.text.strip())
    return {"said": said, "awaiting_input": awaiting, "now": latest}


@app.post("/session/new")
def new_session():
    return {"session_id": handlers.new_session_id()}


@app.post("/admin/wipe")
async def wipe(payload: dict = Body(default={})):
    """Delete every session and the memory file.

    Public, because the service is deployed --allow-unauthenticated so Pub/Sub
    and a browser can both reach it. Anyone with the URL can empty this agent.
    That is acceptable for a workshop and is not acceptable for anything else —
    in a real deployment this route needs auth, or should not exist.
    """
    return await handlers.wipe(session_service, APP_NAME, USER_ID)
