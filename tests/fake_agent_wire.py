#!/usr/bin/env python3
"""A fake `agent-wire` CLI. Each call is appended to calls.jsonl beside it. A `fail` file beside it makes calls fail."""

import json
import sys
from pathlib import Path

here = Path(__file__).parent
with open(here / "calls.jsonl", "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
if (here / "fail").exists():
    print(
        json.dumps({"error": {"code": "no_report", "message": "Publish a report before setting an ask"}}),
        file=sys.stderr,
    )
    sys.exit(1)
print("{}")
