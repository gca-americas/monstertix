"""Step 7 — acting on old news, and buying twice.

Two bugs the world causes, and the two fixes. The re-read is a callback; the
deduplication is a header the venue recognises.
"""
from harness import drive, load_step, needs_model


def test_a_callback_runs_before_every_purchase():
    m = load_step("step7_old_news")
    assert m.root_agent.before_tool_callback is not None, \
        "without the callback the seat map is never re-read"


def test_the_callback_only_guards_purchase():
    import inspect
    load_step("step7_old_news")
    from concert import fence
    src = inspect.getsource(fence)
    assert 'tool.name != "purchase"' in src or "tool.name !=" in src


def test_purchase_sends_an_idempotency_key():
    import inspect
    load_step("step7_old_news")
    from concert import tools
    assert "Idempotency-Key" in inspect.getsource(tools.purchase), \
        "without a key the platform's retry buys the tickets twice"


def test_the_venue_deduplicates_on_that_key(venue):
    """The fix, proven against the venue rather than asserted about the code."""
    body = {"event_id": "ms-ams-01", "section": "B", "seats": 2}
    key = {"Idempotency-Key": "test-step7"}
    venue.break_next_purchase()
    venue.c.post("/purchase", json=body, headers=key)      # commits, then 503
    venue.c.post("/purchase", json=body, headers=key)      # the retry
    assert venue.orders == 1, "the key should have suppressed the duplicate"


def test_without_a_key_the_retry_buys_twice(venue):
    """The bug, so the test suite proves the fix is actually doing something."""
    body = {"event_id": "ms-ams-01", "section": "B", "seats": 2}
    venue.break_next_purchase()
    venue.c.post("/purchase", json=body)
    venue.c.post("/purchase", json=body)
    assert venue.orders == 2


@needs_model
def test_it_re_reads_the_seatmap_after_the_wait(venue):
    """It must look at the seat map again before buying, not trust the old one.

    The queue has to be genuinely advanced, not merely claimed in a message. The
    agent is told never to quote or act on a queue position it has not just
    checked, so telling it "you're at the front" while it sits at 14,203 gets
    the correct answer — a refusal — and never reaches the seat map at all.
    """
    m = load_step("step7_old_news")
    t = drive(m.root_agent, [
        "Get us two tickets to the Amsterdam show.",
        venue.skip_the_wait,                   # actually move it to the front
        "You're at the front now — go ahead.",
    ])
    assert "join_queue" in t.calls, "it should take a queue ticket first"
    assert t.calls.count("get_seatmap") >= 1, "it must look again before buying"
