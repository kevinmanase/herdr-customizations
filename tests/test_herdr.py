import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAB = ROOT / "claude/hooks/herdr-tab"
ORCHESTRATOR = ROOT / "claude/hooks/herdr-orchestrator"
CODEX_TAB = ROOT / "codex/skills/herdr/scripts/herdr-tab.py"


def test_session_hook_tells_the_agent_to_name_its_tab(herdr):
    result = herdr.run(TAB, "hook", "session", stdin='{"source": "startup"}')
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "herdr-tab name" in context
    assert "SendMessage it one line" in context


def test_every_prompt_reminds_the_agent_to_flag_asks(herdr):
    result = herdr.run(TAB, "hook", "remind", stdin="{}")
    assert "herdr-tab ask" in result.stdout


def test_name_keeps_status_and_an_ask_survives_stop(herdr):
    herdr.run(TAB, "name", "🔍 login bug")
    assert herdr.label() == "⏳ 🔍 login bug"
    herdr.run(TAB, "ask", "ship today?")
    assert herdr.label() == "❓ ship today? · 🔍 login bug"
    herdr.run(TAB, "hook", "stop", stdin="{}")
    assert herdr.label() == "❓ ship today? · 🔍 login bug"
    herdr.run(TAB, "hook", "prompt", stdin="{}")
    assert herdr.label() == "⏳ 🔍 login bug"


def test_a_peer_message_keeps_the_ask(herdr):
    herdr.run(TAB, "name", "🔍 login bug")
    herdr.run(TAB, "ask", "ship today?")
    for prompt in ('<cross-session-message from="eng-1">merged</cross-session-message>', "Status from p3: done"):
        herdr.run(TAB, "hook", "prompt", stdin=json.dumps({"prompt": prompt}))
        assert herdr.label() == "❓ ship today? · 🔍 login bug"
    herdr.run(TAB, "hook", "prompt", stdin=json.dumps({"prompt": "yes, ship it"}))
    assert herdr.label() == "⏳ 🔍 login bug"


def test_codex_helper_tells_kevin_from_peers():
    from_kevin = runpy.run_path(str(CODEX_TAB))["from_kevin"]
    assert from_kevin({"prompt": "yes, ship it"})
    assert not from_kevin({"prompt": "Status from p3: done"})
    assert not from_kevin({"prompt": '<cross-session-message from="x">hi</cross-session-message>'})


def test_clear_resets_a_worker_to_ready(herdr):
    herdr.run(TAB, "name", "🛠️ login fix")
    herdr.run(TAB, "hook", "session", stdin='{"source": "clear"}')
    assert herdr.label() == "⚪ ready"


def test_nothing_happens_outside_herdr(herdr):
    herdr.run(TAB, "name", "🔍 login bug", HERDR_ENV="0")
    assert herdr.label() == "⏳ ready"
    assert herdr.state.get("calls", []) == []


def test_who_reports_a_missing_orchestrator(herdr):
    herdr.set_state(agents={})
    result = herdr.run(ORCHESTRATOR, "who")
    assert result.returncode == 1
    assert "no orchestrator" in result.stdout


def test_next_hands_a_brief_to_a_ready_tab(herdr, tmp_path):
    assert herdr.run(ORCHESTRATOR, "next").stdout.strip() == "fleet: queue empty"
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t1": "⚪ ready"},
        panes=[
            {
                "pane_id": "p1",
                "tab_id": "t1",
                "agent": "claude",
                "cwd": str(tmp_path),
                "agent_status": "idle",
            }
        ],
    )
    (tmp_path / "queue" / "01-eng-1.md").write_text("Fix the login bug.")
    result = herdr.run(ORCHESTRATOR, "next")
    assert result.returncode == 0, result.stderr
    calls = herdr.state["calls"]
    assert ["agent", "rename", "p1", "eng-1"] in calls
    assert ["agent", "prompt", "eng-1", "Fix the login bug."] in calls
    assert (tmp_path / "queue" / "started" / "01-eng-1.md").exists()


def test_available_memory_reads_on_this_platform():
    assert runpy.run_path(str(ORCHESTRATOR))["available_mb"]() > 0


def test_codex_helper_keeps_an_ask_until_working(herdr):
    herdr.run(CODEX_TAB, "name", "🛠️ login fix")
    herdr.run(CODEX_TAB, "ask", "ship today?")
    herdr.run(CODEX_TAB, "status", "done")
    assert herdr.label() == "❓ ship today? · 🛠️ login fix"
    herdr.run(CODEX_TAB, "status", "working")
    assert herdr.label() == "⏳ 🛠️ login fix"
