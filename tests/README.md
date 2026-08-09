# Step tests

One folder per solution, mirroring `solutions/`. Every test answers the same
question: **does this step still do what the codelab says it does?**

Not "does the code import" — that is table stakes. These check that if a student
types what the instructions tell them to type, they see what the instructions
show them.

## Run them

```bash
cd ~/longrunningag
./tests/run.sh
```

That is the whole thing. It sources `set_env.sh`, starts a scratch venue on
**:8099** if one is not already there, and runs the fast suite. Takes about a
second.

```
36 passed, 10 skipped in 1.01s
```

The 10 skipped are the live tests. To run those too:

```bash
./tests/run.sh --live
```

Several minutes, and it spends tokens — every one of them drives the real agent
against the real model.

### One step at a time

```bash
./tests/run.sh tests/step9_the_budget
./tests/run.sh --live tests/step9_the_budget
```

Everything except `--live` is passed straight to `pytest`, so `-k`, `-x` and
`-v` all work. If you pass only flags, `tests/` is added for you:

```bash
./tests/run.sh -k budget -v
./tests/run.sh -x                    # stop at the first failure
./tests/run.sh --live -k "new_session"
```

### Without the runner

```bash
. ./set_env.sh
VENUE_DB=/tmp/test-venue.db VENUE_PORT=8099 python -m venue &
VENUE_URL=http://127.0.0.1:8099 pytest tests/ -q
```

## Why :8099 and not :8080

So a test run can never touch the venue you are teaching from. The tests press
**RESET THE VENUE** constantly — between individual assertions — and doing that
to a venue somebody is demonstrating against wipes their queue ticket mid-run.
That has happened; it is why the port is different.

Tests that need the venue skip themselves with a readable message if nothing is
listening, rather than failing with a connection error.

## The two kinds

| | What it checks | Cost |
|---|---|---|
| **structural** | the wiring the step depends on — `join_queue` really is a `LongRunningFunctionTool`, compaction has both required fields, `queue_up` really has `rerun_on_resume=False`, the budget really is session-scoped | milliseconds, no model |
| **behavioural** | drives the agent or the graph through the beats the codelab walks through, and checks the venue afterwards | a minute or more each, real tokens |

Behavioural tests carry `@needs_model` and are skipped unless
`WORKSHOP_TEST_LIVE=1` is set. That split is deliberate: the fast suite is meant
to be usable as a pre-flight check before a run-through, so it has to stay fast
enough that you actually run it.

## What each step asserts

| Step | The claim being held in place |
|---|---|
| 1 bootstrap | two read-only tools, and no way to buy or wait |
| 2 asleep | it *can* buy now, and still does nothing, because nothing calls it — and nothing in it knows what time it is |
| 4 open the box | a real `BaseMemoryService`, `recall` is `async`, and `get_seatmap` writes both `temp:` state and an artifact |
| 5 compaction | compaction is on with both fields, and `budget_split` has `include_contents="none"` |
| 6 pull the plug | `join_queue` is long-running, the app is resumable |
| 7 old news | a `before_tool_callback` guards only `purchase`; the idempotency key deduplicates **and** its absence really does buy twice |
| 8 the workflow | root is the graph, the agent is imported not rebuilt, `queue_up` does not re-run, `check_front` does |
| 9 the budget | the budget node runs first with stable interrupt ids, the budget is session-scoped, `UNATTENDED` exists, and `buyer_agent` never asks for a budget |
| 10 deploy | local only — see below |

## What is deliberately not tested

**Step 10's cloud path.** Creating a Cloud SQL instance takes ten minutes and
costs money, so `setup-cloud-state.sh` and `deploy-agent.sh` are verified by
hand — see `docs/DRYRUN.md`. There is an explicit skipped test saying so, rather
than a silent gap.

What `tests/step10_deploy/` *does* check is everything that must be true before
you deploy: `server.py` mounts a Pub/Sub trigger endpoint, `UNATTENDED` is
honoured, `asyncpg` is declared in `requirements.txt`, the three shell scripts
are valid, and `deploy-agent.sh` warns loudly when the session store is sqlite
in `/tmp`.

## Current status

The fast suite passes: **36 passed, 10 skipped**.

The 10 live tests are **written but have never been run as a suite**. Most of
them encode runs done by hand while building the steps, so they are expected to
pass — the two worth watching the first time are
`step8/test_waking_it_does_not_take_a_second_ticket` and
`step9/test_a_new_session_asks_again`, neither of which has been executed in
exactly this form.

## Adding one

Assert against **behaviour the instructions promise**, not implementation.
`test_join_queue_is_long_running` earns its place because the codelab claims the
run parks. A test that `tools.py` contains nine functions does not.

The helpers are in `harness.py`:

```python
from harness import drive, load_step, needs_model, tool_names

m = load_step("step6_pull_the_plug")     # imports that step's `concert` package
t = drive(m.root_agent, ["Get us two tickets to the Amsterdam show."])
assert t.called("join_queue")
assert venue.tickets == 1                # `venue` is a fixture
```

`load_step` clears any previously imported `concert` first — every step ships a
package with the same name, and without that, step 7's test quietly asserts
against step 6's code and passes for the wrong reason.

`drive` answers interrupts for you. Pass `on_interrupt=lambda msg, t: ...` to
decide what to reply, or return `None` to leave the run parked and assert on
that.
