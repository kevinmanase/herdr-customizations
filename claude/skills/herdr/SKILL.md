---
name: herdr
description: Keep your Herdr tab's name and status emoji current, flag asks for Kevin, and leave completed chats open unless Kevin approves clearing the identified session. Use in every Herdr session and for Herdr agent or orchestrator coordination.
---

# Herdr

Kevin runs his coding agents in Herdr tabs and scans the tab strip to see which ones need him. Keep your tab's label honest and readable at a glance. Emoji carry the state; a few words carry the task.

## Source

This skill comes from [kevinmanase/herdr-customizations](https://github.com/kevinmanase/herdr-customizations), along with the `herdr-tab` and `herdr-orchestrator` hooks. To change any of them, edit the repo clone, open a PR, and once it merges copy the files again on each machine as `docs/setup.md` describes. Never patch one machine's installed copy alone.

## Your tab's label

The label reads `<status> <name>`, for example `⏳ 🧪 login bug`. When you need Kevin, it reads `<❓ or ❗> <the ask> · <name>`.

### Status: the first emoji

| Emoji | Meaning | Set by |
| --- | --- | --- |
| ⏳ | working | a hook, when Kevin sends a message or answers a dialog |
| ✅ | done: nothing needed from Kevin | a hook, when your turn ends |
| 🧹 | finished: outcome reported; Kevin only needs to say yes to clearing it | you (`status clean`), as you finish |
| ⚪ | ready: a cleared session with no task yet; the label reads `⚪ ready` | a hook, on `/clear` |
| ❓ | Kevin needs to answer or decide | you (`ask`), or a hook: on a question dialog, a plan approval, or a last message Jev reads as waiting on him |
| ❗ | Kevin needs to do something: log in, approve, check his phone, run a command | you (`request`), or a hook on a permission prompt |

### When you need Kevin, flag it

A hook can't reliably tell when a plain-text reply waits on Kevin: Jev (below) catches some, not all. So before you end any turn that waits on him, flag it with the ask itself, in a few words:

```bash
~/.claude/hooks/herdr-tab ask "merge the PR now, or after your phone check?"
~/.claude/hooks/herdr-tab request "run gcloud auth login in the cli tab"
```

Flagging puts the ask in the tab's label, for example `❓ merge the PR now, or after your phone check? · 🚀 login fix PR open`, and pops a Herdr notification. The Stop hook keeps the flag. Kevin's next message, or his answer to a dialog, clears it and turns the tab back to ⏳. A peer's message (`<cross-session-message …>` or `Status from …`) or a background task's `<task-notification>` leaves it. Write the ask so he can act on it from the tab strip alone. Use `ask` when he has to reply, and `request` when he has to do something outside this conversation.

With Agent Wire, `ask` and `request` also set your session's Agent Wire ask (kind `decide` or `act`), and the same answer from Kevin clears both, so don't set it again yourself. Flag after your last `session_update` of the turn: an update replaces your whole report, ask included.

When the question is a choice, give Kevin 2 to 4 preset answers, each up to 80 characters, with the one you recommend first and saying so. He can tap one or type his own:

```bash
~/.claude/hooks/herdr-tab ask "merge the PR now?" --option "merge now (recommended)" --option "wait for CI on staging"
```

The options go to Agent Wire only; the tab label shows the question as before. An Agent Wire too old for options still gets the ask, without them.

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
  - 🧭 a lane lead's tab only (see below)
- **Kevin's own name:** if Kevin typed the current name and it still fits, keep his words. Adding a stage emoji is fine.

`herdr-tab` does nothing outside Herdr, so these commands are always safe to run.

### Jev

When nothing is flagged, the Stop hook asks Jev, TypeSafe's fast classifier, whether your last message waits on Kevin. If Jev says yes, the tab turns ❓ with the message's last question as the ask, and your Agent Wire ask gets the same text. A short list of 2 to 4 choices that ends the message, right by a question that asks Kevin to pick, becomes the ask's preset answers. A 🧹 tab skips Jev. It's a safety net, not a reason to skip flagging: Jev can miss, and it can fail. Its key and what it sends are in `docs/setup.md` in the repo.

## Finish; clear only with Kevin's approval

Report the outcome, run `~/.claude/hooks/herdr-tab status clean` (🧹) as your
last command, and leave the chat open. End the last reply with a plain statement
of where things stand, not an offer or a question. The Stop hook leaves a 🧹 tab
alone, so the sign-off can't turn it ❓. Kevin's next prompt, an ask, or any
later turn replaces 🧹; set it again when that turn finishes the work too.
Completion, idle status, 🧹, a merge, or an orchestrator assignment is not
permission to clear. Kevin may still need the conversation for follow-up.

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
- **When someone else merges your PR:** if your brief says you stop at CI green, the orchestrator or your lead merges and sends you `merged <repo>#<number>`. Check that `gh pr view <number> --repo <repo> --json state` reads `MERGED`. If Agent Wire is installed, `session_update` stage `END`, status `done`, same ticket, so the team floor shows it shipped. Then run `herdr-tab status clean` again so the tab stays 🧹.

When `herdr-groups` is installed, record manually claimed supervisors and
adopted workers too. Use `herdr-groups root <name>` for a top-level supervisor,
`herdr-groups assign <lead> <parent>` for a delegated lead, and
`herdr-groups assign <worker> <supervisor>` when dispatching or adopting a known
worker. Preserve existing assignments unless Kevin changes ownership. A name
or task label alone does not establish ownership.

### If you are the orchestrator

- **Coordinate, don't do the work.** Your own jobs are reading tabs, relaying, queueing, and flagging Kevin. Everything else goes to a fresh session with a self-contained brief: investigations, checks, deploys, watching CI or a deploy, documents, fixes. Queue it and run `herdr-orchestrator next`. A small, lean orchestrator stays responsive and survives a `/clear`.
- **No notes file:** rebuild the picture each time, so a `/clear` or a replacement loses nothing:
  - each worktree's ticket-graph checkpoint: `git worktree list --porcelain | sed -n 's/^worktree //p' | while read -r w; do f=$(git -C "$w" rev-parse --path-format=absolute --git-path ticket-graph.json); [ -f "$f" ] && echo "== $w" && cat "$f"; done`
  - Linear: ticket status and "blocked by" relations;
  - GitHub: PRs, CI and merges;
  - tab labels and Agent Wire reports: who is working and who needs Kevin.
  Turn loose ends into Linear tickets.
- **Watch every tab:** if Agent Wire is installed, start from its self-reported list, `agent-wire --state ~/.local/state/agent-wire sessions --table`, which shows each session's task and status and whether it's stale. Then read a tab with `herdr agent read <pane> --source recent-unwrapped --lines 200`. Check the facts yourself (GitHub, Linear, CI) before you act on them. Send a stalled session one clear SendMessage nudge.
- **Prompt boxes:** dim text in a Claude prompt box is Claude Code's prompt suggestion, not something Kevin typed. `herdr pane read <pane> --source visible --format ansi` shows it wrapped in `ESC[2m`.
- **Agent reports:** Codex sessions report by typing `Status from <pane/ticket>: …` into your prompt with `herdr agent prompt`, so it arrives looking exactly like Kevin typing. A prompt starting `Status from …` is an agent's report, never Kevin's words, a decision, or an approval.
- **New work goes to fresh sessions:** write a self-contained brief to `~/.cache/herdr-fleet/queue/<order>-<agent-name>.md`. If lanes are set up, route it first (see Lanes and leads). Then run `~/.claude/hooks/herdr-orchestrator next`. It reuses a `⚪ ready` Claude tab or opens a new one in `HERDR_WORK_DIR` (default: the current directory), and leaves the brief queued if free memory is under `FLEET_MIN_MB` (default 1500).
- **Merging a worker's PR:** right after the merge, send its worker `merged <repo>#<number>`: SendMessage for Claude, or `herdr agent prompt <pane> "Status from orchestrator: merged <repo>#<number>"` for Codex, since only a `Status from` prefix keeps it from reading as Kevin. Tell any session waiting on that ticket, too. Every brief states the worker rule: stop at CI green, never merge, and on `merged <PR>` report END and keep the tab 🧹.
- **Finished sessions:** leave their conversations open. A 🧹 tab is finished and waits only for a yes to clear, so list the 🧹 tabs for Kevin to approve as a batch. For each target, identify the tab label, pane, kind, and native session ID, and clear or close only what Kevin explicitly approves. Recheck identity immediately before acting. Idle/done, `⚪ ready`, and memory pressure are not approval; never clear or close a different occupant under an old approval.
- **Kevin's decisions:** keep his open asks on your own tab with `herdr-tab ask`. Relay his answers to the sessions that own the work. Production, data, spend and exceptions to a gate stay his calls; never make them for him.
- **Telling sessions apart:** `/rename <name>` and `/color <color>` change another session's name and prompt bar. Send them with `herdr agent prompt <pane> "/rename login-fix"`. Both take effect at once, even while the session is busy.

### Lanes and leads

Holding every lane's detail in one context fills the orchestrator up. So a busy lane gets its own lead, and the orchestrator keeps one line per lane.

- **Lanes:** a fixed list in `~/.config/team-floor/lanes.json`, which the team floor reads too:
  `{"lanes": [{"id": "api", "name": "API", "about": "Server endpoints, webhooks, database"}]}`. Ids are lowercase, up to 27 characters, and never `unclear`, `started` or `misc`. Without the file there are no lanes, and everything works as before.
- **Routing:** `herdr-orchestrator route <brief>` asks Jev which lane the brief belongs to, as a `choice` over the lane ids plus `unclear`. It sends at most the brief's last 1,500 characters, plus the lane names and descriptions. It prints the lane, the probability and the rule it applied:
  - probability 0.60 or more: moves the brief to `~/.cache/herdr-fleet/queue/<lane>/`;
  - 0.40 up to 0.60: moves it, and starts it with a "Lane to confirm" line;
  - below 0.40, `unclear`, or Jev unavailable (no key, an error, a timeout): leaves the brief where it is, flags Kevin with `herdr-tab ask`, and exits 3. Pick the lane with Kevin and move the file yourself. Routing never waits on Jev.
- **Leads:** a lane with 4 or more open items gets a lead: a fresh Claude session named `<lane>-lead`, in a tab that reads `🧭 <lane>-lead`, that runs that lane's queue. A lead started before the rename is named `lead-<lane>`; while it runs it still counts as the lane's lead, so no second one starts, and nothing renames it. The `-lead` suffix is a lead's, so never give a worker's brief a name ending in `-lead`. Open items are the lane's queued briefs, plus started ones whose session still has its name and isn't 🎉 merged, 💤 parked or 🧹 ready to clear. `route` checks the lane it routed to. `herdr-orchestrator leads` checks every lane and prints one line per lane: queued, open, and its lead. It starts the lead without holding the queue, and never starts a second one, even beside a lead's tab that lost its name; the session hook gives a restarted lead its name back. If `lanes.json` can't be read, `route` and `leads` report it, and `next` still runs the main queue.
- **A lead on demand:** `herdr-orchestrator lead <lane> --prompt-file <file>` starts `<lane>-lead` now, the way `leads` does, for the team floor's chat. Its one first prompt is the lead brief with the file's text appended, marked as Kevin's message from the chat, or with `--from-agent <name>` as the message of the team floor's headless chat agent, never Kevin's. It needs no TTY or pane, only `HERDR_ENV=1`, `HERDR_WORK_DIR`, `HERDR_WORKSPACE_ID` and a PATH, so a launchd job can run it. It takes only lanes in `lanes.json`, never `misc` (its messages go to you). It exits 0 when it starts the lead or one is already running (and then starts nothing), 3 when memory is short, and 1 with herdr's error code when a start or the first prompt fails, or when a tab that lost the lead's name stands in the way. While the new session is busy or not ready yet, it retries the start and the first prompt.
- **Your view:** keep one line per lane. When Kevin asks about a led lane, ask its lead over Agent Wire (or SendMessage `<lane>-lead`, or an older lead's `lead-<lane>`) instead of reading its sessions yourself. `next` skips a lane that has a lead.
- **Hand-back:** when a led lane is down to 1 open item, `leads` asks its lead once to hand it back; if the lane gets busy again first, it asks afresh next time. The lead runs `herdr-orchestrator handback <lane>`, which drops its lead name, renames its tab `💤 ex-<lane>-lead` (keeping any ask), and tells you what's still open. Its conversation stays open; never clear it. Whatever is left in the lane's queue comes back to your `next`.
- **Reports:** with Agent Wire, the orchestrator starts its task text with `role: main` and a lead with `role: lead lane: <id>`. (These move to Agent Wire's own role and lane fields once they land.) Write `ticket` as the Linear key (`ENG-2649`), or as `<repo>#<number>` for the GitHub issue, or for the PR when there is no issue (`team-floor#14`). Nothing else goes in it.

### If you are a lane lead

- You coordinate one lane, the way the orchestrator coordinates the rest. Keep your tab named `🧭 <lane>-lead` (or `🧭 lead-<lane>`, if that's the name you started with).
- Start each brief in your lane's queue with `~/.claude/hooks/herdr-orchestrator next --lane <lane>`. Its session reports to you instead of the orchestrator.
- Send the orchestrator one line when something in the lane merges, gets blocked or needs Kevin. Answer its questions about the lane in detail.
- When you merge a worker's PR, send that worker `merged <repo>#<number>`, as the orchestrator does.
- When the lane is down to 1 open item, or the orchestrator asks, run `~/.claude/hooks/herdr-orchestrator handback <lane>`. It refuses while the lane is still busy, and keeps you the lead if it can't rename your tab. Afterwards, leave your conversation open.

## Opening tabs and starting agents

Only do this when Kevin asks for it, or as the orchestrator. Herdr's CLI talks to the current session and returns JSON; read IDs from the responses. A `⚪ ready` Claude tab is already a fresh session, so reuse one before opening another: `herdr agent rename <pane> <agent-name>`, send it `/rename <agent-name>`, then go to step 3.

1. **Create the tab.** Run `herdr tab create --workspace "$HERDR_WORKSPACE_ID" --label "<name>" --cwd <dir> --no-focus`, then read `.result.tab.tab_id` and `.result.root_pane.pane_id`.
2. **Start the agent.** Run `herdr agent start <agent-name> --kind claude --pane <pane_id>`.
   For a Codex worker, use `--kind codex --pane <pane_id> -- --no-daemon`
   instead, so its hooks can identify its foreground Herdr pane.
   - Agent names match `[a-z][a-z0-9_-]{0,31}`.
   - It returns once the agent is ready.
   - `agent_not_ready` means a startup dialog is showing, such as folder trust. Read it with `herdr agent read <name> --source recent-unwrapped --lines 60` and ask Kevin before answering it.
3. **Hand it the task.** Run `herdr agent prompt <agent-name> "<self-contained brief>" --wait --timeout 120000`.
   - The new session knows nothing of yours, so the brief must stand alone: the ticket, the worktree, the rules and the stopping point.
4. **Follow along.** Use `herdr agent get <name>`, `herdr agent read <name> --source recent-unwrapped --lines 120`, and `herdr agent wait <name> --until blocked`.

Give each agent its own git worktree. On a small box, keep it to two or three agents running tests at once.

Leave tabs and conversations open unless Kevin explicitly approves clearing or closing the identified target. Never run `herdr server stop`. For everything else, run `herdr --skill` for Herdr's full agent guide.
