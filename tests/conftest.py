import copy
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
FAKE = TESTS / "fake_herdr.py"
FAKE_WIRE = TESTS / "fake_agent_wire.py"
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
def wire(tmp_path):
    """A fake agent-wire CLI in ~/.local/bin, with Claude session s1 and Codex thread c1 enrolled beside another
    session. `calls` lists its argument lists, `ask()` builds one, `fail()` makes every call fail, and `old()` makes
    it a release without the `ask` command."""
    folder = tmp_path / ".local/bin"
    folder.mkdir(parents=True)
    shutil.copy(FAKE_WIRE, folder / "agent-wire")
    identities = tmp_path / ".local/state/agent-wire/identities"
    identities.mkdir(parents=True)
    for name, runtime, native in (("mine", "claude", "s1"), ("codex", "codex", "c1"), ("other", "claude", "s2")):
        identity = {"agent": {"id": name, "runtime": runtime, "native_id": native}, "session_handle": "secret"}
        (identities / f"{name}.json").write_text(json.dumps(identity))
    retired = identities / "retired.json"  # s1's older enrollment: only the newest is used
    retired.write_text((identities / "mine.json").read_text().replace('"mine"', '"retired"'))
    os.utime(retired, (0, 0))

    class Wire:
        def ask(self, *ask, identity="mine"):
            state = str(tmp_path / ".local/state/agent-wire")
            return ["--state", state, "ask", "--identity", str(identities / f"{identity}.json"), *ask]

        @property
        def calls(self):
            log = folder / "calls.jsonl"
            return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

        def fail(self):
            (folder / "fail").touch()

        def old(self):
            (folder / "old").touch()

    return Wire()


@pytest.fixture
def jev():
    """A local stand-in for TypeSafe's endpoint. Set `reply` to a dict, an HTTP status, or a status and its headers;
    `requests` holds the bodies, and `headers` the headers of every request, a followed redirect's GET included."""

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
            if isinstance(fake.reply, (int, tuple)):
                status, headers = fake.reply if isinstance(fake.reply, tuple) else (fake.reply, {})
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.end_headers()
                return
            data = json.dumps(fake.reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # only a followed redirect comes here
            fake.headers.append(dict(self.headers))
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    fake.url = f"http://127.0.0.1:{server.server_port}/v1/systemone"
    yield fake
    server.shutdown()


@pytest.fixture
def env(monkeypatch):
    """Set environment variables for helpers run in this process, after dropping the developer's own TypeSafe
    key and state folder, so a test never reads or writes the real ones."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    def set_env(**values):
        for name, value in values.items():
            monkeypatch.setenv(name, str(value))

    return set_env
