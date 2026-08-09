"""The venue — a fake ticket seller that misbehaves on command.

═══════════════════════════════════════════════════════════════════════════════
WHAT THIS IS
═══════════════════════════════════════════════════════════════════════════════

One file. A pretend Ticketmaster the agent can search, queue for, and buy from —
plus a control panel of buttons that make it fail in specific, useful ways.

It is deliberately not production-shaped. Everything a reader needs to follow
one request is in this file, in the order the request travels.

═══════════════════════════════════════════════════════════════════════════════
HOW A PURCHASE FLOWS
═══════════════════════════════════════════════════════════════════════════════

    agent                          venue
      │
      │  GET  /events              ──►  pick a show
      │  GET  /events/{id}/seatmap ──►  prices + a captured_at stamp
      │                                 (holding this too long is MODULE 4)
      │  POST /queue/join          ──►  ticket + position #14,203
      │                                 returns INSTANTLY, agent stops running
      │
      │       ~40 min of queue (press SKIP THE WAIT). agent not running.
      │
      │  GET  /queue/{ticket}      ──►  position, and whether it is your turn
      │                                 (this is MODULE 4)
      │  POST /purchase            ──►  reserve seats, write an order
      │                                 Idempotency-Key optional (MODULE 4)
      ▼

═══════════════════════════════════════════════════════════════════════════════
WHERE EACH ACT'S BEAT LIVES  (search for the ACT tags)
═══════════════════════════════════════════════════════════════════════════════

    MODULE 1  request log stays flat at 10am — nothing to do here, that's
             the point. Nobody calls the agent.
    MODULE 3  seatmap() returns captured_at, so students can see a snapshot age
    MOD 4    join_queue() returns instantly — the agent parks on it
    MODULE 4  sell_out() makes the snapshot a lie
             hang_once() commits an order and then fails the response
             Idempotency-Key is OPTIONAL, so the retry can buy twice
    MODULE 6  drop_presale() fires the same message Cloud Scheduler sends at 3am

═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sqlite3
import threading
import time
import uuid

import httpx
from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════

DB_PATH = os.environ.get("VENUE_DB", "venue.db")
STATIC = pathlib.Path(__file__).parent / "static"

ARTIST = "The Midnight Signal"

# A queue of 14,203 takes 40 minutes of *venue* time to drain. The clock decides
# how much of your time that is: at 60x it is 40 seconds, at 1x it is 40 real
# minutes. The agent cannot tell the difference either way, which is the honest
# part — we teach the architecture, not the wall clock.
#
# The default is 1x ON PURPOSE. At 60x the queue empties while a student is
# still reading the instruction, so the thing they came to watch is over before
# they look up. At 1x nothing moves far on its own and SKIP THE WAIT is the only
# way to the front, which makes every demo the instructor's to time.
QUEUE_START = 14_203
QUEUE_DRAIN_SECONDS = 2400.0
DRAIN_RATE = QUEUE_START / QUEUE_DRAIN_SECONDS  # people per venue-second

DEFAULT_CLOCK = 1.0

# How long a place at the front is held before it is given away. Expressed in
# people rather than seconds, because that is the unit the queue is in: about as
# long as it takes 1,000 more people to be served. At 1x that is a few minutes of
# yours; at 60x it is a few seconds. Same rule either way, and the agent cannot
# tell the difference — which is the point of the clock.
HOLD_FOR_PEOPLE = 1_000

# id, venue, city, date, weekday.  Mixed weekdays on purpose: the Tuesday shows
# are what make "Sam bails on weeknights" worth remembering.
# The weeknight show in each city comes FIRST, and is $10 cheaper in every
# section. Both of those matter to the workshop: the cheaper, earlier, still
# available show is the one an agent reaches for on price alone, and it is the
# wrong answer for somebody whose friend never turns up on a weeknight.
TOUR = [
    ("ms-ams-02", "Ziggo Dome", "Amsterdam", "2026-11-10", "Tuesday"),
    ("ms-ams-01", "Ziggo Dome", "Amsterdam", "2026-11-14", "Saturday"),
    ("ms-nyc-02", "Barclays Center", "New York", "2026-11-17", "Tuesday"),
    ("ms-nyc-01", "Barclays Center", "New York", "2026-11-21", "Saturday"),
    ("ms-tyo-01", "Tokyo Garden Theater", "Tokyo", "2026-11-28", "Saturday"),
    ("ms-mex-02", "Palacio de los Deportes", "Mexico City", "2026-12-01", "Tuesday"),
    ("ms-mex-01", "Palacio de los Deportes", "Mexico City", "2026-12-05", "Saturday"),
    ("ms-akl-01", "Spark Arena", "Auckland", "2026-12-12", "Saturday"),
]

# How much cheaper a weeknight is, per seat, in every section.
WEEKNIGHT_DISCOUNT = 10.0

# section, tier, price, how many exist
SECTIONS = [
    ("A", "lower bowl", 210.0, 400),
    ("B", "upper bowl", 145.0, 900),
    ("C", "general admission", 95.0, 1200),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS config   (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS events   (id TEXT PRIMARY KEY, venue TEXT, city TEXT,
                                     date TEXT, weekday TEXT);

CREATE TABLE IF NOT EXISTS sections (event_id TEXT, section TEXT, tier TEXT,
                                     price REAL, total INTEGER, sold INTEGER DEFAULT 0,
                                     PRIMARY KEY (event_id, section));

CREATE TABLE IF NOT EXISTS tickets  (ticket TEXT PRIMARY KEY, event_id TEXT,
                                     joined_at REAL, forced_ready INTEGER DEFAULT 0,
                                     forced_at REAL DEFAULT 0);

-- forced_at arrived after the first workshops, and CREATE TABLE IF NOT EXISTS
-- will not add a column to a table that already exists. Anyone with a venue.db
-- from before it would get a 500 on every queue check, which is a confusing
-- morning. Added below, guarded, at startup.

CREATE TABLE IF NOT EXISTS orders   (id TEXT PRIMARY KEY, idem_key TEXT,
                                     event_id TEXT, section TEXT, seats INTEGER,
                                     unit_price REAL, total REAL, created_at REAL);

CREATE UNIQUE INDEX IF NOT EXISTS idx_idem ON orders(idem_key) WHERE idem_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                     ts REAL, kind TEXT, message TEXT);
"""

# ═══════════════════════════════════════════════════════════════════════════
# DATABASE — one connection, one lock. Single venue per student.
# ═══════════════════════════════════════════════════════════════════════════

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)

        # CREATE TABLE IF NOT EXISTS will not add a column to a table that
        # already exists, so a venue.db made before a column was introduced
        # keeps working right up until something reads that column and 500s.
        # Cheap to check, and it makes an old database self-heal.
        have = {r["name"] for r in _conn.execute("PRAGMA table_info(tickets)")}
        for column, ddl in (("forced_at", "REAL DEFAULT 0"),):
            if column not in have:
                _conn.execute(f"ALTER TABLE tickets ADD COLUMN {column} {ddl}")

        _conn.commit()
    return _conn


def rows(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in db().execute(sql, args).fetchall()]


def row(sql: str, args: tuple = ()) -> dict | None:
    found = rows(sql, args)
    return found[0] if found else None


def run(sql: str, args: tuple = ()) -> None:
    with _lock:
        db().execute(sql, args)
        db().commit()


def log(kind: str, message: str) -> None:
    """Everything the panel shows in its activity feed."""
    run("INSERT INTO activity (ts, kind, message) VALUES (?,?,?)",
        (time.time(), kind, message))


def setting(key: str, default: str) -> str:
    found = row("SELECT value FROM config WHERE key=?", (key,))
    return found["value"] if found else default


def set_setting(key: str, value) -> None:
    run("INSERT INTO config (key,value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def seed() -> None:
    """Idempotent — safe on every startup and after a reset."""
    # Upsert, not INSERT OR IGNORE. A student who ran an earlier version of this
    # workshop already has a venue.db, and IGNORE would leave them on the old
    # dates and the old prices for ever — with no error, and nothing on screen to
    # say why their agent is reasoning about numbers you cannot see.
    #
    # `sold` is deliberately left out of the UPDATE. Re-seeding must not un-sell
    # anything; only the catalogue is corrected, never the state of play.
    for eid, venue_name, city, date, weekday in TOUR:
        run("""INSERT INTO events VALUES (?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   venue=excluded.venue, city=excluded.city,
                   date=excluded.date, weekday=excluded.weekday""",
            (eid, venue_name, city, date, weekday))
        discount = WEEKNIGHT_DISCOUNT if weekday not in ("Saturday", "Sunday") else 0.0
        for section, tier, price, total in SECTIONS:
            run("""INSERT INTO sections VALUES (?,?,?,?,?,0)
                   ON CONFLICT(event_id, section) DO UPDATE SET
                       tier=excluded.tier, price=excluded.price,
                       total=excluded.total""",
                (eid, section, tier, price - discount, total))


# ═══════════════════════════════════════════════════════════════════════════
# THE CLOCK  —  the venue owns time, so the workshop never waits for it
# ═══════════════════════════════════════════════════════════════════════════

def clock() -> float:
    return float(setting("clock", str(DEFAULT_CLOCK)))


# ═══════════════════════════════════════════════════════════════════════════
# THE QUEUE
#
# Position is COMPUTED, never stored as a countdown:
#     position = 14203 - drain_rate * (real_elapsed * clock_multiplier)
# which is why changing the clock mid-run instantly moves every waiting ticket.
# ═══════════════════════════════════════════════════════════════════════════

# A place at the front is held for HOLD_FOR_PEOPLE-worth of queue time and then
# released. Real venues do this and it is the reason a queue moves at all.
HOLD_SECONDS = HOLD_FOR_PEOPLE / DRAIN_RATE          # in venue-seconds


def queue_status(ticket: str) -> dict | None:
    t = row("SELECT * FROM tickets WHERE ticket=?", (ticket,))
    if t is None:
        return None

    venue_seconds = (time.time() - t["joined_at"]) * clock()

    if t["forced_ready"]:
        position = 0
    else:
        position = max(0, int(round(QUEUE_START - DRAIN_RATE * venue_seconds)))

    # Expired? Only once you have actually reached the front — nobody loses
    # their place for still being 9,000th. Swept here rather than in a
    # background task, because the venue has no background tasks and does not
    # need any: nothing can observe an expired ticket without asking about it.
    if position == 0:
        if t["forced_ready"] and t["forced_at"]:
            at_front_for = (time.time() - t["forced_at"]) * clock()
        else:
            at_front_for = venue_seconds - (QUEUE_START / DRAIN_RATE)
        if at_front_for > HOLD_SECONDS:
            run("DELETE FROM tickets WHERE ticket=?", (ticket,))
            log("queue", f"{ticket} expired — held the front too long")
            return None

    venue_remaining = position / DRAIN_RATE if position else 0.0
    return {
        "ticket": ticket,
        "event_id": t["event_id"],
        "position": position,
        "ready": position == 0,
        "venue_seconds_remaining": round(venue_remaining, 1),
        "real_seconds_remaining": round(venue_remaining / clock(), 1),
        "clock_multiplier": clock(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# THE APP
# ═══════════════════════════════════════════════════════════════════════════

@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    db()
    seed()
    yield


app = FastAPI(title="Venue", lifespan=lifespan)


# ───────────────────────────────────────────────────────────────────────────
# PUBLIC  —  everything the agent calls
# ───────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "clock_multiplier": clock()}


@app.get("/events")
def list_events(artist: str = "", city: str = "", weekday: str = ""):
    """Search the tour. `artist` is accepted and ignored — there is one artist."""
    sql, args = "SELECT * FROM events WHERE 1=1", []
    if city:
        sql, args = sql + " AND city LIKE ?", args + [f"%{city}%"]
    if weekday:
        sql, args = sql + " AND weekday = ?", args + [weekday]
    found = rows(sql + " ORDER BY date", tuple(args))
    return {"events": [{**e, "artist": ARTIST} for e in found]}


@app.get("/events/{event_id}/seatmap")
def seatmap(event_id: str):
    """MODULE 3 / MODULE 4 — note `captured_at`.

    An agent that stores this and acts on it forty minutes later is holding a
    snapshot, and the snapshot is a lie.
    """
    event = row("SELECT * FROM events WHERE id=?", (event_id,))
    if event is None:
        raise HTTPException(404, "no such event")
    secs = rows("SELECT * FROM sections WHERE event_id=? ORDER BY section", (event_id,))
    return {
        "event_id": event_id,
        "artist": ARTIST,
        "venue": event["venue"],
        "city": event["city"],
        "date": event["date"],
        "weekday": event["weekday"],
        "captured_at": time.time(),
        "sections": [
            {"section": s["section"], "tier": s["tier"], "price": s["price"],
             "available": s["total"] - s["sold"]}
            for s in secs
        ],
    }


@app.post("/queue/join")
def join_queue(payload: dict = Body(...)):
    """Returns INSTANTLY. The waiting happens elsewhere.

    The agent gets a ticket and stops running. Whoever wants to know whether it
    is at the front asks with GET /queue/{ticket}.
    """
    event_id = payload.get("event_id")
    if not event_id:
        raise HTTPException(400, "event_id required")
    if row("SELECT id FROM events WHERE id=?", (event_id,)) is None:
        raise HTTPException(404, "no such event")

    ticket = f"q_{uuid.uuid4().hex[:8]}"
    run("INSERT INTO tickets (ticket, event_id, joined_at) VALUES (?,?,?)",
        (ticket, event_id, time.time()))

    status = queue_status(ticket)
    log("queue", f"joined {event_id} at #{status['position']:,}")
    return status


@app.get("/queue/{ticket}")
def check_queue(ticket: str):
    status = queue_status(ticket)
    if status is None:
        raise HTTPException(404, "no such ticket")
    return status


@app.post("/purchase")
def purchase(
    payload: dict = Body(...),
    idem_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Buy seats.

    MODULE 4 — the Idempotency-Key header is deliberately OPTIONAL. Module 4 begins
    with the agent not sending one, the platform retries after HANG ONCE, and
    the tickets get bought twice. If the venue demanded a key there would be
    nothing to teach.
    """
    # 1. Seen this exact purchase before? Hand back the original order.
    if idem_key:
        seen = row("SELECT * FROM orders WHERE idem_key=?", (idem_key,))
        if seen:
            log("purchase", f"duplicate suppressed — returned {seen['id']}")
            return {**seen, "duplicate": True}

    event_id = payload.get("event_id")
    section = payload.get("section", "A")
    seats = int(payload.get("seats", 2))

    sec = row("SELECT * FROM sections WHERE event_id=? AND section=?", (event_id, section))
    if sec is None:
        raise HTTPException(404, "no such event or section")

    # 2. If a queue ticket was supplied, it has to be at the front.
    if payload.get("queue_ticket"):
        status = queue_status(payload["queue_ticket"])
        if status is None:
            raise HTTPException(404, "no such queue ticket")
        if not status["ready"]:
            raise HTTPException(409, {
                "error": "still_in_queue",
                "position": status["position"],
                "message": "you are not at the front of the queue yet",
            })

    # 3. Are the seats actually there? (SELL OUT SECTION A makes this fail.)
    available = sec["total"] - sec["sold"]
    if available < seats:
        log("error", f"purchase failed — section {section} has {available} left")
        raise HTTPException(409, {
            "error": "sold_out",
            "section": section,
            "available": available,
            "requested": seats,
            "message": "those seats are gone — re-fetch the seatmap before buying",
        })

    # 4. Take the seats and write the order.
    run("UPDATE sections SET sold = sold + ? WHERE event_id=? AND section=?",
        (seats, event_id, section))
    order_id = f"ord_{uuid.uuid4().hex[:8]}"
    total = round(sec["price"] * seats, 2)
    # You bought, so you are out of the queue. A real venue releases your place
    # the moment the order lands — leaving it behind makes the panel show
    # somebody still waiting after they have already gone home, and makes the
    # next purchase look like it came from a queue that had been drained.
    if payload.get("queue_ticket"):
        run("DELETE FROM tickets WHERE ticket=?", (payload["queue_ticket"],))
    else:
        # No ticket supplied — drop the oldest one that had reached the front
        # for this show, which is whoever this purchase belonged to.
        run("""DELETE FROM tickets WHERE ticket = (
                 SELECT ticket FROM tickets
                 WHERE event_id=? AND forced_ready=1
                 ORDER BY joined_at LIMIT 1)""", (event_id,))

    run("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
        (order_id, idem_key, event_id, section, seats, sec["price"], total, time.time()))

    # 5. MODULE 4 — if HANG ONCE is armed, the order is already committed and the
    #    caller is about to be told it failed. The platform retries. Without an
    #    idempotency key, step 1 above cannot save them.
    if setting("hang_once", "0") == "1":
        set_setting("hang_once", "0")
        log("purchase", f"{order_id} COMMITTED, then failed the response (hang-once)")
        raise HTTPException(503, {"error": "upstream_timeout", "message": "try again"})

    log("purchase", f"{order_id} — {seats}x section {section} @ {sec['price']:g} = {total:g}")
    return dict(row("SELECT * FROM orders WHERE id=?", (order_id,)))


# ───────────────────────────────────────────────────────────────────────────
# ADMIN  —  the buttons on the control panel
# ───────────────────────────────────────────────────────────────────────────

@app.post("/admin/clock")
def set_clock(payload: dict = Body(...)):
    value = float(payload.get("multiplier", DEFAULT_CLOCK))
    if value <= 0:
        raise HTTPException(400, "multiplier must be positive")
    set_setting("clock", value)
    log("admin", f"clock set to {value:g}x")
    return {"clock_multiplier": value}


@app.post("/admin/advance-queue")
def advance_queue():
    """Send every waiting ticket straight to the front."""
    # forced_at starts the hold clock. Without it, SKIP THE WAIT would hand you
    # a place that expired the moment you got it, because the hold would be
    # measured from when you joined rather than from when you arrived.
    run("UPDATE tickets SET forced_ready=1, forced_at=? WHERE forced_ready=0",
        (time.time(),))
    log("admin", "queue advanced to the front")
    return {"ok": True}


@app.post("/admin/sellout")
def sell_out(payload: dict = Body(...)):
    """MODULE 4 — make the agent's snapshot a lie, on cue."""
    event_id = payload.get("event_id")
    section = payload.get("section", "A")
    if not event_id:
        raise HTTPException(400, "event_id required")
    run("UPDATE sections SET sold=total WHERE event_id=? AND section=?", (event_id, section))
    log("admin", f"section {section} sold out for {event_id}")
    return {"event_id": event_id, "section": section, "available": 0}


@app.post("/admin/hang-once")
def hang_once():
    """MODULE 4 — arm one purchase to commit and then fail its response.

    The runtime's own retry does the rest. The double purchase is caused by the
    platform, not by anything the student wrote.
    """
    set_setting("hang_once", "1")
    log("admin", "next purchase armed to commit-then-fail")
    return {"hang_once": True}


@app.post("/admin/drop-presale")
def drop_presale():
    """MODULE 6 — wake something up, with no human in the room.

    The venue knows nothing about ADK, Pub/Sub or Cloud Scheduler. It POSTs an
    opaque body to whatever URL it was configured with — the same rule the queue
    webhook follows. A ticket seller has no business importing a cloud SDK.

    Student plane:    PRESALE_TARGET_URL unset -> falls back to AGENT_URL.
    Instructor plane: don't use this button. Cloud Scheduler has its own, and it
                      fires the genuine production path:
                          gcloud scheduler jobs run presale-drop --location=...
    """
    target = os.environ.get("PRESALE_TARGET_URL") or os.environ.get("AGENT_URL")
    message = {"kind": "presale_drop", "artist": ARTIST}

    if not target:
        log("admin", "presale dropped (no target configured)")
        return {"message": message, "note": "set PRESALE_TARGET_URL or AGENT_URL"}

    try:
        httpx.post(target, json=message, timeout=10)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"target unreachable: {exc}") from exc

    log("admin", f"presale posted to {target}")
    return {"posted_to": target, "message": message}


@app.post("/admin/agent-event")
def agent_event(payload: dict = Body(...)):
    """The agent's PanelPlugin posts here, so the panel has something to show
    while the agent is asleep in a queue. A blank projector loses the room."""
    log(payload.get("kind", "agent"), payload.get("message", ""))
    return {"ok": True}


@app.post("/admin/reset")
def reset():
    with _lock:
        for table in ("tickets", "orders", "activity", "sections", "events", "config"):
            db().execute(f"DELETE FROM {table}")
        db().commit()
    seed()
    log("admin", "venue reset")
    return {"ok": True}


@app.get("/admin/state")
def state():
    """Everything the panel polls, twice a second."""
    tickets = rows("SELECT ticket FROM tickets ORDER BY joined_at DESC LIMIT 20")
    orders = rows("SELECT * FROM orders ORDER BY created_at DESC LIMIT 20")
    return {
        "clock_multiplier": clock(),
        "hang_armed": setting("hang_once", "0") == "1",
        "queue": [s for s in (queue_status(t["ticket"]) for t in tickets) if s],
        # Joined to events, so the panel can show "Amsterdam · Saturday"
        # instead of "ms-ams-01". The whole tour is on screen, and which show
        # is the weeknight trap is obvious at a glance.
        "inventory": rows(
            "SELECT s.event_id, s.section, s.total - s.sold AS available, s.total, "
            "       e.city, e.weekday, e.date, e.venue "
            "FROM sections s JOIN events e ON e.id = s.event_id "
            "ORDER BY e.date, s.section"
        ),
        "artist": ARTIST,
        "orders": orders,
        "order_count": len(rows("SELECT id FROM orders")),
        "agent_events": rows("SELECT * FROM activity ORDER BY id DESC LIMIT 25"),
        "now": time.time(),
    }


# ───────────────────────────────────────────────────────────────────────────
# THE PANEL
# ───────────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return RedirectResponse("/panel")


@app.get("/panel")
def panel():
    return FileResponse(STATIC / "panel.html")


@app.get("/themidnightsignal.png")
def poster():
    """The band. Served under its own filename so the URL in panel.html and
    the file on disk are the same string. There is no static mount here on
    purpose: this venue serves a handful of files, and naming them is shorter
    than configuring a directory."""
    return FileResponse(STATIC / "themidnightsignal.png")


@app.get("/midnight_breach.mp3")
def track():
    """The band, audibly. Served under its own filename so the URL in
    panel.html and the file on disk are the same string, with nothing to
    reconcile. Nothing depends on it, so a missing file is a 404 and not a
    broken panel: the <audio> element simply refuses to play."""
    mp3 = STATIC / "midnight_breach.mp3"
    if not mp3.exists():
        raise HTTPException(status_code=404, detail="no track installed")
    return FileResponse(mp3, media_type="audio/mpeg")
