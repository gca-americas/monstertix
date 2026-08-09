# Module 4 — Acting on old news

**New here**
```python
before_tool_callback=refresh_before_purchase      # fence.py
Idempotency-Key: sha256(session:event:section:seats)
```

**Two failures, one act**

*Stale* — press **SELL OUT SECTION A** mid-queue. The agent buys from
`temp:seatmap` anyway. Nothing was missing from context; the wrong thing was
present.

*Repeat* — press **HANG ONCE**. The order commits, the response fails, the
runtime retries, order count hits 2. Neither line of that is student code.

> ADK's own `ResumabilityConfig` docstring: *"Tool call to resume needs to be
> idempotent because we only guarantee an at-least-once behavior once resumed."*

Also new in ADK 2: `runner.rewind_async(rewind_before_invocation_id=...)` to
roll state back to before a bad decision.
