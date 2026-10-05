import json
import runpy
import sys
from pathlib import Path

import pytest

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


def test_peer_and_task_prompts_keep_the_ask(herdr):
    herdr.run(TAB, "name", "🔍 login bug")
    herdr.run(TAB, "ask", "ship today?")
    for prompt in (
        '<cross-session-message from="eng-1">merged</cross-session-message>',
        "Status from p3: done",
        "<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>",
    ):
        herdr.run(TAB, "hook", "prompt", stdin=json.dumps({"prompt": prompt}))
        assert herdr.label() == "❓ ship today? · 🔍 login bug"
    herdr.run(TAB, "hook", "prompt", stdin=json.dumps({"prompt": "yes, ship it"}))
    assert herdr.label() == "⏳ 🔍 login bug"


def test_codex_helper_tells_kevin_from_peers():
    from_kevin = runpy.run_path(str(CODEX_TAB))["from_kevin"]
    assert from_kevin({"prompt": "yes, ship it"})
    assert not from_kevin({"prompt": "Status from p3: done"})
    assert not from_kevin({"prompt": '<cross-session-message from="x">hi</cross-session-message>'})


@pytest.mark.parametrize(
    "source, before, after",
    [
        ("startup", "❓ merge now? · login fix", "✅ login fix"),  # a new session can't answer the old one's ask
        ("resume", "⏳ login fix", "✅ login fix"),  # the last process ended mid-turn
        ("resume", "❓ merge now? · login fix", "❓ merge now? · login fix"),  # still waiting on Kevin
        ("compact", "⏳ login fix", "⏳ login fix"),  # compaction can come mid-turn
        ("compact", "❓ merge now? · login fix", "❓ merge now? · login fix"),
    ],
)
def test_session_start_clears_only_what_an_ended_session_left(herdr, source, before, after):
    herdr.set_state(tabs={**herdr.state["tabs"], "t1": before})
    herdr.run(TAB, "hook", "session", stdin=json.dumps({"source": source}))
    assert herdr.label() == after


def test_an_ask_on_an_unnamed_tab_does_not_become_its_name(herdr):
    herdr.set_state(tabs={**herdr.state["tabs"], "t1": "⏳"})
    herdr.run(TAB, "ask", "which ticket?")
    assert herdr.label() == "❓ which ticket?"
    herdr.run(TAB, "hook", "prompt", stdin="{}")
    assert herdr.label() == "⏳"


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


def test_codex_helper_keeps_an_ask_until_working(herdr, env, monkeypatch):
    env(**herdr.environ)
    helper = runpy.run_path(str(CODEX_TAB))
    helper["main"].__globals__["resolve_hook_pane"] = lambda payload=None: "p1"

    def run(*args):
        monkeypatch.setattr(sys, "argv", [str(CODEX_TAB), *args])
        helper["main"]()

    run("name", "🛠️ login fix")
    run("ask", "ship today?")
    run("status", "done")
    assert herdr.label() == "❓ ship today? · 🛠️ login fix"
    run("status", "working")
    assert herdr.label() == "⏳ 🛠️ login fix"


def wire_ask(wire, *ask, identity="mine"):
    return ["--state", wire.state, "ask", "--identity", wire.identity(identity), *ask]


def test_an_ask_sets_both_and_kevins_prompt_clears_both(herdr, wire):
    herdr.run(TAB, "name", "🔍 login bug")
    result = herdr.run(TAB, "ask", "ship today?", CLAUDE_CODE_SESSION_ID="s1")
    assert result.returncode == 0, result.stderr
    assert herdr.label() == "❓ ship today? · 🔍 login bug"
    assert wire.calls == [wire_ask(wire, "--to", "Kevin", "--text", "ship today?", "--kind", "decide")]
    herdr.run(TAB, "request", "log in", CLAUDE_CODE_SESSION_ID="s1")
    assert wire.calls[-1] == wire_ask(wire, "--to", "Kevin", "--text", "log in", "--kind", "act")
    herdr.run(TAB, "hook", "prompt", stdin=json.dumps({"session_id": "s1", "prompt": "done"}))
    assert herdr.label() == "⏳ 🔍 login bug"
    assert wire.calls[-1] == wire_ask(wire, "--clear")


def test_a_dialog_answer_clears_both(herdr, wire):
    herdr.run(TAB, "ask", "ship today?", CLAUDE_CODE_SESSION_ID="s1")
    herdr.run(TAB, "hook", "resume", stdin=json.dumps({"session_id": "s1", "tool_name": "AskUserQuestion"}))
    assert wire.calls[-1] == wire_ask(wire, "--clear")


def test_peer_and_task_prompts_clear_neither(herdr, wire):
    herdr.run(TAB, "ask", "ship today?", CLAUDE_CODE_SESSION_ID="s1")
    for prompt in ("<task-notification>\n<status>completed</status>\n</task-notification>", "Status from p3: done"):
        herdr.run(TAB, "hook", "prompt", stdin=json.dumps({"session_id": "s1", "prompt": prompt}))
    assert herdr.label() == "❓ ship today? · ready"
    assert len(wire.calls) == 1


def test_a_prompt_with_nothing_flagged_leaves_agent_wire_alone(herdr, wire):
    herdr.run(TAB, "hook", "prompt", stdin=json.dumps({"session_id": "s1", "prompt": "hi"}))
    assert wire.calls == []


def test_without_agent_wire_only_the_tab_changes(herdr):
    result = herdr.run(TAB, "ask", "ship today?", CLAUDE_CODE_SESSION_ID="s1")
    assert result.returncode == 0, result.stderr
    assert herdr.label() == "❓ ship today? · ready"


def test_an_unenrolled_session_only_changes_the_tab(herdr, wire):
    result = herdr.run(TAB, "ask", "ship today?", CLAUDE_CODE_SESSION_ID="s9")
    assert result.returncode == 0, result.stderr
    assert wire.calls == []


def test_a_failed_mirror_still_flags_the_tab_and_the_command_says_so(herdr, wire):
    wire.fail()
    result = herdr.run(TAB, "ask", "ship today?", CLAUDE_CODE_SESSION_ID="s1")
    assert result.returncode == 1
    assert "no_report" in result.stderr
    assert herdr.label() == "❓ ship today? · ready"
    result = herdr.run(TAB, "hook", "prompt", stdin=json.dumps({"session_id": "s1", "prompt": "yes"}))
    assert result.returncode == 0  # hooks fail open
    assert herdr.label() == "⏳ ready"


def test_codex_helper_mirrors_its_ask(herdr, wire):
    herdr.run(CODEX_TAB, "name", "🛠️ login fix")
    result = herdr.run(CODEX_TAB, "ask", "ship today?", CODEX_THREAD_ID="c1")
    assert result.returncode == 0, result.stderr
    assert wire.calls == [
        wire_ask(wire, "--to", "Kevin", "--text", "ship today?", "--kind", "decide", identity="codex")
    ]
    herdr.run(CODEX_TAB, "status", "working", CODEX_THREAD_ID="c1")
    assert herdr.label() == "⏳ 🛠️ login fix"
    assert wire.calls[-1] == wire_ask(wire, "--clear", identity="codex")
