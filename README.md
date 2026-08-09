# Everything You Need to Build Long-Running Agents on Google Cloud

A 2-hour hands-on workshop on **long-running agents**, built with
[ADK](https://adk.dev) (Agent Development Kit) 2.x and Google Cloud.

Students build an agent that buys concert tickets at 3am while they're asleep.

---

## Contents

- [Thesis](#thesis)
- [The scenario](#the-scenario)
- [The nine acts](#the-nine-acts)
- [Architecture](#architecture)
- [Deployment plan](#deployment-plan)
- [Repo layout](#repo-layout)
- [Setup](#setup)
- [Laptop → cloud swap table](#laptop--cloud-swap-table)
- [Instructor checklist](#instructor-checklist)
- [Design decisions](#design-decisions)
- [Verified library facts](#verified-library-facts)
- [ADK 2 decision](#adk-2-decision--resolved)
- [Status](#status)

---

## Thesis

Every framework got better at what goes **in the prompt**. None of them got
better at **being awake**.

A long-running agent needs four things a chat assistant does not:

1. **A clock of its own** — it starts without you
2. **Facts that outlive the conversation** — and survive a summarizer
3. **Survival across process death** — crashes, deploys, closed laptops
4. **Bounded authority** — permission granted in advance, because you're asleep,
   and negotiated at the last moment for the branches you can foresee

The workshop teaches those four, in that order, using one scenario.


---

## The scenario

An agent that books concert tickets.

The on-sale drops at 10am. Tickets are gone in ninety seconds. You are in another timezone, asleep.

That single fact forces the most interesting design question in the space: **human-in-the-loop, when the human is unavailable and waiting means losing.**
The answer is a *budget agreed in advance* — bounded authority, granted while you are still awake.

### Why this scenario

| Requirement | How the scenario delivers |
|---|---|
| Wakes without a user | Presale drops on a schedule |
| Actions that matter | Spends real money |
| Long, honest pause | Queue position 14,203, forty minutes |
| Stale context | Inventory changes in seconds |
| Double-fire hurts | Retry buys four tickets |
| Nested timescales | Envelope (forever) / booking (hours) / seatmap (seconds) |
| Cross-session memory | "Sam bails on weeknights" |

### Ethics note — say this out loud in the room

Ticket bots are a real problem and real ticketing sites prohibit automation. The workshop runs against a **mock venue service the student runs themselves**,
buying **one** allotment for **themselves**, inside limits **they** set.
---

## The ten steps, in six modules

Total: 120 minutes.

### Module 1 · You cannot prompt your way to autonomy *(12 min)*

You demo an assistant that plans a concert trip. It knows the budget,
remembers the friends, picks the right city. The room is impressed.

Tuesday 10am arrives and it does nothing. It runs only when someone types, and
everyone is asleep.

This is also where you handle ChatGPT, which someone is already thinking about.
It does all of this well and is equally asleep at 10am.

```
  MON: you type                      TUE 10:00: nobody types
       │                                     │
       ▼                                     ▼
  ┌─────────┐  search_events()          ┌─────────┐
  │  Agent  │ ──────────────►           │  Agent  │   (never invoked)
  └─────────┘                           └─────────┘
       │                                     │
       ▼                                     ▼
  "Saturday in Amsterdam,            request log
   row F, $210, Sam's in"            10:00 ▁▁▁▁▁▁▁▁ 0 requests
                                     tickets: GONE
```

Then they try the fix everyone reaches for — a system prompt that says
*"monitor the presale and buy the moment it opens"* — restart, and watch it do
absolutely nothing.

That prompt gets written in production constantly. *Monitor our error rates and
alert me. Watch the inbox. Check daily and summarise.* They read perfectly, they
pass review, and they do nothing at all, silently.

**Takeaway:** you cannot write your way out of not being invoked. Something
outside the agent has to call it.

**Running:** `Agent` + `FunctionTool(search_events)` · venue service · `adk web`

---

### Module 2 · Give it a clock *(11 min)*

Step 2 left a problem. This is the smallest honest answer to it: forty lines
with a `sleep` and an HTTP call.

```python
runner = Runner(agent=root_agent, app_name="concert",
                session_service=InMemorySessionService())   # ← the amnesia

await asyncio.sleep(delay)          # ← its own clock, not your keyboard
async for event in runner.run_async(...):
```

No web server, no browser, no `adk web` — which is also the first time students
see what `adk web` had been doing for them since step 1.

Students start it, **put their hands down**, and watch the agent run a minute
later with nobody at the keyboard.

Then they read what it said:

> *"I can't buy tickets, but I can show you what's available. Which show were we
> considering?"*

Asked at 3am, to an empty room. It woke with a fresh session and knows nothing —
not who you are, not about Sam, not the budget. And nobody is reading a chat box
at 3am anyway.

| What went wrong | Fixed in |
|---|---|
| no idea who you are | Module 3 |
| never heard about Sam or the budget | Module 3 |
| asked a question into an empty room | Module 5 |
| cannot buy anything anyway | Module 4 |

**Takeaway:** waking up was never the hard part. An agent that wakes with
nothing is not yet worth waking — and every later act fixes one line of that
table.

> Framed honestly as a stand-in: you started it by hand and it dies with your
> terminal. Cloud Scheduler arrives in Module 6 as the same shape with someone
> else's cron.

---

### Module 3 · Open the box *(13 min)*

Students open a seeded session that has been alive for two days — three past
bookings, a group chat, currently sitting in a queue — and answer five
questions by finding the answers in the State / Events / Artifacts tabs.

```
  QUESTION                                   WHERE THEY FIND IT
  ─────────────────────────────────────      ──────────────────────────
  1. Where does "Sam hates weeknights"       State tab → user:prefs
     actually live?
  2. What's in temp:seatmap, and how old     State tab → temp:seatmap
     is the timestamp?                        (captured 38 min ago)
  3. This session has 84 events. What did    Events tab → compaction
     compaction already replace?              summaries at 20/40/60
  4. Where is the seat map PNG?              Artifacts tab
     (why isn't it in the prompt?)
  5. What does the agent know from           nowhere in this session —
     booking #2 that isn't in this            it's in memory/*.md
     session at all?
```

Then they **write down which of the five survives a restart**, and you restart.

Most people get `temp:seatmap` wrong. That is the one you want them wrong
about, because it is Module 4's bug.

**Takeaway:** every fact has a shelf life.

> **Design note:** this act was originally a paper card-sort. It was cut
> because 20 minutes of sorting cards in a technical workshop is dead air and
> teaches a taxonomy that fits on one slide. Reading real state in the real UI
> teaches the same thing and doubles as a tour of the tool they'll use all day.

---

### Module 3 · What the summary throws away *(13 min)*

Six friends, a group chat, forty tour dates. ADK compacts the session to save
room. In compacting, it loses *"Sam hates weeknights."* The agent books Tuesday
and explains its reasoning perfectly.

```
BEFORE                                  AFTER
────────────────────────────            ────────────────────────────
App(root_agent=agent,                   Agent(..., output_key="group_prefs")
    events_compaction_config=                        │
      EventsCompactionConfig(                        ▼
        compaction_interval=20))        state["user:prefs"] =
         │                                 {"sam": "no_weeknights"}
         ▼                                           │
  events 1–20 ──► LLM summary                        │
    "Sam hates weeknights"  ✗ lost      compaction runs ──► state UNTOUCHED
         │                                           │
         ▼                                           ▼
    books TUESDAY                            books SATURDAY

  + budget_split sub-agent: include_contents='none'
    does arithmetic on 40 tour dates without reading the group chat
```

**Students type:** `output_key="group_prefs"` and `include_contents='none'`.

**Takeaway:** a summary keeps the gist and drops the exceptions. Facts you
can't afford to lose belong outside the chat.

> Seed the session at **18 events** so compaction fires naturally two turns in,
> instead of making students type twenty messages to reach the threshold.

---

### Module 4 · Pull the plug *(13 min)*

The agent is 14,203rd in the queue with forty minutes to go. Everyone kills the
agent. Restart, and it's still in line — and the position has kept dropping the
whole time it was dead.

```
  join_queue()   ← LongRunningFunctionTool
       │  returns IMMEDIATELY: {status:"queued", pos:14203, ticket:"q_88f2"}
       ▼
  state["queue_ticket"] = "q_88f2"   ──► persisted to sessions.db
       │
       ▼
  ══════════ PROCESS DIES ══════════
       │
       ▼
  restart ──► DatabaseSessionService.get_session(session_id)
       │
       ▼
  still #14,203
       │
  venue webhook "you're up" ──► FunctionResponse ──► agent resumes mid-thought
```

Then, on the terminal:

```bash
sqlite3 sessions.db "select * from events limit 5"
```

Their session, as rows, on their screen.

**The point to say out loud:** the agent was not running for forty minutes. It
was *gone*, and a webhook brought it back. That is the whole trick of
long-running.

**Takeaway:** progress has to live outside the program that made it.

---

### Module 4 · Acting on old news *(14 min)*

It returns from the wait and buys seats it saw forty minutes ago. Then it
crashes mid-purchase, retries, and buys them twice.

```
STALE
  temp:seatmap captured t=0 ──── 40 min ────► purchase(row F)  ✗ SOLD AT t=12

  fix:  before_tool_callback("purchase")
          └─► re-fetch inventory NOW ──► compare ──► proceed or re-plan

DOUBLE-FIRE
  purchase() ──► ✓ order_9931 ──► CRASH before response recorded
       └──► retry ──► purchase() ──► order_9932     = 4 tickets

  fix:  idempotency_key = sha(session_id + event_id + seats)
        venue returns order_9931 BOTH times

UNDO (ADK 2)
  runner.rewind_async(rewind_before_invocation_id=bad_id)
        └─► state rolls back to before the bad decision, replay from there
```

**The gift:** the trigger endpoint retries automatically
(`ADK_TRIGGER_MAX_RETRIES` defaults to 3, with exponential backoff). The double
purchase is caused by the *platform*, not by anything the student wrote.

> **The platform will retry you. Idempotency is not optional.**

**Takeaway:** an agent holding expired information acts on it with full
confidence.

---

### Module 5 · Draw the flow in advance *(13 min)*

Everything up to here has been a conversation. At 3am there is nobody to hold
one, and nobody to notice the model picked a Tuesday.

```
  START ─► open ─► pick_show ──► queue_up ──► check_front ──► buy_it
           (fn)    (agent)       (function)   (function)      (agent)
                   picks a show  joins once   at the front?    root_agent,
                                              no → PAUSE       unmodified
```

Two nodes are agents and two are functions. Picking a show from someone's
history is judgement; joining a queue and asking "am I at the front" are rules.
The last node is `root_agent` itself, imported unmodified — the graph surrounds
the agent rather than replacing it.

When the queue is not ready `check_front` returns a `RequestInput`, and the run
**stops**. Nothing loops, nothing sleeps, the process can exit. Waking it re-runs
only `check_front`, because `pick_show` and `queue_up` carry
`@node(rerun_on_resume=False)` — so no second show, no second queue ticket.

**Students type:** nothing meaningful. `root_agent` is the graph from this
module on, so the same `concert` entry now runs it. They send anything, watch it
park, send again, press SKIP THE WAIT, send once more, and it buys.

**Takeaway:** a run that waits should cost nothing while it waits. The limits in
this version are constants at the top of the file, and it will spend the money
without asking anyone — which is what the next module is about.

### Module 5 · Draw a fence around the money *(14 min)*

Ask the room how much of their credit card they'd hand over while asleep. Then
point out that "ask me first" means losing every ticket, because the queue
moves in ninety seconds and they're unconscious.

```
  state["user:budget"] = "up to $100 for the cheap seats, $250 for the good
                          ones, $300 on a Saturday"   # their words
      max_price: 250,  seats: 2,  exclude_days: ["Tue"],
      city: "Amsterdam",  max_purchases: 1
  }
            │
            ▼
  before_tool_callback("purchase", args)
            │
      ┌─────┴──────┐
   INSIDE       OUTSIDE
      │             │
      ▼             ▼
   proceed     LongRunningFunctionTool ──► pause ──► notify human
   silently                                    │
                                    (you're asleep — tickets may be lost.
                                     that is the accepted cost)

  Secret Manager ──► payment_ref ──► venue redeems it
                     agent never sees a card number
```

**Students type:** JSON values only. Zero code.

**Takeaway:** approving each step requires you to be awake. Authority gets
granted in advance, with edges.

---

### Module 6 · The 3am run *(14 min)*

3am presale, nobody awake. The agent wakes itself, queues, waits, checks the
fence, buys, and texts a confirmation.

```
  Cloud Scheduler  (cron: 0 3 * * 2)
         │  publishes message
         ▼
  Pub/Sub topic: presale-drop
         │  push subscription
         ▼
  POST /apps/concert/trigger/pubsub
  ┌──────────────────────────────────────────────┐
  │  Cloud Run  ◄── adk deploy cloud_run         │
  │                                              │
  │  get_fast_api_app(                           │
  │      agents_dir=AGENTS_DIR,                  │
  │      web=False,                              │
  │      trigger_sources=["pubsub"])             │
  │                                              │
  │  DatabaseSessionService  ← REQUIRED          │
  │    (trigger sessions default to in-memory    │
  │     and vanish; this is a live footgun)      │
  └──────────────────┬───────────────────────────┘
                     ▼
        join_queue ──► [ 40 min, nothing running ] ──► webhook
                     ▼
        re-fetch ──► fence check ──► purchase($190, Sat, 2 seats)
                     ▼
        confirmation.pdf ──► artifact ──► GCS
                     ▼
        notification ──► your phone

  Cloud Trace:  ▇▇──────────── 40 min gap ────────────▇▇▇▇
                 ▲                                     ▲
              queued                                bought
                        you: asleep for all of it
```

Then show **the diff** — see [swap table](#laptop--cloud-swap-table). The agent,
tools, and callbacks are byte-identical between their laptop and this.

**Takeaway:** it started itself, stayed inside the fence, remembered the right
things, and you got the seats.

---

### Coda — The discard jar *(4 min)*

Hold up a jar of sourdough discard. Keeping a starter alive means throwing most
of it away every day. Feed it everything and it turns sour and dies.

```
  transcript ──► compacted ──► lossy    (fine, it's chat)
  state      ──► kept        ──► exact  (the stuff that matters)
```

**Takeaway:** keeping everything is hoarding. The skill is choosing what to
throw away.

---

## Architecture

### One plane per student, nothing shared

Every student deploys their own venue and runs their own agent. There is no
shared service anywhere, so nobody can break anybody else — which matters a lot
when half the workshop consists of deliberately breaking things.

```
╔═══════════════════════════════════════════════════════════════╗
║  ONE STUDENT                                                  ║
║  their own Cloud Run venue + their own local agent            ║
╚═══════════════════════════════════════════════════════════════╝
              × 30, with no connection between them
```

### What runs where

```
┌─ THEIR MACHINE (Cloud Shell, or a laptop) ───────────────────────┐
│  ~/longrunningag                                              │
│                                                                  │
│  ┌─ adk web  :8000 ──────────┐   ┌─ trigger/ (Module 2 only) ──┐│
│  │                           │   │  server.py  POST /wake      ││
│  │ App(                      │   │    a Runner you built       ││
│  │   root_agent=…,           │   │  clock.py   calls it        ││
│  │   plugins=[PanelPlugin],  │   │    on a schedule            ││
│  │   events_compaction_      │   │                             ││
│  │     config=…,             │   │  same session store as      ││
│  │   resumability_config=…)  │   │  adk web — they see each    ││
│  │  search_events            │   │  other's sessions           ││
│  │  get_seatmap              │   └─────────────────────────────┘│
│  │  join_queue   ← LRFT      │                                   │
│  │  check_queue              │      sessions.db    (SQLite)      │
│  │  purchase   ← fence.py    │      artifacts/                   │
│  │  set_budget               │      memory/userx.md          │
│  │  budget_split             │        ↑ edit it, behaviour       │
│  │    include_contents=none  │          changes next turn        │
│  └───────────────┬───────────┘                                   │
└──────────────────┼───────────────────────────────────────────────┘
                   │  outbound only — nothing reaches in
                   ▼
┌─ CLOUD RUN — venue-<student> ────────────────────────────────────┐
│  ./deploy-venue.sh                                               │
│                                                                  │
│  GET  /events            GET  /queue/{ticket}                    │
│  GET  /events/{id}/seatmap                                       │
│  POST /queue/join        POST /purchase  (Idempotency-Key)       │
│  /panel  ── SKIP THE WAIT · SELL THE GOOD SEATS ·                │
│             BREAK THE NEXT PURCHASE · FIRE THE PRESALE           │
│                                                                  │
│  SQLite in /tmp   ·   scales to zero between requests            │
└──────────────────────────────────────────────────────────────────┘

  Vertex AI (gemini-2.5-flash) via Application Default Credentials.
  No API keys anywhere.
```

### Why the venue is deployed and the agent is not

The venue is the shared-looking thing that students break, so it has to be
per-student. Putting it on Cloud Run gets it off their machine, survives Cloud
Shell timeouts, and teaches `gcloud run deploy` early — so the final step's
deploy is familiar rather than new.

The agent stays local because students edit it every step. Deploying it seven
times would cost twenty minutes of the two hours.

### The consequence: nothing reaches into the laptop

A venue on Cloud Run cannot POST to a laptop, and this workshop does not pretend
otherwise. Every call goes outbound from the student's machine.

So the queue drains on the venue's own clock, and the agent finds out by asking:

```
  agent (laptop)  ── join_queue ──►  venue (Cloud Run)   returns a ticket, run parks
  agent (laptop)  ── check_queue ─►  venue (Cloud Run)   next time it is woken
```

Module 4 wakes it by typing. Module 2 wakes it with `monstertix/clock.py` hitting
an endpoint the student wrote. Module 6 wakes it with Cloud Scheduler → Pub/Sub
hitting a Cloud Run agent. Same shape all three times: something outside the
agent decides it is time, and the agent picks up where it stopped.

> **Never** let the agent poll itself in a loop. It burns tokens, makes the model
> responsible for patience, and makes "the agent was gone for forty minutes" a lie.

### Cloud only for the last step

Module 6 adds Cloud Scheduler → Pub/Sub → a Cloud Run agent with
`trigger_sources`. That one is an instructor demo, watched rather than done,
because thirty simultaneous agent deploys is not a good use of eighteen minutes.

> ⚠️ Trigger endpoints require **Cloud Run or GKE**. Agent Runtime does not
> support scheduled or event-driven triggers.


## Deployment plan

### The venue service

The most important component, because seven of nine acts need it to misbehave
on cue.

| Endpoint | Purpose |
|---|---|
| `GET /events?artist=` | search — the only "real-feeling" data |
| `GET /events/{id}/seatmap` | tiers + prices, PNG to artifact store |
| `POST /queue/join` | returns `{ticket, position}` immediately |
| `GET /queue/{ticket}` | position, drains at clock speed |
| `POST /purchase` | requires `Idempotency-Key` + `payment_ref` |
| `POST /admin/clock` | 1× / 10× / 60× |
| `POST /admin/advance-queue` | 14,203 → 0 |
| `POST /admin/sellout` | Module 4 staleness on demand |
| `POST /admin/hang-once` | forces platform retry → double purchase |
| `POST /admin/drop-presale` | publishes the Pub/Sub message |

Queue position is **computed, never stored** as a countdown:
`position = f(joined_at, now, multiplier)`. Changing the clock mid-run works
without touching any state.

### The control panel

Served by the venue at `/panel`. Every dramatic beat becomes a button, so
nothing in the workshop waits on a real clock.

```
┌─ VENUE CONTROL ─────────────────────────────────────────┐
│  clock: [1x] ● [10x] [60x]                              │
│                                                          │
│  [ DROP PRESALE NOW ]      → publishes to Pub/Sub topic │
│  [ ADVANCE QUEUE ]         → 14203 → 0 instantly        │
│  [ SELL OUT SECTION A ]    → Module 4 staleness, on cue │
│  [ HANG ONCE ]             → forces the platform retry  │
│  [ RESET EVERYTHING ]                                    │
├─ LIVE ──────────────────────────────────────────────────┤
│  queue: #8,412 ▓▓▓▓▓▓░░░░  ticking down                 │
│  agent: waiting on join_queue (LongRunningFunctionTool)  │
│  state: temp:seatmap  age 00:38                          │
│  inventory: A:0  B:112  C:340                            │
└──────────────────────────────────────────────────────────┘
```

The live panel solves the **dead-screen problem** — a waiting agent shows
nothing, and a blank projector loses the room. Watching `temp:seatmap` age from
00:04 to 00:38 sets up Module 4 without you saying a word.

### Clock compression

The venue owns a speed multiplier, defaulting to **1×**. A 40-minute queue takes
40 minutes, so nothing finishes while a student is still reading, and **SKIP THE
WAIT** is the only way to the front — which puts the timing of every demo in
your hands. Push it to 60× when you want the drain visible on the projector.
**The agent code is byte-identical** at either setting and has no idea. Say the
multiplier out loud once and nobody is confused.

### Cloud Trace will embarrass you

Trace ingestion lags by tens of seconds to minutes. "Now let's look at the
trace" followed by an empty page is where GCP workshops die.

- **Live feedback** comes from `LoggingPlugin` → the control panel. Instant.
- **Cloud Trace** is shown from a run you did the night before, already
  ingested, with a real forty-minute gap in it.

---

## Repo layout

```
longrunningag/
├── setup.sh                asks for a project id once, then does everything:
│                           venv, deps, ADC sign-in, gcloud config, 10 APIs,
│                           .env, a live model call, and it starts the Cloud SQL
│                           instance in the background because step 10 needs it
├── set_env.sh              project, model, VENUE_URL — source it per terminal
├── use-solution.sh         load a step's code, and reset the state around it
├── requirements.txt
├── Dockerfile              the venue image
├── .env.example
│
├── venue/                  the mock ticket seller — ONE file
│   ├── app.py              the whole thing, MODULE tags to search for
│   ├── smoke_test.py       17 checks, one per workshop beat
│   └── static/panel.html   TICKET MONSTER — the control panel you press
│
├── monstertix/             step 3 — the whole front end of the system
│   ├── server.py           THE TRIGGER — builds a Runner, an app, and wires the
│   │                       routes below. Serves index.html at /
│   ├── handlers.py         what those routes DO. No app, no Runner — everything
│   │                       passed in, so step 10 reuses it against Cloud SQL
│   ├── clock.py            THE TRIGGERER — time + httpx, no ADK at all
│   └── index.html          MONSTERTIX — one page, no build step, no ADK. It
│                           posts to /wake and renders what comes back
│
├── agent/                  students work here — adk web agent
│   ├── concert/            the agent package
│   ├── nightly/            step 8 on — the graph, served as its own app
│   └── server.py           step 10 only — the deployable surface
│
├── solutions/              complete working code at every step
│   ├── step1_bootstrap/       → step 1
│   ├── step2_asleep/          → step 2
│   ├── step3_the_trigger/     → step 3   monstertix/, NOT agent code
│   ├── step4_open_the_box/    → step 4
│   ├── step5_compaction/      → step 5
│   ├── step6_pull_the_plug/   → step 6
│   ├── step7_old_news/        → step 7
│   ├── step8_the_workflow/    → step 8   (+ nightly.py, nightly/)
│   ├── step9_the_budget/      → step 9
│   └── step10_deploy/         → step 10  (+ server.py)
│       └── README.md         each has one
│
├── tests/                  one folder per solution, mirroring it
│   ├── run.sh              ./tests/run.sh [--live]
│   ├── harness.py          load_step(), the venue as an object, drive()
│   └── stepN_*/            does this step still do what the codelab says?
│
├── seed/
│   ├── session.py          builds the two-day-old session step 4 opens
│   └── memory/             starting memory, per step, with a default
│
├── memory/userx.md         edit it, the agent changes next turn
├── artifacts/              seat maps the agent saved. Emptied between steps
├── deploy-venue.sh         your own venue on Cloud Run, URL written to .env
├── destroy-venue.sh
├── setup-cloud-state.sh    step 10 — Cloud SQL database, user, and a bucket
├── deploy-agent.sh         step 10 — Cloud Run + Pub/Sub + Cloud Scheduler
├── destroy-agent.sh        (--all also removes the database and the bucket)
├── show-compaction.sh      reads the compaction the dev UI will not show you
└── docs/
    ├── CODELAB.md          the instructions, Google Codelab format
    ├── build-preview.py    renders CODELAB.md → preview.html. Run it after edits
    ├── HANDBOOK.md         one-page reference to keep open beside it
    ├── DRYRUN.md           rehearsal checklist, per step
    ├── INSTRUCTOR.md       runbook: timing, what breaks, what to cut
    └── preview.html        rendered preview, generated
```

### How a step gets loaded

`use-solution.sh N` copies a solution folder into place, and where things land
depends on what they are:

| In the solution folder | Goes to | Why |
|---|---|---|
| `concert/`, `nightly/` | `agent/` | agent code, which is what `adk web` serves |
| `server.py` | `agent/server.py` | it deploys with the agent |
| **anything else** | the repo root, overwriting | a step's material is not always agent code |

That last row is how step 3 works: it ships `monstertix/`, which lands at the
root, and `agent/` is not touched at all — because nothing about the agent
changes in that step, which is the point of it.

A step made only of root-level files also skips the state reset, since there is
no agent state involved.

### Three ports

| | |
|---|---|
| **:8000** | `adk web` — the development UI. Best window into a run, not something you ship |
| **:8080** | the venue. Control panel at `/panel` |
| **:8090** | `monstertix/server.py` — MonsterTix at `/`, the endpoint at `/wake` |

Tests use **:8099** with their own database, so a test run can never reset the
venue you are teaching from.

`solutions/` matters more than it looks. Anyone stuck runs
`./use-solution.sh 5` and rejoins the group. Without it, one
typo costs a student the rest of the workshop.


### Memory as a file

A memory service is exactly two methods:

```python
await memory_service.add_session_to_memory(session)
results = await memory_service.search_memory(app_name, user_id, query)
```

**What actually shipped is simpler: memory is two tools over a Markdown file.**

A custom `BaseMemoryService` can't be handed to `adk web`, which constructs its
own Runner and only accepts a `--memory_service_uri`. Rather than fight that,
`concert/memory.py` exposes `recall()` and `remember()` as ordinary tools:

```python
def recall() -> dict:
    """Read everything learned about this person from previous bookings."""
    return {"memory": (MEMORY_DIR / f"{MEMORY_USER}.md").read_text()}

def remember(fact: str) -> dict:
    """Record a durable fact worth keeping after this conversation ends."""
    ...
```

This is better for the room, not just easier. The agent visibly *reads a file*,
and a student can open that file mid-workshop, delete one line, and watch
behaviour change on the very next turn. `PreloadMemoryTool` and Memory Bank stay
in the closing swap table as the productionised path.

`memory/userx.md`:

```markdown
# Memory — userx

## Preferences
- Sam bails on weeknights          (learned 2026-03-14, booking #2)
- Hates upper deck at Ziggo Dome   (learned 2026-01-08, booking #1)
- Comfortable spend: ~$200/ticket

## Past bookings
- 2026-01-08 · Ziggo Dome · upper deck · $140 · "couldn't see a thing"
- 2026-03-14 · Paradiso   · GA         · $65  · Sam cancelled, Tuesday
- 2026-05-02 · AFAS Live  · lower bowl · $185 · good
```

**The demo Memory Bank cannot give you:** students open the file, edit one
line, and the agent changes behavior on the next turn. Delete *"Sam bails on
weeknights"* and watch it book Tuesday. `PreloadMemoryTool` re-injects every
turn, so feedback is immediate — no restart, no redeploy.

Memory Bank appears once, in the closing swap table, honestly framed: at three
bookings, returning the whole file is correct; at ten thousand you need real
retrieval, consolidation, and contradiction handling. That requires an Agent
Engine resource, which is why it's the one component that doesn't run on a
laptop.

---

## Setup

### Student

```bash
git clone <REPO_URL> && cd longrunningag
./setup.sh                    # asks for a project id, once
source .venv/bin/activate
./deploy-venue.sh             # ~3 min
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"
```

`setup.sh` prompts for the project id, validates it with `gcloud projects
describe`, remembers it in `~/project_id.txt` (which survives Cloud Shell
timeouts and a re-clone), runs `gcloud auth application-default login` if
needed, sets the quota project, enables nine APIs, writes `.env`, and makes one
real `generate_content` call so a bad project or model id fails here rather than
mid-lab.

Re-running it is safe.

### Credentials

Vertex AI via Application Default Credentials. **No API keys anywhere** — not in
`.env`, not in the repo, not on a slide.

```bash
GOOGLE_CLOUD_PROJECT=<theirs>
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=true
ADK_MODEL=gemini-2.5-flash
```

> ⚠️ `gemini-flash-latest` is an AI-Studio-only alias and **404s on Vertex**.
> Verified against a real project: the `-latest` aliases are simply absent from
> `models.list()`. Pin the id.

### APIs enabled

`aiplatform` · `run` · `cloudbuild` · `artifactregistry` · `storage` ·
`pubsub` · `cloudscheduler` · `cloudtrace` · `logging`

### Requirements

- `google-adk >= 2.6.2`
- Python **3.11+** — ADK 2's `Workflow` API requires it
- Cloud Shell, or any machine with `git`, `gcloud` and Python


## Laptop → cloud swap table

Shown in the last step as **the diff**. Deploy both `App` definitions side by
side.

| In the workshop | In production | What changes |
|---|---|---|
| `--session_service_uri=sqlite+aiosqlite:///…` | Cloud SQL | a connection string |
| `--artifact_service_uri=file://…` | `gs://bucket` | a URI |
| `memory/*.md` | `gs://bucket/memory/` | a path |
| ⤷ *at real scale* | `VertexAiMemoryBankService` | one constructor + an Agent Engine resource |
| `adk web agent` | `adk deploy cloud_run` | one command |
| `monstertix/clock.py` on your laptop | Cloud Scheduler → Pub/Sub | `trigger_sources=["pubsub"]` |

```
       root_agent, tools, callbacks, budget:  UNCHANGED
```

Credentials do not appear in that table, because they never change: ADC on the
laptop, ADC on Cloud Run. That is the argument for not using API keys, and it
only lands because students never had one.


## Instructor checklist

Students deploy their own venue, so there is very little left to do.

Night before:

```
[ ] publish the repo (public, no auth)
[ ] confirm every student can reach a project with billing attached
    — setup.sh enables 9 APIs, which needs billing
[ ] Module 6 only: adk deploy cloud_run (concert-agent, trigger_sources)
[ ] Module 6 only: Pub/Sub topic + push subscription → /apps/concert/trigger/pubsub
[ ] Module 6 only: Cloud Scheduler job → topic
[ ] RUN MODULE 6 FOR REAL AT 3AM so Cloud Trace has an ingested trace with a
    genuine 40-minute gap to show
[ ] run ./setup.sh yourself from a clean clone, on the project students will use
```

The last one is the one that catches things. A project without billing, or
without permission to enable APIs, fails in a way no amount of good error
messages can fix at 9am.

### Build order

1. **Venue + control panel** — nothing is demoable until this misbehaves on cue
2. **Seed data** — the pre-loaded session drives step 3
3. **Agent through step 7** — all local, no deploys
4. **Module 6 path** — Cloud Run, Pub/Sub, Scheduler
5. **Solutions + handbook** — last, once the code has stopped moving

### Known risks

| Risk | Mitigation |
|---|---|
| 30 × `gcloud run deploy` at once | Cloud Build quota. Stagger it, or pre-deploy |
| Project has no billing | setup.sh names it explicitly; check the night before |
| Cloud Shell idles out after ~1hr | `sessions.db` is in `$HOME` and survives. If it happens mid-workshop it is step 5, free |
| Venue costs money after the workshop | It scales to zero, so idle cost is nil. The delete command is in both docs anyway |
| A student's typo breaks their agent | `cp -r solutions/stepN_*/concert agent/` |
| Trace ingestion lag | Show last night's trace, never a live one |
| Quiet room during a pause | The control panel banner and ticking queue |


## Design decisions

**Why the concert booker.** Earlier candidates: an expense approver (no
consequential action), a sourdough coach (the agent cannot act — its only
actuator is a notification), a CI/release bot (too hardcore for a workshop), a
trip booker (too common). The concert booker is the only one where the agent
must act *while the human is unavailable*, which is what forces the
agreed-budget pattern.

**Why each student deploys their own venue.** A shared one means the moment
somebody presses **SELL THE GOOD SEATS**, everyone else's agent fails for no
visible reason. Half this workshop is deliberately breaking things, so isolation
is not optional. It also gets `gcloud run deploy` in front of them early, so the
final step's deploy is familiar.

**Why the agent stays local.** Students edit it at every step. Seven deploys
would cost twenty minutes of a two-hour workshop.

**Why a poller rather than a webhook.** A Cloud Run venue cannot reach a laptop,
so a callback cannot work. But the poller is the better design anyway — in
production the thing that resumes paused work is a worker sweeping for ready
items, not the third party calling you back.

**Why Vertex and ADC rather than an API key.** It makes the last step's diff
honest: the credential model is identical on a laptop and on Cloud Run, so the
swap table has nothing to say about auth. A key would have made the workshop
easier to start and the punchline weaker.

**Why SQLite for sessions.** `sqlite3 sessions.db "select * from events"` puts
their session on screen as rows. Cloud SQL through a proxy never feels that
direct.

**Why Cloud Run and not Agent Runtime for Module 6.** Agent Runtime cannot
receive scheduled or event-driven triggers. This is not a preference.


## Verified library facts

Checked against `google-adk 2.6.2` (latest as of 2026-08-05).

**CLI** — `adk api_server` · `conformance` · `create` · `deploy` · `eval` ·
`eval_set` · `migrate` · `optimize` · `run` · `telemetry` · `test` · `web`

`adk deploy` targets: `agent_engine` · `cloud_run` · `gke`

**Triggers** require Cloud Run or GKE. Agent Runtime does not support
event-driven or scheduled triggers.

```python
from google.adk.cli.fast_api import get_fast_api_app

app = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    web=False,
    trigger_sources=["pubsub", "eventarc"],
)
# enables /apps/{app}/trigger/pubsub and /apps/{app}/trigger/eventarc
```

```bash
adk api_server --trigger_sources "pubsub,eventarc" path/to/agent
```

Trigger endpoints handle base64 decoding, CloudEvent parsing, per-event session
creation, a concurrency semaphore, and exponential backoff.

| Setting | Default | Env var |
|---|---|---|
| Max concurrent invocations | 10 | `ADK_TRIGGER_MAX_CONCURRENT` |
| Max retry attempts | 3 | `ADK_TRIGGER_MAX_RETRIES` |
| Base backoff delay | 1.0s | `ADK_TRIGGER_RETRY_BASE_DELAY` |
| Max backoff delay | 30.0s | `ADK_TRIGGER_RETRY_MAX_DELAY` |

**Trigger sessions default to `InMemorySessionService` and vanish.** Set
`DatabaseSessionService` explicitly.

**Pub/Sub and Eventarc cap processing at 10 minutes.** Scheduled execution
pattern: Cloud Scheduler → Pub/Sub topic → `/apps/{app}/trigger/pubsub`. No
custom scheduling code.

**Compaction** — `overlap_size` is required, and the interval counts
**user-initiated invocations, not events**. Both of those bit me:

```python
from google.adk.apps.app import App, EventsCompactionConfig, ResumabilityConfig

app = App(
    name="concert",
    root_agent=root_agent,
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,     # invocations; 3 so it fires during a lab
        overlap_size=1,            # REQUIRED, no default
    ),
    resumability_config=ResumabilityConfig(is_resumable=True),
)
```

`adk web` looks for a module-level `app` **before** `root_agent`, so exporting
an `App` is what makes compaction and plugins take effect.

**`ResumabilityConfig`** is the Module 4 primitive, and its own docstring states
the workshop's thesis:

> *"1. pause an invocation upon a long-running function call. 2. resume an
> invocation from the last event, if it's paused or failed midway through.
> Note: ADK resumes in a best-effort manner: 1. Tool call to resume needs to be
> idempotent because we only guarantee an at-least-once behavior once resumed.
> 2. Any temporary / in-memory state will be lost upon resumption."*

Point 1 is Module 4's second half. Point 2 is why `temp:seatmap` is a trap.

**ADK 2 orchestration:**

```python
from google.adk import Agent, Event, Runner, Workflow
from google.adk.workflow import START, JoinNode, node

Agent(mode="task", output_schema=Model)   # pauses; injects finish_task
Agent(mode="chat" | "single_turn")
Workflow(name=..., edges=[(START, some_function, some_agent)])
```

Function nodes and agent nodes are peers in the same `edges` list. A function
node returns `Event(output=...)` (or a bare value), and an agent node with
`input_schema=` receives it validated.

**Running it** — both URIs must be **absolute**. `file://./artifacts` is
rejected outright:

```bash
adk web agent \
  --session_service_uri="sqlite+aiosqlite:///$(pwd)/sessions.db" \
  --artifact_service_uri="file://$(pwd)/artifacts"
```

Point `adk web` at a directory containing exactly one agent package, or every
sibling directory shows up in the dropdown as an entry that errors when picked.

**Context caching:** `ContextCacheConfig(min_tokens=2048, ttl_seconds=1800,
cache_intervals=10)`

**Session rewind:** `await runner.rewind_async(rewind_before_invocation_id=…)`

**State prefixes:** `user:` (per user) · `app:` (per app) · `temp:` (not
persisted)

**Artifacts:** plain name = session-scoped · `user:` prefix = persists across
sessions. `save_artifact` / `load_artifact(name, version=…)` / `list_artifacts`

**Sessions:** `InMemorySessionService` · `DatabaseSessionService` ·
`VertexAiSessionService`

**Built-in plugins:** `ReflectAndRetryToolPlugin` ·
`BigQueryAgentAnalyticsPlugin` · `ContextFilterPlugin` ·
`GlobalInstructionPlugin` · `SaveFilesAsArtifactsPlugin` · `LoggingPlugin` ·
`DebugLoggingPlugin` · `MultimodalToolResultsPlugin`

**Docs index:** `curl https://adk.dev/llms.txt`

---

## ADK 2 decision — resolved

The workshop uses **both** ADK 2 orchestration styles, each where it actually
fits, rather than picking one:

| Where | What | Why there |
|---|---|---|
| Modules 1–4 | `Agent` + tools + callbacks | A conversation with a human in it. The model should choose. |
| Module 5 | `Agent(mode="task", output_schema=...)` | Talk until a decision is collected, then return a validated object. The run genuinely **pauses**. |
| Module 6 | `Workflow(edges=[...])` graph | 3am, no user. Draw the flow in advance; one model call, at the end. |

That contrast is the teaching. Same domain, same tools, same budget —
different control flow, because the situation is different.

`EventsCompactionConfig` and `ResumabilityConfig` both emit
`[EXPERIMENTAL]` warnings on 2.6.2. Say that out loud in the room rather than
letting thirty people discover it in their logs.

Python **3.11+** is required.

---

## Status

**Built and verified against `google-adk` 2.6.2 on a live Vertex project.**

| Piece | State |
|---|---|
| `venue/app.py` | One file. **22/22 smoke checks** pass locally and against Cloud Run |
| `venue/static/panel.html` | Status banner, act-tagged buttons, verified in a browser |
| `monstertix/` | Verified: fires on its own clock, agent runs with nobody typing |
| `seed/session.py` | Builds `two-days-ago`: 13 events, a real compaction record, verified readable through `adk web` |
| `solutions/step2..step9/` | All eight load. Pre-auth plan logic **9/9** unit checks. The `Workflow` graph constructs; `server.py` exposes `/apps/{app}/trigger/pubsub` |
| `setup.sh` | Project prompt, ADC sign-in, 9 APIs, live model call, seeds the session. Re-runnable |
| `deploy-venue.sh` + `Dockerfile` | Deployed for real; URL written to `.env` |
| `set_env.sh` | Sources `.env` + venv. Every process started by hand, so the changing `adk web` flags stay visible |
| `docs/` | `CODELAB.md` (11 sections) · `HANDBOOK.md` · `DRYRUN.md` · `INSTRUCTOR.md` |
| `deploy-agent.sh` / `destroy-agent.sh` | Module 6: Cloud Run + Pub/Sub + Scheduler, one service per student. Syntax-checked, **not yet run end to end** |
| `monstertix/` | Verified: fires on its own clock, agent runs with no `adk web` at all |

### The one thing standing between this and a teachable workshop

**Nobody has played the eleven steps against a live model.** Every check so far is
structural: modules import, endpoints answer, the venue misbehaves on cue, the
plan logic clears the right breaches. Not one prompt has been exercised.

Step 9 is the exposure. It leans entirely on instruction-following the tests
cannot see:

- keeping the ask to two branches, not reciting a decision tree
- distinguishing "yes, buy it" from "yes, raise my limit"
- re-reading the seat map after an approval that arrived hours late

Book an hour with a real key and play it end to end. Expect to tune prompts.

### Also outstanding

- `<REPO_URL>` is a placeholder — this is not a git repo yet, so nobody can
  clone it. That is the last thing between here and a workshop someone else
  could run.
- `deploy-agent.sh` is syntax-checked but has never been executed. Run it once
  before you rely on it.
- `solutions/step1_bootstrap/` appeared without being part of the design — step
  2's agent plus an unused `memory.py` and `panel.py`. Probably a stray copy.
