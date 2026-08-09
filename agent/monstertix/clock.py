"""THE TRIGGERER — something that knows the time. Ctrl-C to stop.

    python -m monstertix.clock --in 60          once, a minute from now
    python -m monstertix.clock --every 120      every two minutes, forever

Look at what this file imports: `httpx`, `time`, `argparse`. No ADK. It has
never heard of an agent, a Runner or a session — it knows a URL and a clock.

That is the whole point of keeping it separate. In step 10 this file is deleted
and Cloud Scheduler does its job instead, and nothing on the other side changes.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import httpx

TRIGGER_URL = os.environ.get(
    "TRIGGER_URL", f"http://127.0.0.1:{os.environ.get('TRIGGER_PORT', '8090')}"
).rstrip("/")

DEFAULT_MESSAGE = "The presale just opened. Buy the tickets we discussed."


def log(message: str) -> None:
    print(f"[clock] {message}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m monstertix.clock")
    parser.add_argument("--in", dest="delay", type=float, default=60)
    parser.add_argument("--every", type=float, default=0)
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    args = parser.parse_args()

    log(f"target   {TRIGGER_URL}/wake")
    log(f"first fire in {args.delay:g}s"
        + (f", then every {args.every:g}s" if args.every else ", once only"))
    log("go and watch the other terminal — do not touch the keyboard")

    with httpx.Client(timeout=300) as client:
        time.sleep(args.delay)
        while True:
            log("firing → POST /wake")
            try:
                response = client.post(f"{TRIGGER_URL}/wake",
                                       json={"message": args.message})
                if response.status_code >= 400:
                    log(f"trigger returned {response.status_code}")
                else:
                    log("done. the agent ran and you were not involved.")
            except httpx.HTTPError:
                log(f"nothing listening at {TRIGGER_URL} — is the server running?")
            if not args.every:
                return
            time.sleep(args.every)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("stopped.")
        sys.exit(0)
