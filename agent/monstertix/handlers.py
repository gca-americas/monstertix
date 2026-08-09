"""What the endpoints DO, with no opinion about who is serving them.

Nothing here builds a Runner, a FastAPI app, or a session service. Every one of
these takes what it needs as an argument, which is the only reason this file
exists: there are two entrypoints and they must not drift apart.

    monstertix/server.py    step 3 — your own Runner behind your own endpoint
    agent/main.py           step 10 — the same routes bolted onto the app that
                            `get_fast_api_app` builds, in one Cloud Run container

Step 10 is the reason it matters. `get_fast_api_app` builds its own session and
artifact services from the URIs you give it, and in production those point at
Cloud SQL and a bucket. If it imported `server.py` to reuse a handler it would
drag along a second set pointed at SQLite on a container filesystem that is
destroyed when the instance goes away — which is exactly the failure Module 6
exists to teach.
"""

from __future__ import annotations

import os
import pathlib
import uuid

from google.adk.workflow.utils._workflow_hitl_utils import (
    create_request_input_response,
    get_request_input_interrupt_ids,
)
from google.genai import types


def new_session_id() -> str:
    """A fresh session. Nothing is deleted.

    A new session means a new conversation and, from Module 5 on, a new budget —
    session state starts empty, so the agent asks again. Anything under `user:`
    survives, and so does the memory file.
    """
    return f"web-{uuid.uuid4().hex[:8]}"


async def pending_interrupt(session_service, app_name: str, user_id: str,
                            session_id: str) -> str | None:
    """The id of an unanswered `adk_request_input`, if the run is parked on one.

    Walks the session's events newest-first: the first interrupt id with no
    matching function_response after it is the one still waiting. Deliberately
    stateless — the session store already knows, and a dict of ids in this
    process would not survive the container restarting.
    """
    session = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    if not session:
        return None

    answered: set[str] = set()
    for event in reversed(session.events or []):
        for part in (event.content.parts if event.content else []) or []:
            response = getattr(part, "function_response", None)
            if response and response.name == "adk_request_input":
                answered.add(response.id)
        for interrupt_id in get_request_input_interrupt_ids(event):
            if interrupt_id not in answered:
                return interrupt_id
    return None


async def wake(runner, session_service, app_name: str, user_id: str,
               message: str, session_id: str | None = None,
               log=print) -> dict:
    """Run the agent once.

    Whoever calls this does not have to know what an agent is. They send a
    sentence and get sentences back.
    """
    session_id = session_id or f"wake-{uuid.uuid4().hex[:8]}"

    if not await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    ):
        await session_service.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )

    # Is the run parked on a question? If so this message is the ANSWER to it,
    # not a new request. Sending it as ordinary text starts a fresh invocation
    # and replays the graph from the top, which looks like the agent asking the
    # same question forever.
    pending = await pending_interrupt(session_service, app_name, user_id, session_id)
    if pending:
        new_message = types.Content(
            role="user",
            parts=[create_request_input_response(pending, {"result": message})],
        )
        log(f"[server] answering interrupt {pending[:12]}")
    else:
        new_message = types.Content(role="user", parts=[types.Part(text=message)])

    log(f"\n[server] woken · session {session_id}")
    said: list[str] = []
    awaiting = False

    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=new_message
    ):
        for part in (event.content.parts if event.content else []) or []:
            call = getattr(part, "function_call", None)
            if call:
                if call.name == "adk_request_input":
                    awaiting = True
                    asked = (call.args or {}).get("message")
                    if asked:
                        said.append(str(asked))
                log(f"[server]   called {call.name}")
            elif getattr(part, "text", None):
                text = part.text.strip()
                said.append(text)
                log(f"[server]   said   {text[:160]}")

    return {
        "session_id": session_id,
        "said": said,
        # Did the run stop on a question? The page marks that reply so a parked
        # run does not look like an ordinary answer.
        "awaiting_input": awaiting,
    }


async def wipe(session_service, app_name: str, user_id: str, log=print) -> dict:
    """Delete every session and the memory file. Irreversible.

    Written to work wherever the state actually lives, because by Module 6 it
    could be anywhere:

        sessions   sqlite OR Cloud SQL — same session-service API either way, so
                   this never touches SQL or knows which one it is.

        memory     a local file OR an object in a bucket, decided by whether
                   MEMORY_DIR looks like gs://.
    """
    removed_sessions, removed_memory = 0, []

    # Both identities, because the workshop uses both: `adk web` hardcodes
    # userId=user and cannot be told otherwise, while these servers act as
    # MEMORY_USER. Wiping one leaves half the history behind and looks like the
    # button did not work.
    for who in {user_id, "user"}:
        listing = await session_service.list_sessions(app_name=app_name, user_id=who)
        for session in listing.sessions:
            await session_service.delete_session(
                app_name=app_name, user_id=who, session_id=session.id
            )
            removed_sessions += 1

    memory_dir = os.environ.get("MEMORY_DIR", "./memory")
    who = os.environ.get("MEMORY_USER", user_id)

    if memory_dir.startswith("gs://"):
        # Imported here rather than at module scope so a laptop with no cloud
        # libraries installed can still run step 3.
        from google.cloud import storage                        # noqa: PLC0415

        bucket_name, _, prefix = memory_dir[5:].partition("/")
        blob_name = f"{prefix.rstrip('/')}/{who}.md".lstrip("/")
        blob = storage.Client().bucket(bucket_name).blob(blob_name)
        if blob.exists():
            blob.delete()
            removed_memory.append(f"gs://{bucket_name}/{blob_name}")
    else:
        path = pathlib.Path(memory_dir) / f"{who}.md"
        if path.exists():
            path.unlink()
            removed_memory.append(str(path))

    log(f"[server] WIPED {removed_sessions} sessions, memory: {removed_memory}")
    return {
        "sessions_deleted": removed_sessions,
        "memory_deleted": removed_memory,
        "session_id": new_session_id(),
    }
