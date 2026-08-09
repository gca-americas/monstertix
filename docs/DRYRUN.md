# Dry run

Rehearse the whole lab locally before anyone else sees it. Everything runs on
your machine — no Cloud Run deploy, no waiting for builds — so you can restart a
step in seconds.

**What you are looking for is not "does it install".** It is: does each step do
the thing the codelab promises, in front of a live model, without you nudging
it? Every place it needs a nudge is a prompt that needs tuning.

Keep a note open. Write down anything that surprises you.

---

## Set up the local rig

```bash
cd ~/longrunningag

rm -f venue.db sessions.db          # clean slate
python -m seed.session              # rebuild the step 3 session
./use-solution.sh 2
```

Then two terminals. Rehearse against a **local** venue so you can restart it
freely — `. ./set_env.sh local` does that for one terminal only and never edits
`.env`:

```bash
cd ~/longrunningag && . ./set_env.sh local     # in both terminals

python -m venue                    # terminal A — the venue you can break
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"       # terminal B — the agent
```

Two tabs: **localhost:8000** (agent) and **localhost:8080/panel** (control).

Students do not do this. They deploy the venue once and only ever run `adk web`.

To go back to the deployed venue, open a fresh terminal and use
`. ./set_env.sh` without `local`. `.env` still holds the Cloud Run URL, so there
is nothing to undo.

### Between steps

```bash
cd ~/longrunningag
./use-solution.sh N          # Ctrl-C the agent first. resets memory,
                             # sessions and artifacts. venue is untouched —
                             # press RESET THE VENUE for that
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"
```

Press **RESET THE VENUE** on the panel whenever inventory gets messy. Delete
`sessions.db` only if you want to lose the seeded session too — and re-run
`python -m seed.session` after.

---

## Step 2 · You cannot prompt your way to autonomy

**Load** `step2_asleep`

**Type**

> I want to see The Midnight Signal. I'm in Amsterdam, going with Sam, budget around $200 each.

**Check**
- [ ] does it feel genuinely good? The step only works if the room is impressed
      before you pull the rug
- [ ] does it ever ask *which artist*? It should not — `search_events` takes no
      artist argument. If it asks, the docstring drifted
- [ ] panel shows 0 orders, all seats intact

**Then swap** `instruction=INSTRUCTION` for `instruction=PROACTIVE_INSTRUCTION`,
restart, and **do not type anything**.

- [ ] genuinely nothing happens, for as long as you are willing to wait
- [ ] does the explanation land? *"Monitor", "the moment it opens", "keep
      checking" all describe things happening over time. A system instruction
      is not a thing that happens over time.*

> This is the whole step. If people nod along at "the agent was never invoked"
> without having tried the prompt fix themselves, they will write that exact
> prompt in production next month. Make them fail at it here.
>
> Watch for the failure mode where the model *claims* it will monitor — "I'll
> keep an eye on that and let you know!" — which is worse than saying nothing,
> and worth pointing at when it happens.

## Step 3 · Give it a clock

**No code change** — same `step2_asleep`. Put `instruction=INSTRUCTION` back first.

**Stop `adk web` first** — step 3 proves the agent runs without it.

**Terminal 3:** `python -m monstertix.server`  ·  **Terminal 4:** `python -m monstertix.clock --in 60`, then **stop typing**.

**Check**
- [ ] does it actually fire a minute later with nobody at the keyboard?
- [ ] does the `Runner` code read as *"oh, that's all adk web was doing"*? That
      is the second point of the step and it is easy to rush past
- [ ] does the room understand that *you started it* but did not *invoke the
      agent* — the distinction the whole step rests on?
- [ ] read what the agent said. Is it visibly useless? Ours asked *"which show
      were we considering?"* at 3am, which is perfect. If it happens to answer
      well, the beat is weaker — try firing into a project with no prior chat
- [ ] does the "what went wrong" table land as a roadmap, or as a list of
      failures? It should feel like progress

> This is the new load-bearing step. It converts steps 4–9 from "six things to
> learn" into "six reasons you cannot trust it yet". If it lands flat, the rest
> of the workshop loses its motivation.

---

## Step 4 · Open the box

**Load** `step4_open_the_box`

**Type**

> Sam can't do weeknights, by the way.
> Show me the seat map for the Amsterdam Saturday show.

**Then** open the session `two-days-ago` and go find the five answers.

**Check**
- [ ] `user:prefs` visible in the State tab
- [ ] `temp:seatmap` is **absent** — not stale, not empty, missing entirely
- [ ] `seatmap_*.json` in Artifacts
- [ ] **is `two-days-ago` actually in the session dropdown?** `adk web` addresses
      everything as `userId=user` and has no user picker, so a session seeded
      under any other id exists but is invisible
- [ ] the seeded session shows 13 events and a compaction summary

> `temp:` is stripped before the event is persisted, so it never reaches the
> session store. Verified: state comes back as `user:budget`, `user:prefs`,
> `user:purchases_made` and nothing else — with no restart involved.
>
> Does the "where did it go" explanation land, or does absence just read as a
> bug? That is the question for this step.

---

## Step 5 · What the summary throws away

**Load** `step5_compaction`

**Type** four or more turns. Mention Sam's weeknights early, then talk about
other things — cities, prices, other friends.

**Then**

> Book us something.

**Should happen** — compaction fires after 3 invocations, and there is a real
chance it books **Tuesday**.

**Check**
- [ ] compaction summaries appear in the event stream
- [ ] does it actually lose Sam? *This is the one beat that may not reproduce.*
- [ ] after the fix (`user:prefs`), does it hold Sam across compaction?
- [ ] `budget_split` runs without the group chat in its prompt

> If it never loses Sam, the demo has no teeth. Options: raise the turn count,
> drop `compaction_interval` to 2, or make the early turns chattier. Note which
> you needed — the codelab has to say it.

---

## Step 6 · Pull the plug

**Load** `step6_pull_the_plug`

**Type**

> Get us two tickets to the Amsterdam Saturday show.

**Check**
- [ ] does it call `join_queue` **without being told to**?
- [ ] panel banner reads *"Agent is waiting in line — #13,xxx"*
- [ ] Ctrl-C the agent, start it again, ask where it is → still in line, same ticket
- [ ] `sqlite3 sessions.db "select name from pragma_table_info('events');"` — there
      is no `author` column, it is inside `event_data`
- [ ] the ticket is on disk:
      `sqlite3 sessions.db "select event_data from events;" | grep -o '"ticket": "q_[a-z0-9]*"' | tail -1`
- [ ] press **SKIP THE WAIT**, then ask the agent again → it sees the front

> The point of this step is the restart, not the asking. If the ticket survives
> a kill, it works.

---

## Step 7 · Acting on old news

**Load** `step7_old_news`

**Stale half** — queue up, press **SELL THE GOOD SEATS** mid-wait, **SKIP THE
WAIT**, then tell it to buy section A.

- [ ] does it try, and get `stale_plan` back?
- [ ] does it re-read the seat map and pick again *on its own*?
- [ ] does it explain what changed, rather than silently switching?

**Double-buy half** — **RESET**, then **BREAK THE NEXT PURCHASE**, then buy.

- [ ] order count goes to **2**, banner turns red
- [ ] with the idempotency key in place, a second attempt stays at **1**

> The retry here comes from your own client, not the ADK trigger runtime — that
> only retries on the Pub/Sub path in step 9. Worth knowing so you describe it
> accurately in the room.

---

## Step 8 · Draw the flow in advance

**Load** `step8_the_workflow`:

```bash
cd ~/longrunningag
./use-solution.sh 8
```

Restart `adk web`. The dropdown still says `concert`, but `root_agent` is now
the graph — send anything to start it.

Then headless too: `cd ~/longrunningag/agent && python -m concert.nightly`

**Check**
- [ ] `pick_show` picks a Saturday, inside `MAX_PRICE_PER_SEAT`
- [ ] does it skip the upper bowl because of the memory file?
- [ ] `queue_up` stops at #14,203 — press **SKIP THE WAIT**
- [ ] four events, one per node — does the graph read clearly in the UI?
- [ ] the `report` message reads like something a person wants at breakfast, in
      **dollars**, not a status dump
- [ ] run it again: does the idempotency key stop a second order?

Then edit `memory/userx.md`, delete the *"Sam bails on weeknights"* line,
and run again.

- [ ] does behaviour change? That is the memory demo, and it is worth a slide.

---

## Step 9 · Agree a budget, then hold the line

**Load** `step9_the_budget`

**Type**

> Book me two tickets for the Amsterdam show.

- [ ] does it call `recall` and then **ask for a budget**? *(most likely failure:
      it queues without asking, or invents a number from past bookings)*
- [ ] does it queue **before** you give it one? *(it must not)*

**Answer** the way people do — `About a hundred for the cheap seats. Two-fifty if they're the good ones.`

- [ ] it reads the whole thing back and asks you to confirm *before* storing
- [ ] `set_budget` called only after your yes, with the full wording
- [ ] State tab shows `user:budget` — the confirmed **sentence**, not a number
- [ ] then, and only then, `join_queue`

**Add a condition** — `Yes, and I'd go to 300 if it's a Saturday.`

- [ ] does it re-confirm the fuller version? *(most likely failure: it stores the
      first version and drops the condition)*

**Buy** — press **SKIP THE WAIT**, then `You're at the front now — go ahead.`

- [ ] re-reads the seat map first
- [ ] the section it takes is inside what you agreed for that kind of seat
- [ ] does it take the upper bowl, which memory says they hate? *(worth asking
      it why — this is the honest cost of leaving the choice to a model)*
- [ ] venue panel: exactly one order

**The 3am half** — `cd agent && python -m concert.nightly`

- [ ] `[open]` prints the sentence you agreed, not a default
- [ ] a budget with a Saturday condition makes it pick a dearer section

---

## Step 10 · The 3am run

**Load** `step10_deploy` — concert + `server.py`.

```bash
cd ~/longrunningag
./use-solution.sh 10
./deploy-agent.sh            # 3-4 minutes
```

**Check**
- [ ] `adk deploy cloud_run` finishes and prints a URL
- [ ] the push subscription points at `/apps/concert/trigger/pubsub`
- [ ] the Scheduler job exists

Fire it: `gcloud scheduler jobs run presale-<you> --location=us-central1`

- [ ] press **SKIP THE WAIT** when a queue ticket appears on the panel
- [ ] venue panel shows an order **nobody typed for**
- [ ] `gcloud run services logs read …` shows the four node lines
- [ ] Cloud Trace shows the queue wait as a gap in the middle

Then `./destroy-agent.sh` and check it all goes.

---

## After the run

Three questions worth answering honestly:

1. **Which steps needed a nudge?** Anywhere you had to say "no, check the seat
   map first" is a prompt to fix, not a student mistake to warn about.
2. **Which beat failed to reproduce?** Step 4 losing Sam, and step 9's agent
   queueing before it has asked for a budget, are the two that can
   silently not happen.
3. **Where did you get bored?** If you were bored rehearsing it, thirty people
   will be worse.

Nothing to put back. `. ./set_env.sh local` only affected the terminals you
typed it in, and `.env` still points at Cloud Run.
