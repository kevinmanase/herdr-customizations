#!/usr/bin/env python3
"""A fake `herdr` CLI. State lives in the JSON file named by FAKE_HERDR_STATE; calls are logged.

state["fail"] maps the start of a command ("tab rename") to the error code it fails with, or "raw"
for an error that isn't JSON; state["fail_once"] does the same for the next matching call only.
`agent start` records whether the fleet queue's lock was free. With state["start_not_ready"] it starts the agent
but answers agent_not_ready once, as Herdr does for a session still at a startup dialog.
"""

import fcntl
import json
import os
import sys

path = os.environ["FAKE_HERDR_STATE"]
with open(path) as handle:
    state = json.load(handle)
args = sys.argv[1:]
state.setdefault("calls", []).append(args)


def done(result=None, error=None):
    with open(path, "w") as handle:
        json.dump(state, handle)
    if error:
        print(json.dumps({"error": {"code": error}}), file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"result": result or {}}))
    sys.exit(0)


for prefix, code in [*state.get("fail", {}).items(), *state.get("fail_once", {}).items()]:
    if " ".join(args).startswith(prefix):
        state.get("fail_once", {}).pop(prefix, None)
        if code == "raw":
            with open(path, "w") as handle:
                json.dump(state, handle)
            print("connection refused", file=sys.stderr)
            sys.exit(1)
        done(error=code)


def queue_lock_free():
    lock = os.path.join(os.environ.get("HERDR_FLEET_QUEUE", ""), ".lock")
    if not os.path.exists(lock):
        return True
    with open(lock) as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle, fcntl.LOCK_UN)
        return True


def pane(pane_id):
    return next(p for p in state["panes"] if p["pane_id"] == pane_id)


match args:
    case ["pane", "get", pane_id]:
        done({"pane": pane(pane_id)})
    case ["pane", "list"]:
        done({"panes": state["panes"]})
    case ["tab", "get", tab]:
        done({"tab": {"tab_id": tab, "label": state["tabs"][tab]}})
    case ["tab", "rename", tab, label]:
        state["tabs"][tab] = label
        done({"tab": {"tab_id": tab, "label": label}})
    case ["tab", "list", *_]:
        done({"tabs": [{"tab_id": t, "label": label} for t, label in state["tabs"].items()]})
    case ["tab", "close", tab]:
        del state["tabs"][tab]
        state["panes"] = [p for p in state["panes"] if p["tab_id"] != tab]
        done({})
    case ["tab", "create", *rest]:
        tab = f"t{len(state['tabs']) + 1}"
        state["tabs"][tab] = rest[rest.index("--label") + 1]
        state["panes"].append({"pane_id": f"{tab}:p1", "tab_id": tab})
        done({"tab": {"tab_id": tab}, "root_pane": {"pane_id": f"{tab}:p1"}})
    case ["agent", "list"]:
        done({"agents": [{**agent, "name": name} for name, agent in state.get("agents", {}).items()]})
    case ["agent", "get", name]:
        agent = state.get("agents", {}).get(name)
        done({"agent": agent}) if agent else done(error="agent_not_found")
    case ["agent", "rename", pane_id, "--clear"]:
        state["agents"] = {n: a for n, a in state.get("agents", {}).items() if a["pane_id"] != pane_id}
        done({})
    case ["agent", "rename", pane_id, name]:
        held = state.setdefault("agents", {}).get(name)
        if held and held["pane_id"] != pane_id:
            done(error="agent_name_taken")
        state["agents"] = {n: a for n, a in state["agents"].items() if a["pane_id"] != pane_id}
        state["agents"][name] = {**pane(pane_id), "name": name}
        done({})
    case ["agent", "start", name, *rest]:
        pane_id = rest[rest.index("--pane") + 1]
        pane(pane_id)["agent"] = "claude"
        state.setdefault("queue_lock_free_during_start", []).append(queue_lock_free())
        state.setdefault("agents", {})[name] = {**pane(pane_id), "name": name}
        if state.pop("start_not_ready", False):
            done(error="agent_not_ready")
        done({"agent": state["agents"][name]})
    case ["agent" | "notification", *_]:
        done({})
    case _:
        done(error="unsupported")
