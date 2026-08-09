# Module 4 — Pull the plug

**New here**
```python
LongRunningFunctionTool(func=join_queue)          # returns immediately
ResumabilityConfig(is_resumable=True)             # pause + resume
plugins=[PanelPlugin()]                           # feed the control panel
```

Run it with a real session store or none of this survives:
```bash
adk web agent --session_service_uri="sqlite:///sessions.db" \
              --artifact_service_uri="file://./artifacts"
```

**The demo:** queue up, kill the agent, restart, still holding the ticket. Then
`sqlite3 sessions.db "select * from events limit 5"`.

The agent was not running for those forty minutes. It was gone, and the venue's
webhook brought it back — `join_queue` hands the venue an opaque wake payload,
so the venue can resume an ADK session while knowing nothing about ADK.
