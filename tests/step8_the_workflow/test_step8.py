"""Step 8 — the same agent, surrounded by a graph.

The shape of the graph is the lesson, and two of its nodes must not re-run when
the graph is woken — otherwise every wake-up takes another queue ticket.
"""
from harness import drive, load_step, needs_model


def test_the_root_is_the_graph():
    from google.adk.workflow import Workflow
    m = load_step("step8_the_workflow")
    assert isinstance(m.root_agent, Workflow), \
        "adk web runs root_agent — from step 8 that is the graph"
    assert isinstance(m.app.root_agent, Workflow), \
        "the loader checks `app` first, so it has to point at the graph too"


def test_the_agent_is_reused_not_rebuilt():
    m = load_step("step8_the_workflow")
    assert hasattr(m, "buyer_agent"), \
        "the conversational agent should still be here, renamed"
    from concert import nightly
    assert nightly.buyer_agent is m.buyer_agent, \
        "the graph must import the agent, not build a second one"


def test_the_queue_nodes_do_not_rerun():
    from concert import nightly  # noqa: F401
    load_step("step8_the_workflow")
    from concert import nightly as n
    assert n.queue_up.rerun_on_resume is False, \
        "a second run would take a second queue ticket"
    assert n.check_front.rerun_on_resume is True, \
        "the gate is the one node that MUST run again"


def test_the_agent_no_longer_owns_the_queue():
    from harness import tool_names
    m = load_step("step8_the_workflow")
    names = tool_names(m.buyer_agent)
    assert "join_queue" not in names and "check_queue" not in names, \
        "the graph owns the queue from step 8 on"


@needs_model
def test_it_parks_in_the_queue_and_takes_one_ticket(venue):
    m = load_step("step8_the_workflow")
    t = drive(m.root_agent, ["go"], on_interrupt=lambda msg, tr: None)
    assert t.interrupts, "the run should park on check_front"
    assert venue.tickets == 1
    assert venue.orders == 0


@needs_model
def test_waking_it_does_not_take_a_second_ticket(venue):
    """rerun_on_resume=False, proven rather than asserted."""
    m = load_step("step8_the_workflow")
    seen = {"n": 0}

    def answer(msg, tr):
        seen["n"] += 1
        if seen["n"] == 1:
            return "go"          # wake it once, still queued
        venue.skip_the_wait()
        return "go"              # now let it through

    drive(m.root_agent, ["go"], on_interrupt=answer)
    assert venue.tickets <= 1, "waking the graph must not re-join the queue"
    assert venue.orders == 1
