# Herdr customizations

- Run `python -m pytest -q`, `ruff check .`, and `ruff format --check .` before committing.
- Keep this customization independent from Agent Wire and other model services.
- Preserve pending questions across task renames and ordinary lifecycle events.
- Resolve the current tab from the explicit pane ID. Never fall back to the focused tab.
- Hook output is informational. Never approve permissions or clear conversations.
- Keep hooks bounded and fail open. Explicit CLI commands should report failures.
- Keep credentials, session registries, transcripts, and private machine paths out of this repository.
- Test with an isolated fake Herdr boundary, not a person's live tabs.
- Skill and hook installation belongs at user scope, outside project checkouts.
