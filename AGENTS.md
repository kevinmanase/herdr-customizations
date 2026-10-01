# Herdr customizations

- Run `python -m pytest -q`, `ruff check .`, and `ruff format --check .` before committing.
- Keep it working on both Linux and macOS: no `/proc`-only or `flock`-only paths.
- Preserve pending asks across renames and ordinary lifecycle events.
- Resolve the current tab from the pane, never from the focused tab.
- Hooks never approve permissions and fail open. Explicit CLI commands report failures.
- Clear a conversation only with the owner's approval for that exact pane and session.
- Start an orchestrator only when none is live; never run two.
- Agent Wire is optional. Labels, hooks, and the orchestrator must work without it.
- Send nothing off the machine unless the owner sets a key. Jev gets at most the last 1,500
  characters of the agent's last message.
- Keep credentials, session registries, transcripts, private machine paths, and company
  workflows out of this repository.
- Test with the fake Herdr in `tests/`, not a person's live tabs.
- Skill and hook installation belongs at user scope, outside project checkouts.
