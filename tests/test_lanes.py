"""Lanes, Jev routing and lane leads, against the fake Herdr and a local stand-in for Jev.

The Jev reply in fixtures/jev-choice.json follows the choice response documented at
docs.typesafe.ai (quick start and API reference): answers.<question> holds `type`, `choice`,
`confidence` and `probabilities`. It wasn't checked against a live key.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR = ROOT / "claude/hooks/herdr-orchestrator"
TAB = ROOT / "claude/hooks/herdr-tab"
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


def route(herdr, jev, brief, key="test-key"):
    return herdr.run(ORCHESTRATOR, "route", str(brief), TYPESAFE_API_KEY=key, TYPESAFE_API_URL=jev.url)


def started(herdr):
    return [call[2] for call in herdr.state["calls"] if call[:2] == ["agent", "start"]]


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


@pytest.mark.parametrize("reply", [529, {"answers": {}}])
def test_a_jev_error_never_blocks_routing(herdr, jev, lanes, queue, reply):
    jev.reply = reply
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix the Stripe webhook retries.")
    result = route(herdr, jev, brief)
    assert result.returncode == 3
    assert "rule: ask Kevin (Jev unavailable:" in result.stdout
    assert brief.exists()


def test_routing_needs_the_lane_list(herdr, jev, queue):
    brief = queue / "01-webhook-fix.md"
    brief.write_text("Fix it.")
    result = route(herdr, jev, brief)
    assert result.returncode == 2
    assert "no lanes" in result.stderr
    assert jev.requests == []


def test_a_bad_lane_id_is_skipped(herdr, jev, lanes, queue):
    lanes.write_text(json.dumps({"lanes": [*LANES["lanes"], {"id": "unclear"}, {"id": "Bad Id"}]}))
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
    assert "api: 4 queued, 0 open; started lead-api" in result.stdout
    assert started(herdr) == ["lead-api"]
    lead = herdr.state["agents"]["lead-api"]
    assert herdr.label(lead["tab_id"]) == "🧭 lead-api"
    (brief_text,) = prompts(herdr, "lead-api")
    assert f"{queue / 'api'}" in brief_text
    assert "next --lane api" in brief_text
    assert "role: lead lane: api" in brief_text
    assert "never clear it" in brief_text

    result = herdr.run(ORCHESTRATOR, "leads")
    assert f"api: 4 queued, 0 open; lead-api in tab {lead['tab_id']}" in result.stdout
    assert "mobile: 0 queued, 0 open; no lead" in result.stdout
    assert started(herdr) == ["lead-api"]


def test_jev_unavailable_starts_no_lead(herdr, jev, lanes, queue):
    (queue / "api").mkdir()
    for n in range(1, 4):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    brief = queue / "04-task-4.md"
    brief.write_text("Task 4.")
    result = route(herdr, jev, brief, key="")
    assert result.returncode == 3
    assert started(herdr) == []


def test_a_lead_reuses_a_ready_tab(herdr, lanes, queue, tmp_path):
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t2": "⚪ ready"},
        panes=[
            *herdr.state["panes"],
            {"pane_id": "p2", "tab_id": "t2", "agent": "claude", "cwd": str(tmp_path), "agent_status": "idle"},
        ],
    )
    (queue / "api").mkdir()
    for n in range(1, 5):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    result = herdr.run(ORCHESTRATOR, "leads")
    assert "started lead-api in pane p2" in result.stdout
    assert herdr.state["agents"]["lead-api"]["pane_id"] == "p2"
    assert herdr.label("t2") == "🧭 lead-api"
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


def test_no_second_lead_beside_one_that_lost_its_name(herdr, lanes, queue):
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t3": "⏳ 🧭 lead-api"},
        panes=[*herdr.state["panes"], {"pane_id": "p3", "tab_id": "t3", "agent": "claude"}],
    )
    (queue / "api").mkdir()
    for n in range(1, 5):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    result = herdr.run(ORCHESTRATOR, "leads")
    assert "tab t3 reads 🧭 lead-api but lost the name" in result.stdout
    assert started(herdr) == []


def test_a_restarted_lead_takes_its_name_back(herdr):
    herdr.set_state(tabs={**herdr.state["tabs"], "t1": "✅ 🧭 lead-api"})
    result = herdr.run(TAB, "hook", "session", stdin='{"source": "startup"}')
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "you are still lead-api" in context
    assert herdr.state["agents"]["lead-api"]["pane_id"] == "p1"


def be_lead(herdr, lane="api", label="⏳ 🧭 lead-api"):
    herdr.set_state(
        tabs={**herdr.state["tabs"], "t1": label},
        agents={**herdr.state["agents"], f"lead-{lane}": {"pane_id": "p1", "tab_id": "t1"}},
    )


def test_a_quiet_lane_is_asked_back_once(herdr, lanes, queue):
    be_lead(herdr)
    (queue / "api").mkdir()
    (queue / "api/01-task-1.md").write_text("Task 1.")
    for _ in range(2):
        result = herdr.run(ORCHESTRATOR, "leads")
        assert "api: 1 queued, 0 open" in result.stdout
    (nudge,) = prompts(herdr, "lead-api")
    assert nudge.startswith("Status from orchestrator:")  # a peer's words, so it keeps Kevin's ask
    assert "handback api" in nudge


def test_a_lead_hands_a_quiet_lane_back_and_stays_open(herdr, lanes, queue):
    be_lead(herdr, label="❓ merge order? · 🧭 lead-api")
    (queue / "api").mkdir()
    (queue / "api/01-task-1.md").write_text("Task 1.")
    result = herdr.run(ORCHESTRATOR, "handback", "api")
    assert result.returncode == 0, result.stderr
    assert "lead-api" not in herdr.state["agents"]
    assert herdr.label() == "❓ merge order? · 💤 ex-lead-api"
    calls = herdr.state["calls"]
    assert ["agent", "prompt", "p1", "/rename ex-lead-api"] in calls
    assert not any("/clear" in call for call in calls)
    (report,) = prompts(herdr, "orchestrator")
    assert report == "Status from lead-api: handed lane api back to you; open: task-1."


def test_a_busy_lane_is_not_handed_back(herdr, lanes, queue):
    be_lead(herdr)
    (queue / "api").mkdir()
    for n in range(1, 3):
        (queue / f"api/0{n}-task-{n}.md").write_text(f"Task {n}.")
    result = herdr.run(ORCHESTRATOR, "handback", "api")
    assert result.returncode == 1
    assert "keep leading it" in result.stdout
    assert "lead-api" in herdr.state["agents"]


def test_only_the_lead_hands_its_lane_back(herdr, lanes, queue):
    result = herdr.run(ORCHESTRATOR, "handback", "api")
    assert result.returncode == 2
    assert "only lead-api" in result.stderr


def test_next_leaves_a_led_lane_to_its_lead(herdr, lanes, queue):
    herdr.set_state(agents={**herdr.state["agents"], "lead-api": {"pane_id": "p9", "tab_id": "t9"}})
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
