#!/usr/bin/env python3
"""A fake `agent-wire` CLI. Each call is appended to calls.jsonl beside it. A `fail` file beside it makes calls fail;
an `old` file makes it a release without the `ask` command."""

import json
import sys
from pathlib import Path

here = Path(__file__).parent
with open(here / "calls.jsonl", "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
if (here / "old").exists():
    sys.stderr.write("agent-wire: error: argument command: invalid choice: 'ask' (choose from 'serve', 'report')\n")
    sys.exit(2)
if (here / "fail").exists():
    sys.exit("no_report: publish a report before setting an ask")
