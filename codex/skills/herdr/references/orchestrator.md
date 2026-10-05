# Orchestrator coordination from Codex

The single Herdr agent named `orchestrator` is shared across Claude and Codex.
It keeps no notes file. The existing Claude
integration maintains that agent; Codex must not create a competing orchestrator
merely because it is a different agent kind.

## Sending an update

Discover with `herdr agent get orchestrator`. If it is your pane, don't message
yourself. Otherwise send one self-contained line
when you merge, get blocked, finish, or start another session. Include the
sender's pane or ticket, outcome, and remaining work:

```bash
herdr agent prompt orchestrator "Status from <pane/ticket>: <outcome>; <follow-up or none>."
```

Use safely quoted arguments. This replaces Claude's `SendMessage`; Codex's own
subagent messaging tools do not reach an arbitrary Claude session. Do not use
`--wait` for a status update. A submitted prompt is not proof it was read.
If the agent is blocked, inspect with `herdr agent read orchestrator --source
recent-unwrapped --lines 120`; do not answer its approval or question dialog.
Keep the undelivered update in your final handoff instead of retrying blindly.
If no orchestrator exists, report that fact. Start a replacement only as part of
Kevin's request to restore or run orchestration.

## When Kevin makes you the orchestrator

1. Inspect the existing named agent. If another pane owns the role, record that
   pane, run `herdr agent rename <old-pane> --clear`, and remove its crown from
   its tab label while preserving its current status or pending ask.
2. Run `herdr agent rename "$HERDR_PANE_ID" orchestrator`, then use this skill's
   helper to set your name to `👑 orchestrator`. Herdr enforces name uniqueness;
   if a concurrent claim wins, re-inspect instead of starting another agent.
3. Tell the previous owner about the handoff through `herdr agent prompt` if it
   can accept input. Recover the current work and open asks as below.
   Codex does not need Claude's prompt-bar color or session naming API: the
   Herdr name and crown identify the role.

Keep no notes file. Rebuild the picture each time from each worktree's
ticket-graph checkpoint (`git worktree list`, then
`git -C <worktree> rev-parse --path-format=absolute --git-path ticket-graph.json`),
Linear status and "blocked by" relations, GitHub PRs, CI and merges, and tab
labels and Agent Wire reports. Turn loose ends into Linear tickets.
Reconcile updates against git, GitHub, Linear, and CI before acting.
Inspect tabs with `herdr agent read <pane> --source recent-unwrapped --lines 200`.
Send a stalled session one clear, scoped nudge using `herdr agent prompt`.

Keep Kevin's open decisions visible with the helper's `ask` command, and relay
his answers to the responsible agent. Production, data, spend, and exceptions
to a gate remain Kevin's decisions.

Reuse a genuinely ready tab before opening a new one: verify `agent_status` is
idle/done, the label is `⚪ ready`, and agent kind and working directory fit the
task. Rename its Herdr agent and send a self-contained brief. For a new Codex
worker, use the skill's `--kind codex` recipe. The Claude
`herdr-orchestrator next` runner starts Claude sessions; it is not a Codex launcher.

Leave finished worker conversations open by default. A 🧹 tab is finished and
waits only for a yes to clear, so list the 🧹 tabs for Kevin to approve as a
batch. Before clearing any
conversation, identify its tab label, pane, agent kind, and native session ID
and obtain Kevin's explicit approval for that target. Completion and idle/done
are not permission. Recheck the identity immediately before an approved clear;
an approval for an earlier occupant does not cover a replacement. This applies
to your own tab and to raw `herdr agent prompt <pane> "/clear"` commands too.

Do not confuse dim Claude prompt suggestions with user input. If needed,
`herdr pane read <pane> --source visible --format ansi` reveals `ESC[2m` styling.
Inspect actual agent kind before sending product-specific slash commands.

## Lanes and leads

If `~/.config/team-floor/lanes.json` lists lanes, a busy lane gets a Claude
lead named `lead-<lane>` (tab `🧭 lead-<lane>`) that runs
`~/.cache/herdr-fleet/queue/<lane>/`. The orchestrator keeps one line per lane
and asks a lead for detail instead of reading its sessions. Route a new brief
with `~/.claude/hooks/herdr-orchestrator route <brief>`: Jev picks the lane, and
a weak pick, `unclear`, or no Jev leaves the brief unrouted and flags Kevin.
`herdr-orchestrator leads` prints one line per lane and starts a lead for a lane
with 4 or more open items. A lead hands a lane with 1 open item back with
`herdr-orchestrator handback <lane>`, and its conversation stays open. With
Agent Wire, start the task text with `role: main` as the orchestrator, or
`role: lead lane: <id>` as a lead. Write `ticket` as the Linear key (`ENG-2649`),
or as `<repo>#<number>` for the GitHub issue, or for the PR when there is no
issue, and nothing else. The Claude skill's "Lanes and leads"
section has the full rules.
