#!/usr/bin/env python3
"""A fake `herdr` CLI. State lives in the JSON file named by FAKE_HERDR_STATE; calls are logged."""

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
    case ["tab", "create", *rest]:
        tab = f"t{len(state['tabs']) + 1}"
        state["tabs"][tab] = rest[rest.index("--label") + 1]
        state["panes"].append({"pane_id": f"{tab}:p1", "tab_id": tab})
        done({"tab": {"tab_id": tab}, "root_pane": {"pane_id": f"{tab}:p1"}})
    case ["agent", "get", name]:
        agent = state.get("agents", {}).get(name)
        done({"agent": agent}) if agent else done(error="agent_not_found")
    case ["agent", "rename", pane_id, name]:
        state.setdefault("agents", {})[name] = {**pane(pane_id), "name": name}
        done({})
    case ["agent" | "notification", *_]:
        done({})
    case _:
        done(error="unsupported")
