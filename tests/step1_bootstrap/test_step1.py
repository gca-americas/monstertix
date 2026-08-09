"""Step 1 — a good agent that cannot do anything about time.

The codelab's claim: it searches the tour and reads seat maps, and that is all
it can do. If it grew a way to buy or wait, the step would stop making its point.
"""
from harness import drive, load_step, needs_model, tool_names


def test_has_only_the_two_read_only_tools():
    m = load_step("step1_bootstrap")
    assert set(tool_names(m.root_agent)) == {"search_events", "get_seatmap"}


def test_cannot_buy_or_wait():
    m = load_step("step1_bootstrap")
    names = tool_names(m.root_agent)
    for forbidden in ("purchase", "join_queue", "check_queue"):
        assert forbidden not in names, f"step 1 must not be able to {forbidden}"


@needs_model
def test_it_can_talk_about_the_tour(venue):
    m = load_step("step1_bootstrap")
    t = drive(m.root_agent, ["What Amsterdam dates are there?"])
    assert t.called("search_events")
    assert venue.orders == 0, "step 1 must not be able to buy anything"
