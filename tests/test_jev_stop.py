"""The Stop hooks' Jev check in the Claude and Codex helpers, against the fake Herdr and a local stand-in for Jev.

Jev's reply here, answers.<question>.noul, has the shape the live endpoint returned.
"""

import io
import json
import os
import runpy
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TAB = ROOT / "claude/hooks/herdr-tab"
CODEX_TAB = ROOT / "codex/skills/herdr/scripts/herdr-tab.py"
WAITING = {"answers": {"waits_on_reader": {"type": "noul", "noul": 0.9}}}
NO = {"answers": {"waits_on_reader": {"type": "noul", "noul": 0.2}}}
DEEP = "[" * 100_000 + "]" * 100_000  # too deep for json before Python 3.14


def claude(herdr, event, payload, **values):
    """Run the Claude helper's hook as Claude Code does, and return its JSON ({} when it prints nothing)."""
    out = herdr.run(TAB, "hook", event, stdin=json.dumps(payload), **values).stdout
    return json.loads(out) if out.strip() else {}


def codex(herdr, env, monkeypatch, capsys, payload, **values):
    """Run the Codex helper's `hook` command on pane p1 and return the JSON it prints for Codex. It runs in this
    process because the test runner isn't a Codex process, so the helper can't find the pane itself."""
    env(**{**herdr.environ, **values})
    helper = runpy.run_path(str(CODEX_TAB))
    helper["main"].__globals__["resolve_hook_pane"] = lambda payload: "p1"
    monkeypatch.setattr(sys, "argv", [str(CODEX_TAB), "hook"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    capsys.readouterr()
    helper["main"]()
    return json.loads(capsys.readouterr().out)


@pytest.fixture(params=["claude", "codex"])
def stop(request, herdr, jev, env, monkeypatch, capsys):
    """Run one helper's Stop hook on a message, and return the hook's JSON."""

    def run(message, event="Stop", **values):
        """Run the Stop hook on `message`, or with event="UserPromptSubmit" Kevin's prompt `message`."""
        values = {"TYPESAFE_API_URL": jev.url, **values}
        text = {"last_assistant_message" if event == "Stop" else "prompt": message}
        if request.param == "claude":
            return claude(herdr, "stop" if event == "Stop" else "prompt", {"session_id": "s1", **text}, **values)
        payload = {"hook_event_name": event, "session_id": "c1", **text}
        return codex(herdr, env, monkeypatch, capsys, payload, **values)

    run.identity = "mine" if request.param == "claude" else "codex"  # the wire fixture's enrollment of s1 or c1
    return run


@pytest.fixture(params=["claude", "codex"])
def start(request, herdr, env, monkeypatch, capsys):
    """Run one helper's SessionStart hook for a resumed session, and return the hook's JSON."""

    def run(**values):
        if request.param == "claude":
            return claude(herdr, "session", {"source": "resume"}, **values)
        payload = {"hook_event_name": "SessionStart", "source": "resume"}
        return codex(herdr, env, monkeypatch, capsys, payload, **values)

    return run


def write_config(tmp_path, text):
    path = tmp_path / ".config/team-floor/config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_without_a_key_nothing_leaves_the_machine(stop, herdr, jev):
    assert stop("Should I merge it now?") == {}
    assert not jev.requests and herdr.label() == "✅ ready"


def test_the_key_can_come_from_the_team_floor_config(stop, jev, tmp_path):
    write_config(tmp_path, '{"jev": {"api_key": "cfg-key"}}')
    jev.reply = NO
    stop("Should I merge it now?")
    assert jev.headers[0]["Authorization"] == "Bearer cfg-key"


def test_jev_sees_only_the_last_1500_characters_and_the_tab_shows_the_question(stop, herdr, jev):
    jev.reply = WAITING
    message = "x" * 5000 + "\nShould I run this on prod?\n```sql\nDELETE FROM jobs;\n```"
    stop(message, TYPESAFE_API_KEY="test-key")
    assert jev.requests[0]["state"] == message[-1500:]
    assert herdr.label() == "❓ Should I run this on prod? · ready"


def test_a_detected_ask_shows_in_agent_wire_until_kevin_answers(stop, herdr, jev, wire):
    jev.reply = WAITING
    stop("Should I merge it now?", TYPESAFE_API_KEY="test-key")
    ask = wire.ask("--to", "Kevin", "--text", "Should I merge it now?", "--kind", "decide", identity=stop.identity)
    assert wire.calls == [ask]
    stop("yes", event="UserPromptSubmit")
    assert herdr.label() == "⏳ ready"
    assert wire.calls == [ask, wire.ask("--clear", identity=stop.identity)]


def test_the_turn_reads_done_before_jev_answers(stop, herdr, jev):
    seen = []
    jev.reply = NO
    jev.before_reply = lambda: seen.append(herdr.label())
    stop("Should I merge it now?", TYPESAFE_API_KEY="test-key")
    assert seen == ["✅ ready"] and herdr.label() == "✅ ready"


@pytest.mark.parametrize(
    "meanwhile, label",
    [
        ("✅ login fix", "❓ Should I merge it now? · login fix"),  # a rename: the ask keeps the new name
        ("❗ approve Bash · login fix", "❗ approve Bash · login fix"),  # another hook's ask wins
        ("⏳ login fix", "⏳ login fix"),  # a new prompt, which only an async Stop hook lets in
    ],
)
def test_jev_only_turns_a_done_tab_into_a_question(stop, herdr, jev, meanwhile, label):
    jev.reply = WAITING
    jev.before_reply = lambda: herdr.set_state(tabs={**herdr.state["tabs"], "t1": meanwhile})
    stop("Should I merge it now?", TYPESAFE_API_KEY="test-key")
    assert herdr.label() == label


@pytest.mark.parametrize("label", ["❓ merge now? · login fix", "🧹 login fix"])  # an ask, or finished
def test_a_flagged_or_clean_tab_skips_jev(stop, herdr, jev, label):
    herdr.set_state(tabs={**herdr.state["tabs"], "t1": label})
    stop("I've left this conversation open. Want me to clear it?", TYPESAFE_API_KEY="test-key")
    assert not jev.requests and herdr.label() == label


def test_a_herdr_hiccup_still_ends_the_turn_done(stop, herdr):
    herdr.set_state(fail_once={"tab get": "raw"})
    stop("Done.")
    assert herdr.label() == "✅ ready"


def test_an_unreadable_config_still_ends_the_turn_done(stop, herdr, jev, tmp_path):
    write_config(tmp_path, DEEP)
    assert stop("Should I merge it now?") == {}
    assert not jev.requests and herdr.label() == "✅ ready"


def test_kevin_hears_once_when_jev_starts_failing(stop, herdr, jev):
    jev.reply = 401
    first = stop("Should I merge it now?", TYPESAFE_API_KEY="test-key")
    second = stop("Should I merge it now?", TYPESAFE_API_KEY="test-key")
    assert "its last call failed: HTTPError 401 at " in first["systemMessage"]
    assert "systemMessage" not in second and herdr.label() == "✅ ready"


def test_session_start_tells_kevin_why_jev_cannot_run(start, tmp_path):
    assert "no usable TypeSafe key" in start()["systemMessage"]
    write_config(tmp_path, DEEP)
    assert "can't read" in start()["systemMessage"]
    assert "systemMessage" not in start(TYPESAFE_API_KEY="test-key")


def test_a_broken_failure_note_never_costs_a_session_its_context(start, env, tmp_path):
    env(HOME=tmp_path)
    note = Path(runpy.run_path(str(TAB))["JEV_FAILED"])
    note.parent.mkdir(parents=True)
    note.write_bytes(b"\xff not text")
    output = start(TYPESAFE_API_KEY="test-key")
    assert "systemMessage" not in output and output["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize(
    "message, ask",
    [
        ("Should I run this on prod?\n\n```sql\nDELETE FROM jobs;\n```", "Should I run this on prod?"),
        ("Run this?\n~~~\nSELECT * FROM jobs WHERE id = ?\n~~~\n    curl https://x.test/api?", "Run this?"),
        ("```\nwhy?\n```\nShip it?", "Ship it?"),
        ("Which do you want?\n1. Merge now\n2. Wait for CI", "Which do you want?"),
        ("Tests pass.\n**Merge it?**", "Merge it?"),
        ("The cache key missed the lockfile. Should I bump it?", "Should I bump it?"),
        ("Should I deploy this to staging vs. prod?", "Should I deploy this to staging vs. prod?"),
        ("Do you want option A (faster; riskier) or B?", "Do you want option A (faster; riskier) or B?"),
        ("Should I take the fix from PR #41, i.e. retry it?", "Should I take the fix from PR #41, i.e. retry it?"),
        (
            "## Why did CI fail?\nThe cache key missed it.\n\nApprove the fix and I'll push it.",
            "Approve the fix and I'll push it.",
        ),
        (
            "Should I refactor it too?\n" + "x" * 1600 + "\nApprove the fix and I'll push it.",
            "Approve the fix and I'll push it.",
        ),
        ("Tell me which you prefer.\n- A\n- B", "Tell me which you prefer."),
        ("- A\n- B", "reply needed"),
    ],
)
def test_the_ask_is_the_last_question_jev_saw(message, ask):
    assert runpy.run_path(str(TAB))["ask_line"](message) == ask


OPTIONS = [
    ("Which do you want?\n1. Merge now\n2. Wait for CI", ["Merge now", "Wait for CI"]),
    (
        "CI is green. How would you like to proceed?\n\nA) **Merge now** (recommended)\nB) Wait for the phone check",
        ["Merge now (recommended)", "Wait for the phone check"],
    ),
    (
        "Two ways to fix it:\n\n- **Bump the cache key**: quick, but it rebuilds everything\n"
        "- **Pin the lockfile**: slower to land\n\nWhich do you prefer?",
        ["Bump the cache key: quick, but it rebuilds everything", "Pin the lockfile: slower to land"],
    ),
    (
        "Which way?\n1. Proceed with the retry\n   It reruns the whole job.\n2. Revert the change",
        ["Proceed with the retry", "Revert the change"],
    ),
    ("Should I:\n1. Retry the job\n2. Revert the change", ["Retry the job", "Revert the change"]),
    ("Do you want 1 or 2?\n1. Ship it\n2. Hold it", ["Ship it", "Hold it"]),
    ("Pick one?\n- " + "x" * 100 + "\n- y", ["x" * 79 + "…", "y"]),
]
NO_OPTIONS = [
    "Should I open the PR?\n\nWhat I did:\n1. Fixed the parser\n2. Added tests",  # done steps, under a label
    "Which should I do next?\n1. Fixed the parser\n2. Added tests",  # done steps, right under a choice
    "- The parser handles tabs\n- Tests cover it\n\nShould I proceed?",  # facts, then a yes/no question
    "Here's what changed:\n- parser\n- tests\n\nWhat do you think?",  # an open question
    "Changes:\n- parser\n- tests\n\nWould you prefer to merge now or wait for review?",  # its own alternatives
    "Which do you want?\n1. Merge now\n2. Wait for CI\n\nI'd merge.",  # the list isn't at the end
    "Which do you want?\n1. A\n2. B\n3. C\n4. D\n5. E",  # more than 4
    "Which do you want?\n1. Merge now",  # one
    "Which do you want?\n1. Merge now\n3. Wait",  # numbering skips
    "Which do you want?\n1. Merge now\n- Wait",  # mixed markers
    "Which do you want?\n- Merge\n  - now\n  - later\n- Wait",  # nested
    "Which do you want?\n- [ ] Merge\n- [ ] Wait",  # a checklist
    "Which do you want?\n- Merge\n- Merge",  # repeats
    "Do this next:\n1. Run the tests\n2. Push",  # instructions, not a choice
    "Merge it?\n1. CI is green\n2. Review is clean",  # a yes/no question with its reasons
    "Which file?\n```\n- a\n- b\n```",  # code
    "## Which one?\n- A\n- B",  # a heading
    "Which one?\n- A\n- B\n\nOr should I wait?",  # the ask shown isn't the one over the list
]


@pytest.mark.parametrize("message, options", OPTIONS)
def test_a_list_of_choices_at_the_end_gives_the_ask_its_options(message, options):
    helper = runpy.run_path(str(TAB))
    assert helper["ask_options"](message, helper["ask_line"](message)) == options


@pytest.mark.parametrize("message", NO_OPTIONS)
def test_anything_less_clear_leaves_the_ask_without_options(message):
    helper = runpy.run_path(str(TAB))
    assert helper["ask_options"](message, helper["ask_line"](message)) == []


def test_a_detected_choice_reaches_agent_wire_with_its_options(stop, herdr, jev, wire):
    jev.reply = WAITING
    stop("Which do you want?\n1. Merge now\n2. Wait for CI", TYPESAFE_API_KEY="test-key")
    ask = ["--to", "Kevin", "--text", "Which do you want?", "--kind", "decide"]
    assert wire.calls == [wire.ask(*ask, "--option=Merge now", "--option=Wait for CI", identity=stop.identity)]
    assert herdr.label() == "❓ Which do you want? · ready"


def test_a_failed_call_counts_as_no_and_says_why_until_one_succeeds(jev, env, tmp_path):
    env(HOME=tmp_path, TYPESAFE_API_KEY="test-key", TYPESAFE_API_URL=jev.url)
    helper = runpy.run_path(str(TAB))
    for reply, why in [
        (401, "HTTPError 401"),
        ({"answers": {}}, "KeyError"),
        ({"answers": {"waits_on_reader": {"noul": float("nan")}}}, "ValueError"),
        ({"answers": {"waits_on_reader": {"noul": "0.9"}}}, "ValueError"),
    ]:
        jev.reply = reply
        assert helper["jev_says_waiting"]("Should I merge it now?") is False
        assert f"its last call failed: {why} at " in helper["jev_warning"]()
    jev.reply = NO
    assert helper["jev_says_waiting"]("Should I merge it now?") is False
    assert helper["jev_warning"]() == ""


def test_a_network_error_says_what_failed(env, tmp_path):
    with socket.socket() as probe:  # a port nothing listens on
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env(HOME=tmp_path, TYPESAFE_API_KEY="test-key", TYPESAFE_API_URL=f"http://127.0.0.1:{port}/v1/systemone")
    helper = runpy.run_path(str(TAB))
    assert helper["jev_says_waiting"]("Should I merge it now?") is False
    assert "its last call failed: URLError ([Errno" in helper["jev_warning"]()


def test_a_redirect_never_takes_the_key_elsewhere(jev, env, tmp_path):
    env(HOME=tmp_path, TYPESAFE_API_KEY="test-key", TYPESAFE_API_URL=jev.url)
    jev.reply = (302, {"Location": jev.url + "/elsewhere"})
    helper = runpy.run_path(str(TAB))
    assert helper["jev_says_waiting"]("Should I merge it now?") is False
    assert len(jev.headers) == 1 and "HTTPError 302" in helper["jev_warning"]()


def test_a_slow_jev_never_holds_the_hook_and_gets_less_time_while_it_stays_slow(jev, env, tmp_path):
    env(HOME=tmp_path, TYPESAFE_API_KEY="test-key", TYPESAFE_API_URL=jev.url)
    helper = runpy.run_path(str(TAB))
    jev.reply = WAITING
    jev.before_reply = lambda: time.sleep(1.5)
    started = time.monotonic()
    assert helper["jev_says_waiting"]("Should I merge it now?", deadline=0.3) is False
    assert time.monotonic() - started < 1
    calls = [thread for thread in threading.enumerate() if thread.name == "jev"]
    assert calls and all(thread.daemon for thread in calls)  # so a call still running can't keep a hook alive
    assert "its last call failed: TimeoutError at " in helper["jev_warning"]()
    note = Path(helper["JEV_FAILED"])
    stamp = note.stat().st_mtime - 60
    os.utime(note, (stamp, stamp))
    started = time.monotonic()
    assert helper["jev_says_waiting"]("Should I merge it now?") is False  # a second, not five
    assert time.monotonic() - started < 1.4
    assert note.stat().st_mtime == stamp  # a timeout while backing off doesn't restart the five minutes
    stamp -= 300
    os.utime(note, (stamp, stamp))
    jev.before_reply = lambda: time.sleep(1.2)
    assert helper["jev_says_waiting"]("Should I merge it now?") is True  # the full deadline again
    assert helper["jev_warning"]() == ""


def test_check_jev_says_whether_the_stop_hook_can_use_jev(herdr, jev):
    def check(**values):
        return herdr.run(TAB, "check-jev", TYPESAFE_API_URL=jev.url, **values).stdout.strip()

    assert "no usable TypeSafe key" in check()
    jev.reply = 401
    assert "its last call failed: HTTPError 401" in check(TYPESAFE_API_KEY="wrong-key")
    jev.reply = NO
    assert check(TYPESAFE_API_KEY="test-key") == "Jev answered, so the Stop hook can ask it."


def test_claude_waits_for_the_stop_hook():
    hooks = json.loads((ROOT / "hooks/claude-hooks.example.json").read_text())["hooks"]["Stop"]
    assert not any(hook.get("async") for entry in hooks for hook in entry["hooks"])
