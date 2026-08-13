# Instructor runbook

Everything you need that students don't. Read
[`CODELAB.md`](CODELAB.md) for what they see, [`DRYRUN.md`](DRYRUN.md) for
rehearsing it.

---

## The thesis, in one line

Every framework got better at what goes in the prompt. None got better at being
awake.

If you only land one thing, land Module 2: **waking up was never the hard part.**
An agent that wakes with no memory, no durability and nobody listening is not
yet worth waking, and Modules 3 to 5 are the reasons why.

---

## Two weeks before

| | |
|---|---|
| **Confirm a project with billing** | `setup.sh` enables 9 APIs. That fails without billing, and no error message fixes it at 9am |
| **Confirm students can enable APIs on it** | needs `serviceusage.services.enable`. If they can't, enable all 9 yourself beforehand and delete that block from `setup.sh` |
| **Run `./setup.sh` yourself from a clean clone**, on the project students will use | this is the check that catches things |
| **Decide: shared project or one each?** | one each is cleaner; shared is fine if quota holds — see below |

### Cloud Build quota

Thirty simultaneous `./deploy-venue.sh` runs is thirty Cloud Build jobs in one
project. Default concurrency will queue them, and a three-minute deploy becomes
fifteen.

Options, in order of preference:

1. **Stagger it.** The deploy is in Module 1; tell half the room to start it while the
   other half reads. Nobody is blocked — the venue is not needed until Module 1 ends.
2. **Pre-deploy** one venue per student the night before and hand out URLs. Costs
   you an hour, removes the risk entirely.
3. **Run the venue locally.** Set `VENUE_URL=http://127.0.0.1:8080` and skip the
   deploy. You lose the "you deployed something to Cloud Run" moment, and step
   10's diff gets weaker, but everything else works.

---

## The night before

```
[ ] publish the repo, public, no auth
[ ] ./setup.sh from a clean clone on the students' project
[ ] deploy the step 10 path: ./deploy-agent.sh, Pub/Sub topic + push
    subscription → /trigger/wake, Cloud Scheduler job
[ ] RUN STEP 10 FOR REAL AT 3AM so Cloud Trace has an ingested trace with a
    genuine forty-minute gap in it
[ ] rehearse M3 and M5 at least — see "what actually breaks"
[ ] charge a jar of sourdough discard for the coda, if you're doing it
```

The 3am run matters. Trace ingestion lags by minutes, so a live-triggered run
shows an empty page in front of the room. Last night's trace is there instantly
and has a real gap in it.

---

## Timing

120 minutes, six modules. The full breakdown is in
[`AGENDA.md`](AGENDA.md) — this is the version you glance at while teaching.

| | Module | Ends | Cut? |
|---|---|---|---|
| **M1** | Fallacy of Autonomous Prompts & Local Setup | 00:15 | no — setup failures cost more later |
| **M2** | Event-Driven Triggers & Persistence Mechanics | 00:35 | **never.** Everything after depends on it |
| **M3** | Managing Context Lifetime & Preventing Information Loss | 00:55 | trim the artifact walkthrough, −4 min |
| **M4** | Process Failure, Idempotency & Re-verification | 01:15 | drop the double-purchase half, −5 min |
| **M5** | Autonomous Governance, Dynamic Pre-Auth & Envelopes | 01:40 | drop the overnight approval, −10 min |
| **M6** | Unattended 3 AM Execution & Production Deployment | 02:00 | demo only, you drive |
| | Wrap | 02:00 | |

☕ Break at **00:35** if you want one. Setup is done, the payoff has not started.

**If you are running long**, cut in this order: the overnight approval in M5,
then the double-purchase half of M4, then the artifact walkthrough in M3. Each
stands alone.

**Do not cut Module 2.** Without watching the agent wake up badly, Modules 3 to
5 become a list of features with no motivation.

## What actually breaks

Ordered by how likely it is to happen to you.

**M3 · compaction may not lose Sam.** The beat depends on an LLM summary
dropping one constraint, and sometimes it keeps it. If it holds: more turns,
chattier early turns, or drop `compaction_interval` to 2. Rehearse this one.

**The fence only fires on `purchase`.** The agent joins the queue first, so
students must press SKIP THE WAIT and tell it it is at the front before anything
can be refused. Say this before they start or you will field it eight times.

**M5 · the two yeses may blur.** "Yes, buy it" versus "yes, raise my limit
to $300". If it sets `new_limit` when the human only approved one purchase,
that is the failure the step is about. Point at `user:budget` and show it
moved.

**Anywhere · the model claims it will monitor.** *"I'll keep an eye on that!"*
Worse than silence, and a gift if it happens in M1 — it is exactly the
illusion the step is dismantling.

**`two-days-ago` is missing from the dropdown.** `adk web` addresses every
session as `userId=user`, it is not configurable, and there is no user picker in
the UI. `seed/session.py` writes under that id for exactly this reason — if
someone sets `SEED_USER_ID`, the session will exist, answer over the API, and be
invisible in the dropdown. Re-run `python -m seed.session`.

**`asyncio.run() cannot be called from a running event loop`.** A tool called
something async without being `async` itself. ADK already has a loop running
when it invokes your tool, so `asyncio.run()` inside one always fails. Make the
tool `async def` and `await` instead.

**Cloud Shell idles out after ~1 hour.** `sessions.db` is in `$HOME` and
survives. Restarting is Module 4 happening for free; say that rather than
apologising.

**`address already in use`** — something is already on the agent's port. Kill by
port rather than by name: `lsof -ti:8000 | xargs kill -9`. If you are rehearsing
with a local venue, the same applies to `:8080`.

---

## Things worth saying out loud

**On ticket bots.** Someone will think it. Say it first: this runs against a
mock venue each student deploys themselves, buying one allotment for
themselves, inside limits they set. Real ticketing sites prohibit automation
and the band is invented.

**On `[EXPERIMENTAL]` warnings.** `EventsCompactionConfig` and
`ResumabilityConfig` are pre-GA in 2.6.2. Students will see the warnings. Say it
before they ask, and say that the APIs may move.

**On ChatGPT.** Someone will say "ChatGPT already does this." It does, and
better in places. It is also asleep at 10am. The aside in Module 1 has the full
answer — a chat session is a save file, what we are building is a server that
kept running.

**On cost.** The venue scales to zero, so an idle one costs nothing. Delete it anyway.
The clean-up command is in the handbook. Remind them at the end.

---

## The shape of the argument

Useful to have in your head, because students ask "why this order":

```
M1  an instruction cannot invoke anything       → something must call it
M2  so here is that something                   → it wakes, and it is useless
      ├ no idea who you are, reads a paraphrase → M3
      ├ nothing survives, acts on stale facts   → M4
      └ no limit on spending, some questions
        cannot wait                             → M5
M6  the same trigger, deployed                  → someone else's cron
```

Modules 3 to 5 each remove a reason not to leave the agent alone.

---

## Three surfaces, one agent

Students meet all three. Worth being able to place them instantly:

| | Where | What it is |
|---|---|---|
| `adk web` | Modules 1–5 | the dev UI. State, Events, Artifacts tabs |
| a bare `Runner` | Module 2 | ~6 lines. What `adk web` was hiding |
| `get_fast_api_app` | Module 6 | the same Runner behind an HTTP endpoint for Pub/Sub |

---
---

## Generating the code with an assistant

Nobody hand-writes most of this at work, and students will ask. Below is a
usable prompt per step, and — more useful — **what an assistant reliably gets
wrong about ADK**.

Every warning here cost a real debugging cycle while building this workshop.
They are worth reading before you teach it, because if a student generates their
own version rather than running `use-solution.sh`, this is where they will get
stuck and you will be asked why.


### Prompt your way to autonomy?

> Add a `purchase` tool to an ADK agent. It POSTs to `/purchase` on a service at
> `$VENUE_URL` with `{event_id, section, seats}` and returns the order or an
> error. Write the docstring so the model only calls it when it already knows all
> three, and never guesses on the user's behalf.

**Gets wrong:** Docstrings are the tool schema, so an assistant will happily invent parameters that sound plausible. We shipped a `search_events(artist=...)` for a venue that sells one artist, and the model dutifully asked *"which artist?"* instead of calling anything. **Read every generated docstring as if you were the model.**


### Event-Driven Dormancy

> Two files, and keep them separate.
>
> 1. `server.py` — a FastAPI app with one POST endpoint that runs an ADK agent
>    once via `Runner.run_async` and returns what it said. Import `root_agent`
>    from a sibling package. Use `InMemorySessionService` and open a new session
>    per request.
> 2. `clock.py` — a CLI that POSTs to that endpoint on a schedule. Flags `--in`,
>    `--every`, `--message`. It must not import ADK at all.

**Gets wrong:** Ask for them in one file and you will get one file, with the clock and the Runner tangled together. Naming the separation in the prompt is what keeps `clock.py` free of ADK — and that is the only reason you can delete it later and put Cloud Scheduler in its place.


### Managing Context Lifetime

> Implement `BaseMemoryService` from `google.adk.memory` backed by a Markdown
> file per user. `add_session_to_memory` appends the user's turns under a dated
> heading; `search_memory` returns the whole file as a single `MemoryEntry` in a
> `SearchMemoryResponse`. Then add two thin tools, `recall()` and `remember(fact)`,
> that call it.
>
> Also add a `note_companion(name, constraint)` tool that writes to
> `state["user:prefs"]`, and change `get_seatmap` to save the full map with
> `tool_context.save_artifact` and return only a summary.

**Gets wrong:** A tool that awaits anything has to be `async def` — assistants
write `asyncio.run()` inside a sync tool, which always raises inside ADK. Also:
ask for "memory" without naming `BaseMemoryService` and you will get a dictionary, or a vector database you did not want. **Name the interface.** Also check the state prefixes — assistants write `state["prefs"]` when you meant `state["user:prefs"]`, and the difference only shows up two steps later.


### Context Degradation?

> Wrap my ADK agent in an `App` with `EventsCompactionConfig` so older turns get
> summarised, and add a `budget_split` sub-agent that does ticket arithmetic with
> `include_contents="none"` and an `output_key`. Expose the `App` as a module-level
> `app` so `adk web` picks it up.

**Gets wrong:** `EventsCompactionConfig` requires **both** `compaction_interval` and `overlap_size` — there is no default for the second, and an assistant working from memory will omit it. `compaction_interval` also counts *invocations*, not events; ask for "every 20 events" and you will get something that never fires during a workshop.


### Process Resumption

> Make the queue-joining tool a `LongRunningFunctionTool` that returns
> immediately with a ticket, and turn on `ResumabilityConfig(is_resumable=True)`
> on the `App`. Then write a separate poller that asks the venue for tickets that
> have reached the front and POSTs the stored wake payload to the agent.

**Gets wrong:** Two things get fumbled. Assistants suggest `--session_service_uri=sqlite:///...`, which builds an engine that fails on the first write — ADK drives SQLAlchemy through its **asyncio** extension, so it must be `sqlite+aiosqlite://` with `aiosqlite` and `greenlet` installed. And they will write the poller as a loop *inside the agent*, which is the one arrangement that defeats the point.


### Acting on Stale Data

> Add a `before_tool_callback` that runs before any purchase: re-fetch live
> inventory, and short-circuit with an explanatory dict if the seats are gone or
> the price moved. Separately, send an `Idempotency-Key` header derived from
> session id, event, section and seat count so a retry of the same purchase is
> recognised.

**Gets wrong:** Ask for "retry safety" and you will get retry *logic* — backoff, a retry decorator, a circuit breaker. That is the opposite of what you want. The fix is to make the operation safe **to** repeat, not to repeat it more cleverly. Say "idempotency key" explicitly.


### Draw a fence around the money

> Add a spending budget in `user:` state — one number, max price per seat,
> excluded weekdays, allowed cities, max purchases — and check it in the existing
> `before_tool_callback`. When a purchase falls outside it, hand off to a
> sub-agent declared with `mode="task"` and an `output_schema`, so the run pauses
> until a human answers and the answer is validated.

**Gets wrong:** `mode="task"` is ADK 2 and pre-GA, so assistants trained on older material will reach for a loop that asks and waits, or a `while not approved` — both of which burn tokens and never actually pause. If the generated code has no `mode=`, it is not pausing.


### The approval that comes back tomorrow

> Before joining the queue, add a tool that reads live seat counts and queue
> depth and reports which sections are likely to be gone by the front — no
> guessing, only arithmetic on real numbers. Add a second tool that records the
> human's conditional answer as a plan in `user:` state. The purchase check should
> clear a breach only when the plan covers it **and** its condition currently
> holds.

**Gets wrong:** Assistants love to make the agent *predict*. Ask for "anticipate problems" and you will get an agent inventing the idea that prices might rise, with nothing behind it. Insist that every number comes from a tool call. Also watch the conditional: "$280 is fine if the cheap seats are gone" must verify the condition at purchase time, not at the time it was agreed.


### The 3am run

> Rewrite the unattended flow as an ADK 2 `Workflow`: function nodes for picking
> a show, queueing and buying, and a single agent node at the end that writes the
> message a human reads over breakfast. Then expose it for Pub/Sub with
> `get_fast_api_app(agents_dir=..., web=False, trigger_sources=["pubsub"])`.

**Gets wrong:** Assistants will offer to deploy this to Agent Engine. **It cannot work** — trigger endpoints exist only on Cloud Run and GKE. They will also leave the session service unset, and trigger sessions default to in-memory and vanish, so the 3am run forgets it was ever in a queue.


## Why it is built the way it is

The decisions below are not obvious from the code, and each one has a wrong
answer that looks reasonable. If somebody in the room asks "why not just…",
this is the section that answers them.

**Why the concert booker.** Earlier candidates: an expense approver (no
consequential action), a sourdough coach (the agent cannot act, its only actuator
is a notification), a CI bot (too hardcore), a trip booker (too common). The
concert booker is the only one where the agent must act *while the human is
unavailable*, which is what forces the agreed-budget pattern in step 9.

**Why each student deploys their own venue.** A shared one means the moment
somebody presses **SELL THE GOOD SEATS**, everyone else's agent fails for no
visible reason. Half this workshop is deliberately breaking things, so isolation
is not optional. It also gets `gcloud run deploy` in front of them in the first
ten minutes, so step 10 is not the first time they have seen it.

**Why the agent stays local until step 10.** Students edit it at every step. Nine
deploys would cost twenty minutes of a two-hour workshop.

**Why the weeknight shows are cheaper and listed first.** This is the trap the
whole memory lesson rests on, so do not let it pass unnoticed in step 1. Every
weeknight show is $10 a seat cheaper than the weekend one beside it, and it
appears first in the city. It is therefore what an agent reaches for on price
alone, or on order alone, and it is the wrong answer for somebody whose friend
never turns up on a weeknight. The only thing standing between the agent and that
mistake is a memory file it wrote after the last booking. If a student's agent
books a Tuesday, that is the lesson landing, not a bug.

**Why Vertex and ADC rather than an API key.** It makes step 10's diff honest:
the credential model is identical on a laptop and on Cloud Run, so the swap table
has nothing to say about auth. A key would make the workshop easier to start and
the punchline weaker.

**Why SQLite for sessions.** `sqlite3 sessions.db "select * from events"` puts a
session on screen as rows. Cloud SQL through a proxy never feels that direct.

**Why Cloud Run and not Agent Runtime for step 10.** Agent Runtime cannot receive
scheduled or event-driven triggers. This is not a preference, and it is worth
saying plainly if somebody asks why you did not use the managed option.

**Why `seed()` upserts rather than `INSERT OR IGNORE`.** Anyone who ran an
earlier version of this workshop has a `venue.db` holding the old dates and
prices. `INSERT OR IGNORE` would leave them there for ever, with no error and
nothing on screen to explain why their agent is reasoning about numbers nobody
else in the room can see. The upsert corrects the catalogue on startup and
deliberately leaves `sold` alone, so re-seeding never un-sells anything.

## If something is badly broken mid-workshop

```bash
# a student's agent is wrecked
./use-solution.sh N

# their venue is in a strange state
# → RESET THE VENUE on the panel

# their session history is confusing them
rm sessions.db && python -m seed.session

# nothing works and you have four minutes
./setup.sh          # safe to re-run, fixes auth/APIs/seed
```

The `solutions/` folders map one-to-one onto codelab step numbers. Anyone who
falls behind copies forward and rejoins.
