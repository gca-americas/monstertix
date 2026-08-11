"""Thin client for the venue service.

The venue runs on the same machine as the agent, which is what makes the
venue reachable from wherever the agent happens to be running.
"""

from __future__ import annotations

import os

import httpx

# No default. A silent fallback to localhost is worse than no venue at all: the
# agent quietly talks to a machine that is not the one you deployed, and either
# gets connection refused or — much worse — reaches a stale local venue with
# different prices and a different queue. Say what is missing instead.
VENUE_URL = os.environ.get("VENUE_URL", "").rstrip("/")


def _base() -> str:
    if not VENUE_URL:
        raise RuntimeError(
            "VENUE_URL is not set, so there is no venue to talk to.\n"
            "  In this terminal:   . ./set_env.sh\n"
            "  Deployed venue:     ./deploy-venue.sh   (writes it into .env)\n"
            "  Local venue:        . ./set_env.sh local"
        )
    return VENUE_URL
AGENT_URL = os.environ.get("AGENT_URL", "http://127.0.0.1:8000")



def client() -> httpx.Client:
    return httpx.Client(base_url=_base(), timeout=30)


def get(path: str, **params) -> dict:
    """GET, returning errors as data rather than raising.

    A tool that raises gives the model a stack trace; a tool that returns
    {"error": ...} gives it something it can explain to a person. This matters
    most when an instructor presses RESET THE VENUE mid-demo: every queue ticket
    is deleted, and the agent should say "that ticket is gone" instead of
    falling over.
    """
    with client() as c:
        r = c.get(path, params={k: v for k, v in params.items() if v})
        if r.status_code >= 400:
            try:
                return {"error": True, "status": r.status_code, **_detail(r.json())}
            except Exception:
                return {"error": True, "status": r.status_code, "message": r.text}
        return r.json()


def post(path: str, payload: dict, headers: dict | None = None) -> dict:
    with client() as c:
        r = c.post(path, json=payload, headers=headers or {})
        if r.status_code >= 400:
            try:
                return {"error": True, "status": r.status_code, **_detail(r.json())}
            except Exception:
                return {"error": True, "status": r.status_code, "message": r.text}
        return r.json()


def _detail(body: dict) -> dict:
    detail = body.get("detail", body)
    return detail if isinstance(detail, dict) else {"message": str(detail)}
