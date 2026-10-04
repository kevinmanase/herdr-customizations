import copy
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
FAKE = TESTS / "fake_herdr.py"
JEV_CHOICE = json.loads((TESTS / "fixtures/jev-choice.json").read_text())


@pytest.fixture
def herdr(tmp_path):
    """A fake Herdr with one Claude pane, p1 in tab t1, and a separate orchestrator in t9."""
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "tabs": {"t1": "⏳ ready", "t9": "✅ 👑 orchestrator"},
                "panes": [
                    {"pane_id": "p1", "tab_id": "t1", "agent": "claude"},
                    {"pane_id": "p9", "tab_id": "t9", "agent": "claude"},
                ],
                "agents": {"orchestrator": {"pane_id": "p9", "tab_id": "t9"}},
            }
        )
    )
    env = {
        "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "HERDR_ENV": "1",
        "HERDR_PANE_ID": "p1",
        "HERDR_WORKSPACE_ID": "w1",
        "HERDR_BIN_PATH": str(FAKE),
        "FAKE_HERDR_STATE": str(state),
        "HERDR_FLEET_QUEUE": str(tmp_path / "queue"),
        "HERDR_WORK_DIR": str(tmp_path),
        "FLEET_MIN_MB": "0",
    }

    class Herdr:
        environ = env

        def run(self, script, *args, stdin="", **extra):
            return subprocess.run(
                [sys.executable, str(script), *args],
                input=stdin,
                capture_output=True,
                text=True,
                env={**env, **extra},
                timeout=30,
            )

        @property
        def state(self):
            return json.loads(state.read_text())

        def label(self, tab="t1"):
            return self.state["tabs"][tab]

        def set_state(self, **changes):
            state.write_text(json.dumps({**self.state, **changes}))

    return Herdr()


@pytest.fixture
def jev():
    """A local stand-in for TypeSafe's endpoint. Set `reply` (a dict or an HTTP status); `requests` holds bodies."""

    class Jev:
        reply = copy.deepcopy(JEV_CHOICE)
        before_reply = None
        requests = []
        headers = []

        def answer(self, choice, probabilities):
            self.reply = copy.deepcopy(JEV_CHOICE)
            self.reply["answers"]["lane"].update(choice=choice, probabilities=probabilities)

    fake = Jev()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            fake.requests.append(json.loads(body))
            fake.headers.append(dict(self.headers))
            if fake.before_reply:
                fake.before_reply()
            if isinstance(fake.reply, int):
                self.send_response(fake.reply)
                self.end_headers()
                return
            data = json.dumps(fake.reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake.url = f"http://127.0.0.1:{server.server_port}/v1/systemone"
    yield fake
    server.shutdown()
