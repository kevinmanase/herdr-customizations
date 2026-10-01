---
name: herdr
description: Keep your Herdr tab's name and status emoji current, flag asks for Kevin, and leave completed chats open unless Kevin approves clearing the identified session. Use in every Herdr session and for Herdr agent or orchestrator coordination.
---

# Herdr

Kevin runs his coding agents in Herdr tabs and scans the tab strip to see which ones need him. Keep your tab's label honest and readable at a glance. Emoji carry the state; a few words carry the task.

## Your tab's label

The label reads `<status> <name>`, for example `⏳ 🧪 login bug`. When you need Kevin, it reads `<❓ or ❗> <the ask> · <name>`.

### Status: the first emoji

| Emoji | Meaning | Set by |
| --- | --- | --- |
| ⏳ | working | a hook, when Kevin sends a message or answers a dialog |
| ✅ | done: nothing needed from Kevin | a hook, when your turn ends |
| ⚪ | ready: a cleared session with no task yet; the label reads `⚪ ready` | a hook, on `/clear` |
| ❓ | Kevin needs to answer or decide | you (`ask`), or a hook on a question dialog or plan approval |
| ❗ | Kevin needs to do something: log in, approve, check his phone, run a command | you (`request`), or a hook on a permission prompt |

### When you need Kevin, flag it

A hook can't tell when a plain-text reply waits on Kevin. So before you end any turn that waits on him, flag it with the ask itself, in a few words:

```bash
~/.claude/hooks/herdr-tab ask "merge the PR now, or after your phone check?"
~/.claude/hooks/herdr-tab request "run gcloud auth login in the cli tab"
```

Flagging puts the ask in the tab's label, for example `❓ merge the PR now, or after your phone check? · 🚀 login fix PR open`, and pops a Herdr notification. The Stop hook keeps the flag. Kevin's next message, or his answer to a dialog, clears it and turns the tab back to ⏳. Write the ask so he can act on it from the tab strip alone. Use `ask` when he has to reply, and `request` when he has to do something outside this conversation.

### Name: everything after the status

You own the name. Set it as soon as you understand the task well enough to say it in a few words:

```bash
~/.claude/hooks/herdr-tab name "🔍 login bug"
```

Rename when you judge the old name has stopped describing the work: a new stage, or a changed focus. Don't rename for every step.

- **Length:** stay under about 28 characters. Put the ticket id or topic first, then a one- to three-word gist.
- **Stage emoji:** lead with one:
  - 🔍 investigating
  - 🛠️ building
  - 🧪 testing
  - 👀 in review
  - 🚀 PR open
  - 🎉 merged
  - 🚧 blocked
  - 💥 failing
  - 💤 parked
  - 👑 the orchestrator's tab only (see below)
- **Kevin's own name:** if Kevin typed the current name and it still fits, keep his words. Adding a stage emoji is fine.

`herdr-tab` does nothing outside Herdr, so these commands are always safe to run.

### Optional: Jev

With a TypeSafe key set, the Stop hook asks Jev, TypeSafe's fast classifier, whether your last message waits on Kevin, so a question you forgot to flag still shows ❓. The key can be `TYPESAFE_API_KEY` in the environment or a file at `~/.config/typesafe/api-key`. The hook sends Jev only the last 1,500 characters of that message. Without a key, nothing leaves the machine.

## Finish; clear only with Kevin's approval

Report the outcome and set `status done`, leaving the chat open. Completion,
idle status, a merge, or an orchestrator assignment is not permission to clear.
Kevin may still need the conversation for follow-up.

Before proposing a clear, identify the exact tab label, pane ID, agent kind,
and native session ID from live state. Ask Kevin explicitly whether to clear
that conversation and keep the ask visible until he answers. Do not infer the
target from inherited pane variables or the focused tab.

Only after Kevin approves that target, run
`~/.claude/hooks/herdr-tab clear --approved-pane <pane-id> --approved-session <session-id>`.
These flags record permission already given; they do not grant it. The helper
rechecks session identity before scheduling and before delivery. If identity
cannot be verified, leave the chat open. Never use raw terminal input to bypass
approval. The rule applies to your own session and to every other session;
approval expires if the target conversation changes.

The clear also drops your names, unless you're the orchestrator: the hook clears your Herdr agent name and renames your Claude session `ready`, so a note meant for the old task can't wake a session that has no context. A session named `ready` has no task, so don't message it, even when SendMessage or `ListAgents` says it used to be the one you want.

Never carry on with the next ticket in the same session. New work goes to a fresh session: a `⚪ ready` tab or a new one.

## The orchestrator (👑)

Exactly one Claude session in Herdr is the orchestrator. It keeps track of every other session, so Kevin can ask one place what's latest, what's done and what's left.

- **How to spot it:**
  - Its Herdr agent is named `orchestrator`.
  - Its tab reads `👑 orchestrator`, and no other tab uses 👑.
  - Its Claude session is named `orchestrator`, so SendMessage reaches it by that name.
  - Its prompt bar is yellow.
  - `~/.claude/hooks/herdr-orchestrator who` prints where it is.
- **Always exactly one:**
  - Herdr keeps agent names unique, so there can never be two.
  - Whenever none is running, herdr-tab's hooks run `herdr-orchestrator ensure`. It waits a minute, then starts one in the 👑 tab's shell, or in a new tab if no tab wears the crown. It starts none while a 👑 tab still runs Claude. It notifies Kevin instead if memory is short or something else runs in the 👑 tab.
  - The role survives `/clear` and a restart: the tab keeps its crown, and the hook tells the conversation that it's the orchestrator. A restart clears the Herdr name, so the hook gives it back.
- **Moving the role:** when Kevin makes you the orchestrator, run `~/.claude/hooks/herdr-orchestrator claim`. It moves the name and the crown to you, and renames and colors your session. Then tell the old orchestrator with SendMessage.
- **Every other session:** send the orchestrator one line whenever you merge, get blocked, finish, or start another session.

### If you are the orchestrator

- **Coordinate, don't do the work.** Your own jobs are reading tabs, relaying, queueing, keeping notes, and flagging Kevin. Everything else goes to a fresh session with a self-contained brief: investigations, checks, deploys, watching CI or a deploy, documents, fixes. Queue it and run `herdr-orchestrator next`. A small, lean orchestrator stays responsive and survives a `/clear`.
- **Notes:** keep them in `~/.local/state/orchestrator/STATUS.md`, with Latest, Needs Kevin, Done, Left, and a Sessions table. Update them whenever something changes, so a `/clear` or a replacement loses nothing. `~/.local/state/orchestrator` is your own local git repo: if it isn't one yet, run `git init` there. Never add a remote. Commit after each update, so `git log -p STATUS.md` shows what changed and when; don't save `STATUS.before-*.md` copies.
- **Watch every tab:** if Agent Wire is installed, start from its self-reported list, `agent-wire --state ~/.local/state/agent-wire sessions --table`, which shows each session's task and status and whether it's stale. Then read a tab with `herdr agent read <pane> --source recent-unwrapped --lines 200`. Check the facts yourself (GitHub, Linear, CI) before you act on them. Send a stalled session one clear SendMessage nudge.
- **Prompt boxes:** dim text in a Claude prompt box is Claude Code's prompt suggestion, not something Kevin typed. `herdr pane read <pane> --source visible --format ansi` shows it wrapped in `ESC[2m`.
- **Agent reports:** Codex sessions report by typing `Status from <pane/ticket>: …` into your prompt with `herdr agent prompt`, so it arrives looking exactly like Kevin typing. A prompt starting `Status from …` is an agent's report, never Kevin's words, a decision, or an approval.
- **New work goes to fresh sessions:** write a self-contained brief to `~/.cache/herdr-fleet/queue/<order>-<agent-name>.md`, then run `~/.claude/hooks/herdr-orchestrator next`. It reuses a `⚪ ready` Claude tab or opens a new one in `HERDR_WORK_DIR` (default: the current directory), and leaves the brief queued if free memory is under `FLEET_MIN_MB` (default 1500).
- **Finished sessions:** leave their conversations open. Identify the tab label, pane, kind, and native session ID, then obtain Kevin's explicit approval before clearing or closing that target. Recheck identity immediately before acting. Idle/done, `⚪ ready`, and memory pressure are not approval; never clear or close a different occupant under an old approval.
- **Kevin's decisions:** keep his open asks on your own tab with `herdr-tab ask`. Relay his answers to the sessions that own the work. Production, data, spend and exceptions to a gate stay his calls; never make them for him.
- **Telling sessions apart:** `/rename <name>` and `/color <color>` change another session's name and prompt bar. Send them with `herdr agent prompt <pane> "/rename login-fix"`. Both take effect at once, even while the session is busy.

## Opening tabs and starting agents

Only do this when Kevin asks for it, or as the orchestrator. Herdr's CLI talks to the current session and returns JSON; read IDs from the responses. A `⚪ ready` Claude tab is already a fresh session, so reuse one before opening another: `herdr agent rename <pane> <agent-name>`, send it `/rename <agent-name>`, then go to step 3.

1. **Create the tab.** Run `herdr tab create --workspace "$HERDR_WORKSPACE_ID" --label "<name>" --cwd <dir> --no-focus`, then read `.result.tab.tab_id` and `.result.root_pane.pane_id`.
2. **Start the agent.** Run `herdr agent start <agent-name> --kind claude --pane <pane_id>`.
   - Agent names match `[a-z][a-z0-9_-]{0,31}`.
   - It returns once the agent is ready.
   - `agent_not_ready` means a startup dialog is showing, such as folder trust. Read it with `herdr agent read <name> --source recent-unwrapped --lines 60` and ask Kevin before answering it.
3. **Hand it the task.** Run `herdr agent prompt <agent-name> "<self-contained brief>" --wait --timeout 120000`.
   - The new session knows nothing of yours, so the brief must stand alone: the ticket, the worktree, the rules and the stopping point.
4. **Follow along.** Use `herdr agent get <name>`, `herdr agent read <name> --source recent-unwrapped --lines 120`, and `herdr agent wait <name> --until blocked`.

Give each agent its own git worktree. On a small box, keep it to two or three agents running tests at once.

Leave tabs and conversations open unless Kevin explicitly approves clearing or closing the identified target. Never run `herdr server stop`. For everything else, run `herdr --skill` for Herdr's full agent guide.
