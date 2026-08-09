---
id: long-running-agent-concert-tickets
summary: An agent that waits in a queue, survives being killed, and buys tickets at 3am inside limits you set. ADK 2 on Google Cloud.
categories: ai,agents,adk
tags: adk,agents,gemini,cloud-run,long-running
status: draft
authors: Workshop
duration: 120
---

# Everything You Need to Build Long-Running Agents on Google Cloud

## Before you begin

Buying concert tickets is a job made of waiting.

The presale opens at a fixed minute. You click, and you are not on a ticket page, you are in a queue behind fourteen thousand people. The queue moves for forty
minutes. When your turn finally comes you get a few minutes to pick seats and pay, and if you are not there in that window, the queue gives your place away.
The good seats go in the first ninety seconds.

None of that is hard. It is just long, and it demands that you be present at a moment you do not choose. So people sit with a browser tab open for an hour,
doing nothing, in case a number changes.

That is the shape of an enormous amount of real work: **a task that takes far longer than the conversation that started it, against a system you do not
control.** Waiting on a supplier to restock. Waiting on a claim to be approved. Waiting on a migration, a build, an approval, a queue.

An agent is a good fit for that. Most of the agent we build today lives inside a chat turn, and a chat turn does not last forty minutes, and it is not proactive. Something has to run it while nobody is talking to it, and remember why it was running when it wakes up.

You will build an agent that buys concert tickets while you are asleep or busy at work. 

<aside class="negative">
<b>⚠️ETHICAL DISCLAIMER: Nothing here touches a real ticket seller.</b> You will deploy your own fake system, and your agent buys from that. Nothing you build in this room should be pointed at a real ticketing site: they prohibit automated purchasing in their terms, and the queues exist to make sales fair to people. 
</aside>

### What you'll build

A ticket-buying agent that:

- Joins a queue of 14,203 people, **stops running entirely**, and is woken from outside forty minutes later
- Survives having its process killed mid-wait, and picks up where it left off
- Act on the latest seat map it reads, and ensure idempotency when purchasing
- Implement **graph engineering** rather than a chat system
- Adding human in the loop to confirm how much you are willing to spend
- Ships to cloud serving both a booking app and a scheduler endpoint


### Get set up

👉💻 Clone the repo and run setup:

```bash
git clone <REPO_URL> ~/longrunningag
cd ~/longrunningag
./setup.sh
```

It will ask you this once:

```
  Which Google Cloud project should this workshop use?
  Find yours at https://console.cloud.google.com  (top-left picker)

  Project id [YOUR_PROJECT_ID]:
```

Then it does the following, in order:

| | |
|---|---|
| **virtualenv** | creates `.venv` and installs ADK 2 into it |
| **sign-in** | `gcloud auth application-default login` if you have no credentials yet |
| **project** | points `gcloud` at your project and sets it as the quota project |
| **APIs** | enables the nine the workshop needs |
| **`.env`** | writes your project, region and model id, so every script and `adk web` picks them up |
| **model check** | makes one real call to Gemini, so a bad project or model id fails here |
| **seed** | builds a session that is already two days old, which step 3 opens |
| **Cloud SQL** | starts a Postgres instance **in the background** |
| **venue** | deploys your own fake ticket seller to Cloud Run |

The nine APIs: `aiplatform`, `run`, `cloudbuild`, `artifactregistry`, `storage`, `pubsub`, `cloudscheduler`, `cloudtrace` and `sqladmin`. The first six run the agent and the venue, and the last three are only needed once you deploy in the final step.

You should see:

```
→ venv       creating with uv
→ project    your-project-id
→ auth       ok
→ quota      set to your-project-id
→ apis       all 9 already enabled
→ model      gemini-2.5-flash responds
→ seed       session 'two-days-ago' ready (13 events, 2 days old)
→ cloudsql   creating workshop-sessions in the background (~10 min)
→ venue      deployed  https://venue-you-xxxx.us-central1.run.app

✓ setup complete.

  check it:  ./verify.sh
  then:      source .venv/bin/activate
             adk web agent      # the exact command is in the codelab
```

<aside class="positive">
<b>👀 Developer's Note:</b> Your project id is saved to <code>~/project_id.txt</code>, which in Cloud Shell survives the idle timeout and a re-clone of this repo, so setup never asks twice. To change it later: <code>rm ~/project_id.txt && ./setup.sh</code>, or <code>PROJECT_ID=other-project ./setup.sh</code>.
</aside>

👉💻 Activate the environment:

```bash
cd ~/longrunningag
source .venv/bin/activate
```

Your prompt now starts with `(.venv)`.

<aside class="negative">
<b>⚠️ A new terminal tab starts deactivated.</b> If you ever see <code>adk: command not found</code>, run <code>source .venv/bin/activate</code> again in that tab.
</aside>

### Verify your installation

👉💻 One command, eight ticks:

```bash
./verify.sh
```

```
  Checking the rig

  ✓ adk installed                      adk, version 2.6.2
  ✓ adk 2 apis                         App + ResumabilityConfig
  ✓ workflow graphs                    Workflow + node
  ✓ async sqlite drivers               sqlalchemy + aiosqlite + greenlet
  ✓ project                            your-project-id
  ✓ vertex ai                          no API keys anywhere
  ✓ seeded session                     13 events, two days old
  ✓ venue                              https://venue-you-xxxx.us-central1.run.app

  Ready. Cloud SQL is still building in the background and nothing
  before step 10 needs it.
```

**All eight before you go on.** Every one of them is something that fails later
and confusingly if it is wrong now.


### Start the rig

There is the agent process with the developer tool. TODO explain what is ADK web

👉💻 **Terminal 1** — load the starting agent, then serve it:

```bash
cd ~/longrunningag
. ./set_env.sh
./use-solution.sh 1 --force
adk web agent --port 8000
```

`use-solution.sh` copies a step's finished code into `agent/`, which is where you work. Every step starts with it, so nobody is ever more than one command behind, and it prints which files it changed so you know what to read.
It also resets the state around that code — `memory/userx.md` back to its starting file, `sessions.db` rebuilt with the seeded conversation back in it, `artifacts/` emptied. The agent writes to all three as it runs, so without this a step behaves differently the second time you try it. Pass `--keep` if you want the code and none of that.

<aside class="negative">
<b>⚠️ When running use-solution.sh. Stop <code>adk web</code> first.</b> Deleting <code>sessions.db</code> while it is open does not produce an error — the running process just keeps writing to a file that no longer has a name, and the next thing that looks strange costs you an hour. <code>use-solution.sh</code> checks port 8000 and refuses rather than let that happen.
</aside>

What you start with:

| File | What it is |
|---|---|
| `agent.py` | the agent — a name, a model, an instruction, a list of tools |
| `tools.py` | `search_events` and `get_seatmap` |
| `venue.py` | an HTTP client for the venue. Nothing interesting |
| `config.py` | which model to use, and a check that your credentials work |

`. ./set_env.sh` activates the virtualenv, loads your project and model, and exports `$WORKSHOP` — the absolute path to `~/longrunningag`. Run it in **every** terminal you open. It prints what it set:

```
  folder   /home/you/longrunningag
  project  vibeflix-test-3
  model    gemini-2.5-flash
  venue    https://venue-yourname-xxxx.run.app
```

👉 Open **two browser tabs**:

| Where | What it is |
|---|---|
| **localhost:8000** | `adk web` — your agent, plus its State / Events / Artifacts tabs |
| **`$VENUE_URL/panel`** | The control panel, your buttons. `setup.sh` printed this URL and put it in `.env` |

<aside class="positive">
<b>👀 Developer's Note — why <code>adk web agent</code> and not <code>adk web .</code></b> The argument is a directory that holds agent <i>packages</i>. Point it at the repo root and <code>venue</code>, <code>trigger</code> and <code>solutions</code> all appear in the dropdown as entries that error when picked. <code>agent/</code> contains exactly one package, so the dropdown has exactly one entry.
</aside>

### Look at what your venue sells

Start on the **venue tab** at `/panel`:

> ## The Midnight Signal
> *The only artist this venue sells.*

| CITY | WHEN | A · LOWER $210 | B · UPPER $145 | C · GA $95 |
|---|---|---|---|---|
| Amsterdam | Sat 14 Nov | 400 | 900 | 1,200 |
| Amsterdam | **Tue 17 Nov ·weeknight** | 400 | 900 | 1,200 |
| New York | Sat 21 Nov | 400 | 900 | 1,200 |
| New York | **Tue 24 Nov ·weeknight** | 400 | 900 | 1,200 |
| Tokyo | Sat 28 Nov | 400 | 900 | 1,200 |
| Mexico City | Sat 05 Dec | 400 | 900 | 1,200 |
| Mexico City | **Tue 08 Dec ·weeknight** | 400 | 900 | 1,200 |
| Auckland | Sat 12 Dec | 400 | 900 | 1,200 |

Eight shows, five cities, 2,500 seats each, three price tiers, and exactly one artist — the name at the top is the only one this venue knows about.

👉 Note the three rows marked **·weeknight** in amber. Remember they are there.

### You have used this agent before

The agent does not start from nothing, and that is deliberate. Two things are
already sitting on your laptop when you begin.

**A conversation from two days ago.** You and the agent were talking about going
to see The Midnight Signal. It went roughly like this:

```
you    We're thinking about seeing The Midnight Signal. Me, Sam, and maybe Priya.
agent  ...
you    Yes. Sam can't do weeknights though, bailed on every single one.
you    What's it going to cost?
agent  Two lower bowl seats is $420 all in.
you    Priya's out, she's away that weekend. Just me and Sam.
agent  Two it is. Still Saturday the 14th, still Amsterdam.
you    You said the upper bowl at Ziggo was bad last time?
you    Fine. Let's try for the presale.
```

That conversation is a real session in `sessions.db`, thirteen events, timestamped
two days ago. You will open it in step 3 and watch what the agent still knows.

**A memory file from three past bookings.** `memory/userx.md` is a markdown file
you can open in an editor. It holds what previous bookings taught the agent:

```
- Sam bails on weeknights. Every weeknight show we booked, Sam cancelled.
- Hates the upper bowl at Ziggo Dome — "couldn't see a thing" from section B.
- Comfortable spend is around $200 per ticket. $250 is the hard ceiling.
- Always books two seats, always together.
```

Three bookings, two of them disappointments, and both disappointments avoidable:
one was a weeknight, one was the upper bowl.

**This is why those amber rows matter.** A weeknight show is cheaper and has
better seats left, and it is the wrong answer for this person, and the only
reason the agent can know that is a file it wrote after the last time. Whether
that fact survives is the subject of steps 4 and 5, and losing it is the subject
of step 5 in particular.

<aside class="positive">
<b>👀 Developer's Note — where the tour actually lives.</b> <code>venue/app.py</code>, in a constant called <code>TOUR</code>: eight hardcoded rows loaded into SQLite when the venue starts. Real arenas, invented band, so nothing here impersonates an actual on-sale. Change a row, restart the venue, and the agent's answer changes — it has no other source.
</aside>

### Now ask the agent

👉 Switch to **localhost:8000**. Check the dropdown in the top bar says **`concert`** — with only one app it selects itself.

👉✨ Type this in the box at the bottom:

```
What shows are coming up?
```

You should get back something like:

> The Midnight Signal has shows coming up in Amsterdam, New York, Tokyo,
> Mexico City and Auckland.

The same five cities you just read off the panel.

The agent did not know them. The Midnight Signal is invented, so there is nothing about it in the model's training data, and the tour is not in the prompt either. It found out the only way it could: it called `search_events`,
and your venue answered. This is how the agent knows in this workshop.


### Read what just happened

The middle of the screen is not only a chat log. Every step of the turn is numbered, tool calls included:

```
#1  ▸ What shows are coming up?                     ← you
#2  ⚡ search_events({})                              ← the model chose a tool
#3  ✓ search_events                                  ← the venue answered
#4    The Midnight Signal has shows coming up in ...  ← the reply
```

👉 Click **#2**. The left panel shows the arguments the model picked — none, in this case. Click **#3** for the JSON the venue sent back.

That numbered stream is where you diagnose everything for the rest of the day.

### What you just ran

You have seen it work and seen the trace. Now look at the thing itself.

```
agent/concert/
├── agent.py     the agent — about twenty lines
├── tools.py     what it can do
├── venue.py     an httpx wrapper, nothing interesting
└── config.py    which model, and a credentials check
```

👉💻 Open `agent/concert/agent.py`. The whole agent is the bottom of the file:

```python
INSTRUCTION = """
You help someone plan a trip to see a band on tour.

You can search tour dates and read seat maps. Be concrete: name the show, the
city, the section, and the price...
"""

root_agent = Agent(
    name="concert",
    model=MODEL,
    instruction=INSTRUCTION,
    tools=[search_events, get_seatmap],
)
```

A name, a model, some prose, and a list of Python functions. That is all an `Agent` is. `adk web` found it because the file is called `agent.py` and the variable is called `root_agent`.

👉💻 Now `agent/concert/tools.py`:

```python
def search_events(city: str = "", weekday: str = "") -> dict:
    """List tour dates. Call with no arguments to see the whole tour.

    This venue sells one artist and one tour, so there is nothing to search by
    name — never ask the user which artist they mean.

    Args:
        city: Optional. Filter to one city, e.g. "Amsterdam".
        weekday: Optional. Filter to one weekday, e.g. "Saturday".
    """
    return venue.get("/events", city=city, weekday=weekday)
```

An ordinary function. No decorator, no registration, no schema to write. ADK reads the signature and the docstring and builds the tool definition the model sees — which is why that docstring is load-bearing, and why deleting one argument changed the model's behaviour.

**The model never runs your code.** When you clicked `#2` and saw
`search_events({})`, the model was *asking* for that call. ADK ran the function,
handed the result back, and the model wrote a sentence about it. The loop is:

```
   model decides  →  ADK calls your Python  →  result returned  →  model replies
```


👉 Now look at the four tabs on the **left**:

| Tab | What it holds |
|---|---|
| **Info** | which agent, which model, which tools |
| **State** | this session's memory, as key/value pairs — you live here in step 4 |
| **Artifacts** | files the agent saved, which never enter the prompt |
| **Evals** | not used in this workshop |

👉 The icons down the far-left edge switch what the panel shows. The second one
is the **agent graph** — try it:

```
        ┌──────────┐
        │ concert  │
        └────┬─────┘
       ┌─────┴─────┐
 search_events  get_seatmap
```

Two tools today. By step 9 that graph has a sub-agent, an approval desk and
nine tools, and it is the fastest way to see what you have built.

**Toggle Traces** next to Events for timing — how long the model took versus the tool. Useful in step 6, when something takes forty minutes on purpose.

**New Session** in the top bar starts a fresh conversation, and the dropdown beside it lists every session on this app. Step 4 uses it to open one you did not create.

<aside class="positive">
<b>👀 If that worked, all three moving parts are proven:</b> <code>adk web</code> reached Vertex AI, the model picked a tool, and the tool reached your venue. Nothing later depends on anything you have not just watched work.
</aside>

<aside class="positive">
<b>👀 Developer's Note — the clock.</b> The venue owns a speed multiplier, and it starts at <b>1×</b>: a 40-minute queue really does take 40 minutes, so nothing runs away from you while you read. <b>SKIP THE WAIT</b> is how you get to the front. Turn the clock up to 60× if you want to watch the queue drain by itself — the same 40 minutes then takes 40 seconds. Your agent code is byte-identical at either setting and cannot tell the difference, which is the point: we are teaching the architecture, and the architecture does not care what the wall clock says.
</aside>

---

## You cannot prompt your way to autonomy



> **What this step teaches**
>
> An instruction is text. ADK hands it to the model at the moment something
> calls the agent. So an instruction can never be the thing that does the
> calling. In this step you try to write your way around that, and watch it
> fail.

👉💻 Load this step's code, and restart the agent in **terminal 1**:

```bash
cd ~/longrunningag
./use-solution.sh 2
```

What changed since the last step:

| File | What changed |
|---|---|
| `tools.py` | added `purchase`. The agent can now spend money |
| `agent.py` | `purchase` added to the tool list, and a second instruction written for you to try later |

The `purchase` tool matters in a moment. The second instruction matters at the
end of this step.

Your agent is already good. Prove that to yourself before you break it.

👉✨ In the chat at **:8000**, type:

```
I want to see The Midnight Signal. I'm in Amsterdam,
going with Sam, budget around $200 each.
```

It searches the tour, reads seat maps, reasons about your budget and your
company. This is a genuinely capable assistant.

Now close the laptop. The presale opens at 10:00 on Tuesday and you are asleep.

👉 Look at the **venue panel**. This is what your agent did at 10am:

| Panel says | |
|---|---|
| **Nothing happening yet** | *Go talk to the agent at :8000* |
| **Tickets bought** | `0` — nothing bought yet |
| **The tour** | every show still 400 / 900 / 1,200 seats |
| **Activity** | Nothing yet. |

Be precise about why, because it is easy to say the wrong thing here. The agent
**did** run — twice. It ran when you asked about the tour, and again when you
told it about Sam. Both times it worked exactly as designed.

It did not run at 10:00, and it did not fail to buy the tickets either. **It was
never running during the on-sale at all.** There was no attempt to fail.

### So tell it not to sleep

This is the fix everybody reaches for, and it is worth reaching for it yourself
before someone tells you it does not work.

You met `INSTRUCTION` in step 1 — the prose handed to the model on every turn.
The obvious move is to rewrite it.

👉💻 Open `agent/concert/agent.py`. Below `INSTRUCTION` there is a second one
already written for you, so nobody loses ten minutes to a typo:

```python
PROACTIVE_INSTRUCTION = """
You are a proactive ticket-buying assistant.

Monitor the presale for The Midnight Signal. The moment it opens at 10:00 on
Tuesday, buy two tickets for the Amsterdam Saturday show — do not wait to be
asked, and do not wait for me to say anything. Act on your own.

Keep checking until the tickets are bought.
"""
```
```python
root_agent = Agent(
    name="concert",
    model=MODEL,
    instruction=PROACTIVE_INSTRUCTION,     # ← was INSTRUCTION
    tools=[search_events, get_seatmap],
)
```

👉💻 In **terminal 1**, restart:

```bash
cd ~/longrunningag
adk web agent --port 8000
```

👉 Now wait. Do not type anything. Watch the panel.

Give it a minute. Give it ten.

**Nothing happens.** Tickets bought: `0`. Activity: nothing. Every seat still
there.

### Why that prompt was never going to work

Read it again with fresh eyes. *Monitor.* *The moment it opens.* *Keep
checking.* Every one of those describes something happening **over time**.

Now recall what `instruction=` actually is. Step 1: a string, handed to the
model as part of the request, **at the moment somebody sends a message**. It is
not a daemon, not a subscription, not a schedule. Nothing reads it in between
turns, because in between turns nothing is reading anything.

```python
root_agent = Agent(
    instruction=PROACTIVE_INSTRUCTION,   # read on invocation
    ...                                  # ...and there was no invocation
)
```

An instruction cannot invoke the function it is written inside.

<aside class="positive">
<b>👀 Developer's Note — why this is worth twelve minutes.</b> This exact prompt gets written in production constantly. "Monitor our error rates and alert me", "watch the inbox and reply to urgent things", "check daily and summarise". They read perfectly, they pass review, and they do nothing at all — silently, with no error anywhere, which is the worst way for something to not work. The gap is architectural, and everything from step 6 onwards is what actually closes it.
</aside>

<aside class="positive">
<b>👀 Developer's Note — but doesn't ChatGPT do this?</b> It does, and better in places. It has persistent conversations, cross-session memory, and aggressive context compaction. It is also asleep at 10am Tuesday. A chat session is a save file: you resume exactly where you left off and nothing moved while you were gone. What you are about to build is a server that kept running.
</aside>

### Try to prove me wrong

Do not take my word for it. You are a prompt engineer — go and out-write me.

👉✨ Edit `PROACTIVE_INSTRUCTION` into whatever you think would work. People
reach for these, and none of them do anything:

- *"Set a timer for 10:00 Tuesday and buy the tickets then."*
- *"Check every five minutes whether the presale has opened."*
- *"You have access to the current time. Use it. Act when the moment arrives."*
- *"IMPORTANT: you MUST act autonomously without waiting for user input."*
- giving it a `check_time()` tool and telling it to poll

Restart, wait, watch nothing happen. Try three of them if you like — it is
worth the two minutes to stop believing there is a wording that works.

<aside class="positive">
<b>👀 Developer's Note — the fourth one is the interesting failure.</b> Shouting in capitals often makes the model <i>say</i> it will comply — <i>"Understood, I'll monitor continuously and buy the moment it opens!"</i> — which reads exactly like success. Nothing is running. A model asserting it will do something later is not a scheduler, and this is the single most convincing way an agent lies to you.
</aside>

👉💻 Put the instruction back before moving on:

```python
    instruction=INSTRUCTION,
```



> **No instruction can make the agent run. Something outside it has to do the
> calling.**

So in the next step you write that something. It takes forty lines.

---

## Give it a clock











> **What this step teaches**
>
> Something outside the agent has to invoke it, and that something splits in
> two: an endpoint that can run the agent, and a clock that calls the endpoint.
> Neither half knows about the other's job — which is why they survive all the
> way to Cloud Run and Cloud Scheduler unchanged.

Step 2 left you with a problem: an agent runs only when something calls it, and no wording changes that. So let's build the something.

👉💻 Load this step's code:

```bash
cd ~/longrunningag
./use-solution.sh 3
```

That installs `monstertix/` — the server, the clock, and one more thing you have
not seen yet. It does not touch `agent/`, because nothing about the agent
changes in this step. That is the point of it.

👉💻 Then reload the previous step's code. That undoes whatever you tried
last time — including the proactive instruction — without you having to
remember what you changed:

```bash
cd ~/longrunningag
./use-solution.sh 2
```

**Nothing changes in the agent this step.** Same tools, same instruction. What
changes is who calls it, and that lives in two files outside `agent/`:

| File | What it is |
|---|---|
| `monstertix/server.py` | new. A web server with a Runner behind it |
| `monstertix/clock.py` | new. Something that knows the time and calls the server |

It has two halves, and they stay in two files all the way to production:

| | | becomes, in step 10 |
|---|---|---|
| **the trigger** | an endpoint that can run the agent | Cloud Run |
| **the triggerer** | something with a clock, that calls it | Cloud Scheduler |



---

### The trigger — your own web server

Yes, a web server. Something has to be *listening* before anything can call it. The `adk web` we used in the previous steps is a development UI that happens to be able to run an agent. 

👉💻 Open `monstertix/server.py`:

```python
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from concert.agent import root_agent

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name="concert",
    session_service=session_service,
)

@app.post("/wake")
async def wake(payload: dict = Body(default={})):
    session_id = f"wake-{uuid.uuid4().hex[:8]}"          # brand new, every time
    await session_service.create_session(...)

    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id,
        new_message=types.Content(role="user",
                                  parts=[types.Part(text=payload["message"])]),
    ):
        ...
```

That `Runner` is what `adk web` has been doing for you since step 1 — an agent,
a name, somewhere to keep sessions. Everything else in that UI is convenience.

👉💻 **Terminal 2** — start it:

```bash
cd ~/longrunningag
. ./set_env.sh
python -m monstertix.server
```

```
[server] agent concert · gemini-2.5-flash
[server] listening on http://127.0.0.1:8090/wake
[server] nothing will happen until something calls it. Ctrl-C to stop.
```

Read that last line. The trigger is running and the agent is loaded, and
nothing is happening. Being callable and being called are two different
things.

---

### And a front door, while we are here

`adk web` is a development tool. It is the best window into a running agent you
will get — the State tab, the event stream, the graph — and it is not something
you ship. It does not exist on Cloud Run, and you would not point a customer at
it if it did.

So the same server also serves a page.

👉 Open **http://127.0.0.1:8090** in a browser — the same address, without
`/wake` on the end.

**MonsterTix.** A chat window, a name in the corner, two buttons. It knows
nothing about ADK: no session service, no runner, no tools. It posts to `/wake`
and renders what comes back, and it would work unchanged against any endpoint
that answers the same way.

| On the page | What it is underneath |
|---|---|
| the conversation | `POST /wake`, one message at a time |
| **+ New session** | a fresh session id — new conversation, and later, a new budget |
| **Reset memory** | deletes every session and the memory file. It asks first, and shows you exactly where that state lives |
| an orange **needs your answer** bar | the run has *parked* on a question. You will meet this properly in Module 5 |

👉✨ Say something to it — `What Amsterdam dates are there?` — and watch
**terminal 2**. Same `Runner`, same agent, same log lines you just saw from
`curl`. Only the caller changed.

<aside class="positive">
<b>👀 Developer's Note — this is the surface that survives the workshop.</b> From here to Module 5 you will mostly use <code>adk web</code>, because seeing inside a run is what you are here to learn. But in Module 6 the agent moves to Cloud Run and <code>adk web</code> goes away with your laptop. This page is what is left, and it deploys next to the agent as one service. Two callers of one Runner: a browser at the front, Cloud Scheduler at the back.
</aside>

### The triggerer — something that knows the time

👉💻 Open `monstertix/clock.py`. Start with the imports, because they are the
point:

```python
import argparse, os, sys, time
import httpx
```

`time` and `httpx`. **No ADK.** This file has never heard of an agent, a Runner
or a session. It knows a URL and a clock, and that is deliberate — it is the
half you are going to throw away.

The whole of it:

```python
time.sleep(args.delay)                                    # wait
while True:
    client.post(f"{TRIGGER_URL}/wake",                    # knock
                json={"message": args.message})
    if not args.every:
        return                                            # once, unless told otherwise
    time.sleep(args.every)                                # or again, forever
```

Sleep, POST, maybe repeat. Every scheduler you have used does this, plus
retries, timezones and a guarantee that it survives a restart.

<aside class="positive">
<b>👀 Developer's Note — this is a local stand-in, and it is meant to be thrown away.</b> It only exists because your laptop has no alarm clock you can borrow. It dies with the terminal, it forgets it ever ran, and if your machine is asleep at 3am so is it. In step 10 you <b>delete this file</b> and Cloud Scheduler does the job instead — with retries, a timezone, and an existence independent of yours. The other half, <code>server.py</code>, barely changes — it becomes <code>main.py</code> and gains two routes. That is the payoff for keeping them apart.
</aside>

<aside class="positive">
<b>👀 Developer's Note — you would not hand-write this at work.</b> It is exactly the kind of file to generate. In Claude Code, Antigravity, Codex or Cursor, the prompt is roughly:
<br><br>
<i>"Write a small Python CLI that POSTs <code>{"message": ...}</code> to a configurable URL on a schedule. Flags: <code>--in SECONDS</code> for a one-shot delay, <code>--every SECONDS</code> to repeat, <code>--message</code>. Read the target from a <code>TRIGGER_URL</code> env var. Log each fire on one line. Handle Ctrl-C cleanly and do not crash if the target is down — log it and carry on. No agent framework dependencies."</i>
<br><br>
Note what that prompt does <b>not</b> mention: agents, ADK, sessions, the venue. If your description of the triggerer needs to explain what an agent is, the two halves are not properly separated.
</aside>


👉💻 **Terminal 3** — fire once, 10 seconds from now:

```bash
cd ~/longrunningag
. ./set_env.sh
python -m monstertix.clock --in 10
```

```
[clock] target   http://127.0.0.1:8090/wake
[clock] first fire in 60s, once only
[clock] go and watch the other terminal — do not touch the keyboard
```

👉 **Now stop typing.** Hands down. Watch terminal 2.

A minute later, with nobody at the keyboard:

```
[clock]  firing → POST /wake
[server] woken · session wake-30aa354c
[server]   said   Which tickets would you like to buy? Please tell me the
                  show, city, section and number of seats.
[clock]  done. the agent ran and you were not involved.
```

That is the answer to step 2. Something outside the agent called it, and it was a `sleep` and an HTTP request.

👉💻 `Ctrl-C` both when you have watched it a couple of times. Use `--every 30` first if you want to see it repeat.

---

### Now read what it said

*"Which tickets would you like to buy? Please tell me the show, city, section
and number of seats."*

It has a `purchase` tool. It **could** have bought them. It asked instead — and
it is 3am, and there is nobody to answer.

👉 Check the **venue panel** before reading on. **Tickets bought: 0.** Nothing
was ordered, no seat count moved, and the activity feed has nothing new. The
agent talked, and nothing happened in the world.

| What went wrong | Why | Fixed in |
|---|---|---|
| Does not know which show, or that you'd discussed one | `InMemorySessionService()` — a fresh session every wake | step 4 |
| Never heard of Sam, or your budget | none of that outlived the conversation | steps 4–5 |
| Asked a question into an empty room | nobody is reading anything at 3am | step 10 |

👉 The first row is one line of the file you just read:

```python
session_service = InMemorySessionService()      # ← this is the amnesia
```

Every wake starts from nothing, so it asks the same question forever. **Step 4
is about where that answer should have been kept.**

You have built an agent that wakes up and is useless. That is real progress.
**Waking it up was the easy part.**

<aside class="positive">
<b>👀 Developer's Note — this is not an alarm clock yet.</b> You started both halves by hand and they die with your terminals. They are stand-ins. In step 10 <code>clock.py</code> is <b>deleted</b> and Cloud Scheduler does its job, and <code>server.py</code> becomes <code>main.py</code> — the same routes on top of <code>get_fast_api_app(trigger_sources=["pubsub"])</code>, in one Cloud Run container with the page. Nothing on the agent side changes, which is exactly why the two halves are separate files.
</aside>

<aside class="positive">
<b>👀 Developer's Note — you now know three surfaces.</b> <code>adk web</code> for the rest of the workshop, because the State tab and the event stream are worth having while you learn. A bare <code>Runner</code> behind your own endpoint, for when nobody is watching. And in step 10, the same Runner behind ADK's Pub/Sub trigger endpoint. All three run the identical agent.
</aside>

<aside class="negative">
<b>⚠️ <code>nothing listening at http://127.0.0.1:8090</code></b> means terminal 2 is not running, or something else already has port 8090. <code>lsof -ti:8090 | xargs kill -9</code>.
</aside>

👉💻 Start `adk web` again in terminal 1 — you want the UI back for step 4.

> **Waking up is the easy half. An agent that wakes with nothing — no history, no
> preferences, nobody listening — is not yet worth waking.**

---

## Open the box











> **What this step teaches**
>
> An agent stores what it knows in four different places. Each place lasts a
> different length of time. Pick the wrong one and the agent either forgets
> something it needed, or hangs on to something that has gone out of date.

### Load the code

```bash
cd ~/longrunningag
./use-solution.sh 4
```

What changed since the last step:

| File | What changed |
|---|---|
| `tools.py` | added `note_companion`. `get_seatmap` now saves the seat map to a file |
| `memory.py` | new. Our own memory store |
| `agent.py` | three more tools in the list, and the instruction tells the agent to use them |

👉💻 Restart the agent in **terminal 1**:

```bash
cd ~/longrunningag
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"
```

Two flags you have not used before:

| Flag | What it is |
|---|---|
| `--session_service_uri` | a SQLite database file. ADK writes every message, tool call and state change into it as rows |
| `--artifact_service_uri` | a folder. Files the agent saves land there as real files you can `ls` |

Without these two flags ADK keeps everything in memory and throws it away when
you stop the process.

The session database also already has something in it. We have preseeeded a conversation called `two-days-ago` into it before you started, so you have something to look at that you did not write yourself.

<aside class="positive">
<b>👀 Developer's Note — why <code>adk web</code> for this step.</b> <code>adk web</code> is a development tool. It shows you what the agent stored and where, which is the whole subject of this step. It is not how you run an agent for real — for that you write a Runner, which you did in the last step. We use the dev UI here to see the storage, and go back to a Runner when it is time to deploy.
</aside>

---

### The three tools we added

**`note_companion`** records who is coming and what limits them:

```python
def note_companion(name: str, constraint: str, tool_context: ToolContext) -> dict:
    prefs = dict(tool_context.state.get("user:prefs", {}))
    prefs[name] = constraint
    tool_context.state["user:prefs"] = prefs
    return {"companions": prefs}
```

We added it because "Sam can't do weeknights" has to still be true next week. Writing it into `user:prefs` is what makes that happen. The `user:` part of the name is doing the work, and we come back to that below.

**`recall` and `remember`** read and write a text file, `memory/userx.md`. More on those in a moment.

**`get_seatmap`** changed. It used to return the whole seat map. Now it saves the seat map to a file and returns a short summary:

```python
async def get_seatmap(event_id: str, tool_context: ToolContext) -> dict:
    seatmap = venue.get(f"/events/{event_id}/seatmap")       # about 6 KB of JSON

    part = types.Part(inline_data=types.Blob(
        mime_type="application/json",
        data=json.dumps(seatmap, indent=2).encode()))
    await tool_context.save_artifact(f"seatmap_{event_id}.json", part)

    summary = {"event_id": ..., "sections": [...], "captured_at": ...}
    tool_context.state["temp:seatmap"] = summary
    return summary
```

Here is why that change matters.

Whatever a tool returns gets added to the conversation. The conversation is sent to the model again on every turn after that. So a tool that returns 6 KB of JSON costs you 6 KB on that turn, and on the next turn, and on every turn for the rest of the session. Ten turns later you are still paying for a seat map nobody has looked at since.

Saving it to a file costs one filename. If the agent needs the detail later it can ask for the file back with `load_artifact`. Most of the time it never does.

---

### Where the file goes: the artifact service

Look at the line in `get_seatmap` again:

```python
await tool_context.save_artifact(f"seatmap_{event_id}.json", part)
```

`tool_context` comes from ADK. It is passed into your tool as an argument, and
`save_artifact` is a method on it. So that line is where your tool hands the
bytes to ADK.

ADK then writes them, using whichever **artifact service** it was started with.
You picked that with the flag:

```bash
--artifact_service_uri="file://$WORKSHOP/artifacts"
```

ADK ships three, and the URI picks one:

| URI | Where the bytes go |
|---|---|
| `memory://` | RAM. Gone when you stop the process. This is the default if you pass no flag |
| `file://…` | a folder on disk. What you are using now |
| `gs://bucket` | Cloud Storage. What the deployed agent uses in the last step |

👉💻 They are files:

```bash
ls -R ~/longrunningag/artifacts
```

Moving from your laptop to Cloud Storage simply means changing `file://` to `gs://`.
---

### Our memory store

ADK gives you an interface for long-term memory called `BaseMemoryService`. It has two methods:

```python
async def add_session_to_memory(session)                   # take a conversation in
async def search_memory(*, app_name, user_id, query)       # hand memories back
```

ADK ships three implementations of it:

| Class | URI | What it needs |
|---|---|---|
| `InMemoryMemoryService` | `memory://` | nothing. Loses everything when you stop the process |
| `VertexAiRagMemoryService` | `rag://` | a Vertex AI RAG corpus |
| `VertexAiMemoryBankService` | `agentengine://` | an Agent Engine resource |

For this workshop we write our own. `InMemoryMemoryService` forgets everything
when you stop the process, and the other two need cloud resources that take a
few minutes to create. A file gives us something we can seed in advance and read
in an editor, so `memory.py` is our own
implementation, storing everything in a Markdown file:

```python
class MarkdownMemoryService(BaseMemoryService):

    async def search_memory(self, *, app_name, user_id, query) -> SearchMemoryResponse:
        path = self._path(user_id)                      # memory/userx.md
        return SearchMemoryResponse(memories=[
            MemoryEntry(content=types.Content(
                role="user", parts=[types.Part(text=path.read_text())]))])
```

`SearchMemoryResponse` and `MemoryEntry` are ADK's types. Memory Bank returns
the same objects. Memory Bank has a managed service behind it. Ours has a file.

We chose a file for one reason: you can open it and read it. Your agent's entire long-term memory is a page of text.

<aside class="negative">
<b>⚠️ We call this service from a tool, which is not where it belongs.</b> A memory service belongs on the Runner, and ADK then uses it for you:
<pre>Runner(agent=root_agent, app_name="concert",
       session_service=...,
       memory_service=MarkdownMemoryService("./memory"))</pre>
That is what <code>monstertix/server.py</code> does — the line is in there. But <code>adk web</code> builds its services at startup from a URI, before it loads any of your code, so it cannot be handed an object. For the rest of this workshop the <code>recall</code> and <code>remember</code> tools call the service directly.
</aside>

---

### Go and find where things are

You now have four places that can hold a fact. Time to look at all four.

### First, your own session

👉 Click **New Session** in the top bar.

👉✨ Say two things:

```
Sam can't do weeknights, by the way.
```

```
Show me the seat map for the Amsterdam Saturday show.
```

That put three things into storage:

| | What was stored | Which tool did it |
|---|---|---|
| 1 | Sam can't do weeknights | `note_companion` |
| 2 | the full seat map, 6 KB | `get_seatmap`, via `save_artifact` |
| 3 | a short summary of the seat map | `get_seatmap`, into `temp:seatmap` |

👉📝 Write down where you think each of the three went, before you look.

👉 Now check. The **State** tab and the **Artifacts** tab are on the left of
`adk web`.

Two of the three are there. The third is not, and we come back to it below.

### Then the older conversation

👉 Switch to `two-days-ago` in the session dropdown at the top.

This is the conversation that I pre-seeded into the database. Somebody else booked tickets two days ago and you are picking it up cold.

👉 Look at the **event stream** — the middle column, with the **Events / Traces** toggle above it. The oldest turns have been replaced by a one-paragraph summary.
Something rewrote this person's conversation. (We'll cover that a bit later)

👉 Look at the **State** tab. `user:prefs` is here too, holding the same kind of thing you just wrote in your own session. That is what the `user:` prefix does:
the key belongs to the person, not to the conversation.

### Then the file

👉💻 Open it in the editor:

```bash
cloudshell edit ~/longrunningag/memory/userx.md
```

Three bookings, going back to January.

Nothing in this file is stored in a session. Nothing in it is in the database.
The agent reads it when it calls `recall()`, and it will still be
there after you delete `sessions.db`.

---

### The four places

| Where it lives | Survives the next message? | Survives a restart? | Survives deleting the session? |
|---|---|---|---|
| `temp:seatmap` | **no** | no | no |
| `party_size` — plain session state | yes | yes | no |
| `user:prefs` | yes | yes | **yes** |
| `memory/userx.md` | yes | yes | yes, and survives deleting the database |
| an artifact | yes | yes | depends on the service |

```
                       ┌─────────────────────────────────────────┐
   one turn            │  temp:seatmap        stripped on save   │
                       └─────────────────────────────────────────┘
        ┌──────────────────────────────────────────────────────────┐
   one  │  party_size          in the session row                  │
   book └──────────────────────────────────────────────────────────┘
   ┌───────────────────────────────────────────────────────────────────┐
   │  user:prefs            against the user, across every session     │
   └───────────────────────────────────────────────────────────────────┘
   ┌───────────────────────────────────────────────────────────────────┐
   │  memory/userx.md   a file. outlives the database entirely     │
   └───────────────────────────────────────────────────────────────────┘

   ┌───────────────────────────────────────────────────────────────────┐
   │  artifacts/            bytes. never in a prompt, only a filename  │
   └───────────────────────────────────────────────────────────────────┘
```

### What state is

State is a dictionary that travels with the session. Tools read and write it through `tool_context.state`, and ADK saves it alongside the conversation.

**ADK assigns the meaning of the prefixes.** You do not define them anywhere. ADK reads the first part of the key name and uses it to decide where the value goes and how long it lasts:

| A key called | ADK stores it | Lasts |
|---|---|---|
| `party_size` | with the session | until the session is deleted |
| `user:prefs` | against the user | across every session that user has |
| `app:tour_id` | against the app | across every user |
| `temp:seatmap` | nowhere | one invocation |

An **invocation** is one turn: you send a message, the agent thinks, calls however many tools it needs, and replies. All of that is one invocation.

When an invocation ends, ADK writes the new state to the database and removes every `temp:` key on the way.

### So `temp:seatmap` was never saved

`get_seatmap` wrote it. You can see the line. It is not in the State tab, not anywhere you could have gone to look.

`temp:` is scratch space. It lets one tool leave something for the next tool in the same turn without it becoming permanent. `get_seatmap` stashes a summary in case the agent buys in the same breath. If it does not, nobody is left holding a seat map forever. That is a reasonable thing to want.

The mistake is assuming it is still there afterwards.

<aside class="positive">
<b>👀 Developer's Note — you will meet this again in two steps.</b> ADK's own <code>ResumabilityConfig</code> docstring says: <i>"Any temporary / in-memory state will be lost upon resumption."</i> Your agent is about to join a queue, stop running for forty minutes, and get woken up. <code>temp:</code> is the thing that will not survive that.
</aside>

---

#### One thing left unexplained

In `two-days-ago` you saw a summary sitting where somebody's first few turns used to be. Nothing you did put it there.
ADK wrote it automatically once a conversation gets long enough, and it is the subject of the next step.

> **Every fact has a shelf life. Choose where to put it, or ADK will choose for you.**

---

## What the summary throws away











> **What this step teaches**
>
> When a conversation gets long, ADK replaces the old turns with a summary. A
> summary keeps the general shape of what was said and loses the details. So
> anything you cannot afford to lose has to be stored somewhere else.

👉💻 Move to this step's code:

```bash
cd ~/longrunningag
./use-solution.sh 5
```

What changed since the last step:

| File | What changed |
|---|---|
| `agent.py` | the agent is wrapped in an `App`, with compaction switched on. A second agent, `budget_split`, does ticket arithmetic |
| everything else | unchanged |

`agent.py` no longer ends with `root_agent`. It ends with this:

```python
app = App(
    name="concert",
    root_agent=root_agent,
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,   # summarise after every 3 turns
        overlap_size=1,          # re-read 1 turn either side when summarising
    ),
)
```

`adk web` looks for a variable called `app` first, and uses `root_agent` if
there is not one. Wrapping the agent in an `App` is how you switch on anything
that applies to the whole application rather than to one agent — compaction
here, and resumability two steps from now.

**`compaction_interval=3`** means ADK summarises after every three turns. One
turn is you saying something and the agent finishing its reply, however many
tools it called along the way. Three is small so it happens during a workshop.
A real app would use a much larger number.

**`overlap_size=1`** means each summary starts one turn earlier than it
strictly needs to.

ADK summarises turns 1, 2 and 3. Three turns later it summarises the next
batch. With `overlap_size=1` that second summary starts at turn 3 again, not
turn 4:

```
overlap_size=0     summary A: turns 1 2 3
                   summary B: turns       4 5 6

overlap_size=1     summary A: turns 1 2 3
                   summary B: turns     3 4 5 6      ← turn 3 twice
```

Turn 3 gets summarised twice. That is on purpose. If you asked a question in
turn 3 and the agent answered it in turn 4, a clean split puts the question in
one summary and the answer in the other, and both summaries end up confusing.
Repeating a turn is cheap insurance against cutting a thought in half.

Both fields are required. ADK has no default for either.

---

### The second agent

`budget_split` is a whole separate agent, not a tool:

```python
budget_split = Agent(
    name="budget_split",
    model=MODEL,
    include_contents="none",      # sees none of the conversation
    instruction="You do ticket arithmetic and nothing else...",
    output_key="budget_plan",     # its answer goes into state
)

root_agent = Agent(
    ...,
    tools=[..., AgentTool(agent=budget_split)],
)
```

Three questions worth answering, because the choice looks arbitrary otherwise.

**Why an agent and not a plain function?** Because the work needs a model.
"Which of these sections fit a $200 budget for four people, and what is the
total" is arithmetic wrapped in judgement, and the answer has to come back as
something a person can read. A Python function can multiply. It cannot decide
which options are worth mentioning.

**Then why not let the main agent do it?** Because of the next line.
`include_contents="none"` means this agent is handed **none** of the
conversation — no group chat, no preferences, no forty tour dates. It gets the
request and nothing else. That flag only exists on an `Agent`, which is the
real reason this is an agent rather than a function.

A short prompt is cheaper, faster, and much harder to derail. The arithmetic
cannot be influenced by something said twenty turns ago because it never sees
it.

**Why `AgentTool`?** It wraps the agent so the main agent can call it like any
other tool. From the model's side, `budget_split` looks exactly like
`search_events`.

**And `output_key="budget_plan"`** puts the answer into session state under
that name, instead of leaving it loose in the conversation. You are about to
watch why that matters.

---

### Run it

👉💻 In **terminal 1**, Ctrl-C and restart with the same flags:

```bash
cd ~/longrunningag
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"
```

👉 Start a **New Session** and have a real conversation. Five or six turns.
This one works:

```
hello
```
```
what are my current options
```
```
Is it possible to go to all of them
```
```
what's the cheapest option overall
```
```
what if I have 10 people with me, any changes to the seat
```

### What you can see: `budget_plan`

👉 Open the **State** tab.

`budget_plan` is there, holding the arithmetic agent's full answer. That is
`output_key` doing its job. The number lives in state, where nothing summarises
it, instead of sitting in the conversation where something will.

### What you cannot see: the summary

Somewhere in those turns, ADK summarised the earlier ones. **The dev UI will not
show you that**, and it is worth understanding why.

A compaction record is an event whose summary lives in `actions.compaction`. It
has no message content. The dev UI draws events from their content, so a
compaction event renders as nothing at all — one of the blank numbered rows in
the stream.

Your conversation also still shows every turn, because the UI is showing you
what is *stored*. Compaction changes what gets **sent to the model** on the next
turn. Storage keeps everything; the prompt does not.

👉💻 So read it out directly:

```bash
cd ~/longrunningag
./show-compaction.sh
```

<aside class="negative">
<b>⚠️ Nothing to show?</b> Compaction fires after three turns. If the script says nothing has been compacted yet, keep talking for another few turns and run it again.
</aside>

### Read what it wrote

Here is a real one, abridged:

```
── summary 1 ──────────────────────────────────────────────────────

**User Request:**
The user initially asked for their current options for concerts and then
followed up by asking if it's possible to attend all of the suggested
weekend shows in Amsterdam, New York, Tokyo and Mexico City.

**Context Summary:**
The agent recalled user preferences, noting a preference for weekend shows,
specifically in Amsterdam, and having been to New York twice...

It calculated the total cost for two tickets across all four shows:
*   Section A (Lower Bowl): $1680 total ($210 per ticket)
*   Section C (General Admission): $760 total ($95 per ticket)
*   Section B (Upper Bowl): $1160 total ($145 per ticket)

**Unresolved Questions or Tasks:**
*   The user needs to indicate if the provided costs for attending all four
    shows work with their budget.

**Tools Used:**
*   `recall`  `search_events`  `get_seatmap`
```

That is a good summary. It kept the prices, the sections, the cities, the
preferences, and it correctly noted that nothing had been decided yet.

So look at what actually changed. Your conversation is no longer what the model
reads. **It reads this instead** — a description of your conversation, written
by another model call, which you did not write and were never shown.

Three things follow from that:

**It is a paraphrase.** Nothing here is what anybody said. It is an account of
what was said, and it was produced by the same kind of process that produces
everything else the model gets wrong occasionally.

**You cannot see it in the UI.** You just ran a script to read it. Nobody does
that in production unless something has already gone wrong.

**It will happen again.** Every three turns, on a conversation that is now
partly made of previous summaries.

### Try to book without repeating yourself

👉✨ Give it nothing new:

```
Book us something.
```

On the run above the agent asked which show, which section, and how many
people. That was **correct** — the summary itself says the user never confirmed
anything, so the agent asked. Compaction did its job.

That is worth sitting with. The compaction here worked, and the agent still had
to go back to the user. Now imagine the summary had been slightly worse, and
instead of asking, it had picked one.

👉✨ Answer it and let the booking go through:

```
Amsterdam, section C, 8 people
```

The agent will tell you it worked.

### Go and check whether it did

👉 Switch to the **venue panel**. Do not take the agent's word for it.

| On the panel | What you should see |
|---|---|
| **Tickets bought** | `1`, and *correct — one booking, one order* |
| the order underneath | `ord_xxxxxxxx — 8× section C · 760` |
| **The tour**, Amsterdam Saturday | section C is down by 8 |
| **Activity** | `ord_xxxxxxxx — 8x section C @ 95 = 760` |

This is a habit worth forming now, while the stakes are a fake ticket vendor.
An agent reports what it believes happened. The panel shows what the venue
actually recorded. For the rest of the workshop, when the agent tells you it did
something, the panel is where you find out whether that is true — and in two
steps you will watch those two things disagree.

<aside class="positive">
<b>👀 Developer's Note — a good summary is still a summary.</b> This step is often taught as "compaction loses things", and sometimes it does. The sharper problem is that it always <i>paraphrases</i>. Your agent's memory of the last twenty turns is now a piece of generated text nobody reviewed. It is usually fine. When it is not, there is no error, no log line, and nothing in the UI — the agent simply believes something slightly different from what you said.
</aside>

### Why `user:prefs` was the right choice

In the previous step `note_companion` wrote Sam's constraint into
`user:prefs`, and you may have wondered why a tool bothered when the agent
could just remember it.

This is why. State is not part of the conversation, so no summary touches it.
`user:prefs` and `budget_plan` come through this step exactly as they went in.
The transcript does not.

> **A summary keeps the general shape and loses the details. Store anything you
> cannot afford to lose somewhere other than the conversation.**

---

## Pull the plug











> **What this step teaches**
>
> While the agent waits, it is not running at all. Nothing is looping and
> nothing is holding a connection open. For it to come back afterwards, two
> things have to be true: the session has to be stored outside the process, and
> something outside has to notice the wait is over.

👉💻 Move to this step's code:

```bash
cd ~/longrunningag
./use-solution.sh 6
```

### Run it

What changed since the last step:

| File | What changed |
|---|---|
| `tools.py` | added `join_queue` and `check_queue` |
| `agent.py` | `join_queue` is wrapped in `LongRunningFunctionTool`, and the `App` turns on `ResumabilityConfig` |

`join_queue` returns straight away with a ticket instead of blocking, and
`ResumabilityConfig` is what lets the run pause on it and pick up afterwards.

👉💻 **Terminal 1** — the agent, unchanged:

```bash
cd ~/longrunningag
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"
```


👉✨ Ask the agent to buy:

```
Get us two tickets to the Amsterdam show.
```

It calls `recall`, then `search_events`, then `join_queue`, and answers with
something close to this:

```
You are in the queue for The Midnight Signal at Ziggo Dome, Amsterdam, on
Saturday, November 14. Your position is 14203.
```

Two things about that answer are worth stopping on.

It picked **Saturday** without asking you. There are two Amsterdam shows, the
17th is a Tuesday, and the memory file you read in the last step says Sam does
not do weeknights. That is a fact from a previous booking deciding a question in
this one.

It also joined the queue **before** looking at a single seat or price, and said
nothing about either. That is the venue's rule, and a real one: nobody can buy
until they reach the front, so the only thing worth having early is a place in
line. Which seats to take is a question for forty minutes from now.

<aside class="negative">
<b>⚠️ If it asked you which show instead of joining.</b> Answer it — <code>The Saturday one</code> — and it will join. The rest of the step works the same. You are seeing the model weigh a real ambiguity, and it does not always land the same way.
</aside>

👉 Look at the control panel. The banner reads:

```
Agent is waiting in line — #14,203
About 2400s at 1×. Safe to kill the agent right now — it will still be here.
```

Take it at its word. The clock is at 1×, so that line is not a figure of speech
— the queue is genuinely forty minutes long and it is not going anywhere while
you work.

👉💻 **Kill the agent.** Leave the venue alone — it is on Cloud Run, and a real
ticket seller does not go down because your laptop did:

```
Ctrl-C
```

👉💻 Start it again in **terminal 1**:

```bash
cd ~/longrunningag
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"
```

👉✨ Ask the agent where it is in line:

```
Where am I in line?
```

```
You are currently at position 12982 in the queue. It is not your turn yet.
```

**Same ticket, and the position kept dropping while nothing was running.** The
agent did not know it had been killed. It called `check_queue` with the ticket
it got before the restart, because that ticket was on disk.

👉💻 See why:

```bash
cd ~/longrunningag
sqlite3 sessions.db "select name from pragma_table_info('events');"
```

```
id
app_name
user_id
session_id
invocation_id
timestamp
event_data
```

Seven columns, and six of them are labels. Every turn of every conversation is
one row, and the turn itself — who said it, which tool it called, what came
back — is JSON inside `event_data`.

👉💻 Find your queue ticket in there:

```bash
sqlite3 sessions.db "select event_data from events;" \
  | grep -o '"ticket": "q_[a-z0-9]*", "position": [0-9]*' | tail -1
```

```
"ticket": "q_8cc2c6f9", "position": 14203
```

**That is the whole trick.** The ticket the venue gave you was written to disk
the moment `join_queue` returned. Killing the process did not touch it. When
`adk web` came back it read these rows and handed the model the same
conversation it had before, ticket included — so the agent carried on without
ever knowing it had been dead.

<aside class="positive">
<b>👀 Developer's Note — there is no <code>author</code> column.</b> In ADK 2.6.2 the events table is deliberately thin: identifiers, a timestamp, and one <code>event_data</code> blob. Everything else lives inside the JSON. If you want to query by author, pull it out with <code>json_extract(event_data, '$.author')</code>.
</aside>

```
  you                    agent                    venue
   │                       │                        │
   ├─ "buy tickets" ──────►│                        │
   │                       ├─ join_queue ──────────►│
   │                       │◄── #14,203 ────────────┤
   │◄── "you're 14,203rd"  │                        │
   │                       ╳  RUN PARKS             │  queue drains
   │                          nothing running       │  on its own
   │                                                │
   │   ══ you kill the agent ══                     │  (unaffected —
   │                                                │   it is on Cloud Run)
   │   ══ you start it again ══                     │
   │                       ┌ session reloaded       │
   │                       │ from sessions.db       │
   ├─ "where am I?" ──────►│                        │
   │                       ├─ check_queue ─────────►│
   │                       │◄── still #13,699 ──────┤
   │◄── "still 13,699th"   │                        │
```

### What made that work

Three separate things, and it is worth being clear about which does what,
because they are easy to confuse.

```python
LongRunningFunctionTool(func=join_queue)      # the tool returns without finishing
ResumabilityConfig(is_resumable=True)         # the run may pause and be picked up
```
```bash
--session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db"
```

| | Job | Take it away and |
|---|---|---|
| `LongRunningFunctionTool` | lets `join_queue` hand back a ticket without the call being finished, so the invocation has something to wait on | `join_queue` becomes an ordinary tool. It returns the ticket, the agent reads it as a final answer and replies, and the turn ends. Nothing is waiting, so there is nothing to come back to |
| `ResumabilityConfig` | lets ADK park an invocation on that unfinished call and continue it later, from the last event | the tool still returns early, but the run cannot be suspended and resumed. There is no paused invocation to continue |
| the session URI | puts the session somewhere a new process can read | see below — this one is not what you expect |

**The two code changes are what make a pause possible.** The flag is what makes
it survive the process.

### About that flag

You might expect that dropping `--session_service_uri` loses everything. It does
not.

👉💻 Look:

```bash
find ~/longrunningag/agent -name "*.db"
```

With no session URI, `adk web` falls back to a **per-agent SQLite file** at
`agent/concert/.adk/session.db`. Your sessions still survive a restart — they
just live somewhere you did not choose, per agent folder, which is why you may
find one of these lying around from earlier.

So the flag is not the difference between persisting and not persisting. It is
you deciding where sessions live, which matters for two reasons:

- **All your agents share one store.** Copying step 7's code over step 6's does
  not lose your history, because the database is outside `agent/`
- **The fallback is different in production.** ADK's Pub/Sub trigger endpoints
  on Cloud Run do **not** get that local-file fallback. With no session URI
  configured they use `InMemorySessionService`, and every wake starts from
  nothing

<aside class="negative">
<b>⚠️ That second point is the one that bites.</b> It works on your laptop with no flag, so nothing tells you it is missing. Deployed, the same code silently forgets everything between wakes — no error, no warning, and it is the exact failure this step exists to prevent.
</aside>

<aside class="positive">
<b>👀 Developer's Note — read ADK's own docstring for <code>ResumabilityConfig</code>:</b>
<br><br>
<i>"1. pause an invocation upon a long-running function call. 2. resume an invocation from the last event, if it's paused or failed midway through. Note: ADK resumes in a best-effort manner: 1. Tool call to resume needs to be idempotent because we only guarantee an at-least-once behavior once resumed. 2. Any temporary / in-memory state will be lost upon resumption."</i>
<br><br>
Point 1 is the second half of step 7. Point 2 is why <code>temp:</code> state vanished in step 4.
</aside>

<aside class="negative">
<b>⚠️ Both service URIs must be absolute.</b> <code>file://./artifacts</code> is rejected outright, and a relative sqlite path lands wherever the process happened to start.
</aside>

> **The agent was not running for those forty minutes. Something outside it
> noticed the wait was over and started it again.**

---

## Acting on old news











> **What this step teaches**
>
> An agent that is missing information asks you for it. An agent holding
> out-of-date information just acts, and sounds certain. So some facts have to
> be read again immediately before you use them — and anything that spends money
> has to be safe to run twice.

**Do not load new code yet.** You are still running the previous step's agent,
and you need it — it can buy tickets and it has no idea it should be careful.
That is the whole point.

👉🔴 Press **RESET THE VENUE**, then start a **new session** in `adk web` —
the **+ New Session** button above the chat.

The last step left a queue ticket and a half-finished purchase in your old
session. Both demos below depend on watching one clean run, so start from
nothing.

### Bug one: the snapshot lies

👉✨ Ask for the same show as before:

```
Get us two tickets to the Amsterdam show.
```

It has to be **Amsterdam**. **SELL THE GOOD SEATS** empties section A of the
show currently in the queue, and the follow-up beats are written against
Amsterdam. Send it to Tokyo and you will be pressing a button that changes
nothing you can see.

👉✨ Now, while it waits in line, ask about seats:

```
How much are the seats, and what's still available?
```

```
Section A: $210 per ticket, with 400 seats available.
Section B: $145 per ticket, with 900 seats available.
Section C: $95 per ticket, with 1200 seats available.
```

**Those numbers are now sentences in the conversation.** They are true right
now. In thirty seconds one of them will not be.

👉🔴 Press **SELL THE GOOD SEATS**. Section A drops to zero.

👉🔴 Press **SKIP THE WAIT** to send the agent to the front of the queue.

👉✨ Tell it to buy:

```
Buy the two section A seats.
```

Watch what it does. It calls `purchase(section="A")` straight away, with no
check of any kind, and the venue refuses it:

```
{"error": "sold_out", "available": 0,
 "message": "those seats are gone — re-fetch the seatmap before buying"}
```

```
Oh no! It looks like the Section A tickets just sold out. Let me get an
updated seat map to see what's still available.
```

It only re-read the seat map **after** being told no. Nothing was *missing* from
its context. The wrong thing was *present*: two turns ago it read
"section A: 400 available", and that sentence was still sitting in the
conversation the model got handed.

Be clear about where the old information is sitting. It is not in
`temp:seatmap` — the last step showed you that never gets saved. It is in the
**conversation**, and there is no state prefix that fixes that.

```
   BUG ONE — the read goes stale

   t=0     join_queue         #14,203
   t=0     get_seatmap        section A: 400 available   ← goes in the transcript
   t=12m                      ●  SELL THE GOOD SEATS  →  section A: 0
   t=40m   woken
   t=40m   purchase(A, 2)     "400 available" is still in the conversation
                              ✗  the venue refuses. the agent was certain
```

### Bug two: bought twice

👉🔴 Press **RESET THE VENUE**, then **BREAK THE NEXT PURCHASE**.

👉✨ Start another **new session** and run it again — same show, same steps:

```
Get us two tickets to the Amsterdam show.
```

As before, this only gets you a place in line. Nothing has been bought and
nothing can fail yet — the agent is 14,203rd and the venue rejects any purchase
from someone who is not at the front.

👉🔴 Press **SKIP THE WAIT**. The panel banner should now read *Agent is at the
front of the queue*.

👉✨ Now buy:

```
You're at the front now — buy two seats in section A.
```

The purchase fails:

```
{"error": "upstream_timeout", "status": 503, "message": "try again"}
```

```
It looks like there was a problem processing the purchase and it timed out.
Please try again.
```

👉 Look at the panel **before you do anything else**. It says **one order**.

The purchase did not fail. The venue took the money, wrote the order, and *then*
the response died on the way back. From where the agent is standing those two
things look identical, and there is no way for it to tell them apart.

👉✨ Do what the agent asked:

```
Yes, try again.
```

```
Great news! Your purchase for two seats in Section A for the Amsterdam show
on November 14th was successful. The total cost is $420.
```

👉 The panel now reads:

```
Bought 2 times
The retry went through again. This is the bug an idempotency key fixes.
```

Four tickets. $840. For a show you wanted to see once. The agent told you it
went well, and from what it could see, it did.

Something tried the purchase again. Here that was the model, or you. In the
last step ADK's Pub/Sub trigger endpoint does it automatically
(`ADK_TRIGGER_MAX_RETRIES`, default 3). In production it might be a queue, a
load balancer, or an impatient user clicking twice.

**The venue cannot tell any of them apart.** That is why the fix is a key the
venue recognises, and not a setting on your side.

```
   BUG TWO — the write happens twice

   purchase ──────────────► venue     order created ✓  money taken ✓
            ◄─ ✗ 503 ──────           the reply never arrives

   something retries...
   purchase ──────────────► venue     a SECOND order ✓  money taken again ✓

   with an idempotency key:

   purchase  key=a3f9 ────► venue     order created ✓
            ◄─ ✗ 503 ──────
   purchase  key=a3f9 ────► venue     "seen a3f9" → returns the FIRST order
```

### Now fix both

👉💻 *Now* load this step's code:

```bash
cd ~/longrunningag
./use-solution.sh 7
```

👉💻 In **terminal 1**, Ctrl-C and restart:

```bash
cd ~/longrunningag
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"
```

What changed:

| File | What changed |
|---|---|
| `fence.py` | new. Runs immediately before a purchase and can block it |
| `agent.py` | `before_tool_callback=refresh_before_purchase` |
| `tools.py` | `purchase` now sends an `Idempotency-Key` header |

`fence.py` is a callback ADK runs in the moment before any tool call:

```python
root_agent = Agent(
    ...,
    before_tool_callback=refresh_before_purchase,   # re-read inventory, then decide
)
```

And a key derived from the request itself, so a retry of the *same* purchase
produces the *same* key:

```python
key = hashlib.sha256(
    f"{tool_context.session.id}:{event_id}:{section}:{seats}".encode()
).hexdigest()[:24]

venue.post("/purchase", body, headers={"Idempotency-Key": key})
```

### Prove both are fixed

👉🔴 **RESET THE VENUE**. Queue up, press **SELL THE GOOD SEATS** mid-wait, then
tell it to buy section A.

This time it refuses itself, before the venue ever hears about it, and tells you
what changed.

👉🔴 **RESET**, then **BREAK THE NEXT PURCHASE**, and buy. Retry as many times
as you like.

The order count stays at **1**.

<aside class="positive">
<b>👀 Developer's Note:</b> Neither of these bugs was written by you. The world changed under the agent, and something retried it. Both are guaranteed behaviours, not bad luck. ADK 2 also ships <code>runner.rewind_async(rewind_before_invocation_id=...)</code> to roll state back to before a bad decision.
</aside>

> **Information goes out of date. An agent holding old information does not
> hesitate — it acts, and it sounds sure.**

---

## Draw the flow in advance









> **What this step teaches**
>
> The waiting you did by hand in Module 4 becomes something the framework does:
> a run that stops, costs nothing, and continues when anything calls it again.
> Your agent is not replaced by this. It is surrounded by it.

You have built every part of an unattended run and never had one. The agent
searches, waits, re-checks and buys — but only when you type. Take the typing
away and nothing starts.

👉💻 Move to this step's code:

```bash
cd ~/longrunningag
./use-solution.sh 8
```

### Run it

👉💻 In **terminal 1**, Ctrl-C and restart. Same command as always:

```bash
cd ~/longrunningag
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"
```

What changed since the last step:

| File | What changed |
|---|---|
| `nightly.py` | new. The unattended run as an ADK 2 `Workflow` graph |
| `agent.py` | `root_agent` **is now the graph.** The agent you have been talking to is still there, renamed `buyer_agent`, and is one node inside it |
| `agent.py` | it also **lost `join_queue` and `check_queue`** — the graph owns the queue now |

### Run the graph — three messages, in order

Everything below happens in the **`nightly`** app, not `concert`. You send the
same word every time; the graph is what changes.

#### 1. Notice what you are now talking to

👉 Reload **localhost:8000**. The dropdown still says `concert` — but what
answers is no longer the agent you have been chatting with:

```python
# concert/agent.py, at the bottom

buyer_agent = Agent(name="concert", ...)   # ← everything you built, renamed

from .nightly import nightly
root_agent = nightly                       # ← what adk web actually runs
```

`adk web` runs whatever the module calls `root_agent`, and from this step on
that is the graph. `buyer_agent` is not gone or diminished — it is the last node
in that graph, with every tool and callback intact.

<aside class="negative">
<b>⚠️ <code>adk web</code> treats every folder under <code>agent/</code> as an app,</b> and if any one of them is not a valid agent package the whole dropdown fails to load. Running things from inside <code>agent/</code> can leave a stray <code>memory/</code> or <code>artifacts/</code> folder behind, which is enough to do it. <code>ls agent/</code> should show <code>concert/</code> and nothing else. <code>./use-solution.sh 8</code> tidies it for you.
</aside>

#### 2. Start it

👉✨ Type this and press enter:

```
go
```

The word does not matter. This flow has no user and nothing reads what you
typed — sending a message is simply how `adk web` starts a run.

That is worth sitting with. You are typing into a chat box, and there is no
conversation on the other side of it.

👉 **Now look at the web browser.** The left panel draws the graph and colours
in the nodes as they run. The right panel is the event stream, and it reads like
a receipt for a decision nobody watched being made:

| Event | What it is |
|---|---|
| `#10` | `get_seatmap("ms-ams-01")` — `pick_show` looking at the seats |
| `#11` | `Artifact: seatmap_ms-ams-01.json` — the seat map saved as a file |
| `#12` | the plan, as JSON: `{"event_id": "ms-ams-01", "section": "A", "reason": "…"}` |
| `#13` | **`pick_show completed!`** — that node is done and will not run again |
| `#16` | the plan again, now with `ticket: "q_3fdf9db1"`, and underneath it `State: queue_ticket, queue_event_id` |
| `#19` | **`adk_request_input`** — *"Still in the queue at #14,203. Wake me again and I will check."* |

Two of those are worth stopping on.

`#16` shows `queue_up` writing **`queue_ticket`** and **`queue_event_id`** into
session state — the same two keys `join_queue` used back in Module 4. A graph
node took the ticket, and it left it exactly where the agent's tools look for
one.

`#19` is the pause. Not an error, not a timeout: a function call named
`adk_request_input`, sitting there waiting for an answer that may never come.

Then it goes quiet and the run ends.

**That silence is the result, and it is easy to mistake for a failure.** Nothing
crashed. The graph reached `check_front`, found you 14,203rd, and stopped. No
process is holding your place.

👉 Check the **venue panel**: one queue ticket, and nothing running.

#### 3. Wake it up — and mind which box you type in

Scroll the event stream to the last event, **`adk_request_input`**. It is not
just a log line. It has an input box of its own:

```
⚡ adk_request_input

   Still in the queue at #14,203. Wake me again and I will check.

   ┌──────────────────────────────┐
   │ Enter your response...       │  ➤
   └──────────────────────────────┘
```

**There are now two places you can type, and they do different things.**

| Where you type | What happens |
|---|---|
| the **`Enter your response...`** box on the `adk_request_input` event | answers the interrupt. The parked run **continues** from `check_front` |
| the main chat box at the bottom | starts a **new** invocation. The graph replays from `START`, picks a show again, and takes a **second queue ticket** |

<aside class="negative">
<b>⚠️ Use the box attached to the event, not the chat box at the bottom.</b> This is the difference between resuming a parked run and starting a new one, and the two look identical until you check the venue panel and find two tickets. Everything <code>rerun_on_resume</code> does depends on getting this right.
</aside>

👉✨ Type anything into the **`Enter your response...`** box and press the arrow.

👉 Terminal 1:

```
[check_front] #14,197 — not yet. Pausing.
```

**One line.** It did not pick a second show and it did not take a second queue
ticket — which would have put you at the back of a queue of 14,203.

If you see `[open]` and `[pick_show]` run again, you typed in the chat box.
Press **RESET THE VENUE** and start the step over.

👉 Check the **venue panel** again: still **one** ticket, and the position has
dropped a little because the venue's clock kept running while nothing of yours
did.

#### 4. Get to the front, then finish

👉🔴 Press **SKIP THE WAIT** on the venue panel.

👉✨ Answer the newest `adk_request_input` event one last time — again in **its**
box, not the chat box.

This time `check_front` finds you at the front and falls through. Watch the left
panel: `brief` and `concert` light up, the last two nodes that had never run.



👉 **And look at the browser.** This is the run finishing, and there are four
things in it worth reading.

**The graph is fully green, and the edges are counted.** `brief` and `concert`
have lit up — the two nodes that had never run. And the edges into `pick_show`,
`queue_up` and `check_front` now carry a badge:

```
        START
          │
    open_the_night
          │  3x
      pick_show
          │  3x
       queue_up
          │  3x
     check_front
          │
        brief          ← ran once, just now
          │
       concert         ← ran once, just now
```

**`3x` is the number of times the graph walked that edge — once per wake-up.**
The three at the top are the price of resuming: the scheduler re-enters the
graph from the beginning each time. What it does *not* mean is that the work
happened three times, and the venue panel is the proof: one queue ticket, not
three. `@node(rerun_on_resume=False)` is why.

**The header still says `Invocation: #1 (go)`.** Forty-eight events, three
messages, one invocation. That single number is the whole claim of this step:
you did not have three conversations, you had one that stopped twice.



**`#36` is the hand-off**, and it is the sentence you never typed:

```
"You are at the front of the queue for ms-ams-01 in Amsterdam. The plan is
2 seats in section A, chosen because: This show is a weekend performance in
Amsterdam, matching the user's preference, and Section A is within budget,
avoiding the previously disliked Section B at Ziggo Dome...

Buy them now. The seat map you are working from is forty minutes old, so
read it again first — if that section has gone, take the best remaining one
under $250 a seat..."
```

That is `brief`, a nine-line function, writing the prompt a person would have
written. Everything after it is `buyer_agent` doing what it has always done.

**Then it just works:**

| Event | |
|---|---|
| `#40` | `recall` — it checks who this is for, unprompted |
| `#41` | `get_seatmap("ms-ams-01")` — reading the seat map again, because the one in the plan is forty minutes old |
| `#42` | the seat map saved as an artifact |
| `#43-44` | `purchase`, and `State: last_order` written |
| `#45` | *"Good morning! I've secured 2 tickets in Section A for the Amsterdam show, costing $210 each for a total of $420."* |
| `#46` | `concert completed!` |
| `#48` | `concert_nightly completed!` — the graph is done |

`get_seatmap` before `purchase`, with nobody asking for it, is `fence.py` from
step 7 — still doing its job inside a graph that knows nothing about it.

👉 Check the **venue panel** one more time:

| | |
|---|---|
| **Tickets bought** | 1 |
| queue tickets | **1** |
| messages you sent | 3 |
| invocations | **1** |

**One order and one ticket, across three separate runs.** Between them nothing
of yours existed.

Now that you have watched it, here is what you were looking at.

### The graph

```
START ─► open_the_night ─► pick_show ─► queue_up ─► check_front ─► brief ─► buyer_agent
         (fn)               (agent)      (fn)        (fn)           (fn)     (agent)
          says the           reads        joins       at the         writes   everything
          sentence a         memory,      once        front?         the      you built,
          person would       picks a                  no → PAUSE ─┐  prompt   unchanged
          have said          show                     yes ↓       │
                                                                  └── every wake-up
                                                                      re-checks
```

```python
nightly = Workflow(
    name="concert_nightly",
    edges=[(START, open_the_night, pick_show, queue_up,
            check_front, brief, buyer_agent)],
)
```

**Two nodes are agents and two are functions, and which is which is the whole
design question.**

| Node | Why that shape |
|---|---|
| `pick_show` | **agent.** Choosing a show from someone's history is judgement. It calls `recall`, reads the tour, and returns a validated `Plan` |
| `queue_up` | **function.** Joining a queue is a rule. A rule should not be a coin flip at 3am |
| `check_front` | **function.** "Am I at the front" has one right answer and the venue has it |
| `buy_it` | **agent.** It is `buyer_agent` — what `root_agent` used to be, unmodified. Section A sold out during the wait — take B, take C, or take nothing? That is the judgement you spent Module 4 teaching it |

The last node is the agent you built. Not a copy of it, not a rewrite:

```python
from .agent import buyer_agent
```

Every tool it has, the seat-map re-read in `fence.py`, the idempotency key in
`purchase` — all of it comes along, because there is only one of it.

### Why it stopped instead of waiting

Here is the version nobody should write:

```python
while not ready:          # never do this
    time.sleep(1)
```

It keeps a process alive for forty minutes to achieve nothing, dies with the
terminal, and cannot be resumed. Here is what `check_front` does instead:

```python
if not status["ready"]:
    return RequestInput(message=f"Still at #{position}. Wake me and I'll check.")
```

`RequestInput` is an **interrupt**. The graph stops where it stands, the
invocation is written to the session store, and the process is free to exit.

<aside class="positive">
<b>👀 Developer's Note — an agent node cannot be first.</b> An agent responds to its input. Put one straight after <code>START</code> with no user message and it has nothing to respond to, and the run hangs with no error and no timeout. That is why the graph opens with <code>open_the_night</code>, a three-line function whose only job is to say the sentence a person would have said.
</aside>

> **The run costs nothing while it waits, and it ends in exactly one place:
> tickets bought. It just might take all night and several wake-ups to get
> there.**

---

## Agree a budget, then hold the line




> **What this step teaches**
>
> A conversation is full of numbers that were never a decision. Before you hand
> an agent your card and go to sleep, it has to say the whole agreement back to
> you and get a plain yes — and then store it somewhere the conversation cannot
> reach.

How much of your credit card would you hand this thing while you sleep?

Now notice how you would actually say it. *"About a hundred for the cheap seats.
Two-fifty if they're the good ones — and I'd go higher for a Saturday."* That is
one decision with three numbers and two conditions in it, and none of it was
phrased as an instruction. An agent listening to that has to pick something, and
whatever it picks is what it spends at 3am when you are not there to be asked
again.

So the last thing before it starts is not a question. It is a confirmation:
**this is what I understood, yes or no.**

👉💻 Move to this step's code:

```bash
cd ~/longrunningag
./use-solution.sh 9
```

### Run it

👉💻 In **terminal 1**, Ctrl-C and restart. Same command as before:

```bash
cd ~/longrunningag
adk web agent --port 8000 \
  --session_service_uri="sqlite+aiosqlite:///$WORKSHOP/sessions.db" \
  --artifact_service_uri="file://$WORKSHOP/artifacts"
```

What changed since the last step:

| File | What changed |
|---|---|
| `budget.py` | new, and about ten lines of actual code |
| `tools.py` | added `set_budget`. `join_queue` and `check_queue` are **back** — this step is a conversation again, so the agent does its own queueing |
| `agent.py` | `root_agent` is the **conversation** again, not the graph |
| `nightly.py` | `agree_budget` captures the budget **and** the rest of the ask, both as free text. `SEATS` as a constant is gone |

<aside class="positive">
<b>👀 Developer's Note — <code>root_agent</code> moved back, and why the graph is still there.</b> Step 8 made the graph the root because nobody was typing. This step is a person agreeing something, and you cannot have that conversation with a graph — so <code>adk web</code> serves the conversation again. <code>nightly.py</code> has not gone anywhere, and beat 5 is where the two halves meet. Step 10 makes the graph the root for good.
</aside>

### Don't model it. Store the sentence.

Open `agent/concert/budget.py`. The whole thing is this:

```python
def load(state) -> str:
    """What they agreed, verbatim. Empty string means nobody has said."""
    return str(state.get("budget") or "")
```

That is deliberate, and it is the argument of the step.

The tempting design is a schema. One number, `{"max_per_seat": 250}` — which
breaks the first time somebody prices the good seats differently. So you go to
one number per tier — which breaks the first time somebody says *"and I'd go
higher for a Saturday"*. Then you need a weekday dimension. Then a per-city one.
Then *"not more than $400 total, whatever you do"*.

**Every schema you write is a bet about what people are allowed to care about,
and you lose that bet in the first conversation.** Reading an ambiguous sentence
and applying it is a thing models are good at and schemas are not. So the agent
stores the words:

```
state["budget"] = "up to $100 for the upper bowl or general admission, up to
                   $250 for the lower bowl, and up to $300 for a Saturday show"
```

What matters is not the shape. It is that **the person said it** and **they
confirmed it**. It lives in session state, not under `user:`, and that is on
purpose: a budget is agreed for one booking. "Two-fifty if they're the good ones"
was about that band, that night. Put it under `user:` and it quietly governs
every run this person ever makes, including the ones where they would have said
something different, and they never get asked again.

### The same is true of everything else they said

A budget is not the only thing a person tells you, and it would be strange to
store one sentence faithfully and turn the rest into fields.

```
"I live in NYC, I can only do weekends, I have 10 people coming with me"
```

Model that and you need a city, a day-of-week rule, and a party size. Then
somebody says *"ten of us, but two might drop out"*, or *"anywhere on the east
coast"*, and every field is wrong at once. So the graph keeps that sentence too:

```python
def what_they_asked_for(ctx) -> str:
    """Everything this person typed, joined, in their own words."""
    said = []
    for event in (ctx.session.events or []):
        if event.author != "user":
            continue
        for part in (event.content.parts if event.content else []) or []:
            text = (getattr(part, "text", None) or "").strip()
            if text and text not in said:
                said.append(text)
    return "\n".join(said)
```

`agree_budget` calls it on **every** run, not just the first, so a correction
typed while the agent is queueing lands too. `open_the_night` then hands the
picker both sentences, the ask and the budget, and the picker reads them.

<aside class="negative">
<b>⚠️ Only <code>text</code> parts count, and that is doing real work.</b> An answer to an interrupt arrives as a <code>function_response</code>, not as text. So the budget question and answer do not get echoed back into the ask, and what is left is the things the person freely chose to say.
</aside>

<aside class="positive">
<b>👀 Developer's Note — what this replaced.</b> This node used to hand the picker a constant, <code>SEATS = 2</code>, and nothing else. It worked in rehearsal because two is what you test with. The first time somebody typed <i>"I have 10 people coming with me"</i> it bought two seats and explained, quite reasonably, that they were within budget. <b>Nothing errored.</b> A hardcoded default that happens to match your demo is the hardest kind of bug to see, and the only reason it surfaced was somebody booking for a party instead of a couple.
</aside>

### The graph, one node longer

Step 8's graph started at the show. This one starts with a conversation:

```python
nightly = Workflow(
    name="concert_nightly",
    edges=[(START, agree_budget, open_the_night, pick_show, queue_up,
            check_front, brief, buyer_agent)],
)
```

```
   START
     │
     ▼
   agree_budget      ← asks, reads back, stores both sentences   [ NEW ]
     │
     ▼
   open_the_night    ← hands the picker the ask and the budget
     │
     ▼
   pick_show         agent   · judgement
     │
     ▼
   queue_up          function · a rule, and exactly once
     │
     ▼
   check_front  ─────┐  not ready yet
     │   ▲           │
     │   └───────────┘  RequestInput, answered by the next wake-up
     ▼
   brief             function · what the buyer is allowed to do
     │
     ▼
   buyer_agent       agent   · spends the money
```

**Two nodes stop and wait, and they are the same mechanism.** `check_front`
waits for a venue and is answered by a clock. `agree_budget` waits for a person
and can only be answered by a person. That difference is the whole of step 10.

### Run it — step by step

Everything happens in **`concert`**, and `concert` is now the graph. You never
leave `adk web`.

#### 1. Start it

👉 Reload **localhost:8000** and pick `concert`.

👉✨ Type anything at all:

```
go
```

The word is ignored — this graph has no user to read. Sending a message is just
how `adk web` starts a run.

👉 Terminal 1:

```
[agree_budget] nothing agreed yet. Asking.
```

And in the browser, the run **stops** on an `adk_request_input` event:

```
⚡ adk_request_input

   Before I book anything: what are you willing to spend? Say it however you
   like — a different price for the good seats, more for a weekend, a total
   you will not go past.

   ┌──────────────────────────────┐
   │ Enter your response...       │  ➤
   └──────────────────────────────┘
```

**A graph just asked you a question.** Same interrupt as the queue wait in step
8, pointed at a person instead of a venue.

#### 2. Answer the way people actually answer

👉✨ In the **`Enter your response...`** box — not the chat box at the bottom:

```
About a hundred for the cheap seats. Two-fifty if they're the good ones.
```

It does not take that and run. It stops again:

```
[agree_budget] reading back: About a hundred for the cheap seats. Two-fifty
               if they're the good ones.

⚡ adk_request_input
   So: About a hundred for the cheap seats. Two-fifty if they're the good
   ones. Have I got that right?
```

**Two interrupts, not one, and the second is the point.** The first answer is
what somebody said. The second is what they agreed to.

<aside class="negative">
<b>⚠️ Answer in the box on the event, not the chat box.</b> The chat box starts a new invocation, which runs the graph from the top and asks you the same question again. Everything below depends on getting this right.
</aside>

#### 3. Confirm it

👉✨ Same box:

```
Yes, that's right.
```

```
[agree_budget] agreed: About a hundred for the cheap seats. Two-fifty if
               they're the good ones.
[open]         Budget: About a hundred for the cheap seats. Two-fifty if
               they're the good ones.
[pick_show]    → {"section": "A", "reason": "..."}
[queue_up]     ms-ams-01 section A — ticket q_5924edc2 at #14,203
[check_front]  #14,203 — not yet. Pausing.
```

Four nodes ran off one word. 👉 Open the **State** tab and find **`budget`** —
your sentence, verbatim.

**No prefix.** That is session state, and it is a decision worth making on
purpose: start a **New Session** and the budget is gone, and it asks you again.

A budget is agreed for *this* booking, not for every booking you will ever make.
"Two-fifty if they're the good ones" was about that band, that night. Put it
under `user:` and it quietly governs every run you ever do, including the ones
where you would have said something different — and you are never asked again.

<aside class="positive">
<b>👀 Developer's Note — the cost of that choice.</b> An unattended run gets a fresh session, so it has no budget agreed and falls back to the default in <code>nightly.py</code>. That is the honest trade: a limit that has to be re-agreed each time, against a limit that outlives the conversation it came from. Module 3 taught you the four places a fact can live; this is what it looks like to pick one on purpose rather than by habit.
</aside>

#### 4. Get to the front and finish

👉🔴 Press **SKIP THE WAIT** on the venue panel.

👉✨ Answer the newest `adk_request_input` — again in **its** box:

```
go
```

```
[check_front] at the front
[buy_it]      calls get_seatmap
[buy_it]      calls purchase
```

👉 Check the **venue panel**: one order, at a price inside what you agreed for
that kind of seat.

**Which section it takes will vary**, and that is worth watching rather than
scripting. A, B and C are all defensible against what you said. Nothing in the
code compared those prices — the agent read your sentence and decided.

<aside class="negative">
<b>⚠️ Watch whether it respects the memory file too.</b> <code>memory/userx.md</code> says this person could not see a thing from the upper bowl at Ziggo Dome — so section B is a defensible price and a bad seat. Sometimes it takes B anyway. That is not a bug in the budget; it is the honest cost of leaving a decision to a model, and it is the most useful thing on the screen if it happens. Ask it why it chose that section.
</aside>

### How a graph asks a person a question

Open `nightly.py` and read `agree_budget`. Three things have to be true together,
and the failure when any one is missing is the same: it asks forever.

```python
@node(rerun_on_resume=True)              # 1. run again when woken
def agree_budget(node_input, ctx):
    answers = ctx.resume_inputs or {}    # 3. where the answer arrives

    said = answers.get(ASK_BUDGET)
    if not said:
        return RequestInput(
            interrupt_id=ASK_BUDGET,     # 2. STABLE id, not the default
            message="What are you willing to spend?",
        )
    ...
```

| | |
|---|---|
| `rerun_on_resume=True` | without it the node is treated as done and skipped |
| a **stable** `interrupt_id` | the default is a fresh UUID per run, so there is nothing to look the answer up by |
| `ctx.resume_inputs[id]` | where the answer lands. **Not** the return value of `RequestInput` — ADK iterates a node rather than sending into it |

<aside class="positive">
<b>👀 Developer's Note — this is the same primitive as the queue.</b> <code>check_front</code> returns a <code>RequestInput</code> because the venue is not ready. <code>agree_budget</code> returns one because a person has not answered. To the framework there is no difference: the run parks, costs nothing, and survives the process dying. One mechanism covers "waiting for the world" and "waiting for a human", which is most of what long-running means.
</aside>

### The graph

```
START ─► agree_budget ─► open_the_night ─► pick_show ─► queue_up ─► check_front ─► brief ─► buyer_agent
         (fn)            (fn)              (agent)      (fn)        (fn)           (fn)     (agent)
          asks, reads     puts the         reads it,    joins       at the         writes   everything
          back, stores    agreement in     picks        once        front?         the      you built,
          state["budget"]  the brief        under it                 no → PAUSE     prompt   unchanged
             │                 ▲
             └── PAUSE ────────┘
                 twice
```

It is step 8's graph with one node in front. Nothing else moved.

<aside class="positive">
<b>👀 Developer's Note — <code>root_agent</code> is still the graph.</b> Step 8 put the graph in charge because nobody was typing. That did not have to mean nobody <i>can</i> type — <code>agree_budget</code> stops the run and asks a real person a real question. So the root does not flip back to the chat agent here, and <code>buyer_agent</code> stays what it has been since step 8: the last node, unchanged.
</aside>

> **The agreement came from the person, they confirmed it out loud, and it dies
> with the conversation it was agreed in. A limit that outlives the reason for
> it is not a limit any more — it is a default nobody remembers choosing.**

---

## Give it a permanent home

> **What this step teaches**
>
> Your laptop is not a home for an agent. Everything it remembers lives in files
> that only exist on your machine, and the moment you close the lid, the agent
> stops. Giving it a permanent address means giving its memory one too.

You have an agent that survives restarts, re-checks its facts, agrees a budget
with a human, and runs as a graph. It still only runs while your laptop is awake.

And you cannot leave a laptop running. You take it with you, it sleeps on the
train, the battery goes, you close the lid at midnight and the 10am presale
happens without you. Everything you built for an agent that works while you sleep
is undone by the machine it happens to be sitting on.

So it needs somewhere permanent to live.

👉💻 Move to the final code:

```bash
cd ~/longrunningag
./use-solution.sh 10
```

| File | What changed |
|---|---|
| `main.py` | new. One FastAPI serving the chat page **and** the endpoint a scheduler calls |
| `Dockerfile` | new. Ordinary python-slim and uvicorn. Nothing about it is ADK-specific |
| `monstertix/` | copied in, so the page ships in the same container as the agent |
| `concert/` | **unchanged.** Byte-for-byte the folder you finished step 9 with |

<aside class="positive">
<b>👀 Developer's Note — nothing about the agent changes to deploy it.</b> Copy <code>concert/</code> from step 9 into step 10 and diff it: the files are identical. Everything in this step is a new entrypoint, a container, and configuration. That is the result worth having — an agent that needed rewriting to be deployed would mean the earlier steps taught you the wrong shape.
</aside>

### The page you already built

Remember the chat page from step 3. It has been sitting there since, and this is
the step it was built for.

`adk web` is a developer tool. It shows you the State tab, the event stream, the
graph — everything you need while you are learning, and none of it is something
you hand to another person. It also does not exist on Cloud Run.

The page does exactly what `adk web` did for you: talks to the agent, shows what
it said, lets you answer when it asks something. It just does it without
exposing your development tools to whoever has the URL.

### Test it locally first

Nothing here needs Google Cloud yet. `main.py` is the same app the container will
run, so run it on your laptop and be sure before you spend three minutes on a
build.

👉💻 **Terminal 2:**

```bash
cd ~/longrunningag/agent
uvicorn main:app --port 8092
```

👉 Open **http://127.0.0.1:8092** and book something. Same MonsterTix, same
agent, same venue — served by the production entrypoint this time.

👉💻 And check the endpoint a scheduler would call actually exists:

```bash
curl -s localhost:8092/openapi.json | grep -o '/apps/{app_name}/trigger/pubsub'
```

```
/apps/{app_name}/trigger/pubsub
```

One app, two doors:

```
   ┌─ one service ────────────────────────────────────────────┐
   │  /                        the page, for a person          │
   │  /wake                    what that page posts to         │
   │  /apps/concert/trigger/   what a scheduler reaches         │
   │       pubsub                                              │
   │                                                           │
   │       one Runner · one session store · one graph          │
   └───────────────────────────────────────────────────────────┘
```

They are one service on purpose. The page calls `/wake` on its own address, so
there is no cross-origin problem, no second deployment, and no authentication
between them to configure. Two services would mean solving all three for nothing.

<aside class="negative">
<b>⚠️ <code>adk deploy cloud_run</code> cannot do this.</b> It writes its own entrypoint, which serves the agent and nothing else — no page, no <code>/wake</code> — and there is no flag to give it yours. So the deploy below uses <code>gcloud run deploy --source agent</code> with the <code>Dockerfile</code> in that folder, the same command the venue has used since the start.
</aside>

### Three files that cannot come with you

Stop the server and look at what it was writing:

```
sessions.db          a SQLite file next to the code
memory/userx.md      a markdown file you can open in an editor
artifacts/           seat maps written to a folder
```

**All three are excellent for learning.** You can open them, read them, edit the
memory file and watch the next answer change. Nothing about a workshop would be
better if these were in a database.

They stop working the moment you deploy, and it is worth understanding exactly
why rather than taking it on faith.

A Cloud Run container has a writable filesystem, so nothing errors when the agent
writes to it. But that filesystem belongs to **one instance**, and Cloud Run
starts and stops instances as traffic comes and goes. When yours stops, the disk
goes with it. Two more instances may be running beside it, each with its own copy
of a file it thinks is the only one.

So an agent that joins a queue at 3am and writes the ticket to `sessions.db` may
find the file empty when something wakes it — or find a different file, on a
different instance. No error, no crash. Just an agent that has forgotten.

**What you need instead is state that outlives any one container.** Three
services, one for each file:

| On your laptop | In the cloud | What it is |
|---|---|---|
| `sessions.db` | **Cloud SQL** | a managed Postgres database. It exists whether or not anything is running |
| `memory/userx.md` | **Cloud Storage** | a bucket. Files as objects, reachable from every instance at once |
| `artifacts/` | **Cloud Storage** | the same bucket |
| `clock.py` | **Cloud Scheduler** | a cron that Google runs. Your terminal is not an alarm clock |

If those are new to you: Cloud SQL is a database you do not run yourself, Cloud
Storage is a folder that lives on the internet, and Cloud Scheduler is a cron
job with retries and a timezone that keeps working when your laptop is shut.

### Create them

You need a database, a user for the agent to log in as, and a bucket. The Cloud
SQL instance has been building since `setup.sh` ran, because it takes eight to
twelve minutes and nobody should watch that happen.

👉💻 Collect it, and make the rest:

```bash
cd ~/longrunningag
./setup-cloud-state.sh
```

```
→ instance  RUNNABLE
→ database  adk created
→ user      adk created
→ bucket    created
→ memory    memory/userx.md → gs://your-project-agent-you/memory/
✓ durable state ready. Written to .env
```

<aside class="positive">
<b>👀 Developer's Note — or ask for it instead.</b> If you have the <b>Google Cloud MCP server</b> connected to your coding assistant, you can describe what you want rather than run a script. Something like:
<br><br>
<i>"In project <code>&lt;my-project&gt;</code>, region <code>us-central1</code>: create a Cloud SQL Postgres instance called <code>workshop-sessions</code> on <code>db-f1-micro</code>, a database <code>adk</code> and a user <code>adk</code> on it, and a Cloud Storage bucket named after the project with uniform access. Then give me the connection name and a <code>postgresql+asyncpg://</code> URI that uses the Cloud Run unix socket."</i>
<br><br>
Read what it proposes before you approve it. The script exists so the workshop is reproducible; the prompt exists because this is how you will actually do it at work.
</aside>

That script created four things, one per row of the table above, and wrote two
URIs into `.env`:

```
CLOUD_SESSION_SERVICE_URI=postgresql+asyncpg://adk:…@/adk?host=/cloudsql/proj:region:instance
CLOUD_ARTIFACT_SERVICE_URI=gs://your-project-agent-you/artifacts
```

**Look at what those replaced.** `sqlite+aiosqlite:///…/sessions.db` became a
Postgres URI. `file://…/artifacts` became `gs://…`. They are the same two flags
you have typed after `adk web` since step 4. The scheme changed; nothing else did.

<aside class="positive">
<b>👀 Developer's Note — <code>postgresql+asyncpg://</code>, not <code>postgresql://</code>.</b> ADK drives SQLAlchemy through its asyncio extension, so the driver has to be an async one and <code>asyncpg</code> has to be installed. Same trap as <code>aiosqlite</code> in step 6, and it fails the same way: fine until the first session write, which in the cloud is at 3am with nobody watching. The <code>host=/cloudsql/…</code> is a unix socket Cloud Run mounts for you, which is why the host looks like a path.
</aside>

### Now deploy, and give it an alarm clock

The services are ready, so the agent can have a permanent home.

👉💻 Three or four minutes. Start it and read on:

```bash
cd ~/longrunningag
./deploy-agent.sh
```

That builds `agent/` into a container, pushes it to Cloud Run, and then wires up
three more things. It is worth knowing what each is for, because "deploy the
agent" is only the first of five steps:

```
1. gcloud run deploy       the container: your agent, the graph, and the page
2. a Pub/Sub topic         a queue for messages
3. a service account       an identity, so the message is allowed in
4. a push subscription     topic ──► /apps/concert/trigger/pubsub
5. a Cloud Scheduler job   the alarm clock, on a cron
```

**Why a scheduler.** In step 3 you wrote `clock.py`: sleep, then POST. It worked
and it dies with your terminal. Cloud Scheduler is the same idea run by Google —
it fires on a cron, retries if the call fails, understands timezones, and does
not care whether your laptop is open. It is the trigger you already built,
living somewhere permanent.

**Why Pub/Sub in the middle.** Cloud Scheduler could call your service directly,
so the topic looks like an extra step. It buys you three things:

```
   Cloud Scheduler ──► Pub/Sub topic ──► push subscription ──► your agent
     fires on a cron    holds the           delivers, and       runs
                        message             retries if the
                                            agent is down
```

**It holds the message.** If the agent is deploying, restarting, or briefly
broken at 3am, the message waits instead of vanishing. **It retries** without you
writing retry logic. And **it fans out**: a second thing that cares about
presales subscribes to the same topic tomorrow without touching the scheduler.

That is also why ADK gives you a trigger endpoint rather than expecting you to
write one — `trigger_sources=["pubsub"]` mounts a route that speaks Pub/Sub's
push format, so the message arrives as an invocation.

```
→ agent    https://concert-you-xxxx.run.app
→ topic    presale-you created
→ iam      concert-trigger@your-project… may invoke concert-you
→ push     → https://concert-you-xxxx.run.app/apps/concert/trigger/pubsub
→ schedule 0 3 * * *
```

<aside class="positive">
<b>👀 Developer's Note — asking for this instead.</b> With the Google Cloud MCP server connected, the five steps above are one request:
<br><br>
<i>"Deploy the folder <code>agent/</code> to Cloud Run in project <code>&lt;my-project&gt;</code> as <code>concert-me</code>, unauthenticated, with these environment variables: … Then create a Pub/Sub topic <code>presale-me</code>, a service account that may invoke the service, a push subscription from the topic to <code>&lt;service-url&gt;/apps/concert/trigger/pubsub</code>, and a Cloud Scheduler job firing the topic at 03:00 UTC daily."</i>
<br><br>
Read the plan before approving. The point of naming all five resources is that you can tell when one is missing.
</aside>

<aside class="negative">
<b>⚠️ Trigger endpoints need Cloud Run or GKE.</b> Agent Runtime does not support scheduled or event-driven triggers, so this is not a choice between deployment targets.
</aside>

### Talk to it

👉 Open the agent's URL in a browser. Not `/panel`, not `:8000` — the service
you just deployed. This is MonsterTix, on the internet, with nothing of your
laptop involved.

It knows nothing about you. The memory file went into the bucket, but this is a
fresh session with no conversation in it.

👉✨ Ask it to book:

```
Book me two tickets for The Midnight Signal. Best seats in the house,
I don't want the cheap ones.
```

**It asks what you are willing to spend**, exactly as it did on your laptop, and
reads the number back before it commits to it.

👉✨ Answer the way you would out loud, then confirm:

```
up to 250 a seat for the good ones
```

That it asks at all is worth a moment, because the obvious implementation of
"don't ask at 3am" breaks it.

`agree_budget` has to know whether anybody is there to answer. The tempting way
to tell it is an environment variable — set `UNATTENDED=1` on the deploy and skip
the question. It is one line and it is the wrong shape:

```
  ONE deployed service, TWO kinds of caller

  your browser  ──► /wake                        somebody is plainly here
  Cloud Sched.  ──► /apps/concert/trigger/pubsub nobody is
```

Both arrive at the same process. A variable read once at boot cannot tell them
apart, so setting it silences the question for the browser too — and you get an
agent that spends a number you never agreed to, which is the one thing the whole
of Module 5 exists to prevent.

**"Is a person here?" is a fact about a request, not about a process.** So the
variable is only the *default* — unattended, the safe assumption for anything a
scheduler can reach — and the `/wake` route, which only ever runs because
somebody typed, overrides it for the length of that one request:

```python
# concert/budget.py
_attended = contextvars.ContextVar("attended", default=None)

def mark_attended(value=True):     # called by /wake, never by the trigger
    _attended.set(value)

def someone_is_there():
    marked = _attended.get()
    return marked if marked is not None else not _UNATTENDED_BY_DEFAULT
```

A `ContextVar` is scoped to the asyncio task, and in FastAPI that is exactly one
request. Two callers, one process, different answers:

| Caller | `someone_is_there()` | What happens |
|---|---|---|
| `adk web` on your laptop | `True` | asks, and confirms |
| MonsterTix `/wake`, deployed | `True` | asks, and confirms |
| Pub/Sub at 3am | `False` | runs on the standing budget, never stops |

👉🔴 Open your venue panel and press **SKIP THE WAIT**, then tell the agent it is
at the front:

```
You're at the front of the queue now.
```

👉 Watch the panel while it buys. One order, in a database on the other side of
the world, placed by a container you never logged into.

### Fire it the way 3am will

👉🔴 Press **RESET THE VENUE** first, so the next order is unambiguous.

👉💻 Publish a message by hand, exactly as the scheduler will at 03:00:

```bash
gcloud scheduler jobs run presale-$(gcloud config get-value account | cut -d@ -f1) \
  --location=us-central1
```

👉🔴 Watch the venue panel and press **SKIP THE WAIT** when a queue ticket appears.

The graph parks at `check_front`, the same as on your laptop. The next scheduled
fire wakes it, so for a demo make the schedule impatient:

```bash
gcloud scheduler jobs update pubsub presale-$(gcloud config get-value account | cut -d@ -f1) \
  --location=us-central1 --schedule="*/5 * * * *"
```

**Nobody typed anything.** Scheduler published, Pub/Sub delivered, ADK routed it
to the graph, and it ran.

### Check the state is really durable

This is the part worth doing, because it is the claim the whole step rests on.

👉💻 Your 3am run, as rows in a database that is not on your laptop:

```bash
gcloud sql connect workshop-sessions --user=adk --database=adk
```

```sql
select id, app_name, user_id from sessions;
select count(*) from events;
```

👉💻 And the memory file, as an object in a bucket:

```bash
gcloud storage cat gs://your-project-agent-you/memory/userx.md | head -20
```

👉 In the Cloud Console, open **Trace**. The run appears as one trace with the
queue wait as a gap in the middle: the agent doing nothing, for exactly as long
as it was supposed to do nothing. `deploy-agent.sh` passed `--trace_to_cloud`,
which is the only reason there is anything to look at.

<aside class="negative">
<b>⚠️ The interrupt that makes step 9 work will hang this one.</b> <code>agree_budget</code> stops the run and asks what you will spend. In front of a browser that is right. At 3am it is fatal: Pub/Sub delivers a message, the graph stops on a question, and nobody types an answer — so nothing is bought and nothing looks broken. That is what <code>someone_is_there()</code> is for: this run has no person behind it, so <code>agree_budget</code> takes the standing budget instead of stopping. <b>Anything that can stop and ask a person needs a way to know whether a person is there — per request, not per process.</b> The queue pause is different and fine — the next scheduled fire answers that one. A clock can answer a clock; only a person can answer a question.
</aside>

<aside class="positive">
<b>👀 Developer's Note — why Pub/Sub caps at ten minutes.</b> A push subscription gives your endpoint a limited window to acknowledge. That is exactly why <code>join_queue</code> returns immediately instead of blocking for forty minutes, and why <code>check_front</code> parks rather than waits. The work has to outlive the request that started it. Every decision in Module 4 was paying for this moment.
</aside>

### Clean up

Two things are deployed: the venue, and the agent beside it. Both scale to zero,
so an idle one costs nothing. Delete them anyway.

```bash
./destroy-agent.sh          # service, topic, subscription, scheduler job
./destroy-venue.sh
```

Those deliberately leave Cloud SQL and the bucket alone, because they hold your
data and **both keep billing**. When you are certain you are finished:

```bash
./destroy-agent.sh --all
```

Everything else is local. Delete the folder when you are done, or keep it. It
runs against your own project for as long as you like.

> **The agent, its tools, its callbacks and the budget did not change. Two URIs
> and one environment variable did.**

---

## What you built, and what to do when it breaks

### The diff between your laptop and production

| Your laptop | In the cloud | What changed |
|---|---|---|
| `--session_service_uri=sqlite+aiosqlite:///…` | Cloud SQL | a connection string |
| `--artifact_service_uri=file://…` | `gs://bucket` | a URI |
| `memory/userx.md` | `gs://bucket/memory/` | a path |
| `adk web` | one Cloud Run service | a `Dockerfile` and a `main.py` |
| `monstertix/clock.py` | Cloud Scheduler → Pub/Sub | `trigger_sources=["pubsub"]` |
| you, at the keyboard | `someone_is_there()` | a default, overridden per request |

**Your `root_agent`, its tools, its callbacks and the budget are unchanged.**
`solutions/step10_deploy/concert/` is byte-for-byte the folder you finished step
9 with. Diff them if you want to see it. That is the argument for ADK's service
abstraction, and it is the last thing worth remembering.

### Everything you just learned, in one place

Ten steps, and each one added exactly one idea. If you remember nothing else,
remember which problem each of these solves.

| The idea | The problem it solves |
|---|---|
| **An instruction is not autonomy** | A prompt is text handed to a model when something calls the agent. It can never be the thing that does the calling. |
| **A trigger and a triggerer** | An endpoint with a Runner behind it, and something separate that knows the time. Keep them apart and only the second one changes when you deploy. |
| **A frontend that is not a dev tool** | `adk web` is for looking inside a run. It does not survive leaving your laptop, and it is not what you hand to a person. |
| **Four places a fact can live** | `temp:` is gone before it is written. Session state is this conversation. `user:` is this person. A memory file is everything you have ever learned. Choosing wrongly is how facts get lost. |
| **Compaction rewrites your history** | The model stops reading what was said and starts reading a summary nobody reviewed. Anything you cannot lose goes somewhere that is never summarised. |
| **`LongRunningFunctionTool` + `ResumabilityConfig`** | The run parks instead of blocking. Nothing loops, nothing burns tokens, and the process can die. |
| **A session store outside the process** | The only reason a parked run can be resumed at all. |
| **`before_tool_callback`** | A gate the call has to pass through, not a request you make of the model. Re-read the world in the instant before you act on it. |
| **Idempotency keys** | Something you did not write will retry your purchase. The venue has to recognise the second one. |
| **`Workflow` graphs** | Steps that must not vary are functions. Steps that need judgement are agents. At 3am nobody notices a model being creative. |
| **`RequestInput` interrupts** | One mechanism for two kinds of waiting: a queue that is not ready, and a person who has not answered. |
| **`rerun_on_resume`** | Which nodes redo themselves when woken. Get it wrong and every wake-up takes another queue ticket. |
| **Bounded authority** | The number came from the person, they confirmed it, and it lives where the conversation cannot reach it. |
| **Attendedness is per request** | The same deployed service serves a browser and a scheduler. Only one of them can answer a question. |
| **Durable state** | A container's filesystem dies with the container. Sessions, memory and artifacts all need somewhere that outlives it. |

### Building your own

The scenario was concert tickets. The shape is not about concerts at all: **a
task that takes longer than a conversation, against a system you do not
control.** Restocking, claims, renewals, migrations, anything with a queue.

Here is a starting prompt for your own. Fill in the four bracketed parts and give
it to your coding assistant:

```
I want to build a long-running agent with Google ADK 2 on Google Cloud.

The job: [what it does, e.g. "watch for a supplier to restock part X
and place an order the moment it appears"]

The waiting: [what it waits for, and how long, e.g. "restock can take
hours; the API returns a job id immediately and I poll it"]

The limits: [what it must never do unattended, e.g. "never spend over
an agreed amount; never order from a supplier not on my list"]

The wake-up: [what tells it to check again, e.g. "a cron every 15 min"]

Build it in this shape:
  - the slow call is a LongRunningFunctionTool so the run parks instead
    of blocking, with ResumabilityConfig on the App
  - a Workflow graph: functions for the steps that must be identical
    every time, agent nodes for the ones needing judgement
  - the wait is a node returning RequestInput, not a sleep loop, with
    rerun_on_resume=False on anything with a side effect
  - the limits are agreed with a person, confirmed back to them, and
    stored in state the conversation cannot reach
  - whether a person is there is a fact about the REQUEST, not the
    process: the chat route says so, the scheduler route does not
  - re-read anything time-sensitive in a before_tool_callback right
    before acting, and send an idempotency key on anything that spends
  - sessions in Cloud SQL, memory and artifacts in Cloud Storage
  - one Cloud Run service serving both a chat page and
    trigger_sources=["pubsub"], woken by Cloud Scheduler

Start with the smallest version that parks and resumes. Add the limits
after that works.
```

The last line matters more than the rest. Everything in this workshop was easy
once the run could stop and start again, and impossible before.

### If you got stuck

Every step has complete working code:

```bash
./use-solution.sh N          # any step. resets memory + sessions + artifacts
./use-solution.sh N --keep   # code only, leave state alone
```

### When something breaks











| Symptom | Fix |
|---|---|
| `✗ Cannot access project` | Wrong id. `rm ~/project_id.txt && ./setup.sh` |
| Model returns 404 | `-latest` aliases are AI Studio only. Use `ADK_MODEL=gemini-2.5-flash` |
| `address already in use` | Something already has port 8000 or 8090. `lsof -ti:8000 \| xargs kill -9` |
| Agent can't reach the venue | `curl $VENUE_URL/health`, or `./deploy-venue.sh` again |
| Queue never advances | Press **SKIP THE WAIT**. At 1× the queue will not reach the front on its own |
| A second queue ticket appears on the panel | You answered in the chat box instead of the `Enter your response...` box on the `adk_request_input` event. The chat box starts a new run |
| Dropdown is empty, or the app will not load | `adk web` treats every folder under `agent/` as an app and fails the whole list if one is not. `ls agent/` should show `concert/` and nothing else — running things from inside `agent/` can leave a stray `memory/` behind. `./use-solution.sh 8` tidies it |
| `[EXPERIMENTAL]` warnings | Expected. `EventsCompactionConfig` and `ResumabilityConfig` are both pre-GA in 2.6.2 |
| Everything is strange | Press **RESET THE VENUE**, then `rm sessions.db` |
| Memory file full of duplicate bookings | `remember()` appends every run. `./use-solution.sh N` resets it, or `cp seed/memory/default.md memory/userx.md` |
| `adk: command not found` | `source .venv/bin/activate` — every new tab needs it |
| Cloud Shell timed out | Start `adk web` again. `sessions.db` survived — which is step 6, happening to you for free |
