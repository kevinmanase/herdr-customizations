"""Agent grouping against an in-memory API; no live Herdr state is read or changed."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins/agent-groups/groups.py"
SOURCE = "plugin:kevin.agent-groups"
ORDER = "herdr_groups_order"
TREE = "herdr_groups_tree"


@pytest.fixture
def groups():
    spec = importlib.util.spec_from_file_location("herdr_agent_groups", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def agent(name, number, **extra):
    return {"name": name, "pane_id": f"w1:p{number}", "tab_id": f"w1:t{number}", "tokens": {}, **extra}


class FakeCall:
    def __init__(self, agents, view=None, shells=None):
        self.agents = deepcopy(agents)
        self.panes = [*self.agents, *deepcopy(shells or [])]
        self.tabs = [{"tab_id": item["tab_id"], "label": f"❓ approve? · {item['name']}"} for item in agents]
        self.view = deepcopy(view)
        self.calls = []
        self.closed = False

    def __call__(self, method, params):
        self.calls.append((method, deepcopy(params)))
        if method == "session.snapshot":
            return {
                "type": "session_snapshot",
                "snapshot": deepcopy({"agents": self.agents, "tabs": self.tabs, "panes": self.panes}),
            }
        if method == "agent.get":
            target = next((item for item in self.agents if item["name"] == params["target"]), None)
            if target is None:
                raise RuntimeError("agent not found")
            return {"type": "agent", "agent": deepcopy(target)}
        if method == "pane.report_metadata":
            assert set(params) == {"pane_id", "source", "tokens"}
            assert params["source"] == SOURCE
            assert set(params["tokens"]) <= {ORDER, TREE}
            target = next(item for item in self.panes if item["pane_id"] == params["pane_id"])
            for key, value in params["tokens"].items():
                if value is None:
                    target["tokens"].pop(key, None)
                else:
                    target["tokens"][key] = value
            return {"type": "ok"}
        if method == "agent.view.set":
            self.view = deepcopy(params)
            return {"type": "agent_view", "active": True, **params}
        if method == "agent.view.clear":
            if self.view is not None and self.view["source"] == params["source"]:
                self.view = None
            return {"type": "agent_view", "active": self.view is not None}
        raise AssertionError(f"Unexpected API effect: {method}")

    call = __call__

    def close(self):
        self.closed = True

    @property
    def writes(self):
        return [(method, params) for method, params in self.calls if method not in {"session.snapshot", "agent.get"}]


def test_two_orchestrators_and_a_nested_lead_follow_tree_order(groups):
    agents = [
        agent("worker-b", 1),
        agent("orchestrator-b", 2),
        agent("independent", 3),
        agent("nested-worker", 4),
        agent("orchestrator-a", 5),
        agent("lead-a", 6),
        agent("worker-a", 7),
        agent(None, 8),
    ]
    parents = {
        "orchestrator-a": None,
        "worker-a": "orchestrator-a",
        "lead-a": "orchestrator-a",
        "nested-worker": "lead-a",
        "orchestrator-b": None,
        "worker-b": "orchestrator-b",
    }

    assert [(item["name"], depth, supervisor) for item, depth, supervisor in groups.plan(agents, parents)] == [
        ("orchestrator-b", 0, True),
        ("worker-b", 1, False),
        ("orchestrator-a", 0, True),
        ("lead-a", 1, True),
        ("nested-worker", 2, False),
        ("worker-a", 1, False),
        ("independent", 0, False),
        (None, 0, False),
    ]


def test_a_missing_supervisor_keeps_its_workers_visible_at_the_top_level(groups):
    agents = [agent("worker", 1), agent("independent", 2)]
    parents = {"missing-orchestrator": None, "worker": "missing-orchestrator"}

    assert groups.plan(agents, parents) == [(agents[0], 0, False), (agents[1], 0, False)]


def test_no_groups_preserves_all_agents_including_unnamed_ones(groups):
    agents = [agent("independent", 1), agent(None, 2), agent("other", 3)]

    assert groups.plan(agents, {}) == [(item, 0, False) for item in agents]


@pytest.mark.parametrize(
    "parents",
    [
        None,
        [],
        "orchestrator",
        {1: None},
        {"": None},
        {"Uppercase": None},
        {"@orchestrator": None},
        {"name with spaces": None},
        {"a" * 33: None},
        {"é": None},
        {"root": 1},
        {"root": []},
        {"worker": "unregistered"},
        {"root": "root"},
        {"a": "b", "b": "a"},
        {"root": None, "a": "b", "b": "c", "c": "a"},
    ],
)
def test_invalid_parent_maps_are_rejected(groups, parents):
    with pytest.raises(ValueError):
        groups.validate(parents)


def test_registered_parents_and_the_herdr_name_boundary_are_valid(groups):
    groups.validate({"a" + "x" * 31: None, "lead-1": "a" + "x" * 31, "worker_2": "lead-1"})
    groups.validate({})


def test_sync_publishes_only_group_order_and_tree_prefixes(groups):
    call = FakeCall(
        [
            agent("worker", 1, tokens={"summary": "waiting for approval"}),
            agent("root", 2),
            agent("independent", 3),
            agent("nested-worker", 4),
            agent("lead", 5),
        ]
    )
    parents = {"root": None, "worker": "root", "lead": "root", "nested-worker": "lead"}

    groups.sync(call, parents)

    assert call.calls[0][0] == "session.snapshot"
    by_name = {item["name"]: item["tokens"] for item in call.agents}
    assert by_name["root"][ORDER] == "00000000"
    assert by_name["worker"][ORDER] == "00000001"
    assert by_name["lead"][ORDER] == "00000002"
    assert by_name["nested-worker"][ORDER] == "00000003"
    assert by_name["root"][TREE] == "👑"
    assert by_name["worker"][TREE] == "│   └─"
    assert by_name["lead"][TREE] == "│   👑"
    assert by_name["nested-worker"][TREE] == "│   │   └─"
    assert by_name["independent"] == {}
    assert by_name["worker"]["summary"] == "waiting for approval"
    assert call.view["source"] == SOURCE
    assert call.view["sort"] == [{"field": {"token": ORDER}, "order": "asc"}]
    assert not call.view.get("filter")


def test_refresh_with_correct_metadata_does_not_write_again(groups):
    call = FakeCall([agent("worker", 1), agent("root", 2)])
    parents = {"root": None, "worker": "root"}
    groups.sync(call, parents)
    call.calls.clear()

    groups.sync(call, parents, activate=False)

    assert call.writes == []


def test_deep_tree_prefixes_match_herdr_token_normalization(groups):
    agents = [agent(f"node-{index}", index) for index in range(23)]
    parents = {f"node-{index}": f"node-{index - 1}" if index else None for index in range(23)}
    call = FakeCall(agents)

    def normalized(method, params):
        params = deepcopy(params)
        if method == "pane.report_metadata":
            params["tokens"] = {
                key: value.strip()[:80].strip() if value is not None else None
                for key, value in params["tokens"].items()
            }
        return call(method, params)

    groups.sync(normalized, parents)
    call.calls.clear()
    groups.sync(normalized, parents, activate=False)

    assert call.writes == []


def test_already_correct_metadata_is_not_rewritten_during_activation(groups):
    call = FakeCall([agent("root", 1, tokens={ORDER: "00000000", TREE: "👑", "summary": "keep me"})])

    groups.sync(call, {"root": None})

    assert all(method != "pane.report_metadata" for method, _ in call.writes)


def test_sync_preserves_pending_labels_and_agent_lifecycle_fields(groups):
    call = FakeCall(
        [
            agent("root", 1, agent_status="blocked", agent_session={"session_id": "native-root"}),
            agent("worker", 2, state_labels={"blocked": "permission needed"}, title="❗ sign in"),
        ]
    )
    original_tabs = deepcopy(call.tabs)
    original_agents = [{key: value for key, value in item.items() if key != "tokens"} for item in call.agents]

    groups.sync(call, {"root": None, "worker": "root"})

    assert call.tabs == original_tabs
    assert [{key: value for key, value in item.items() if key != "tokens"} for item in call.agents] == original_agents


def test_empty_groups_clear_only_our_tokens_and_source_scoped_view(groups):
    call = FakeCall(
        [
            agent("root", 1, tokens={ORDER: "00000000", TREE: "👑", "summary": "keep me"}),
            agent("independent", 2, tokens={"model": "keep this too"}),
        ],
        view={"source": SOURCE, "sort": [{"field": {"token": ORDER}, "order": "asc"}]},
    )

    groups.sync(call, {})

    assert call.agents[0]["tokens"] == {"summary": "keep me"}
    assert call.agents[1]["tokens"] == {"model": "keep this too"}
    assert call.view is None
    assert [(method, params) for method, params in call.writes if method == "agent.view.clear"] == [
        ("agent.view.clear", {"source": SOURCE})
    ]
    patches = [params for method, params in call.writes if method == "pane.report_metadata"]
    assert len(patches) == 1
    assert patches[0]["tokens"] == {ORDER: None, TREE: None}


def test_empty_groups_preserve_another_plugins_view(groups):
    foreign_view = {"source": "plugin:other.agent-view", "filter": {"op": "exists", "field": "agent"}}
    call = FakeCall([agent("worker", 1, tokens={ORDER: "00000000", TREE: "│   └─"})], view=foreign_view)

    groups.sync(call, {})

    assert call.view == foreign_view
    assert ("agent.view.clear", {"source": SOURCE}) in call.writes
    assert all(method != "agent.view.set" for method, _ in call.writes)


def test_event_refresh_leaves_a_newly_selected_view_alone(groups):
    foreign_view = {"source": "plugin:other.agent-view", "sort": [{"field": "attention", "order": "desc"}]}
    call = FakeCall([agent("root", 1), agent("worker", 2)], view=foreign_view)

    groups.sync(call, {"root": None, "worker": "root"}, activate=False)

    assert call.view == foreign_view
    assert all(not method.startswith("agent.view.") for method, _ in call.writes)


def test_removing_a_worker_clears_its_group_metadata_without_hiding_it(groups):
    call = FakeCall(
        [agent("root", 1), agent("worker", 2, tokens={ORDER: "00000001", TREE: "│   └─", "summary": "keep me"})]
    )

    groups.sync(call, {"root": None}, activate=False)

    assert [item["name"] for item in call.agents] == ["root", "worker"]
    assert call.agents[1]["tokens"] == {"summary": "keep me"}


def test_empty_event_refresh_does_not_clear_a_view(groups):
    call = FakeCall([agent("independent", 1)], view={"source": SOURCE})

    groups.sync(call, {}, activate=False)

    assert call.writes == []


def test_invalid_configuration_cannot_publish_partial_metadata(groups):
    call = FakeCall([agent("root", 1), agent("worker", 2)])

    with pytest.raises(ValueError):
        groups.sync(call, {"root": "worker", "worker": "root"})

    assert call.writes == []


@pytest.fixture
def cli(groups, monkeypatch, tmp_path):
    def prepare(args, parents, agents):
        path = tmp_path / "groups.json"
        path.write_text(json.dumps(parents, indent=2) + "\n")
        call = FakeCall(agents)
        monkeypatch.setenv("HERDR_ENV", "1")
        monkeypatch.setenv("HERDR_SOCKET_PATH", "/fake.herdr.sock")
        monkeypatch.setattr(sys, "argv", [str(PLUGIN), "--config", str(path), *args])
        monkeypatch.setattr(groups, "Client", lambda socket_path: call)
        return path, call

    return prepare


@pytest.mark.parametrize(
    "args, parents",
    [
        (["root", "not a name"], {"root": None}),
        (["root", "root"], {"root": "worker", "worker": "root"}),
        (["assign", "root", "worker"], {"root": None, "worker": "root"}),
        (["assign", "root", "root"], {"root": None}),
        (["assign", "worker", "not a name"], {"root": None}),
    ],
)
def test_rejected_cli_assignments_do_not_save_configuration(groups, cli, args, parents):
    path, call = cli(args, parents, [agent("root", 1), agent("worker", 2)])
    original = path.read_bytes()

    with pytest.raises(ValueError):
        groups.main()

    assert path.read_bytes() == original
    assert not path.with_suffix(".tmp").exists()
    assert call.writes == []
    assert call.closed


def test_cli_assign_resolves_exact_names_before_saving(groups, cli):
    path, call = cli(["assign", "worker", "root"], {}, [agent("root", 1), agent("worker", 2)])

    groups.main()

    assert json.loads(path.read_text()) == {"root": None, "worker": "root"}
    assert [(method, params) for method, params in call.calls if method == "agent.get"] == [
        ("agent.get", {"target": "worker"}),
        ("agent.get", {"target": "root"}),
    ]
    assert call.calls[:2] == [("agent.get", {"target": "worker"}), ("agent.get", {"target": "root"})]
    assert call.closed


@pytest.mark.parametrize("args", [["root", "absent"], ["assign", "worker", "absent"]])
def test_cli_rejects_a_name_that_is_not_a_live_agent(groups, cli, args):
    path, call = cli(args, {"root": None}, [agent("root", 1), agent("worker", 2)])
    original = path.read_bytes()

    with pytest.raises(RuntimeError, match="agent not found"):
        groups.main()

    assert path.read_bytes() == original
    assert call.writes == []
    assert call.closed


def test_refresh_clears_group_metadata_from_an_agent_that_has_exited(groups):
    exited = agent(None, 3, tokens={ORDER: "00000001", TREE: "│   └─", "summary": "keep me"})
    untouched_shell = agent(None, 4, tokens={"model": "keep this too"})
    call = FakeCall([agent("root", 1)], shells=[exited, untouched_shell])

    groups.sync(call, {"root": None, "old-worker": "root"}, activate=False)

    assert call.panes[1]["tokens"] == {"summary": "keep me"}
    assert call.panes[2]["tokens"] == {"model": "keep this too"}
    assert ("pane.report_metadata", {"pane_id": "w1:p3", "source": SOURCE, "tokens": {ORDER: None, TREE: None}}) in (
        call.writes
    )
    assert all(params.get("pane_id") != "w1:p4" for _, params in call.writes)


def test_clear_removes_group_tokens_from_shells_as_well_as_agents(groups):
    call = FakeCall(
        [],
        shells=[agent(None, 1, tokens={ORDER: "00000000", TREE: "👑", "summary": "keep me"})],
    )

    groups.sync(call, {})

    assert call.panes[0]["tokens"] == {"summary": "keep me"}
    assert ("agent.view.clear", {"source": SOURCE}) in call.writes


def test_a_later_occupant_cannot_inherit_the_exited_agents_group(groups):
    call = FakeCall(
        [agent("root", 1)],
        shells=[agent(None, 2, tokens={ORDER: "00000001", TREE: "│   └─", "summary": "shared pane metadata"})],
    )
    parents = {"root": None, "old-worker": "root"}
    groups.sync(call, parents, activate=False)
    assert call.panes[1]["tokens"] == {"summary": "shared pane metadata"}

    new_occupant = call.panes[1]
    new_occupant["name"] = "independent"
    call.agents.append(new_occupant)
    call.tabs.append({"tab_id": new_occupant["tab_id"], "label": "⏳ new task"})
    call.calls.clear()
    ordered, _ = groups.sync(call, parents, activate=False)

    assert [(item["name"], depth, supervisor) for item, depth, supervisor in ordered] == [
        ("root", 0, True),
        ("independent", 0, False),
    ]
    assert new_occupant["tokens"] == {"summary": "shared pane metadata"}
    assert call.writes == []
