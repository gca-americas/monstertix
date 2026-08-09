"""Step 4 — four places a fact can live.

The codelab has students find session state, user: state, an artifact and a
memory file, and predict which survives. These tests hold the wiring in place so
the exercise still has four different answers to find.
"""
from harness import load_step, needs_model, tool_names, drive


def test_memory_is_a_real_memory_service():
    load_step("step4_open_the_box")
    from concert import memory
    from google.adk.memory import BaseMemoryService
    assert isinstance(memory.memory_service, BaseMemoryService), \
        "step 4 teaches BaseMemoryService — it has to actually be one"


def test_recall_is_async():
    """It awaits search_memory. A sync recall() raises 'asyncio.run() cannot be
    called from a running event loop' the first time a student uses it."""
    import inspect
    load_step("step4_open_the_box")
    from concert import memory
    assert inspect.iscoroutinefunction(memory.recall)


def test_the_agent_can_write_to_all_four_places():
    m = load_step("step4_open_the_box")
    names = tool_names(m.root_agent)
    assert "note_companion" in names   # user: state
    assert "remember" in names          # the memory file
    assert "recall" in names
    assert "get_seatmap" in names       # temp: state + an artifact


def test_get_seatmap_writes_temp_state_and_an_artifact():
    load_step("step4_open_the_box")
    import inspect
    from concert import tools
    src = inspect.getsource(tools.get_seatmap)
    assert "temp:" in src, "the temp: trap is the point of the step"
    assert "save_artifact" in src


@needs_model
def test_seatmap_produces_an_artifact(venue):
    m = load_step("step4_open_the_box")
    t = drive(m.root_agent, ["Show me the seat map for the Amsterdam Saturday show."])
    assert t.called("get_seatmap")
