#!/usr/bin/env python3
"""Group named agents in Herdr's Agents view. Python standard library, Linux/macOS."""

import argparse
import fcntl
import json
import os
import re
import socket
import sys
from pathlib import Path

PLUGIN = "kevin.agent-groups"
SOURCE = f"plugin:{PLUGIN}"
ORDER, TREE = "herdr_groups_order", "herdr_groups_tree"
NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")


def validate(parents):
    if not isinstance(parents, dict):
        raise ValueError("groups.json must map agent names to a supervisor name or null")
    for name, parent in parents.items():
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError(f"invalid agent name: {name!r}")
        if parent is not None and (not isinstance(parent, str) or parent not in parents):
            raise ValueError(f"{name}: supervisor must be a registered agent name or null")
    for name in parents:
        seen = set()
        current = name
        while current is not None:
            if current in seen:
                raise ValueError(f"supervisor cycle involving {name}")
            seen.add(current)
            current = parents[current]


def plan(agents, parents):
    validate(parents)
    named = {agent.get("name"): agent for agent in agents if agent.get("name") in parents}
    children = {name: [] for name in named}
    roots = []
    for name in named:
        parent = parents[name]
        if parent in named:
            children[parent].append(name)
        else:
            roots.append(name)
    result = []

    def visit(name, depth):
        result.append((named[name], depth, bool(children[name]) or parents[name] is None))
        for child in children[name]:
            visit(child, depth + 1)

    # Actual roots precede workers whose supervisor is currently absent.
    for name in sorted(roots, key=lambda name: parents[name] is not None):
        visit(name, 0)
    result.extend((agent, 0, False) for agent in agents if agent.get("name") not in parents)
    return result


def sync(call, parents, activate=True):
    snapshot = call("session.snapshot", {})["snapshot"]
    ordered = plan(snapshot["agents"], parents)
    # A released agent leaves its terminal tokens behind. Do not let the next occupant inherit a tree marker.
    active = {agent["pane_id"] for agent in snapshot["agents"]}
    for pane in snapshot.get("panes", []):
        if pane["pane_id"] not in active:
            patch = {key: None for key in (ORDER, TREE) if key in pane.get("tokens", {})}
            if patch:
                call("pane.report_metadata", {"pane_id": pane["pane_id"], "source": SOURCE, "tokens": patch})
    for rank, (agent, depth, supervisor) in enumerate(ordered):
        grouped = agent.get("name") in parents
        desired = {
            ORDER: f"{rank:08d}" if grouped else None,
            TREE: ("│   " * depth + ("👑" if supervisor else "└─"))[:80].strip() if grouped else None,
        }
        current = agent.get("tokens", {})
        patch = {key: value for key, value in desired.items() if current.get(key) != value}
        if patch:
            call("pane.report_metadata", {"pane_id": agent["pane_id"], "source": SOURCE, "tokens": patch})
    if activate:
        if parents:
            call(
                "agent.view.set",
                {"source": SOURCE, "label": "orchestrators", "sort": [{"field": {"token": ORDER}, "order": "asc"}]},
            )
        else:
            call("agent.view.clear", {"source": SOURCE})
    return ordered, {tab["tab_id"]: tab["label"] for tab in snapshot["tabs"]}


def request(method, params):
    # Herdr serves one request per connection, except for event subscriptions.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(5)
        stream.connect(os.environ["HERDR_SOCKET_PATH"])
        stream.sendall(json.dumps({"id": "agent-groups", "method": method, "params": params}).encode() + b"\n")
        with stream.makefile("rb") as reader:
            line = reader.readline(8 * 1024 * 1024)
        if not line.endswith(b"\n"):
            raise RuntimeError("Herdr returned an incomplete response")
        response = json.loads(line)
        if "error" in response:
            raise RuntimeError(f"{method}: {response['error']['message']}")
        return response["result"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="groups.json path (defaults to the plugin's config directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("sync", "refresh", "preview", "clear"):
        commands.add_parser(command)
    commands.add_parser("root").add_argument("agent")
    assign = commands.add_parser("assign")
    assign.add_argument("agent")
    assign.add_argument("supervisor")
    commands.add_parser("remove").add_argument("agent")
    args = parser.parse_args()
    if os.environ.get("HERDR_ENV") != "1" or not os.environ.get("HERDR_SOCKET_PATH"):
        raise ValueError("run inside Herdr; no focused-session fallback is used")
    config_dir = Path(
        os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
        or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "herdr/plugins/config" / PLUGIN
    )
    path = args.config or config_dir / "groups.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # fcntl is available on both supported platforms. Serialize concurrent event hooks and assignments.
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        parents = json.loads(path.read_text()) if path.exists() else {}
        validate(parents)
        if args.command in {"root", "assign"}:
            # Resolve the exact names before saving an assignment; never infer ownership from a task label.
            for name in [args.agent] + ([args.supervisor] if args.command == "assign" else []):
                if not NAME.fullmatch(name):
                    raise ValueError(f"invalid agent name: {name}")
                request("agent.get", {"target": name})
            if args.command == "assign":
                parents.setdefault(args.supervisor, None)
            parents[args.agent] = args.supervisor if args.command == "assign" else None
        elif args.command == "remove":
            parents.pop(args.agent, None)
            for name, parent in list(parents.items()):
                if parent == args.agent:
                    parents[name] = None
        elif args.command == "clear":
            parents = {}
        validate(parents)
        if args.command in {"root", "assign", "remove", "clear"}:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(parents, indent=2) + "\n")
            temporary.replace(path)
        if args.command == "preview":
            snapshot = request("session.snapshot", {})["snapshot"]
            ordered = plan(snapshot["agents"], parents)
            labels = {tab["tab_id"]: tab["label"] for tab in snapshot["tabs"]}
        else:
            ordered, labels = sync(request, parents, activate=args.command != "refresh")
        if args.command != "refresh":
            for agent, depth, supervisor in ordered:
                print("    " * depth + ("👑 " if supervisor else "") + labels[agent["tab_id"]])


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"agent-groups: {error}", file=sys.stderr)
        sys.exit(1)
