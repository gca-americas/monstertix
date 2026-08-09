"""End-to-end check that every workshop beat actually fires.

Run against a live venue:   python -m venue.smoke_test
Each block maps to one module. If a block fails, that module fails in the room.
"""

from __future__ import annotations

import os
import sys
import time

import httpx

BASE = os.environ.get("VENUE_URL", "http://127.0.0.1:8080")
EVENT = "ms-ams-01"
ok, failed = 0, 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global ok, failed
    if condition:
        ok += 1
        print(f"  \033[32mPASS\033[0m  {label}")
    else:
        failed += 1
        print(f"  \033[31mFAIL\033[0m  {label}  {detail}")


c = httpx.Client(base_url=BASE, timeout=20)
c.post("/admin/reset")

print("\nMODULE 1 — search")
r = c.get("/events", params={"artist": "Midnight"}).json()
check("tour dates returned", len(r["events"]) == 8, str(len(r["events"])))
check("has Tuesday shows", any(e["weekday"] == "Tuesday" for e in r["events"]))

print("\nMODULE 4 — seatmap carries a timestamp")
m = c.get(f"/events/{EVENT}/seatmap").json()
check("captured_at present", "captured_at" in m)
check("section A available", m["sections"][0]["available"] == 400)

print("\nMODULE 4 — queue and clock")
c.post("/admin/clock", json={"multiplier": 60})
q = c.post("/queue/join", json={"event_id": EVENT}).json()
ticket = q["ticket"]
check("starts near the back", q["position"] > 14000, str(q["position"]))
check("40 virtual min ≈ 40 real sec", 35 < q["real_seconds_remaining"] < 45,
      str(q["real_seconds_remaining"]))

time.sleep(3)
after = c.get(f"/queue/{ticket}").json()
check("position drains over time", after["position"] < q["position"],
      f"{q['position']} -> {after['position']}")

bad = c.post("/purchase", json={"event_id": EVENT, "section": "A", "seats": 2,
                                "queue_ticket": ticket})
check("purchase blocked while queued", bad.status_code == 409, str(bad.status_code))

c.post("/admin/advance-queue")
check("ADVANCE QUEUE reaches the front", c.get(f"/queue/{ticket}").json()["ready"])

print("\nMODULE 4 — stale seatmap")
c.post("/admin/sellout", json={"event_id": EVENT, "section": "A"})
sold = c.post("/purchase", json={"event_id": EVENT, "section": "A", "seats": 2,
                                 "queue_ticket": ticket})
check("sold-out section rejects", sold.status_code == 409, str(sold.status_code))
check("error explains the fix", "re-fetch" in sold.text, sold.text[:80])

print("\nMODULE 4 — double purchase without a key")
c.post("/admin/reset")
c.post("/admin/hang-once")
body = {"event_id": EVENT, "section": "B", "seats": 2}
first = c.post("/purchase", json=body)
check("commit-then-fail returns 503", first.status_code == 503, str(first.status_code))
c.post("/purchase", json=body)          # the platform's retry
n = c.get("/admin/state").json()["order_count"]
check("retry bought them twice", n == 2, f"{n} orders")

print("\nMODULE 4 — idempotency key fixes it")
c.post("/admin/reset")
c.post("/admin/hang-once")
key = {"Idempotency-Key": "sess-42:ms-ams-01:B:2"}
c.post("/purchase", json=body, headers=key)   # commits, then 503
retry = c.post("/purchase", json=body, headers=key)
n = c.get("/admin/state").json()["order_count"]
check("only one order exists", n == 1, f"{n} orders")
check("retry returns the original", retry.json().get("duplicate") is True)


print("\nCONTROL PANEL")
check("panel serves", c.get("/panel").status_code == 200)
check("state endpoint serves", c.get("/admin/state").status_code == 200)

c.post("/admin/reset")
print(f"\n{ok} passed, {failed} failed\n")
sys.exit(1 if failed else 0)
