"""Lanes, Jev routing and lane leads, against the fake Herdr and a local stand-in for Jev.

The Jev reply in fixtures/jev-choice.json follows the choice response documented at
docs.typesafe.ai (quick start and API reference): answers.<question> holds `type`, `choice`,
`confidence` and `probabilities`. It wasn't checked against a live key.
"""

import inspect
import json
import runpy
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR = ROOT / "claude/hooks/herdr-orchestrator"
TAB = ROOT / "claude/hooks/herdr-tab"
CODEX_TAB = ROOT / "codex/skills/herdr/scripts/herdr-tab.py"
HELPERS = [TAB, CODEX_TAB]
COPIES = [ORCHESTRATOR, *HELPERS]
LANES = {
    "lanes": [
        {"id": "api", "name": "API", "about": "Server endpoints, webhooks, database"},
        {"id": "mobile", "name": "Mobile", "about": "iOS and Android apps"},
    ]
}


@pytest.fixture
def lanes(tmp_path):
    path = tmp_path / ".config/team-floor/lanes.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(LANES))
    return path


@pytest.fixture
def queue(tmp_path):
    folder = tmp_path / "queue"
    folder.mkdir()
    return folder


@pytest.fixture
def grouping_cli(herdr, tmp_path):
    folder = tmp_path / "bin"
    folder.mkdir()
    log = tmp_path / "groups-calls.jsonl"
    command = folder / "herdr-groups"
    command.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"with open({str(log)!r}, 'a') as output: output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if os.environ.get('GROUPS_TEST_FAIL'): sys.stderr.write('grouping unavailable'); sys.exit(1)\n"
    )
    command.chmod(0o755)
    herdr.environ["PATH"] = f"{folder}:{herdr.environ['PATH']}"
    return log


@pytest.mark.parametrize("lane,supervisor", [(None, "orchestrator"), ("api", "api-lead")])
def test_a_new_worker_is_grouped_under_its_explicit_supervisor(herdr, queue, grouping_cli, lane, supervisor):
    folder = queue / lane if lane else queue
    folder.mkdir(exist_ok=True)
    (folder / "01-task.md").write_text("Fix the login bug.")
    result = herdr.run(ORCHESTRATOR, "next", *(["--lane", lane] if lane else []))
    assert result.returncode == 0, result.stderr
    assert json.loads(grouping_cli.read_text()) == ["assign", "task", supervisor]
    assert prompts(herdr, "task")


def test_a_missing_grouping_cli_warns_once_and_starts_the_task(herdr, queue):
    (queue / "01-task.md").write_text("Fix the login bug.")
    result = herdr.run(ORCHESTRATOR, "next")
    assert result.returncode == 0, result.stderr
    assert result.stderr.count("herdr-groups is not on the PATH") == 1
    assert prompts(herdr, "task")


def test_a_grouping_failure_does_not_stop_the_queued_task(herdr, queue, grouping_cli):
    (queue / "01-task.md").write_text("Fix the login bug.")
    result = herdr.run(ORCHESTRATOR, "next", GROUPS_TEST_FAIL="1")
    assert result.returncode == 0, result.stderr
    assert "grouping task failed: grouping unavailable" in result.stderr
    assert prompts(herdr, "task")
    assert (queue / "started/01-task.md").exists()


def test_a_new_lead_groups_the_lanes_existing_workers(herdr, lanes, queue, grouping_cli):
    (queue / "api/started").mkdir(parents=True)
    (queue / "api/started/01-worker.md").write_text("Already started.")
    for index in range(2, 5):
        (queue / f"api/{index:02d}-task-{index}.md").write_text("Queued.")
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t2": "⏳ worker"},
        agents={**herdr.state["agents"], "worker": {"pane_id": "p2", "tab_id": "t2"}},
        panes=[*herdr.state["panes"], {"pane_id": "p2", "tab_id": "t2", "agent": "claude"}],
    )
    result = herdr.run(ORCHESTRATOR, "leads")
    assert result.returncode == 0, result.stderr
    assert [json.loads(line) for line in grouping_cli.read_text().splitlines()] == [
        ["assign", "api-lead", "orchestrator"],
        ["assign", "worker", "api-lead"],
    ]


def test_a_failed_optional_worker_survey_cannot_leave_a_lead_without_its_brief(monkeypatch, tmp_path, capsys):
    start = runpy.run_path(str(ORCHESTRATOR))["start_lead"]
    calls = []
    for name, value in {
        "QUEUE": str(tmp_path),
        "locked": lambda *args: nullcontext(),
        "agent_named": lambda *args: None,
        "labelled_panes": lambda *args: [],
        "start_session": lambda *args: "p2",
        "group_session": lambda *args: True,
        "herdr": lambda *args, **options: calls.append(args),
    }.items():
        monkeypatch.setitem(start.__globals__, name, value)

    def unavailable(*args):
        raise RuntimeError("agent list unavailable")

    monkeypatch.setitem(start.__globals__, "lane_items", unavailable)
    assert start(LANES["lanes"][0]) == (0, "started api-lead in pane p2")
    assert calls[0][:3] == ("agent", "prompt", "api-lead")
    assert "You are api-lead" in calls[0][3]
    assert "workers failed: agent list unavailable" in capsys.readouterr().err


def test_handback_groups_the_remaining_worker_under_the_orchestrator(herdr, lanes, queue, grouping_cli):
    be_lead(herdr)
    (queue / "api/started").mkdir(parents=True)
    (queue / "api/started/01-worker.md").write_text("Already started.")
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t2": "⏳ worker"},
        agents={**herdr.state["agents"], "worker": {"pane_id": "p2", "tab_id": "t2"}},
        panes=[*herdr.state["panes"], {"pane_id": "p2", "tab_id": "t2", "agent": "claude"}],
    )
    result = herdr.run(ORCHESTRATOR, "handback", "api")
    assert result.returncode == 0, result.stderr
    assert json.loads(grouping_cli.read_text()) == ["assign", "worker", "orchestrator"]


def route(herdr, jev, brief, key="test-key"):
    return herdr.run(ORCHESTRATOR, "route", str(brief), TYPESAFE_API_KEY=key, TYPESAFE_API_URL=jev.url)


def started(herdr):
    return [call[2] for call in herdr.state.get("calls", []) if call[:2] == ["agent", "start"]]


def prompts(herdr, name):
    return [call[3] for call in herdr.state["calls"] if call[:3] == ["agent", "prompt", name]]


def test_a_sure_pick_routes_to_the_lane(herdr, jev, lanes, queue):
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix the Stripe webhook retries.")
    result = route(herdr, jev, brief)
    assert result.returncode == 0, result.stderr
    assert "lane: api, probability: 0.85, rule: route (>= 0.60)" in result.stdout
    assert not brief.exists()
    assert (queue / "api/01-webhook-fix.md").read_text() == "Fix the Stripe webhook retries."
    question = jev.requests[0]["questions"]["lane"]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {"api", "mobile", "unclear"}
    assert jev.requests[0]["model"] == "jev-latest"
    assert jev.headers[0]["Authorization"] == "Bearer test-key"


def test_jev_gets_only_the_last_1500_characters(herdr, jev, lanes, queue):
    brief = queue / "01-big.md"
    brief.write_text("x" * 5000 + "tail")
    route(herdr, jev, brief)
    state = jev.requests[0]["state"]
    assert len(state) == 1500
    assert state.endswith("tail")


def test_a_middling_pick_routes_and_marks_the_brief(herdr, jev, lanes, queue):
    jev.answer("mobile", {"api": 0.4, "mobile": 0.52, "unclear": 0.08})
    brief = queue / "01-push.md"
    brief.write_text("Push notifications drop on resume.")
    result = route(herdr, jev, brief)
    assert result.returncode == 0, result.stderr
    assert "lane: mobile, probability: 0.52, rule: confirm" in result.stdout
    text = (queue / "mobile/01-push.md").read_text()
    assert text.startswith("Lane to confirm:")
    assert text.endswith("Push notifications drop on resume.")


@pytest.mark.parametrize(
    "choice, probabilities, why",
    [
        ("api", {"api": 0.39, "mobile": 0.35, "unclear": 0.26}, "below 0.40; Jev leaned api"),
        ("unclear", {"api": 0.05, "mobile": 0.05, "unclear": 0.9}, "Jev said unclear"),
    ],
)
def test_a_weak_or_unclear_pick_asks_kevin(herdr, jev, lanes, queue, choice, probabilities, why):
    jev.answer(choice, probabilities)
    brief = queue / "01-vague.md"
    brief.write_text("Make it better.")
    result = route(herdr, jev, brief)
    assert result.returncode == 3
    assert f"lane: none, probability: {probabilities[choice]:.2f}, rule: ask Kevin ({why})" in result.stdout
    assert brief.exists()
    assert herdr.label().startswith("❓ which lane for 01-vague?")


def test_routing_without_a_key_sends_nothing_and_asks_kevin(herdr, jev, lanes, queue):
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix the Stripe webhook retries.")
    result = route(herdr, jev, brief, key="")
    assert result.returncode == 3
    assert "probability: -, rule: ask Kevin (Jev unavailable: no TypeSafe key)" in result.stdout
    assert jev.requests == []
    assert brief.exists()
    assert herdr.label().startswith("❓")


def write_config(tmp_path, data):
    path = tmp_path / ".config/team-floor/config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize("env_key, sent", [("", "cfg-key"), ("env-key", "env-key")])
def test_routing_takes_the_key_from_the_environment_then_the_config(herdr, jev, lanes, queue, tmp_path, env_key, sent):
    write_config(tmp_path, {"jev": {"api_key": " cfg-key "}})
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix the Stripe webhook retries.")
    result = route(herdr, jev, brief, key=env_key)
    assert result.returncode == 0, result.stderr
    assert jev.headers[0]["Authorization"] == f"Bearer {sent}"


@pytest.mark.parametrize("reply", [529, {"answers": {}}])
def test_a_jev_error_never_blocks_routing(herdr, jev, lanes, queue, reply):
    jev.reply = reply
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix the Stripe webhook retries.")
    result = route(herdr, jev, brief)
    assert result.returncode == 3
    assert "rule: ask Kevin (Jev unavailable:" in result.stdout
    assert brief.exists()


def test_routing_never_follows_a_redirect(herdr, jev, lanes, queue):
    jev.reply = (302, {"Location": jev.url + "/elsewhere"})
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix the Stripe webhook retries.")
    result = route(herdr, jev, brief)
    assert result.returncode == 3 and "HTTPError" in result.stdout
    assert len(jev.headers) == 1  # the key went nowhere else


def test_routing_needs_the_lane_list(herdr, jev, queue):
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix it.")
    result = route(herdr, jev, brief)
    assert result.returncode == 2
    assert "no lanes" in result.stderr
    assert jev.requests == []


def test_a_bad_lane_id_is_skipped(herdr, jev, lanes, queue):
    lanes.write_text(json.dumps({"lanes": [*LANES["lanes"], {"id": "unclear"}, {"id": "misc"}, {"id": "Bad Id"}]}))
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix it.")
    result = route(herdr, jev, brief)
    assert result.returncode == 0, result.stderr
    assert set(jev.requests[0]["questions"]["lane"]["criteria"]) == {"api", "mobile", "unclear"}
    assert "skipping" in result.stderr


def test_the_fourth_brief_starts_a_lead_and_only_one(herdr, jev, lanes, queue):
    (queue / "api").mkdir()
    for n in range(1, 4):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    brief = queue / "04-task-4.md"
    brief.write_text("Task 4.")
    result = route(herdr, jev, brief)
    assert result.returncode == 0, result.stderr
    assert "api: 4 queued, 0 open; started api-lead" in result.stdout
    assert started(herdr) == ["api-lead"]
    lead = herdr.state["agents"]["api-lead"]
    assert herdr.label(lead["tab_id"]) == "🧭 api-lead"
    (brief_text,) = prompts(herdr, "api-lead")
    assert f"{queue / 'api'}" in brief_text
    assert "next --lane api" in brief_text
    assert "role: lead lane: api" in brief_text
    assert "never clear it" in brief_text

    result = herdr.run(ORCHESTRATOR, "leads")
    assert f"api: 4 queued, 0 open; api-lead in tab {lead['tab_id']}" in result.stdout
    assert "mobile: 0 queued, 0 open; no lead" in result.stdout
    assert started(herdr) == ["api-lead"]


def test_jev_unavailable_starts_no_lead(herdr, jev, lanes, queue):
    (queue / "api").mkdir()
    for n in range(1, 4):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    brief = queue / "04-task-4.md"
    brief.write_text("Task 4.")
    result = route(herdr, jev, brief, key="")
    assert result.returncode == 3
    assert started(herdr) == []


def ready_tab(herdr, tmp_path):
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t2": "⚪ ready"},
        panes=[
            *herdr.state["panes"],
            {"pane_id": "p2", "tab_id": "t2", "agent": "claude", "cwd": str(tmp_path), "agent_status": "idle"},
        ],
    )


def test_a_lead_reuses_a_ready_tab(herdr, lanes, queue, tmp_path):
    ready_tab(herdr, tmp_path)
    (queue / "api").mkdir()
    for n in range(1, 5):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    result = herdr.run(ORCHESTRATOR, "leads")
    assert "started api-lead in pane p2" in result.stdout
    assert herdr.state["agents"]["api-lead"]["pane_id"] == "p2"
    assert herdr.label("t2") == "🧭 api-lead"
    assert started(herdr) == []


def test_open_sessions_count_until_merged_or_parked(herdr, lanes, queue):
    (queue / "api/started").mkdir(parents=True)
    for n in range(1, 5):
        (queue / f"api/started/0{n}-eng-{n}.md").write_text(f"Task {n}.")
    tabs = {**herdr.state["tabs"], "t3": "⏳ 🛠️ eng-1", "t4": "✅ 🎉 eng-2 merged", "t5": "✅ 👀 eng-3"}
    panes = [*herdr.state["panes"], *({"pane_id": f"p{n}", "tab_id": f"t{n}"} for n in (3, 4, 5))]
    agents = {**herdr.state["agents"], **{f"eng-{n - 2}": {"pane_id": f"p{n}", "tab_id": f"t{n}"} for n in (3, 4, 5)}}
    herdr.set_state(tabs=tabs, panes=panes, agents=agents)
    result = herdr.run(ORCHESTRATOR, "leads")
    assert "api: 0 queued, 2 open; no lead" in result.stdout  # eng-2 merged, eng-4 is gone
    assert started(herdr) == []


@pytest.mark.parametrize("lead", ["api-lead", "lead-api"])  # lead-api: a lead started before the rename
def test_no_second_lead_beside_one_that_lost_its_name(herdr, lanes, queue, lead):
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t3": f"⏳ 🧭 {lead}"},
        panes=[*herdr.state["panes"], {"pane_id": "p3", "tab_id": "t3", "agent": "claude"}],
    )
    (queue / "api").mkdir()
    for n in range(1, 5):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    result = herdr.run(ORCHESTRATOR, "leads")
    assert "tab t3 reads as api-lead's but lost the name" in result.stdout
    assert started(herdr) == []


@pytest.mark.parametrize("lead", ["api-lead", "lead-api"])
def test_a_restarted_lead_takes_its_name_back(herdr, lead):
    herdr.set_state(tabs={**herdr.state["tabs"], "t1": f"✅ 🧭 {lead}"})
    result = herdr.run(TAB, "hook", "session", stdin='{"source": "startup"}')
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert f"you are {lead}, a lane lead" in context
    assert herdr.state["agents"][lead]["pane_id"] == "p1"


def test_a_restarted_old_lead_stays_unnamed_beside_the_lanes_new_lead(herdr):
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t1": "✅ 🧭 lead-api"},
        agents={**herdr.state["agents"], "api-lead": {"pane_id": "p9", "tab_id": "t9"}},
    )
    result = herdr.run(TAB, "hook", "session", stdin='{"source": "startup"}')
    assert "a lane lead" not in json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "lead-api" not in herdr.state["agents"]


def be_lead(herdr, lead="api-lead", label=None):
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t1": label or f"⏳ 🧭 {lead}"},
        agents={**herdr.state["agents"], lead: {"pane_id": "p1", "tab_id": "t1"}},
    )


# Leads started before the rename are named lead-<lane>. One still running leads its lane until it hands back.


def test_a_lead_with_the_old_name_still_leads_its_lane(herdr, lanes, queue, tmp_path):
    be_lead(herdr, "lead-api")
    (queue / "api").mkdir()
    for n in range(1, 5):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    result = herdr.run(ORCHESTRATOR, "leads")
    assert "api: 4 queued, 0 open; lead-api in tab t1" in result.stdout
    assert start_lead(herdr, tmp_path).stdout == "api: lead-api is already running, so none started\n"
    assert herdr.run(ORCHESTRATOR, "next").stdout == "fleet: queue empty\n"
    assert started(herdr) == []


def test_a_lane_worker_reports_to_an_old_named_lead(herdr, lanes, queue, grouping_cli):
    be_lead(herdr, "lead-api")
    (queue / "api").mkdir()
    (queue / "api/01-task.md").write_text("Fix the login bug.")
    result = herdr.run(ORCHESTRATOR, "next", "--lane", "api")
    assert result.returncode == 0, result.stderr
    assert json.loads(grouping_cli.read_text()) == ["assign", "task", "lead-api"]
    (brief,) = prompts(herdr, "task")
    assert "While lead-api runs" in brief


def test_an_old_named_lead_hands_back_under_the_new_label(herdr, lanes, queue):
    be_lead(herdr, "lead-api")
    result = herdr.run(ORCHESTRATOR, "handback", "api")
    assert result.returncode == 0, result.stderr
    assert "lead-api" not in herdr.state["agents"]
    assert herdr.label() == "⏳ 💤 ex-api-lead"
    assert ["agent", "prompt", "p1", "/rename ex-api-lead"] in herdr.state["calls"]
    (report,) = prompts(herdr, "orchestrator")
    assert report == "Status from lead-api: handed lane api back to you; open: nothing."


def test_a_quiet_lane_is_asked_back_once(herdr, lanes, queue):
    be_lead(herdr)
    (queue / "api").mkdir()
    (queue / "api/01-task-1.md").write_text("Task 1.")
    for _ in range(2):
        result = herdr.run(ORCHESTRATOR, "leads")
        assert "api: 1 queued, 0 open" in result.stdout
    (nudge,) = prompts(herdr, "api-lead")
    assert nudge.startswith("Status from orchestrator:")  # a peer's words, so it keeps Kevin's ask
    assert "handback api" in nudge


def test_a_lane_without_a_queue_folder_is_asked_back(herdr, lanes, queue):
    be_lead(herdr)
    result = herdr.run(ORCHESTRATOR, "leads")
    assert result.returncode == 0, result.stderr
    assert "api: 0 queued, 0 open; asked api-lead to hand it back" in result.stdout
    assert (queue / "api/.handback-asked").exists()


def test_next_waits_for_a_new_tab_s_shell(herdr, queue):
    herdr.set_state(fail_once={"agent start": "agent_pane_busy"})
    (queue / "01-eng-1.md").write_text("Fix the login bug.")
    result = herdr.run(ORCHESTRATOR, "next")
    assert result.returncode == 0, result.stderr
    assert started(herdr) == ["eng-1", "eng-1"]
    assert [call[:2] for call in herdr.state["calls"]].count(["tab", "create"]) == 1
    assert herdr.state["agents"]["eng-1"]["tab_id"] == "t3"
    assert (queue / "started/01-eng-1.md").exists()


def test_next_closes_a_tab_it_could_not_start_in(herdr, queue):
    herdr.set_state(fail={"agent start": "agent_start_timeout"})
    (queue / "01-eng-1.md").write_text("Fix the login bug.")
    result = herdr.run(ORCHESTRATOR, "next")
    assert result.returncode == 1
    assert "agent_start_timeout" in result.stderr
    assert ["tab", "close", "t3"] in herdr.state["calls"]
    assert set(herdr.state["tabs"]) == {"t1", "t9"}
    assert (queue / "01-eng-1.md").exists()


def test_a_lead_hands_a_quiet_lane_back_and_stays_open(herdr, lanes, queue):
    be_lead(herdr, label="❓ merge order? · 🧭 api-lead")
    (queue / "api").mkdir()
    (queue / "api/01-task-1.md").write_text("Task 1.")
    result = herdr.run(ORCHESTRATOR, "handback", "api")
    assert result.returncode == 0, result.stderr
    assert "api-lead" not in herdr.state["agents"]
    assert herdr.label() == "❓ merge order? · 💤 ex-api-lead"
    calls = herdr.state["calls"]
    assert ["agent", "prompt", "p1", "/rename ex-api-lead"] in calls
    assert not any("/clear" in call for call in calls)
    (report,) = prompts(herdr, "orchestrator")
    assert report == "Status from api-lead: handed lane api back to you; open: task-1."


def test_a_busy_lane_is_not_handed_back(herdr, lanes, queue):
    be_lead(herdr)
    (queue / "api").mkdir()
    for n in range(1, 3):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    result = herdr.run(ORCHESTRATOR, "handback", "api")
    assert result.returncode == 1
    assert "keep leading it" in result.stdout
    assert "api-lead" in herdr.state["agents"]


def test_only_the_lead_hands_its_lane_back(herdr, lanes, queue):
    result = herdr.run(ORCHESTRATOR, "handback", "api")
    assert result.returncode == 2
    assert "only api-lead" in result.stderr


def test_next_leaves_a_led_lane_to_its_lead(herdr, lanes, queue):
    herdr.set_state(agents={**herdr.state["agents"], "api-lead": {"pane_id": "p9", "tab_id": "t9"}})
    (queue / "api").mkdir()
    (queue / "api/01-task-1.md").write_text("Task 1.")
    (queue / "mobile").mkdir()
    (queue / "mobile/02-app-fix.md").write_text("Fix the app.")
    result = herdr.run(ORCHESTRATOR, "next")
    assert result.returncode == 0, result.stderr
    assert started(herdr) == ["app-fix"]
    assert (queue / "mobile/started/02-app-fix.md").exists()

    result = herdr.run(ORCHESTRATOR, "next", "--lane", "api")
    assert result.returncode == 0, result.stderr
    (brief,) = prompts(herdr, "task-1")
    assert brief.startswith("Task 1.")
    assert "send it your one-line updates" in brief
    assert (queue / "api/started/01-task-1.md").exists()


def test_a_brief_started_while_jev_answers_is_not_routed(herdr, jev, lanes, queue):
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix the Stripe webhook retries.")
    (queue / "started").mkdir()
    jev.before_reply = lambda: brief.rename(queue / "started" / brief.name)  # `next` got there first
    result = route(herdr, jev, brief)
    assert result.returncode == 1
    assert "started or moved while Jev answered" in result.stderr
    assert not (queue / "api").exists()


@pytest.mark.parametrize(
    "reply",
    [
        {"answers": {"lane": "api"}},
        {"answers": {"lane": {"choice": ["api"], "probabilities": {}}}},
        {"answers": {"lane": {"choice": "api", "probabilities": {"api": 1.7}}}},
        {"answers": {"lane": {"choice": "search", "probabilities": {"search": 0.9}}}},
        ["not", "an", "object"],
    ],
)
def test_a_malformed_reply_counts_as_jev_unavailable(herdr, jev, lanes, queue, reply):
    jev.reply = reply
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix it.")
    result = route(herdr, jev, brief)
    assert result.returncode == 3, result.stderr
    assert "rule: ask Kevin (Jev unavailable:" in result.stdout
    assert brief.exists()


def test_a_bad_lane_file_does_not_stop_the_main_queue(herdr, lanes, queue):
    lanes.write_text("{")
    (queue / "01-eng-1.md").write_text("Fix the login bug.")
    result = herdr.run(ORCHESTRATOR, "next")
    assert result.returncode == 0, result.stderr
    assert "skipping lane queues" in result.stderr
    assert started(herdr) == ["eng-1"]
    assert herdr.run(ORCHESTRATOR, "leads").returncode == 2


def test_a_lead_is_asked_again_after_the_lane_gets_busy(herdr, lanes, queue):
    be_lead(herdr)
    (queue / "api").mkdir()
    (queue / "api/01-task-1.md").write_text("Task 1.")
    herdr.run(ORCHESTRATOR, "leads")
    for n in range(2, 5):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    assert "api-lead in tab t1" in herdr.run(ORCHESTRATOR, "leads").stdout
    for n in range(2, 5):
        (queue / f"api/0{n}-task-{n}.md").unlink()
    herdr.run(ORCHESTRATOR, "leads")
    assert len(prompts(herdr, "api-lead")) == 2


def test_a_lead_keeps_the_lane_if_its_tab_cannot_be_renamed(herdr, lanes, queue):
    be_lead(herdr)
    herdr.set_state(fail={"tab rename": "tab_not_found"})
    result = herdr.run(ORCHESTRATOR, "handback", "api")
    assert result.returncode == 1
    assert "keeps the lane" in result.stderr
    assert herdr.state["agents"]["api-lead"]["pane_id"] == "p1"
    assert prompts(herdr, "orchestrator") == []


def test_a_lead_starts_without_holding_the_queue(herdr, lanes, queue):
    (queue / "api").mkdir()
    for n in range(1, 5):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    herdr.run(ORCHESTRATOR, "leads")
    assert started(herdr) == ["api-lead"]
    assert herdr.state["queue_lock_free_during_start"] == [True]


def test_open_sessions_take_one_look_at_herdr(herdr, lanes, queue):
    (queue / "api/started").mkdir(parents=True)
    for n in range(1, 30):
        (queue / f"api/started/{n:02}-eng-{n}.md").write_text(f"Task {n}.")
    herdr.run(ORCHESTRATOR, "leads")
    calls = herdr.state["calls"]
    assert calls.count(["agent", "list"]) == 1
    assert not any(call[:2] == ["agent", "get"] and call[2].startswith("eng-") for call in calls)


def test_a_herdr_error_message_that_is_not_json_is_reported(herdr, lanes, queue):
    herdr.set_state(fail={"agent get api-lead": "raw"})
    result = herdr.run(ORCHESTRATOR, "leads")
    assert result.returncode == 1
    assert result.stderr.strip() == "herdr-orchestrator leads: connection refused"


@pytest.mark.parametrize("held", [{"pane_id": "p1", "tab_id": "t1"}, {"pane_id": "p9", "tab_id": "t9"}])
def test_a_lead_name_already_held_is_left_alone(herdr, held):
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t1": "✅ 🧭 api-lead"},
        agents={**herdr.state["agents"], "api-lead": held},
    )
    result = herdr.run(TAB, "hook", "session", stdin='{"source": "startup"}')
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "lane lead" not in context
    assert herdr.state["agents"]["api-lead"] == held
    assert not any(call[:2] == ["agent", "rename"] for call in herdr.state["calls"])


def test_a_herdr_error_is_not_a_missing_lead(herdr):
    herdr.set_state(tabs={**herdr.state["tabs"], "t1": "✅ 🧭 api-lead"}, fail={"agent get api-lead": "timeout"})
    result = herdr.run(TAB, "hook", "session", stdin='{"source": "startup"}')
    assert "lane lead" not in json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert not any(call[:2] == ["agent", "rename"] for call in herdr.state["calls"])


@pytest.mark.parametrize(
    "name, scripts",
    [
        ("typesafe_key", COPIES),
        ("jev_says_waiting", HELPERS),
        ("ask_line", HELPERS),
        ("ask_options", HELPERS),
        ("jev_warning", HELPERS),
        ("wire_ask", HELPERS),
    ],
)
def test_the_shared_copies_are_identical(name, scripts):
    assert len({inspect.getsource(runpy.run_path(str(script))[name]) for script in scripts}) == 1


def test_the_helpers_read_list_items_alike():
    assert len({runpy.run_path(str(script))["LIST_ITEM"].pattern for script in HELPERS}) == 1


def test_the_copies_share_the_jev_constants(env, tmp_path):
    orchestrator, claude, codex = (runpy.run_path(str(script)) for script in COPIES)
    assert orchestrator["JEV_URL"] == claude["JEV_URL"] == codex["JEV_URL"]
    assert orchestrator["JEV_CHARS"] == claude["JEV_CHARS"] == codex["JEV_CHARS"]
    env(XDG_STATE_HOME=tmp_path)
    claude, codex = (runpy.run_path(str(script)) for script in HELPERS)
    assert claude["JEV_FAILED"] == codex["JEV_FAILED"] == str(tmp_path / "herdr-tab/jev-failed")


@pytest.mark.parametrize("script", COPIES, ids=["orchestrator", "herdr-tab", "codex-herdr-tab"])
def test_every_copy_finds_the_typesafe_key_the_same_way(script, env, tmp_path, monkeypatch):
    env(HOME=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ts").write_text("repo-key")
    monkeypatch.chdir(repo)

    def key():
        problems = []
        return runpy.run_path(str(script))["typesafe_key"](problems), problems

    assert key() == ("", [])
    default_file = tmp_path / ".config/typesafe/api-key"
    default_file.parent.mkdir(parents=True)
    default_file.write_text("file-key\n")
    assert key() == ("file-key", [])
    folder = tmp_path / ".config/team-floor"
    folder.mkdir(parents=True)
    (folder / "config.json").write_text('{"jev": {"api_key": "x"},}')
    found, problems = key()
    assert found == "file-key" and "config.json" in problems[0]
    (folder / "ts").write_text("folder-key")
    write_config(tmp_path, {"jev": {"api_key_file": "ts"}})
    assert key() == ("folder-key", [])
    (folder / "ts").write_bytes(b"\xff\xfe not text")
    found, problems = key()
    assert found == "" and "UnicodeDecodeError" in problems[0]
    write_config(tmp_path, {"jev": {"api_key": "cfg-key"}})
    assert key() == ("cfg-key", [])
    write_config(tmp_path, {"jev": {"api_key": "FAKE-KEY\nnote"}})
    found, problems = key()
    assert found == "" and "control characters" in problems[0]
    monkeypatch.setenv("TYPESAFE_API_KEY", "env-key")
    assert key() == ("env-key", [])


def test_route_never_echoes_a_bad_key(herdr, jev, lanes, queue, tmp_path):
    write_config(tmp_path, {"jev": {"api_key": "FAKE-KEY\nnote"}})
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix the Stripe webhook retries.")
    result = route(herdr, jev, brief, key="")
    assert "FAKE-KEY" not in result.stdout + result.stderr
    assert "no TypeSafe key" in result.stdout and not jev.requests


def test_route_says_why_there_is_no_key(herdr, jev, lanes, queue, tmp_path):
    (tmp_path / ".config/team-floor/config.json").write_text('{"jev": {"api_key": "K"},}')
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix the Stripe webhook retries.")
    result = route(herdr, jev, brief, key="")
    assert "can't read" in result.stdout and "config.json" in result.stdout


def test_the_lead_label_matches_the_orchestrator():
    orchestrator = runpy.run_path(str(ORCHESTRATOR))
    tab = runpy.run_path(str(TAB))
    lane = orchestrator["LANE_ID"].pattern
    assert tab["LEAD_LABEL"].pattern == f"{orchestrator['LEAD']} (?:({lane})-lead|lead-({lane}))"
    assert orchestrator["lead_names"]("api") == ("api-lead", "lead-api")


def start_lead(herdr, tmp_path, lane="api", text="Why is the webhook retrying twice?", after=(), **extra):
    message = tmp_path / "message.txt"
    message.write_text(text)
    herdr.environ.pop("HERDR_PANE_ID", None)  # a launchd job runs outside any pane, with no TTY
    return herdr.run(ORCHESTRATOR, "lead", lane, "--prompt-file", str(message), *after, **extra)


def test_lead_starts_with_one_first_prompt_from_outside_herdr(herdr, lanes, queue, tmp_path):
    result = start_lead(herdr, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "api: started api-lead in pane t3:p1" in result.stdout
    assert started(herdr) == ["api-lead"]
    (create,) = [call for call in herdr.state["calls"] if call[:2] == ["tab", "create"]]
    assert create[create.index("--workspace") + 1] == "w1"
    assert create[create.index("--cwd") + 1] == str(tmp_path)
    assert herdr.label("t3") == "🧭 api-lead"
    (brief,) = prompts(herdr, "api-lead")
    assert brief.startswith("You are api-lead, the lead for the API lane")
    assert brief.endswith(
        "----- Kevin's message -----\nWhy is the webhook retrying twice?\n----- end of Kevin's message -----"
    )


def test_lead_from_the_chat_agent_says_its_message_is_the_agent_s(herdr, lanes, queue, tmp_path):
    text = "The chat agent on m1 passes on this request from Kevin's chat:\n\nAdd an index"
    result = start_lead(herdr, tmp_path, text=text, after=("--from-agent", "chat-agent@m1"))
    assert result.returncode == 0, result.stderr
    (brief,) = prompts(herdr, "api-lead")
    assert "The team floor's chat agent (chat-agent@m1) started this lead from the chat" in brief
    assert brief.endswith("Add an index\n----- end of chat-agent@m1's message -----")
    assert "Kevin's message" not in brief and "Kevin started this lead" not in brief


@pytest.mark.parametrize(
    "extra",
    [("--from-agent",), ("--from-agent", "x y"), ("--from", "chat-agent@m1"), ("--from-agent", "Kevin@floor")],
)
def test_lead_refuses_a_bad_from_agent(herdr, lanes, queue, tmp_path, extra):
    result = start_lead(herdr, tmp_path, after=extra)
    assert result.returncode == 2
    assert "usage: herdr-orchestrator lead" in result.stderr
    assert started(herdr) == []


def test_lead_does_nothing_when_the_lead_exists(herdr, lanes, queue, tmp_path):
    be_lead(herdr)
    result = start_lead(herdr, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "api: api-lead is already running, so none started\n"
    assert started(herdr) == [] and prompts(herdr, "api-lead") == []


def test_lead_exits_3_when_memory_is_short(herdr, lanes, queue, tmp_path):
    result = start_lead(herdr, tmp_path, FLEET_MIN_MB="100000000")
    assert result.returncode == 3
    assert "api-lead waits for memory" in result.stdout
    assert started(herdr) == [] and set(herdr.state["tabs"]) == {"t1", "t9"}


def test_lead_reports_herdr_s_error_code(herdr, lanes, queue, tmp_path):
    herdr.set_state(fail={"agent start": "agent_start_timeout"})
    result = start_lead(herdr, tmp_path)
    assert result.returncode == 1
    assert "agent_start_timeout" in result.stderr
    assert set(herdr.state["tabs"]) == {"t1", "t9"}  # the new tab is closed again


def test_lead_waits_while_the_new_session_is_busy_or_not_ready(herdr, lanes, queue, tmp_path):
    herdr.set_state(fail_once={"agent start": "agent_pane_busy", "agent prompt api-lead": "agent_not_ready"})
    result = start_lead(herdr, tmp_path)
    assert result.returncode == 0, result.stderr
    assert started(herdr) == ["api-lead", "api-lead"]
    assert len(prompts(herdr, "api-lead")) == 2


def test_lead_prompts_a_session_that_started_not_ready(herdr, lanes, queue, tmp_path):
    herdr.set_state(start_not_ready=True)
    result = start_lead(herdr, tmp_path)
    assert result.returncode == 0, result.stderr
    assert started(herdr) == ["api-lead"]
    assert len(prompts(herdr, "api-lead")) == 1


@pytest.mark.parametrize("lane", ["misc", "web"])
def test_lead_refuses_misc_and_unknown_lanes(herdr, lanes, queue, tmp_path, lane):
    result = start_lead(herdr, tmp_path, lane=lane)
    assert result.returncode == 2
    assert f"{lane} is not a lane" in result.stderr
    assert started(herdr) == []


@pytest.mark.parametrize("extra", [[], ["--file", "message.txt"]])
def test_lead_needs_a_prompt_file(herdr, lanes, extra):
    result = herdr.run(ORCHESTRATOR, "lead", "api", *extra)
    assert result.returncode == 2
    assert "usage: herdr-orchestrator lead" in result.stderr


@pytest.mark.parametrize("unset", ["HERDR_WORK_DIR", "HERDR_WORKSPACE_ID"])
def test_lead_needs_the_callers_workspace_and_folder(herdr, lanes, queue, tmp_path, unset):
    herdr.environ.pop(unset)
    result = start_lead(herdr, tmp_path)
    assert result.returncode == 2
    assert f"set {unset}" in result.stderr
    assert started(herdr) == []


def test_lead_refuses_an_empty_message(herdr, lanes, queue, tmp_path):
    result = start_lead(herdr, tmp_path, text="  \n")
    assert result.returncode == 2
    assert "is empty" in result.stderr
    assert started(herdr) == []


def test_two_nexts_do_not_share_one_ready_tab(herdr, queue, tmp_path):
    ready_tab(herdr, tmp_path)
    (queue / "01-eng-1.md").write_text("First.")
    (queue / "02-eng-2.md").write_text("Second.")
    for _ in range(2):
        result = herdr.run(ORCHESTRATOR, "next")
        assert result.returncode == 0, result.stderr
    agents = herdr.state["agents"]
    assert agents["eng-1"]["pane_id"] == "p2"
    assert agents["eng-2"]["pane_id"] != "p2"
    assert herdr.label("t2") == "eng-1"


def test_a_ready_tab_whose_agent_rename_fails_reads_ready_again(herdr, lanes, queue, tmp_path):
    ready_tab(herdr, tmp_path)
    herdr.set_state(fail={"agent rename p2": "agent_name_taken"})
    result = start_lead(herdr, tmp_path)
    assert result.returncode == 1
    assert "agent_name_taken" in result.stderr
    assert herdr.label("t2") == "⚪ ready"


def test_lead_says_when_the_session_missed_its_brief(herdr, lanes, queue, tmp_path):
    herdr.set_state(fail={"agent prompt api-lead": "agent_blocked"})
    result = start_lead(herdr, tmp_path)
    assert result.returncode == 1
    assert "api-lead started in pane t3:p1 but didn't get its brief" in result.stderr
    assert "agent_blocked" in result.stderr


def test_a_new_lead_that_missed_its_brief_is_not_marked_asked_back(herdr, lanes, queue, tmp_path):
    (queue / "api").mkdir()
    (queue / "api/.handback-asked").touch()  # left by a lead that exited without handing back
    herdr.set_state(fail={"agent prompt api-lead": "agent_blocked"})
    assert start_lead(herdr, tmp_path).returncode == 1
    assert not (queue / "api/.handback-asked").exists()


def test_next_reuses_a_ready_tab_without_a_workspace_id(herdr, queue, tmp_path):
    ready_tab(herdr, tmp_path)
    herdr.environ.pop("HERDR_WORKSPACE_ID")
    (queue / "01-eng-1.md").write_text("First.")
    result = herdr.run(ORCHESTRATOR, "next")
    assert result.returncode == 0, result.stderr
    assert herdr.state["agents"]["eng-1"]["pane_id"] == "p2"
