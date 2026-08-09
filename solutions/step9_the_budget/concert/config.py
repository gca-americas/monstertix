"""Model selection and a fail-fast credentials check.

We run on Vertex AI, so auth comes from Application Default Credentials rather
than an API key. Without the checks below, a missing project or a bad model id
surfaces as ~290 lines of traceback with the real cause on the last line.
"""

from __future__ import annotations

import os
import sys

# On Vertex the "-latest" aliases do not exist and 404. Pin the id.
MODEL = os.getenv("ADK_MODEL", "gemini-2.5-flash")

_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1", "yes")

if _vertex:
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        sys.exit(
            "✗ GOOGLE_CLOUD_PROJECT is not set.\n"
            "  cp .env.example .env  and check the project id."
        )
    if "latest" in MODEL:
        sys.exit(
            f"✗ ADK_MODEL={MODEL!r} is an AI-Studio-only alias and 404s on Vertex.\n"
            "  Set ADK_MODEL=gemini-2.5-flash in .env"
        )
elif not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
    sys.exit(
        "✗ No credentials found.\n"
        "  This workshop runs on Vertex AI. In .env set:\n"
        "    GOOGLE_CLOUD_PROJECT=vibeflix-test-3\n"
        "    GOOGLE_CLOUD_LOCATION=global\n"
        "    GOOGLE_GENAI_USE_VERTEXAI=true\n"
        "  then:  gcloud auth application-default login"
    )
