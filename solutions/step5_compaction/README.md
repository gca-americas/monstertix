# Module 3 — What the summary throws away

**New here**
```python
App(events_compaction_config=EventsCompactionConfig(
        compaction_interval=3, overlap_size=1))   # both fields required
budget_split = Agent(..., include_contents="none", output_key="budget_plan")
```

`compaction_interval` counts **user-initiated invocations, not events**. 3 is
tuned so students see it fire in a few turns; production values are far larger,
or use `token_threshold`.

`adk web` looks for `app` before `root_agent`, so the `App` is what runs.

**The bug:** the summary keeps the gist and drops "Sam bails on weeknights".
**The fix:** load-bearing facts live in `user:` state and the memory file, where
no summarizer can reach them.
