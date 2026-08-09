"""Step 2 — you cannot prompt your way to autonomy.

The step gives the agent `purchase`. It can now buy tickets, and at 10am it
still does not, because nothing calls it. That gap is the whole module: an
instruction is text handed to the model when something invokes the agent, and it
can never be the thing that does the invoking.
"""
from harness import drive, load_step, needs_model, tool_names


def test_it_can_now_buy():
    m = load_step("step2_asleep")
    assert "purchase" in tool_names(m.root_agent), \
        "step 2 hands it the ability to buy, so that doing nothing is the agent's own"


def test_but_it_still_cannot_wait_or_be_woken():
    """No queue, no long-running tool, no resumability. Nothing to wake."""
    from google.adk.tools import LongRunningFunctionTool
    m = load_step("step2_asleep")
    names = tool_names(m.root_agent)
    assert "join_queue" not in names
    assert "check_queue" not in names
    assert not any(isinstance(t, LongRunningFunctionTool) for t in m.root_agent.tools)


def test_nothing_in_the_agent_knows_what_time_it_is():
    """The point students are asked to find: no clock, anywhere.

    Checked against imports rather than the text, because the file legitimately
    uses the word "asleep" to describe the problem it cannot solve.
    """
    import ast, inspect
    load_step("step2_asleep")
    from concert import tools

    imported = set()
    for node in ast.walk(ast.parse(inspect.getsource(tools))):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    for clock in ("time", "sched", "schedule", "asyncio", "datetime"):
        assert clock not in imported, f"step 2 must not know what time it is ({clock})"


@needs_model
def test_it_buys_when_asked_and_only_when_asked(venue):
    m = load_step("step2_asleep")
    assert venue.orders == 0, "nobody asked, so nothing happened"
    t = drive(m.root_agent, ["Buy us two tickets in section C for the Amsterdam Saturday show."])
    assert t.called("purchase")
    assert venue.orders == 1, "it can buy — it just never does it unprompted"
