"""Step 6 — the run parks, and survives the process dying.

Two pieces make 'long-running' mean anything, and the step is built on both.
"""
from harness import drive, load_step, needs_model, tool_names


def test_join_queue_is_long_running():
    from google.adk.tools import LongRunningFunctionTool
    m = load_step("step6_pull_the_plug")
    wrapped = [t for t in m.root_agent.tools
               if isinstance(t, LongRunningFunctionTool)]
    assert any(getattr(t, "name", "") == "join_queue" for t in wrapped), \
        "join_queue must be a LongRunningFunctionTool or the run cannot park"


def test_the_app_is_resumable():
    m = load_step("step6_pull_the_plug")
    assert m.app.resumability_config is not None
    assert m.app.resumability_config.is_resumable


def test_it_can_ask_where_it_is_in_line():
    m = load_step("step6_pull_the_plug")
    assert "check_queue" in tool_names(m.root_agent)


@needs_model
def test_joining_the_queue_does_not_block(venue):
    """The agent comes back with a position instead of waiting forty minutes."""
    m = load_step("step6_pull_the_plug")
    t = drive(m.root_agent, ["Get us two tickets to the Amsterdam show."])
    assert t.called("join_queue")
    assert venue.tickets == 1
    assert venue.orders == 0, "it should be waiting, not buying"
