---
name: herdr
description: Keep this Codex session's Herdr tab name and status current when HERDR_ENV=1, flag asks for Kevin, and leave finished conversations open. Clear only an identified conversation explicitly approved by Kevin. Also use for Herdr tabs and agents, communicating with the shared orchestrator, or acting as orchestrator when Kevin assigns that role.
---

# Herdr for Codex

Kevin scans Herdr's tab strip to see what each agent is doing and which ones need
him. Keep the label honest: a status emoji, a stage emoji, and a short task name.
This skill controls the local terminal workspace through the `herdr` CLI.

## Source

This skill comes from [kevinmanase/herdr-customizations](https://github.com/kevinmanase/herdr-customizations), along with its `herdr-tab.py` helper. To change any of them, edit the repo clone, open a PR, and once it merges copy the files again on each machine as `docs/setup.md` describes. Never patch one machine's installed copy alone.

## Keep your tab current

Use the bundled [herdr-tab helper](scripts/herdr-tab.py). The commands below use
the default install path; if the skill lives elsewhere, resolve the script beside
this `SKILL.md`.

At the start of a user turn, set working status. Once you know the task, name it:

```bash
python3 ~/.codex/skills/herdr/scripts/herdr-tab.py status working
python3 ~/.codex/skills/herdr/scripts/herdr-tab.py name "🔍 herdr Codex port"
```

Keep the name around 28 characters: topic or ticket first, then a few words.
Preserve Kevin's own wording when it still fits. Rename when the stage or focus
changes, not for each tool call. Stage emoji: 🔍 investigating, 🛠️ building,
🧪 testing, 👀 reviewing, 🚀 PR open, 🎉 merged, 🚧 blocked, 💥 failing, 💤 parked.
Reserve 👑 for the shared orchestrator.

| First emoji | Meaning |
| --- | --- |
| ⏳ | Working |
| ✅ | Turn finished; nothing needed from Kevin |
| ⚪ | Ready, with no active task; a cleared session reads `⚪ ready` |
| ❓ | Kevin needs to answer or decide |
| ❗ | Kevin needs to act, such as signing in or approving a permission |

Before asking Kevin a question or ending a turn that needs him, put the actual
ask in the label:

```bash
python3 ~/.codex/skills/herdr/scripts/herdr-tab.py ask "merge now, or after your phone check?"
python3 ~/.codex/skills/herdr/scripts/herdr-tab.py request "run gcloud auth login in the cli tab"
```

These show `❓ <ask> · <name>` or `❗ <ask> · <name>` and send a local Herdr
notification. Use `ask` for a reply and `request` for an action. Do not include
secrets in a label or notification. An asynchronous question remains pending
after the question tool returns; clear it when Kevin answers, not when it is sent.
If work continues before the answer arrives, keep the question flag visible.

When finishing with nothing needed, run:

```bash
python3 ~/.codex/skills/herdr/scripts/herdr-tab.py status done
```

`status done` preserves an existing ❓/❗. `status working` clears it when Kevin
responds or the request is resolved. The prompt hook clears it only for Kevin's
own prompt, not a peer's `Status from …` or `<cross-session-message …>`. All commands are no-ops outside Herdr.
The helper resolves the pane's current tab so a moved pane does not rename its
old tab. It does not start other agents.

## Finish; clear only with Kevin's approval

The default is to report the outcome and set `status done`, leaving the chat
open. Completion, idle status, a merge, or an orchestrator assignment is not
permission to clear a conversation. Kevin may still need it for follow-up.

Before proposing a clear, identify the exact tab label, pane ID, agent kind,
and native session ID from live state. Ask Kevin explicitly whether to clear
that identified conversation, and keep the ask visible until he answers.
Do not infer the target from inherited pane variables or the focused tab.

Only after Kevin approves that target, run:

```bash
python3 ~/.codex/skills/herdr/scripts/herdr-tab.py clear \
  --approved-pane <pane-id> --approved-session <native-session-id>
```

Those flags record an approval already given; they do not grant permission.
The helper checks the identity again before scheduling and before delivery,
and refuses pending asks or blocked dialogs. If identity cannot be verified,
leave the chat open. Never use raw terminal input to bypass this requirement.
The same rule applies to clearing another agent's session. An approval expires
if the target conversation changes.

New tickets belong in fresh sessions. Codex supports `/clear` and `/rename`, but
Claude's `/color`, `SendMessage`, and `-n` launch flag are not Codex interfaces.
See [Codex CLI commands](https://developers.openai.com/codex/cli/slash-commands).

## The shared orchestrator

Find it with `herdr agent get orchestrator`. Use the same orchestrator for Claude
and Codex; do not create one per agent kind. When merging, getting blocked,
finishing, or starting a session, send the existing orchestrator one concise
update via Herdr's agent interface. Read
[orchestrator coordination](references/orchestrator.md) before messaging it or
when Kevin assigns you that role. Session hooks retain the crown across a clear
and remind a Codex orchestrator to rebuild its picture rather than keep notes.

## Automatic Codex hooks

The local installation registers hooks in `~/.codex/hooks.json` for session
start/reset, user prompts, questions, permission requests, tool completion, and
turn completion. Session and prompt hooks remind Codex to use this skill.
Explicit helper calls above also work when hooks have not been trusted yet.
Fresh sessions (`startup` or `clear`) reset the tab to `⚪ ready`; resume and
compaction preserve the task and pending asks. The shared orchestrator keeps its
crown on a fresh session.

Codex requires review of new or changed hook definitions in `/hooks` before they
run. Review the Herdr entries there; do not bypass hook trust or edit trust hashes.
If changes are not visible, restart or resume Codex. See the
[Codex hook documentation](https://learn.chatgpt.com/docs/hooks).

After installing or changing the reset-on-clear hook, restart Codex processes
that were already running and review the Herdr entries in `/hooks`. Do not rely
on `/clear` alone to activate newly installed hook definitions. An older process
has been observed clearing its chat while retaining the previous task label;
the closed process's loaded hook configuration could not be verified. This is
a rollout caveat, not proof that every helper-script edit requires a restart:
the registered command reads `herdr-tab.py` each time it runs. If a restarted
process with the current hook trusted still retains the label after `/clear`,
investigate it as a reset bug rather than attributing it to process age.

These hooks only update labels and notifications; they do not approve or deny
permissions. Question hooks use Codex's `request_user_input` and
`request_user_input_async`, including namespaced tool names. Keep flagging plain
text asks yourself; a hook cannot reliably infer intent from prose.

Optional Jev fallback: like the Claude setup, the Stop hook can classify the last
assistant message when there's a TypeSafe key: `TYPESAFE_API_KEY`, `jev.api_key` in
`~/.config/team-floor/config.json`, or the file named by `jev.api_key_file` there (by default
`~/.config/typesafe/api-key`).
Only the last 1,500 characters go to TypeSafe. No key means no classifier request.
Set `HERDR_JEV_ENABLED=0` to disable it even when a key exists. Explicit ❓/❗ flags
take precedence. Codex's `last_assistant_message` field is used directly; the
helper does not depend on Claude transcript formats.

## Inspect tabs or start agents when Kevin asks

Verify `HERDR_ENV=1` before issuing raw Herdr commands. If it is absent, report
that this session is outside Herdr; do not target another client's focused pane.
Read `herdr --skill` for the installed CLI's full guide and use `--help` for the
relevant command. Read IDs from JSON responses, never tab order or examples.

For a requested new tab and Codex agent:

1. Create the tab with
   `herdr tab create --workspace "$HERDR_WORKSPACE_ID" --label "<name>" --cwd <dir> --no-focus`.
   Read `.result.tab.tab_id` and `.result.root_pane.pane_id`. If your pane has moved,
   get its current workspace from `herdr pane current --current` first.
2. Start with `herdr agent start <agent-name> --kind codex --pane <pane_id>`.
   Respect a different agent kind if Kevin requested one. Names match
   `[a-z][a-z0-9_-]{0,31}`. `agent_not_ready` can mean a trust or login dialog:
   read it and get Kevin's decision before answering it.
3. Send a self-contained brief:
   `herdr agent prompt <agent-name> "<task, worktree, rules, and stopping point>"`.
   For a short task, append `--wait --timeout 30000`; for long work, return to your
   own task and check later. A wait timeout does not mean the prompt was unsent;
   inspect before retrying. Quote user text safely instead of interpolating it
   into shell source.
4. Inspect with `herdr agent get <agent-name>` and
   `herdr agent read <agent-name> --source recent-unwrapped --lines 120`.
   Bound waits, for example `herdr agent wait <agent-name> --until blocked --timeout 30000`.

Start or assign work to another agent only when Kevin requested that work or
assigned you the orchestrator role. Status updates to the existing orchestrator
follow the coordination reference. For agents
making independent code changes, use separate git worktrees. Keep concurrent
test jobs modest on this machine. Never close tabs or panes you did not create,
or run `herdr server stop`, unless Kevin explicitly asks for that action.
