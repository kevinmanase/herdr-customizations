"""Codex labels bind to a foreground process, never an inherited or focused pane."""

import importlib.util
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "codex/skills/herdr/scripts/herdr-tab.py"


@pytest.fixture
def codex(monkeypatch):
    spec = importlib.util.spec_from_file_location("codex_herdr_tab", SCRIPT)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "other")
    monkeypatch.setenv("CODEX_THREAD_ID", "session-1")
    monkeypatch.setattr(helper.os, "getppid", lambda: 200)
    state = {
        "processes": {200: "1 /usr/local/bin/codex"},
        "panes": [
            {"pane_id": "other", "tab_id": "other-tab", "agent": "codex"},
            {"pane_id": "mine", "tab_id": "my-tab", "agent": "codex"},
        ],
        "foreground": {"other": [300], "mine": [200]},
        "tabs": {"other-tab": "⏳ another task", "my-tab": "⏳ 🔍 login fix"},
        "calls": [],
    }

    def ps(args, **kwargs):
        assert args[:3] == ["ps", "-o", "ppid=,command="]
        return SimpleNamespace(stdout=state["processes"][int(args[-1])])

    def herdr(*args, **kwargs):
        state["calls"].append(args)
        match args:
            case ("pane", "list"):
                return {"panes": state["panes"]}
            case ("pane", "process-info", "--pane", pane):
                return {"process_info": {"foreground_processes": [{"pid": pid} for pid in state["foreground"][pane]]}}
            case ("pane", "get", pane):
                return {"pane": next(item for item in state["panes"] if item["pane_id"] == pane)}
            case ("tab", "get", tab):
                return {"tab": {"label": state["tabs"][tab]}}
            case ("tab", "rename", tab, label):
                state["tabs"][tab] = label
                return {}
            case ("notification", *_):
                return {}
        raise AssertionError(f"unexpected Herdr call: {args}")

    monkeypatch.setattr(helper.subprocess, "run", ps)
    monkeypatch.setattr(helper, "herdr", herdr)
    monkeypatch.setattr(helper, "session_role", lambda: (False, "Role context."))
    monkeypatch.setattr(helper, "jev_warning", lambda: "")
    return helper, state


def label_writes(state):
    return [call for call in state["calls"] if call[:2] in (("tab", "rename"), ("notification", "show"))]


@pytest.mark.parametrize("inherited", ["missing", "other", ""])
def test_explicit_name_uses_foreground_pane_despite_stale_or_missing_environment(codex, monkeypatch, inherited):
    helper, state = codex
    monkeypatch.setenv("HERDR_PANE_ID", inherited)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "name", "🧪 login fix"])

    helper.main()

    assert state["tabs"]["my-tab"] == "⏳ 🧪 login fix"
    assert state["tabs"]["other-tab"] == "⏳ another task"
    assert label_writes(state) == [("tab", "rename", "my-tab", "⏳ 🧪 login fix")]


def test_foreground_binding_works_without_native_session_metadata(codex):
    helper, state = codex
    state["panes"][1].pop("agent")

    assert helper.resolve_hook_pane({"session_id": "session-1"}) == "mine"
    assert helper.resolve_hook_pane() == "mine"


@pytest.mark.parametrize("runtime", ["app-server", "ambiguous", "unmatched", "not-codex"])
@pytest.mark.parametrize(
    "command", [["name", "🧪 login fix"], ["status", "done"], ["ask", "ship?"], ["request", "sign in"]]
)
def test_explicit_label_commands_refuse_uncertain_targets(codex, monkeypatch, capsys, runtime, command):
    helper, state = codex
    if runtime == "app-server":
        state["processes"][200] = "1 /usr/local/bin/codex app-server"
    elif runtime == "ambiguous":
        state["foreground"]["other"] = [200]
    elif runtime == "unmatched":
        state["foreground"]["mine"] = [400]
    else:
        state["processes"][200] = "1 /usr/bin/python3"
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), *command])

    with pytest.raises(SystemExit) as error:
        helper.main()

    assert error.value.code == 1
    assert "Cannot bind this Codex process" in capsys.readouterr().err
    assert label_writes(state) == []


def test_a_stage_rename_keeps_the_pending_ask(codex, monkeypatch):
    helper, state = codex
    state["tabs"]["my-tab"] = "❓ ship today? · 🔍 login fix"
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "name", "🧪 login fix"])

    helper.main()

    assert state["tabs"]["my-tab"] == "❓ ship today? · 🧪 login fix"


@pytest.mark.parametrize("event", ["SessionStart", "UserPromptSubmit"])
def test_bound_root_gets_exact_name_and_stage_commands(codex, event):
    helper, _ = codex

    output = helper.hook({"hook_event_name": event, "session_id": "session-1", "source": "resume"})

    context = output["hookSpecificOutput"]["additionalContext"]
    assert f'python3 "{SCRIPT}" name "🔍 <short task>"' in context
    for stage in ("🛠️", "🧪", "👀", "🚀"):
        assert f'"{stage} <short task>"' in context


@pytest.mark.parametrize("event", ["SessionStart", "UserPromptSubmit"])
@pytest.mark.parametrize("failure", ["app-server", "discovery-error", "session-mismatch"])
def test_unbound_root_keeps_targeted_context_without_commands_or_writes(codex, monkeypatch, event, failure):
    helper, state = codex
    if failure == "app-server":
        state["processes"][200] = "1 /usr/local/bin/codex app-server"
    elif failure == "discovery-error":

        def fail(*args, **kwargs):
            raise RuntimeError("pane discovery failed")

        monkeypatch.setattr(helper, "herdr", fail)
    else:
        monkeypatch.setenv("CODEX_THREAD_ID", "another-session")

    output = helper.hook({"hook_event_name": event, "session_id": "session-1", "source": "startup"})

    context = output["hookSpecificOutput"]["additionalContext"]
    assert "automatic labels were skipped" in context
    assert "inherited pane IDs" in context
    assert "python3" not in context
    assert label_writes(state) == []


@pytest.mark.parametrize("event", ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"])
def test_subagent_hook_never_adopts_the_parent_tab(codex, event):
    helper, state = codex

    assert helper.hook({"hook_event_name": event, "session_id": "session-1", "agent_id": "child-1"}) == {}
    assert state["calls"] == []


def test_hook_discovery_errors_still_produce_valid_json(codex, monkeypatch, capsys):
    helper, state = codex

    def fail(payload=None):
        raise RuntimeError("pane discovery failed")

    monkeypatch.setattr(helper, "resolve_hook_pane", fail)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "hook"])
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"hook_event_name":"UserPromptSubmit","session_id":"session-1"}'))

    helper.main()

    assert '"hookEventName": "UserPromptSubmit"' in capsys.readouterr().out
    assert label_writes(state) == []


def test_an_explicit_discovery_error_is_reported_without_label_writes(codex, monkeypatch, capsys):
    helper, state = codex

    def fail(payload=None):
        raise RuntimeError("pane discovery failed")

    monkeypatch.setattr(helper, "resolve_hook_pane", fail)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "status", "working"])

    with pytest.raises(SystemExit) as error:
        helper.main()

    assert error.value.code == 1
    assert "pane discovery failed" in capsys.readouterr().err
    assert label_writes(state) == []


def test_an_ask_is_mirrored_into_agent_wire_and_working_clears_it(codex, monkeypatch):
    helper, state = codex
    asks = []
    monkeypatch.setattr(helper, "wire_ask", lambda *args: asks.append(args[:4]) or "")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "ask", "ship today?"])
    helper.main()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "status", "working"])
    helper.main()

    assert state["tabs"]["my-tab"] == "⏳ 🔍 login fix"
    assert asks == [("codex", "session-1", "ship today?", "decide"), ("codex", "session-1", "", "")]


def test_an_asks_options_reach_agent_wire_and_a_bad_list_changes_nothing(codex, monkeypatch, capsys):
    helper, state = codex
    asks = []
    monkeypatch.setattr(helper, "wire_ask", lambda *args: asks.append(args) or "")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "ask", "ship today?", "--option", "yes", "--option", "no"])
    helper.main()
    assert asks == [("codex", "session-1", "ship today?", "decide", ["yes", "no"])]

    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "ask", "merge now?", "--option", "yes"])
    with pytest.raises(SystemExit) as error:
        helper.main()
    assert error.value.code == 1
    assert "2 to 4 options" in capsys.readouterr().err
    assert state["tabs"]["my-tab"] == "❓ ship today? · 🔍 login fix"
    assert len(asks) == 1


def test_agent_wire_clears_whenever_a_command_leaves_the_tab_without_an_ask(codex, monkeypatch):
    # #23: `status ready` drops the tab's ask, and a retried `status working` finds none left on the tab.
    helper, state = codex
    asks = []
    monkeypatch.setattr(helper, "wire_ask", lambda *args: asks.append(args[:4]) or "")

    def run(*args):
        monkeypatch.setattr(sys, "argv", [str(SCRIPT), *args])
        helper.main()

    run("ask", "ship today?")
    run("status", "ready")
    assert state["tabs"]["my-tab"] == "⚪ ready"
    run("status", "working")
    run("name", "🔍 login fix")
    run("ask", "ship today?")
    run("status", "clean")
    assert state["tabs"]["my-tab"] == "🧹 🔍 login fix"
    assert asks == [
        ("codex", "session-1", "ship today?", "decide"),
        ("codex", "session-1", "", ""),
        ("codex", "session-1", "", ""),
        ("codex", "session-1", "ship today?", "decide"),
        ("codex", "session-1", "", ""),
    ]
