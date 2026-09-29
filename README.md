# Herdr customizations

**One orchestrator. Named workers. Questions that stay visible.**

My tab naming setup for [Herdr](https://github.com/herdrdev/herdr), packaged
as a skill, a small Python helper, and lifecycle hooks for Claude Code and
Codex. The agents keep their native tools and sessions. The labels help me
see what they are doing and which ones need me.

I mainly talk to one orchestrator. It coordinates the workers and brings
decisions back to me. I reserve the crown for that agent so it is easy to
find in a busy workspace.

## What it looks like

<img src="docs/screenshots/herdr-orchestrator.png" alt="Kevin's Herdr sidebar with a crowned orchestrator, named Claude and Codex workers, stage icons, and a pending question" width="560" />

*Screenshot from my working setup. The portable helpers in this repository
use the same naming convention. Herdr's own sidebar indicators are separate
from the label prefixes added by these hooks.*

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

| Prefix | Meaning in this customization |
| --- | --- |
| `⏳` | Working |
| `✅` | Turn finished, nothing needed from me |
| `⚪` | Ready, no active task |
| `❓` | I need to answer or decide |
| `❗` | I need to take an action |

A checkmark means a turn ended. Tests, review, and the actual result establish
whether a task is finished.

## Keep the question and the task

An agent can keep working while a question is pending. The label preserves
both parts:

```text
⏳ 🛠️ login fix
❓ ship today? · 🛠️ login fix
❓ ship today? · 🧪 login tests
```

Renaming, tool completion, a new prompt, and Stop leave the question visible.
Once it is answered, the agent calls `resolve` and the label returns to
`⏳ 🧪 login tests`. Action requests work the same way.

## Set it up

Requirements: [Herdr](https://github.com/herdrdev/herdr), Python 3.11+, and
Claude Code or Codex running inside a Herdr pane. The helper uses Python's
standard library and the Herdr CLI. Command shapes were checked with Herdr 0.9.1.

```sh
git clone https://github.com/kevinmanase/herdr-customizations.git
cd herdr-customizations
```

Follow the [setup guide](docs/setup.md) to copy the skill into your user skills
directory and merge the hook definitions into your existing settings.

- [Naming skill](skills/herdr-labels/SKILL.md)
- [Python helper](skills/herdr-labels/scripts/herdr_tab.py)
- [Claude Code hook example](hooks/claude-hooks.example.json)
- [Codex hook example](hooks/codex-hooks.example.json)

After installing the Codex skill, these commands run inside its Herdr pane:

```sh
helper="${CODEX_HOME:-$HOME/.codex}/skills/herdr-labels/scripts/herdr_tab.py"
python3 "$helper" name "🛠️ login fix"
python3 "$helper" status working
python3 "$helper" ask "ship today?"
```

The setup guide also covers optional notifications, hook review, and removal.
Hooks return `{}` without approving permissions. They leave conversations
open and fail open when Herdr is unavailable.

## Make it yours

Edit the installed [skill](skills/herdr-labels/SKILL.md) to change stage icons,
task naming, or the orchestrator convention. These are instructions for the
agent; the helper does not assign roles or infer the task from a transcript.
If you replace the crown symbol, update the helper's startup preservation
check too so the orchestrator name survives a fresh session.

The [helper](skills/herdr-labels/scripts/herdr_tab.py) owns the status markers
in `MARKERS` and the field length in `MAX_NAME`. Change it alongside the skill
if you want different prefixes. Set `HERDR_LABEL_NOTIFICATIONS=1` before
launching the agent to enable notifications when a tab enters an attention
state. Use `HERDR_BIN_PATH` if Herdr is outside the hook process's PATH.

Use one naming helper per tab. If you already have custom naming hooks,
compare and merge the behavior you want. Keep Herdr's built-in session
integration in place.

## Pair it with Agent Wire

I use [Agent Wire](https://github.com/kevinmanase/agent-wire) for a shared work
list and messages between enrolled Claude and Codex sessions. Herdr labels
make the workspace readable; Agent Wire gives the agents a way to coordinate.

Both projects work independently. A crown or pane ID is not an Agent Wire
identity, and the tab's turn-finished checkmark is separate from a task report.

## Development

Development tools can live outside the checkout:

```sh
python3 -m venv "$HOME/.cache/herdr-customizations-dev/venv"
dev="$HOME/.cache/herdr-customizations-dev/venv/bin"
"$dev/python" -m pip install -r requirements-dev.txt
"$dev/python" -m pytest -q
"$dev/ruff" check .
"$dev/ruff" format --check .
```

Tests use a fake Herdr command boundary. They check pending asks, renaming,
orchestrator names, hook output, stale pane references, timeouts, and error
handling without touching live tabs. See [the tests](tests/test_herdr_labels.py).

## License

Copyright © 2026 Kevin Manase and contributors.

Herdr customizations is licensed under the
[GNU Affero General Public License, version 3 only](LICENSE)
(`AGPL-3.0-only`). The full license is included in this repository.
