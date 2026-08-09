# Quick Reference

The one page to keep open beside the codelab. Full instructions live in
[`CODELAB.md`](CODELAB.md).

---

## The rig

```
   your machine                              Google Cloud
   ─────────────────────────────             ────────────────────────────
   adk web        :8000  ──────────────►  venue-you.run.app
                                            the fake ticket seller
   sessions.db   artifacts/                 + control panel
   memory/*.md
```

Two processes. The venue is deployed once and stays up; you run `adk web`
yourself, because the flags change between steps and those flags are the
material.

---

## Setup

```bash
git clone <REPO_URL> ~/longrunningag
cd ~/longrunningag
./setup.sh                      # asks for your project id, once
source .venv/bin/activate       # every new terminal tab
./deploy-venue.sh               # your own venue on Cloud Run, ~3 min
```

Then, each in its own terminal, after `cd ~/longrunningag && . ./set_env.sh`:

```bash
python -m venue            # only if you want a local venue instead of Cloud Run
python -m monstertix.server   # Module 2 only — your own endpoint + Runner
python -m monstertix.clock    # Module 2 only — the thing with the clock
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"   # every module from 3 on
```

`setup.sh` also builds the `two-days-ago` session that step 3 opens. Rebuild it
any time with `python -m seed.session`.

The memory file grows every run — `remember()` appends to it. `use-solution.sh`
restores it from `seed/memory/`, which also holds per-step starting files if a
step needs one. See `seed/memory/README.md`.

| File | Holds |
|---|---|
| `~/project_id.txt` | your project id — survives Cloud Shell timeouts |
| `.env` | project, model, `VENUE_URL` — written by the scripts |

Change project: `rm ~/project_id.txt && ./setup.sh`
Re-running `setup.sh` is always safe.

---

## Where a fact should live

The question behind the whole workshop.

| Home | Survives a restart? | Survives compaction? | Use for |
|---|---|---|---|
| conversation | yes | **no — summarised** | chat |
| `temp:` | **no** | n/a | snapshots that expire in seconds |
| session state | yes | yes | this booking |
| `user:` state | yes | yes | preferences, and the agreed budget |
| artifact | yes | never in the prompt | seat maps, confirmations |
| `memory/*.md` | outlives the app | yes | learned across bookings |

---

## Steps, and the code for each

Codelab steps map one-to-one onto `solutions/`:

| Step | Folder | The one thing it adds |
|---|---|---|
| 2 · You cannot prompt your way to autonomy | `step2_asleep` | a good agent that nothing ever calls |
| 3 · Give it a clock | *(same code)* | `python -m trigger` — the triggerer |
| 4 · Open the box | `step4_open_the_box` | memory file, artifacts, `temp:` vs `user:` |
| 5 · What the summary throws away | `step5_compaction` | `EventsCompactionConfig`, `include_contents="none"` |
| 6 · Pull the plug | `step6_pull_the_plug` | `LongRunningFunctionTool`, `ResumabilityConfig` |
| 7 · Acting on old news | `step7_old_news` | `before_tool_callback`, `Idempotency-Key` |
| 8 · Draw the flow in advance | `step8_the_workflow` | `Workflow` graph, four nodes, one model call |
| 9 · Agree a budget, then hold the line | `step9_the_budget` | `budget.py`, `set_budget`, the check in `before_tool_callback` |
| 10 · The 3am run | `step10_deploy` | `server.py`, `trigger_sources`, Cloud Run + Pub/Sub + Scheduler |

**Load a step's code:**

```bash
./use-solution.sh 6
```

**Rescue — you are never more than one command behind:**

```bash
./use-solution.sh N       # Ctrl-C adk web first — this rebuilds sessions.db
```

---

## The control panel

At your venue's `/panel`. The banner at the top always says what is going on.

| Button | What it does | For |
|---|---|---|
| **SKIP THE WAIT** | queue → front, now | step 6 |
| **SELL THE GOOD SEATS** | section A → 0, so a saved seat map is a lie | step 7 |
| **BREAK THE NEXT PURCHASE** | charges, then fails the reply; the retry buys again | step 7 |
| **FIRE THE PRESALE** | wakes the agent with no human present | step 10 |
| **RESET THE VENUE** | 8 shows, all seats, clock 1× | any time |

Clock is **1×** by default, so the queue barely moves and **SKIP THE WAIT** is
how you reach the front. Turn it up to 60× if you want the drain visible. The agent
cannot tell.

---

## ADK 2 you will actually type

```python
from google.adk.agents import Agent
from google.adk.apps.app import App, EventsCompactionConfig, ResumabilityConfig
from google.adk.tools import LongRunningFunctionTool
from google.adk import Workflow
from google.adk.workflow import START

Agent(include_contents="none")              # sub-agent reads no history
Agent(output_key="budget_plan")             # result to state, not transcript
Agent(mode="task", output_schema=Model)     # pauses; injects finish_task

App(
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,              # INVOCATIONS, not events
        overlap_size=1,                     # required, no default
    ),
    resumability_config=ResumabilityConfig(is_resumable=True),
)

Workflow(edges=[(START, fn_node, agent_node)])
runner.rewind_async(rewind_before_invocation_id=...)
```

`adk web` looks for a module-level `app` **before** `root_agent`, so the `App`
is what actually runs.

---

## Commands worth remembering

```bash
# what is in my session, really  (from ~/longrunningag)
sqlite3 sessions.db "select json_extract(event_data,'\$.author') as who,
       substr(json_extract(event_data,'\$.content.parts[0].text'),1,52) as said
       from events order by timestamp limit 10;"

# is the venue alive
curl $VENUE_URL/health

# what does my project actually offer
python -c "from google import genai; \
  [print(m.name) for m in genai.Client(vertexai=True, \
  project='$GOOGLE_CLOUD_PROJECT', location='global').models.list()]"

# does the venue still behave (22 checks)
python -m venue.smoke_test

# rebuild the pre-loaded session for step 3
python -m seed.session
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `adk: command not found` | `source .venv/bin/activate` — every new tab |
| `✗ Cannot access project` | wrong id: `rm ~/project_id.txt && ./setup.sh` |
| Model returns 404 | `-latest` aliases are AI Studio only. Use `gemini-2.5-flash` |
| Agent can't reach the venue | `curl $VENUE_URL/health`, then `./deploy-venue.sh` |
| Queue never advances | press **SKIP THE WAIT**. At 1× it will not advance on its own |
| Triggerer fires but nothing happens | is `adk web` up on :8000? it prints `agent unreachable` |
| `[EXPERIMENTAL]` warnings | expected — compaction and resumability are pre-GA in 2.6.2 |
| `address already in use` | `lsof -ti:8080 \| xargs kill -9` (`pkill` misses it) |
| Everything is strange | **RESET THE VENUE**, then `rm sessions.db` |
| Cloud Shell timed out | start the three processes again — `sessions.db` survived, which is step 6 for free |

---

## When you are done

The venue stays deployed and scales to zero. Delete it:

```bash
gcloud run services delete venue-$(gcloud config get-value account | cut -d@ -f1) \
  --region us-central1
```

Everything else is local and yours to keep.
