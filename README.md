# Herdr customizations

**Named supervisors. Workers beneath them. Questions that stay visible.**

My tab naming and orchestrator setup for [Herdr](https://github.com/herdrdev/herdr),
packaged as skills, small Python helpers, and lifecycle hooks for Claude Code
and Codex. The agents keep their native tools and sessions. The labels help me
see what they are doing and which ones need me.

The optional [orchestrator groups plugin](plugins/agent-groups/README.md) puts
each named supervisor above its workers in the Agents sidebar, with indentation
for workers and nested leads. It supports several top-level supervisors.

I mainly talk to one orchestrator. It coordinates the workers and brings
decisions back to me. The crown makes supervisors easy to find in a busy
workspace.

## What it looks like

<img src="docs/screenshots/herdr-orchestrator.png" alt="Kevin's Herdr sidebar with a crowned orchestrator, named Claude and Codex workers, stage icons, and a pending question" width="560" />

*Screenshot from my working setup. Herdr's own sidebar indicators are
separate from the label prefixes added by these hooks.*

The tab labels follow **status + stage + short task**:

| Part | Example | Meaning |
| --- | --- | --- |
| Status | `⏳` | The agent is working |
| Stage | `👀` | It is reviewing |
| Task | `login fix` | The work this tab owns |
| Orchestrator | `👑 orchestrator` | The shared supervisor I mainly talk to |

Workers rename their tabs at milestones: investigating, building, testing,
reviewing, PR open, merged, or parked. The skill keeps the task and stage
current. Hooks update turn state and flag questions or permission requests.
When a turn ends with nothing flagged, Jev, TypeSafe's fast classifier, checks
whether the agent's last message waits on me, so a question it forgot to flag
still shows ❓. A finished session sets 🧹 itself, and the Stop hook leaves that
tab alone, so its sign-off can't read as a question.

| Prefix | Meaning in this customization |
| --- | --- |
| `⏳` | Working |
| `✅` | Turn finished, nothing needed from me |
| `🧹` | Task finished and reported; it only needs my yes to clear it |
| `⚪` | Ready, no active task |
| `❓` | I need to answer or decide |
| `❗` | I need to take an action |

A checkmark means a turn ended. Tests, review, and the actual result establish
whether a task is finished.

## Keep the question and the task

An agent can keep working while a question is pending. The label keeps
both parts:

```text
⏳ 🛠️ login fix
❓ ship today? · 🛠️ login fix
```

A turn ending leaves the question visible. My next message, or my answer
to a question dialog, clears it and the tab goes back to `⏳`. Another
agent's message doesn't.

## Why the hooks inject context

A skill that the agent has to remember to load doesn't get used. So the
Claude `SessionStart` hook tells every session to name its tab and how,
and each prompt carries a one-line reminder to flag asks before stopping.
The Codex helper does the same through its hook output.

## The shared orchestrator

One Claude or Codex session owns the shared orchestrator role. Its Herdr agent is named
`orchestrator` and its tab reads `👑 orchestrator`. Its session hook tells it
the role, and tells every other session to report to it.

- `herdr-orchestrator claim` makes the calling session the orchestrator.
- `herdr-orchestrator who` prints where it is.
- `herdr-orchestrator ensure` runs from the hooks. If the orchestrator is
  gone, it restarts it in its crowned tab, but never alongside a live one.
- `herdr-orchestrator next` hands the next queued brief to a `⚪ ready`
  Claude tab, or opens a new tab when there is enough free memory.
- `herdr-orchestrator route <brief>` asks Jev which lane a brief belongs to,
  and `herdr-orchestrator leads` gives a busy lane its own lead (below).

The orchestrator coordinates. It hands investigations, fixes and watching CI
to fresh sessions. It keeps no notes file: it rebuilds its picture each time
from ticket-graph checkpoints, Linear, GitHub and the tabs.

## Lanes and leads

One orchestrator holding every lane's detail fills its context. So the work
is split into lanes, listed in `~/.config/team-floor/lanes.json`, and a busy
lane gets a lead: a Claude session named `<lane>-lead` that runs that lane's
queue (leads started before the rename keep the old name, `lead-<lane>`, until
they hand back). The orchestrator stays the one way in and keeps one line per lane.

Jev picks a brief's lane; fixed rules decide what to do with the pick. A
sure pick (0.60 or more) routes the brief. A middling one (0.40 to 0.60)
routes it marked "lane to confirm". Anything weaker, `unclear`, or no Jev at
all leaves the brief unrouted and asks me. A lane with 4 or more open items
gets a lead. The team floor's chat can also start one at once, with my
message as its first prompt (`herdr-orchestrator lead <lane> --prompt-file`).
When it's down to 1, the lead hands it back and its conversation stays open.

## Set it up

Requirements: [Herdr](https://github.com/herdrdev/herdr) (checked with 0.9.1),
Python 3.11+, `jq`, a TypeSafe key for Jev, and Claude Code or Codex running inside a Herdr pane.
Linux and macOS both work. Follow the [setup guide](docs/setup.md).

- [Claude skill](claude/skills/herdr/SKILL.md) and hooks:
  [herdr-tab](claude/hooks/herdr-tab), [herdr-orchestrator](claude/hooks/herdr-orchestrator)
- [Codex skill](codex/skills/herdr/SKILL.md) and
  [helper](codex/skills/herdr/scripts/herdr-tab.py)
- Hook examples for [Claude Code](hooks/claude-hooks.example.json) and
  [Codex](hooks/codex-hooks.example.json)

Hooks never approve permissions and fail open when Herdr or Jev is
unavailable. Conversations are cleared only after I approve the exact pane and
session.

With a TypeSafe key, the Stop hooks send the last 1,500 characters of each
turn's last message to TypeSafe for Jev, and `route` sends the last 1,500
characters of a brief with the lane names and descriptions. Without a key,
nothing leaves the machine.

## Pair it with Agent Wire

I use [Agent Wire](https://github.com/kevinmanase/agent-wire) for a shared work
list and messages between Claude and Codex sessions. The orchestrator reads
that list to see what each session reports. `herdr-tab ask` and `request` also
set the session's Agent Wire ask, and my answer clears both. The labels and
hooks work without it.

## Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

[The tests](tests/test_herdr.py) run the helpers against a
[fake Herdr](tests/fake_herdr.py), never live tabs.

## License

Copyright © 2026 Kevin Manase and contributors.

Herdr customizations is licensed under the
[GNU Affero General Public License, version 3 only](LICENSE)
(`AGPL-3.0-only`). The full license is included in this repository.
