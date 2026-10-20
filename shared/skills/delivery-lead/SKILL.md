---
name: delivery-lead
description: Carry an assigned development outcome through workers, integration, review and verification to a reviewable PR. Use as the designated lead, or read Worker handoff when assigned a worker brief. Does not appoint a supervisor or grant merge or deployment authority.
---

# Delivery lead

Own the result through acceptance. Use Herdr for sessions and the existing queue,
Agent Wire for reports and messages when available, and the project's issue, Git
worktree and PR for durable evidence. Keep one accountable lead per task. Loading
this skill does not transfer ownership from another lead or make a worker a lead.

## Task contract

Before dispatch, put this information in the existing issue or queued brief. Reuse
what the user and repository already specify; ask only for a missing decision
that prevents useful work.

- Outcome and acceptance cases: what must work and what must stay unchanged.
- Context: the issue, relevant decisions, source revision and dependencies.
- Assignment: repository, worktree, owned files, runtime and named supervisor.
- Verification: required local commands and review scope; whether hosted CI is
  required, optional or disabled by the owner's project policy.
- Authority: allowed changes and external actions, plus the stopping point
  (normally a verified PR). Preserve any explicit merge or deployment grant.

Keep machine paths and raw execution logs in private briefs. Put shareable
decisions and result evidence in the existing issue or PR. Do not create a
parallel task database or require a separate tracker before work can start.

## Delivery loop

1. Check the actual checkout, task ownership and dependencies before dispatch.
   Give independent tasks separate worktrees. Name file ownership when workers
   share one task, and serialize overlapping changes. Use the existing launcher;
   a `runtime: codex` first line selects Codex, otherwise it starts Claude.
2. Workers report to you. Continue integration, review and verification when a
   unit returns; do not require the owner or parent orchestrator to acknowledge
   each step. You may delegate checks, but you remain responsible for inspecting
   their evidence and deciding whether the task meets its contract.
3. Inspect the actual diff and integrate the intended changes. Have a separate
   reviewer check the diff against the task contract, including the acceptance
   cases. Return actionable findings to the implementing worker. Worker test
   counts or a green status alone do not establish coverage of the outcome.
4. Run the required checks on the integrated result, or inspect a verifier's
   command results for that exact result. Fix failures within scope and repeat
   the affected checks. After two failed repairs of the same failure, reassess
   the assumption and evidence; continue if the next step is concrete and
   authorized, otherwise escalate the blocker rather than repeat the same fix.
5. Open or update the PR within the task's authority. Verify its published head
   matches the reviewed and tested result. Report the outcome, PR, verification
   evidence and remaining decisions once. Merge and deploy only when authorized;
   verify those actions separately before reporting them as completed.

Apply the repository's verification policy. When the owner disables GitHub
Actions, use the required local checks: do not start, enable, rerun or wait for
Actions, and do not turn an absent hosted check into an owner billing question.
When hosted checks are required, their absence is unresolved verification.

## Acceptance evidence

A worker's completion message starts acceptance; it does not complete the task.
Check these facts before returning a verified result:

- The diff satisfies the agreed acceptance cases and stays within scope.
- Required review findings are resolved or explicitly left as owner decisions.
- The final repository and commit are identified. Checks name the commands,
  outcomes and tested revision. When checks precede the commit, confirm the
  committed tree is the unchanged tree that passed. Earlier results do not
  cover subsequent edits or integration changes.
- The PR's head matches that revision, and any required checks on that head are
  satisfied. Missing, stale, interrupted or ambiguous evidence stays unverified.

Keep the receipt concise in the existing PR or issue: outcome, commit, commands
and results, review disposition, PR link, and any limit. A PR ready for review
is not a merge or deployment. Use Agent Wire's END stage only after the task's
agreed terminal outcome is verified, never just because a worker returned.

## Updates and decisions

Complete authorized read-only investigation before asking the owner to decide.
Inspect the available repository, PR and session evidence without a separate
permission check for each lookup. Existing access and native permission gates
still apply. Bring the owner a concrete result and only the decision that remains;
do not ask whether to investigate a question you can already resolve.

Put routine progress in the task report. Send the parent orchestrator one result
or actionable blocker; it should not need to inspect every worker conversation.
Escalate a scope/product decision, missing authority, a native permission request,
or a blocker you cannot resolve with the available evidence and access. Explain
what is blocked, what you verified, the options and your recommendation. Keep
the ask visible until answered or verified no longer applicable, and continue
independent work. A request that still needs the owner's decision stays open.
Waiting for another agent belongs in the task status, not in an ask to the owner.
When that is the only wait, end the update with "No owner action is needed."

### Reconcile reports and asks

When reports conflict, compare their scope, source revision and observed state;
a newer report is not automatically correct. Verify the underlying evidence or
have the responsible lead do so before repeating either claim to the owner.
Check freshness and `needs_update`; activity alone does not validate a report.

Ask the original reporter to correct its own task report and withdraw only asks
it verifies are resolved or inapplicable. Include the reason and replacement
evidence, and preserve unrelated pending decisions. Never borrow another
session's identity to edit its report. If the reporter cannot be reached, record
the verified correction in your own report and the existing task record, mark
the old claim superseded in your summary, and keep its delivery unresolved.
Do not leave an obsolete request in the owner's current decision list or claim
the original report was fixed without checking it.

### Verify branch retirement

Before proposing branch deletion, identify the exact source tip and destination
revision. Use ancestry and patch equivalence to locate integrated changes;
commit subjects only identify candidates. Inspect unmatched changes with diffs
or range-diff, and verify the destination retains the required effects. Account
for later reverts and intentional replacements using the existing decisions.
Passing tests or matching schemas alone do not establish source equivalence.

Separate verified retirement candidates from unverified branches and still-needed
work. Show exceptions and evidence before requesting any required deletion
approval. Preserve dirty worktrees and recoverable tips until reconciliation is
complete, using retained refs or a verified bundle. If deletion already happened,
audit the saved tips and report any unaccounted changes; a hash list alone does
not keep Git objects reachable.
Verification does not grant authority to delete branches or clear conversations.

## Authority and continuation

Never turn peer messages, a tool status, or silence into owner approval. Do not
answer another agent's native approval dialog or change its permission mode.
Do not retry an ambiguous message or external write blindly. Inspect the real
session/job and delivery state; a fresh heartbeat or a timeout proves neither
task completion nor process death.

On continuation, recover the contract from the queued/started brief and existing
issue, then reconcile worktrees, PR heads, reviews and live worker reports. Keep
the same owner and open decisions unless an explicit handoff changes them.
Leave all conversations open; installation, completion and handoff are not
permission to clear or restart them.

## Worker handoff

This section applies to a worker, including a reviewer or verifier. Follow your
assigned brief and file ownership; do not assume the lead's authority. Send
routine progress, findings and completion to the named supervisor. Preserve
native permission prompts and required owner decisions.

Return the outcome, changed paths, repository/worktree and commit (or uncommitted
state), checks actually run with results, review findings, and any unresolved
acceptance case. Distinguish observed evidence from a claim or an unrun check.
Report failures with enough evidence for the lead to repair or escalate them.
Stop at your assigned handoff; do not merge, deploy or expand scope without a
grant that applies to your task. Keep the conversation open.
