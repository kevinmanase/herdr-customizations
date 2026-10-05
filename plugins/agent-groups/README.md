# Orchestrator groups

Put each named orchestrator above the agents it supervises in Herdr's **Agents**
sidebar. Multiple orchestrators can sit at the top; a lead and its workers can
also nest beneath one. Uses Herdr 0.9.1's existing metadata and Agent view APIs.
Requires Python 3.11 or newer on Linux or macOS. Agent Wire is optional.

```text
👑 product
    personal-chat
    👑 run-lab
        candidate-runs
        review
👑 tooling
    agent-wire
    team-floor
independent-agent
```

Assignments are explicit Herdr agent names, not guesses from tasks or tab labels.
The names follow their current occupants. Reusing an assigned name retains its
group; removing or changing an assignment is explicit. If a supervisor exits,
its workers stay visible at the top until it returns. Unassigned agents follow
the groups. Existing statuses and pending questions remain visible.

## Install

After this plugin is merged, install it at user scope:

```sh
herdr plugin install kevinmanase/herdr-customizations/plugins/agent-groups --yes
```

Copy `groups.py` to `~/.local/bin/herdr-groups` and make it executable. The
`herdr-orchestrator next` and `leads` commands then assign new workers and leads
to their known supervisor automatically. Grouping failures report a warning
without stopping the worker's task.

Add the tree token before the normal status and label in Herdr's `config.toml`:

```toml
[ui.sidebar.agents]
rows = [["$herdr_groups_tree", "state_icon", "tab"]]
```

Keep any existing row preferences you want; add `$herdr_groups_tree` to the
first row. Tree connectors indent descendants without changing tab names.
Missing tokens disappear, so unassigned agents retain their normal labels.
Reload the UI configuration with `herdr server reload-config`.

## Assign agents

Run these commands from a Herdr pane:

```sh
herdr-groups root product
herdr-groups assign personal-chat product
herdr-groups assign run-lab product
herdr-groups assign candidate-runs run-lab
herdr-groups root tooling
herdr-groups assign agent-wire tooling
```

`herdr agent list` gives the exact names. Name an unnamed session with
`herdr agent rename <pane-id> <name>`. A launcher can run `assign` after it
starts a worker. The shared orchestrator's automatic recovery still owns its
single named role; these display groups can include other named supervisors.
After manually claiming or naming a supervisor, register it with `root` or
`assign`; assign any known workers beneath it too. `sync` refreshes existing
assignments after a rename, but does not create ownership for a new name.
Preserve an existing assignment unless ownership changes.

Assignments live in the plugin's user config directory as `groups.json`:

```json
{
  "product": null,
  "personal-chat": "product",
  "run-lab": "product",
  "candidate-runs": "run-lab",
  "tooling": null,
  "agent-wire": "tooling"
}
```

Find it with `herdr plugin config-dir kevin.agent-groups`. `--config /path/to/groups.json`
selects a different file for a CLI invocation. Cycles and unknown supervisor
names are rejected before applying changes. Manually edited assignments may
include agents that are currently absent; the `root` and `assign` commands
check that their named agents exist.

`preview` prints the hierarchy without writing to Herdr. `sync` applies edited
assignments and selects the grouped Agents view. `remove <name>` removes its
assignment and makes its direct children top-level. `clear` removes every
assignment, clears only this plugin's metadata, and releases its own view.

Startup restores the grouping. Events refresh the order when agents appear,
move, or leave, or tabs are renamed or reordered. Refreshes only write metadata that changed and
do not replace another subsequently selected Agent view. Herdr has one active
Agent view per server: `sync` explicitly selects this one. Sorting covers the
current server; groups do not combine agents across saved machines.

The expanded sidebar shows tree connectors; this is a visual hierarchy, not
collapsible folders. Compact and mobile lists keep the group ordering. The
plugin never changes tab labels, agent state, sessions, prompts, or permissions.
It uses only the local Herdr socket and sends nothing off the machine.

Run `clear` before disabling or uninstalling the plugin to remove its tree
tokens. The optional row token can stay in the config when the plugin is off.
