"""Step 9 — a graph that stops and asks a person a question.

The interrupt is the same primitive as the queue wait, pointed at a human. And
the budget is session-scoped on purpose: it is agreed for this booking, not for
every booking this person will ever make.
"""
from harness import SOLUTIONS, drive, load_step, needs_model


def test_the_budget_node_runs_first_and_reruns():
    load_step("step9_the_budget")
    from concert import nightly as n
    assert n.agree_budget.rerun_on_resume is True, \
        "it has to run again to see the answer"
    edges = str(n.nightly.edges)
    assert edges.index("agree_budget") < edges.index("open_the_night"), \
        "the answer to an interrupt goes to the node after START"


def test_the_interrupt_ids_are_stable():
    """A fresh uuid per run cannot be looked up in ctx.resume_inputs."""
    load_step("step9_the_budget")
    from concert import nightly as n
    assert isinstance(n.ASK_BUDGET, str) and n.ASK_BUDGET
    assert isinstance(n.CONFIRM_BUDGET, str) and n.CONFIRM_BUDGET
    assert n.ASK_BUDGET != n.CONFIRM_BUDGET


def test_the_budget_is_session_scoped_not_user_scoped():
    """A new session should ask again. `user:` would mean it never does."""
    load_step("step9_the_budget")
    from concert import budget
    assert budget.load({"budget": "up to $100"}) == "up to $100"
    assert budget.load({"user:budget": "up to $250"}) == "", \
        "user: state would outlive the booking it was agreed for"
    assert budget.load({}) == "", "a fresh session has nothing agreed"


def test_a_written_budget_is_readable_back():
    load_step("step9_the_budget")
    from concert import budget
    state = {}
    state["budget"] = "up to $100 for the cheap seats"
    assert budget.load(state).startswith("up to $100")


def test_unattended_never_asks():
    """At 3am a question parks the run forever and nothing is ever bought."""
    load_step("step9_the_budget")
    from concert import budget
    assert hasattr(budget, "someone_is_there")
    assert hasattr(budget, "mark_attended")


def test_attendedness_is_per_request_not_per_process():
    """The deployed service handles both kinds of caller, so one flag cannot do.

    A browser has a person behind it; a Pub/Sub push does not. The service is
    the same process for both, so the answer has to travel with the request.
    """
    import importlib.util
    import os

    def fresh():
        path = SOLUTIONS / "step9_the_budget" / "concert" / "budget.py"
        spec = importlib.util.spec_from_file_location("b_probe", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    os.environ.pop("UNATTENDED", None)
    laptop = fresh()
    assert laptop.someone_is_there(), "adk web on a laptop must ask"

    os.environ["UNATTENDED"] = "1"
    try:
        cloud = fresh()
        assert not cloud.someone_is_there(), "a 3am Pub/Sub push must not ask"
        cloud.mark_attended()
        assert cloud.someone_is_there(), \
            "a browser hitting /wake on the SAME deployed service must ask"
    finally:
        os.environ.pop("UNATTENDED", None)


def test_the_buyer_agent_never_asks_for_a_budget():
    """It is the last node of an unattended run. A question there hangs it."""
    m = load_step("step9_the_budget")
    text = m.buyer_agent.instruction.lower()
    assert "never ask" in text
    assert "join_queue" not in text, "the graph already queued"


@needs_model
def test_it_asks_reads_back_then_buys(venue):
    m = load_step("step9_the_budget")
    answers = ["About a hundred for the cheap seats. Two-fifty if they're the good ones.",
               "Yes, that's right."]

    def answer(msg, tr):
        if answers:
            return answers.pop(0)
        venue.skip_the_wait()
        return "go"

    t = drive(m.root_agent, ["go"], on_interrupt=answer)
    assert len(t.interrupts) >= 2, "it should ask, then read back before storing"
    assert venue.orders == 1
    assert venue.tickets == 0, "buying should release the queue place"


@needs_model
def test_a_new_session_asks_again(venue):
    """The point of session scope, proven twice over."""
    m = load_step("step9_the_budget")
    first = drive(m.root_agent, ["go"], on_interrupt=lambda msg, tr: None)
    second = drive(m.root_agent, ["go"], on_interrupt=lambda msg, tr: None)
    assert first.interrupts and second.interrupts
    assert "willing to spend" in second.interrupts[0].lower(), \
        "a new session must not inherit the previous budget"
