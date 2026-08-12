# Everything You Need to Build Long-Running Agents on Google Cloud

A 2-hour hands-on workshop on **long-running agents**, built with
[ADK 2](https://adk.dev) and Google Cloud.

Students build an agent that buys concert tickets while they are asleep: it joins
a queue of fourteen thousand people, stops running entirely for forty minutes,
survives having its process killed, re-checks the world before it spends money,
agrees a budget with a human, and finally ships to Cloud Run with a scheduler
waking it at 3am.

**The instructions live in [`docs/CODELAB.md`](docs/CODELAB.md).** Everything
below is for whoever is running or maintaining the workshop.

---

## The problem it teaches

Every framework got better at what goes **in the prompt**. None of them got
better at **being awake**.

A long-running agent needs four things a chat assistant does not:

1. **A clock of its own** — it starts without you
2. **Facts that outlive the conversation** — and survive a summariser
3. **Survival across process death** — crashes, deploys, closed laptops
4. **Bounded authority** — a limit agreed while the human was still there

The workshop teaches those four, in that order, against one scenario: a task that
takes far longer than the conversation that started it, against a system you do
not control.

---

## The eleven steps

Each one adds a single idea, and each has complete working code in `solutions/`.

| # | Step | What it adds |
|---|---|---|
| 1 | Before you begin | setup, the venue, the seeded history |
| 2 | Prompt your way to autonomy? | why no wording makes an agent proactive |
| 3 | Event-Driven Dormancy | a trigger endpoint, and something that calls it |
| 4 | Managing Context Lifetime | four places a fact can live: `temp:`, session, `user:`, a file |
| 5 | Context Degradation? | compaction rewrites history behind your back |
| 6 | Process Resumption | `LongRunningFunctionTool` + `ResumabilityConfig` |
| 7 | Acting on Stale Data | `before_tool_callback`, and idempotency keys |
| 8 | Autonomous Workflow | `Workflow` graphs, and `RequestInput` interrupts |
| 9 | Working With a Human | human-in-the-loop inside a graph |
| 10 | The Cloud Stack | one Cloud Run service, Cloud SQL, Cloud Storage, Pub/Sub, Scheduler |
| 11 | What you built | the concept map, and a prompt for building your own |

---

## Repo layout

```
setup.sh                 one command: venv, auth, APIs, .env, seed, Cloud SQL, venue
verify.sh                eight ticks. run it before you trust anything
use-solution.sh N        load step N's code and reset the world around it
deploy-venue.sh          your own venue on Cloud Run
deploy-agent.sh          the agent, the topic, the subscription, the schedule
destroy-venue.sh         tear the venue down
destroy-agent.sh         tear the agent down  (--all also drops Cloud SQL + bucket)
setup-cloud-state.sh     database, user, bucket, and the two URIs, written to .env
set_env.sh               source this in every new terminal
show-compaction.sh       reads the compaction the dev UI will not show you

agent/                   where students work. use-solution.sh writes here
  concert/               the agent package
  nightly/               the workflow graph, from step 8
  monstertix/            the chat page and its server, from step 10
  main.py, Dockerfile    the single-container entrypoint, step 10 only

venue/                   the mock ticket seller. its own Cloud Run service
  app.py                 queue, seatmap, purchase, and every admin button
  static/                the control panel, the poster, the theme tune

monstertix/              the chat frontend and the trigger, from step 3
  server.py              your own Runner behind your own endpoint
  clock.py               the local stand-in for Cloud Scheduler
  handlers.py            what the endpoints DO, shared by both entrypoints
  index.html             the page students actually hand to someone

solutions/               one folder per step. use-solution.sh copies from here
tests/                   one folder per step, mirroring solutions/
seed/                    the two-days-ago conversation, and the memory file
docs/
  CODELAB.md             the workshop itself
  build-preview.py       renders CODELAB.md → preview.html. run after edits
  DRYRUN.md              rehearsal checklist, per step
  INSTRUCTOR.md          runbook: timing, what breaks, what to cut
```

### How a step gets loaded

`use-solution.sh N` copies a solution folder into place, and where things land
depends on what they are:

| In the solution folder | Goes to | Why |
|---|---|---|
| `concert/`, `nightly/` | `agent/` | they are agent packages, and `adk web` reads that directory |
| everything else | the repo root | `monstertix/` is a sibling of `agent/`, not an app inside it |

It also resets the state around the code: `memory/userx.md` back to its seed,
`sessions.db` rebuilt with the two-days-ago conversation, `artifacts/` emptied.
Pass `--keep` for the code alone.

**One exception worth knowing.** `solutions/step3_the_trigger/` contains only
`monstertix/` — step 3 changes nothing about the agent, which is the point of it.
So `use-solution.sh 3` leaves whatever agent was staged before. Going 2 → 3 in
order is correct; jumping to 3 from a later step leaves the wrong agent in place.

### Three ports

| | |
|---|---|
| **:8000** | `adk web` — the development UI. Best window into a run, not something you ship |
| **:8080** | the venue. Control panel at `/panel` |
| **:8090** | `monstertix/server.py` — the page at `/`, the endpoint at `/wake` |

Tests use **:8099** with their own database, so a test run can never reset the
venue you are teaching from.

---

## Setup

```bash
git clone <REPO_URL> ~/longrunningag
cd ~/longrunningag
./setup.sh          # asks for a project id, once
./verify.sh         # eight ticks
```

`setup.sh` creates the virtualenv, signs in if needed, points `gcloud` at the
project, enables ten APIs, writes `.env`, makes one real Gemini call so a bad
model id fails immediately, seeds the two-days-ago session, starts a Cloud SQL
instance **in the background** for step 10, and deploys the venue.

**Every step of it is safe to re-run.** It reuses an existing `.venv`, remembers
the project id in `~/project_id.txt`, skips APIs that are already on, and will
not create a second Cloud SQL instance.

### Credentials

Vertex AI via Application Default Credentials. **No API keys anywhere** — not in
`.env`, not in the repo, not on a slide.

```
GOOGLE_CLOUD_PROJECT=<theirs>
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=true
ADK_MODEL=gemini-2.5-flash
```

> ⚠️ `gemini-flash-latest` is an AI-Studio-only alias and **404s on Vertex**.
> The `-latest` aliases are simply absent from `models.list()`. Pin the id.

### Requirements

- `google-adk >= 2.6.2`
- Python **3.11+** — ADK 2's `Workflow` API requires it
- Cloud Shell, or any machine with `git`, `gcloud` and Python

---

## Laptop → cloud

Step 10 shows this as the diff, and the point is how little is in it.

| On a laptop | In the cloud | What changes |
|---|---|---|
| `--session_service_uri=sqlite+aiosqlite:///…` | Cloud SQL | a connection string |
| `--artifact_service_uri=file://…` | `gs://bucket` | a URI |
| `memory/userx.md` | `gs://bucket/memory/` | a path |
| `adk web` | one Cloud Run service | a `Dockerfile` and a `main.py` |
| `monstertix/clock.py` | Cloud Scheduler → Pub/Sub | `trigger_sources=["pubsub"]` |
| you, at the keyboard | `someone_is_there()` | a default, overridden per request |

```
   root_agent, its tools, its callbacks and the budget:  UNCHANGED
```

`solutions/step10_deploy/concert/` is byte-for-byte the folder students finish
step 9 with. Credentials do not appear in that table because they never change:
ADC on the laptop, ADC on Cloud Run. That is the argument for not using API keys,
and it only lands because students never had one.

---

## Testing

```bash
./tests/run.sh
```

One folder per solution, mirroring `solutions/`. Tests that need a model are
skipped unless `RUN_LIVE=1`. Everything else is offline and runs in about a
second. Currently **38 passing, 10 skipped**.

---

## For instructors

- **[`docs/INSTRUCTOR.md`](docs/INSTRUCTOR.md)** — timing, what breaks, what to
  cut when you are running late, and what to say out loud
- **[`docs/DRYRUN.md`](docs/DRYRUN.md)** — rehearse the whole lab locally, step
  by step, before anyone else sees it
Run the dry run at least once on a fresh clone. Most of what goes wrong in a room
is state left over from the last rehearsal, and `use-solution.sh` exists to make
that recoverable in one command.
