# Set up the Herdr customization

Requirements: [Herdr](https://github.com/herdrdev/herdr) (checked with 0.9.1),
Python 3.11+, `jq`, and a TypeSafe key for Jev (see below), on Linux or macOS. Run Claude Code or Codex inside a
Herdr pane. Herdr supplies `HERDR_ENV=1` and `HERDR_PANE_ID`, and every
helper does nothing without them.

## Copy the files

From a checkout of this repository:

```sh
mkdir -p ~/.claude/hooks ~/.claude/skills ~/.codex/skills
cp claude/hooks/herdr-tab claude/hooks/herdr-orchestrator ~/.claude/hooks/
cp -R claude/skills/herdr ~/.claude/skills/
cp -R codex/skills/herdr ~/.codex/skills/
```

The skills refer to these exact paths, so keep them. To update, pull and
copy again. If your Claude Stop hook entry still has `"async": true` from an
earlier version, remove it (see below).

## Add the hooks

Merge the entries from [the Claude example](../hooks/claude-hooks.example.json)
into the `hooks` object in `~/.claude/settings.json`, and
[the Codex example](../hooks/codex-hooks.example.json) into
`~/.codex/hooks.json`. Replace `/ABSOLUTE/HOME` with your home directory.
Append to the existing event arrays; keep Herdr's own integration hooks and
Agent Wire's hooks. Use one naming helper per tab: remove the older
`herdr-labels` hooks and skill if you installed them.

Codex asks you to trust new hook definitions in `/hooks`. Claude picks up
settings changes on its own; start a new session to get the session hook's
context.

Keep Claude's Stop hook synchronous, as in the example (no `"async"`). Claude
Code takes the next prompt only after it returns, so Jev's answer about one
turn can't land on the next. The hook marks the turn ✅ before it asks Jev, and
its Jev call gives up after 5 seconds, or after 1 for five minutes after Jev times out.

## Add the TypeSafe key

Jev needs a TypeSafe key. Put it in `~/.config/team-floor/config.json`, the
config the team floor also reads, as `{"jev": {"api_key": "<your key>"}}`. If
the file already exists, add the `jev` entry to it. Use an editor, not a shell
command, so the key stays out of your shell history. Then keep the file
private:

```sh
chmod 600 ~/.config/team-floor/config.json
```

To check it, run this in a Herdr pane. It asks Jev once and says whether the
Stop hook can use it:

```sh
~/.claude/hooks/herdr-tab check-jev
```

Run it again after you change the key. Until a call succeeds, sessions open
with a Herdr message saying why Jev isn't working, and a session tells you once
when Jev starts failing.

## Settings

| Variable | Default | Used for |
| --- | --- | --- |
| `HERDR_WORK_DIR` | the current directory | where `herdr-orchestrator` starts new sessions |
| `HERDR_FLEET_QUEUE` | `~/.cache/herdr-fleet/queue` | briefs for `herdr-orchestrator next` |
| `FLEET_MIN_MB` | `1500` | free memory needed before opening another tab |
| `HERDR_BIN_PATH` | `herdr` on PATH | the Herdr CLI, if the hook's PATH lacks it |
| `TYPESAFE_API_KEY`, then `jev.api_key` in `~/.config/team-floor/config.json` (keep it `chmod 600`), then the file named by `jev.api_key_file` (relative to that folder), by default `~/.config/typesafe/api-key` | none: add one (above) | the key for both Jev calls: the Stop hook asks whether a reply waits on you, and `route` asks for a brief's lane |
| `TYPESAFE_API_URL` | TypeSafe's endpoint | where both Jev calls go (the Stop hook and `route`); the tests point it at a local fake |
| `~/.config/team-floor/lanes.json` | none | the lanes, shared with the team floor: `{"lanes": [{"id", "name", "about"}]}` |

Without a TypeSafe key nothing leaves the machine. With one, the Stop hook
sends the last 1,500 characters of the agent's last message, and
`herdr-orchestrator route` sends the last 1,500 characters of the brief with
the lane names and descriptions.

## Start the orchestrator

In the Claude session you want as the orchestrator:

```sh
~/.claude/hooks/herdr-orchestrator claim
```

From then on, the hooks keep exactly one running. To hand it work, write a
self-contained brief to `~/.cache/herdr-fleet/queue/<order>-<agent-name>.md` and
run `~/.claude/hooks/herdr-orchestrator next`.

With lanes set up, route the brief first, and check the lanes now and then:

```sh
~/.claude/hooks/herdr-orchestrator route ~/.cache/herdr-fleet/queue/01-webhook-fix.md
~/.claude/hooks/herdr-orchestrator leads
```

## Try the labels

Inside a Herdr pane:

```sh
~/.claude/hooks/herdr-tab name "🔍 login bug"
~/.claude/hooks/herdr-tab ask "ship today?"
~/.claude/hooks/herdr-tab status working
```

The tab reads `⏳ 🔍 login bug`, then `❓ ship today? · 🔍 login bug`, then
`⏳ 🔍 login bug` again. Codex uses
`python3 ~/.codex/skills/herdr/scripts/herdr-tab.py` with the same commands.
