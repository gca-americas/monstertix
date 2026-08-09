"""Step 5 — what the summary throws away.

Compaction has to be ON and configured, or there is nothing to look at. Both
fields are required by ADK and neither has a default, which is the trap.
"""
from harness import load_step, tool_names


def test_compaction_is_configured():
    m = load_step("step5_compaction")
    cfg = m.app.events_compaction_config
    assert cfg is not None, "no compaction means step 5 has nothing to show"
    assert cfg.compaction_interval > 0
    assert cfg.overlap_size > 0, "overlap_size has no default — ADK requires it"


def test_budget_split_cannot_see_the_conversation():
    """include_contents='none' is what makes the sub-agent worth demonstrating."""
    m = load_step("step5_compaction")
    sub = next((t.agent for t in m.root_agent.tools
                if hasattr(t, "agent") and t.agent.name == "budget_split"), None)
    assert sub is not None, "budget_split should be an AgentTool here"
    assert sub.include_contents == "none"
    assert sub.output_key, "it writes to state under output_key"
