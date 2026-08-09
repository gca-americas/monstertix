# Module 5 — Draw the flow in advance

The same job as Module 4, with the conversation taken out.

```
START ─► pick_show ─► queue_up ─► verify_and_buy ─► report
         (function)   (function)   (function)        (agent)
          0 LLM        0 LLM        0 LLM             1 LLM
```

**The demo:** `python -m concert.nightly`, press SKIP THE WAIT when it queues,
and read the breakfast message it writes. Then open `nightly` in `adk web` and
watch each node's input and output in the Events tab.

**What is new:** `concert/nightly.py` — an ADK 2 `Workflow`, and a `nightly/`
package so `adk web` can serve the graph. `concert/agent.py` is untouched.

The graph does **not** call the functions in `tools.py`. It shares `venue.py`,
`memory.py` and `config.py`, and does the venue calls itself. That is not an
oversight — see the codelab. Every tool except `search_events` takes a
`ToolContext`, and a graph node has no such thing.

**The point:** at 3am nobody is there to notice the model picked a Tuesday. Four
nodes, one model call, and the model call is the part that genuinely needs
language. Everything upstream is arithmetic, so it is code, and code does the
same thing every night.

Limits are constants at the top of the file. Module 5 replaces them with an
envelope a person can change and the agent has to ask about.
