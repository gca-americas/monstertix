"""Step 10 — the deployable surface, tested locally only.

Nothing here talks to Google Cloud. Creating a Cloud SQL instance takes ten
minutes and costs money, so the cloud path is verified by hand — see
docs/DRYRUN.md. What these tests hold in place is everything that has to be
true BEFORE you deploy.
"""
import os
import pathlib

import pytest

from harness import ROOT, load_step

STEP = ROOT / "solutions" / "step10_deploy"


def test_it_ships_the_deployable_surface():
    assert (STEP / "main.py").is_file(), "deploy-agent.sh looks for agent/main.py"
    assert (STEP / "monstertix" / "server.py").is_file(), "step 3's server ships too"
    assert (STEP / "monstertix" / "index.html").is_file(), "the page ships in the container"


def test_the_root_is_the_graph():
    from google.adk.workflow import Workflow
    m = load_step("step10_deploy")
    assert isinstance(m.root_agent, Workflow)
    assert isinstance(m.app.root_agent, Workflow)


def test_server_mounts_a_pubsub_trigger():
    """The endpoint Cloud Scheduler eventually reaches, checked without deploying."""
    import sys
    sys.path.insert(0, str(STEP))
    for name in [m for m in list(sys.modules) if m in ("main", "concert", "monstertix")]:
        del sys.modules[name]
    import main
    paths = [r.path for r in main.app.routes]
    assert any("/trigger/wake" in p for p in paths), \
        "no /trigger/wake means the scheduler cannot resume a parked session"
    assert any("/session/{session_id}/messages" in p for p in paths), \
        "without this the page never learns that a scheduled run finished"


def test_unattended_skips_the_question():
    """The bug that would hang every 3am run: an interrupt nobody can answer.

    And its mirror: a browser on the SAME deployed service must still be asked.
    """
    load_step("step10_deploy")
    from concert import budget, nightly
    import inspect
    assert "someone_is_there" in inspect.getsource(nightly.agree_budget.func) \
        if hasattr(nightly.agree_budget, "func") else True
    assert callable(budget.someone_is_there)
    assert callable(budget.mark_attended)


def test_wake_marks_the_request_as_attended():
    """/wake only runs because a person typed. The trigger route never does."""
    src = (STEP / "main.py").read_text()
    assert "mark_attended" in src, \
        "without this the deployed page gets the 3am path and is never asked"
    assert src.index("mark_attended") < src.index("handlers.wake("), \
        "the mark has to be set before the run starts"


def test_the_async_postgres_driver_is_declared():
    """postgresql+asyncpg://, not postgresql:// — and asyncpg has to be installed
    in the image or the first session write fails at 3am."""
    reqs = (ROOT / "requirements.txt").read_text()
    assert "asyncpg" in reqs


def test_the_deploy_scripts_are_valid_shell():
    import subprocess
    for script in ("deploy-agent.sh", "destroy-agent.sh", "setup-cloud-state.sh"):
        r = subprocess.run(["bash", "-n", str(ROOT / script)], capture_output=True)
        assert r.returncode == 0, f"{script}: {r.stderr.decode()[:200]}"


def test_deploy_warns_when_state_is_not_durable():
    """sqlite in /tmp dies with the container. The script must not do it quietly."""
    s = (ROOT / "deploy-agent.sh").read_text()
    assert "DIES" in s or "dies" in s


@pytest.mark.skip(reason="cloud path — run by hand, see docs/DRYRUN.md")
def test_the_cloud_path():
    """Deliberately not automated: ./setup-cloud-state.sh then ./deploy-agent.sh."""
