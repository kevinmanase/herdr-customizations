#!/usr/bin/env python3
"""Codex Herdr labels and informational hooks. Python standard library only."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

WORKING, DONE, READY, QUESTION, REQUEST = "⏳", "✅", "⚪", "❓", "❗"
SEPARATOR = " · "
READY_LABEL = READY + " ready"
JEV_URL = os.environ.get("TYPESAFE_API_URL") or "https://api.typesafe.ai/v1/systemone"
JEV_CHARS = 1500
STATE_HOME = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
JEV_FAILED = os.path.join(STATE_HOME, "herdr-tab/jev-failed")  # shared by the Claude and Codex helpers
SCRIPT = Path(__file__).resolve()
SKILL = SCRIPT.parent.parent / "SKILL.md"
REMINDER = (
    f'Herdr: before task work, run python3 "{SCRIPT}" name "🔍 <short task>". '
    f'Rename with the same command to "🛠️ <short task>" when building, "🧪 <short task>" when testing, '
    '"👀 <short task>" when reviewing, and "🚀 <short task>" once the PR is open. '
    f"Use the herdr skill at {SKILL}. Before waiting on Kevin, call "
    f'python3 "{SCRIPT}" ask "<question>" or request "<action needed>". '
    "Keep pending asks visible until answered."
)
UNBOUND_REMINDER = (
    "Herdr: this Codex session could not be matched to one foreground Herdr pane, so automatic labels were skipped. "
    "Do not rename tabs or change labels using inherited pane IDs or the focused tab. "
    "For terminal sessions, launch codex --no-daemon, or resume the saved session with --no-daemon. "
    "Shared app-server sessions need a verified session-to-pane binding before label commands can work."
)


def herdr(*args, timeout=2):
    result = subprocess.run(
        [os.environ.get("HERDR_BIN_PATH") or "herdr", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Herdr command failed")
    response = json.loads(result.stdout or "{}")
    if "error" in response:
        raise RuntimeError(str(response["error"]))
    return response.get("result", {})


def resolve_hook_pane(payload=None):
    """Bind a hook or explicit command to its foreground Codex process, never inherited pane IDs.

    Shared app-server threads have no trustworthy per-pane process ancestry.
    Until the runtime supplies that binding, skip their automatic metadata and
    labels. Explicit commands enforce the same binding.
    """
    if payload is not None:
        session = payload.get("session_id")
        inherited = os.environ.get("CODEX_THREAD_ID")
        if not session or payload.get("agent_id") or (inherited and inherited != session):
            return None
    ancestors = set()
    seen = set()
    pid = os.getppid()
    while pid > 1:
        if pid in seen or len(seen) >= 32:
            return None
        seen.add(pid)
        # ps reads the process table on both Linux and macOS.
        try:
            ps = subprocess.run(
                ["ps", "-o", "ppid=,command=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
            ppid, *argv = ps.stdout.split()
            if "app-server" in argv:
                return None
            if argv and os.path.basename(argv[0]) == "codex":
                ancestors.add(pid)
            pid = int(ppid)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
    if not ancestors:
        return None

    # Herdr's foreground PID facility also handles a moved pane or stale env.
    panes = herdr("pane", "list")["panes"]
    matches = []
    for pane in panes:
        if pane.get("agent") not in (None, "codex"):
            continue
        info = herdr("pane", "process-info", "--pane", pane["pane_id"])["process_info"]
        if ancestors.intersection(p["pid"] for p in info["foreground_processes"]):
            matches.append(pane["pane_id"])
    return matches[0] if len(matches) == 1 else None


def current_tab():
    # Moved panes retain inherited tab IDs. Never fall back to a stale tab ID.
    return herdr("pane", "get", os.environ["HERDR_PANE_ID"])["pane"]["tab_id"]


def parse(label):
    label = label.strip()
    if label == READY_LABEL:
        return READY, "", ""
    for status in (WORKING, DONE, READY, QUESTION, REQUEST):
        if label.startswith(status):
            rest = label[len(status) :].strip()
            if status in (QUESTION, REQUEST) and SEPARATOR in rest:
                ask, name = rest.split(SEPARATOR, 1)
                return status, ask.strip(), name.strip()
            if status in (QUESTION, REQUEST):
                return status, rest, ""
            return status, "", rest
    return "", "", label


def clean(text, limit):
    text = " ".join(str(text).replace("·", "-").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def read(tab):
    return parse(herdr("tab", "get", tab)["tab"].get("label") or "")


def render(tab, status, ask, name):
    if status in (QUESTION, REQUEST):
        label = f"{status} {ask or 'needs you'}" + (SEPARATOR + name if name else "")
    elif status == READY and not name:
        label = READY_LABEL
    else:
        label = " ".join(part for part in (status, name) if part)
    herdr("tab", "rename", tab, label)


def needs(status, ask):
    tab = current_tab()
    previous, previous_ask, name = read(tab)
    ask = clean(ask, 48) or "needs you"
    if (previous, previous_ask) == (status, ask):
        return
    render(tab, status, ask, name)
    herdr(
        "notification",
        "show",
        f"{status} {clean(name, 40) or 'Codex'} needs you",
        "--body",
        ask,
        "--sound",
        "request",
    )


# Peer traffic arrives as a prompt too: a Codex report typed in with `herdr agent prompt`, or a
# Claude cross-session message. Only Kevin's own prompt answers his pending ask.
PEER_PROMPTS = ("<cross-session-message", "Status from ")


def from_kevin(payload):
    return not str(payload.get("prompt") or "").lstrip().startswith(PEER_PROMPTS)


def set_status(status, clear_needs=False):
    """Set the tab's status. Returns whether that cleared an ask."""
    tab = current_tab()
    current, _, name = read(tab)
    if not clear_needs and current in (QUESTION, REQUEST):
        return False
    if current != status:
        render(tab, status, "", name)
    return current in (QUESTION, REQUEST)


def wire_ask(runtime, session, text="", kind=""):
    """Set this session's Agent Wire ask for Kevin (`text`, of `kind` decide or act), or clear it (no `kind`).
    The session is the enrollment whose identity file names `runtime` and the native `session` id, never a pane or
    the focused tab. Without the agent-wire CLI, one that predates `ask`, or an enrollment, it does nothing. Returns
    what failed, or ""; never raises. Keep this identical in claude/hooks/herdr-tab and
    codex/skills/herdr/scripts/herdr-tab.py."""
    state = os.path.join(STATE_HOME, "agent-wire")
    folder = os.path.join(state, "identities")
    search = os.environ.get("PATH", "") + os.pathsep + os.path.expanduser("~/.local/bin")
    command = shutil.which("agent-wire", path=search)
    if not session or not command or not os.path.isdir(folder):
        return ""
    newest = (0, "")  # a re-enrolled session's older identities are retired
    for entry in os.scandir(folder):
        try:
            with open(entry.path, encoding="utf-8") as handle:
                agent = json.load(handle)["agent"]
            if (agent["runtime"], agent["native_id"]) == (runtime, session):
                newest = max(newest, (entry.stat().st_mtime, entry.path))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if not newest[1]:
        return ""
    ask = ["--to", "Kevin", "--text", clean(text, 120) or "needs you", "--kind", kind] if kind else ["--clear"]
    try:
        result = subprocess.run(
            [command, "--state", state, "ask", "--identity", newest[1], *ask], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"Agent Wire ask failed: {error}"
    if result.returncode == 0 or "invalid choice: 'ask'" in result.stderr:  # an older agent-wire is no agent-wire
        return ""
    return "Agent Wire ask failed: " + (result.stderr.strip() or "no reason given")


def mirror(kind="", text=""):
    """Mirror an explicit command's ask into Agent Wire: set it as `kind`, or clear it. Raises what failed."""
    failed = wire_ask("codex", os.environ.get("CODEX_THREAD_ID"), text, kind)
    if failed:
        raise RuntimeError(failed)


def set_name(name):
    tab = current_tab()
    status, ask, _ = read(tab)
    _, _, name = parse(name)
    render(tab, status or WORKING, ask, clean(name, 60))


def tool_name(payload):
    # Codex surfaces can include a namespace in the tool name.
    return str(payload.get("tool_name") or "").rsplit(".", 1)[-1]


def dialog_ask(payload):
    arguments = payload.get("tool_input") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            arguments = {}
    if not isinstance(arguments, dict):
        return "answer the question"
    questions = arguments.get("questions") or []
    first = questions[0] if isinstance(questions, list) and questions else {}
    if not isinstance(first, dict):
        return "answer the question"
    return first.get("question") or first.get("title") or first.get("header") or "answer the question"


def permission_ask(payload):
    return clean(f"approve {tool_name(payload) or 'permission'} in Codex", 48)


def session_role():
    try:
        me = herdr("agent", "get", os.environ["HERDR_PANE_ID"])["agent"]
        if me.get("name") == "orchestrator":
            return True, (
                "You are the shared Herdr orchestrator (👑). Read the skill's "
                "orchestrator reference; keep no notes file."
            )
        agent = herdr("agent", "get", "orchestrator")["agent"]
        return False, (
            f"The shared orchestrator is a {agent['agent']} agent named orchestrator. "
            "Use the skill's Herdr messaging workflow for updates, not Claude SendMessage."
        )
    except Exception:
        return (
            False,
            "No shared orchestrator was found; do not start another agent without an orchestration request.",
        )


def same_session(agent, session, terminal):
    return (
        agent.get("agent") == "codex"
        and agent.get("terminal_id") == terminal
        and (agent.get("agent_session") or {}).get("value") == session
    )


def clear_idle(pane, session, terminal):
    """Detached worker: never clear a dialog, another agent, or a newer chat."""
    settled = herdr("agent", "wait", pane, "--timeout", "30000", timeout=32)["agent"]
    current = herdr("agent", "get", pane)["agent"]
    if not same_session(current, session, terminal):
        return
    if current.get("agent_status") not in ("idle", "done"):
        return
    if current.get("state_change_seq") != settled.get("state_change_seq"):
        return
    if read(current["tab_id"])[0] in (QUESTION, REQUEST):
        return
    herdr("agent", "prompt", pane, "/clear", timeout=5)


def clear_when_done(approved_pane=None, approved_session=None):
    if not approved_pane or not approved_session:
        raise RuntimeError(
            "Clear requires Kevin's explicit approval for the identified tab and session. "
            "After approval, pass --approved-pane and --approved-session. Leaving chat open."
        )
    me = herdr("agent", "get", approved_pane)["agent"]
    session, terminal = os.environ.get("CODEX_THREAD_ID"), me.get("terminal_id")
    if (
        approved_session != session
        or me.get("pane_id") != approved_pane
        or not session
        or not terminal
        or not same_session(me, session, terminal)
    ):
        raise RuntimeError(
            "Cannot confirm this Codex session in Herdr. Trust its SessionStart "
            "integration in /hooks and restart or resume before scheduling a clear."
        )
    if read(me["tab_id"])[0] in (QUESTION, REQUEST):
        raise RuntimeError("Resolve the pending ask before clearing this session")
    log_dir = Path(STATE_HOME) / "herdr-codex"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "clear.log").open("a") as log:
        subprocess.Popen(
            [sys.executable, str(SCRIPT), "_clear-idle", me["pane_id"], session, terminal],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    print("Scheduled /clear when this turn settles (30-second limit).")


def typesafe_key(problems=None):
    """TYPESAFE_API_KEY, then jev.api_key in ~/.config/team-floor/config.json, then the file named by
    jev.api_key_file (relative paths start in ~/.config/team-floor), by default ~/.config/typesafe/api-key.
    Returns "" when there's no usable key, and adds what went wrong to `problems`. Keep this identical in
    herdr-orchestrator, herdr-tab and codex/skills/herdr/scripts/herdr-tab.py; tests/test_lanes.py compares them."""
    problems = [] if problems is None else problems
    folder = os.path.expanduser("~/.config/team-floor")
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        jev = {}
        try:
            with open(os.path.join(folder, "config.json"), encoding="utf-8") as handle:
                jev = json.load(handle).get("jev", {})
        except FileNotFoundError:
            pass
        except Exception as error:
            problems.append(f"can't read {folder}/config.json ({type(error).__name__})")
        jev = jev if isinstance(jev, dict) else {}
        key = jev.get("api_key") if isinstance(jev.get("api_key"), str) else ""
        key = key.strip()
        named = jev.get("api_key_file")
        custom = isinstance(named, str) and bool(named)
        if named is not None and not custom:
            problems.append("jev.api_key_file in config.json must be a path")
        if not key:
            path = os.path.expanduser("~/.config/typesafe/api-key")
            if custom:
                path = os.path.join(folder, os.path.expanduser(named))
            try:
                with open(path, encoding="utf-8") as handle:
                    key = handle.read().strip()
            except FileNotFoundError:
                if custom:
                    problems.append("the file named by jev.api_key_file doesn't exist")
            except (OSError, ValueError) as error:
                problems.append(f"can't read the TypeSafe key file ({type(error).__name__})")
    if key and (" " in key or not key.isprintable()):
        problems.append("the TypeSafe key has spaces or control characters, so it isn't used")
        return ""
    return key


def jev_says_waiting(text, deadline=5):
    """Whether Jev reads `text` as ending by waiting on the reader. Sends only its last JEV_CHARS characters,
    and nothing without a TypeSafe key. Never raises: a failed call, or one that takes over `deadline` seconds
    (1 for five minutes after Jev times out), counts as no, and JEV_FAILED says why until a call succeeds. Keep
    this, ask_line and jev_warning identical in claude/hooks/herdr-tab and codex/skills/herdr/scripts/herdr-tab.py;
    tests/test_lanes.py compares them."""
    key = typesafe_key() if isinstance(text, str) and text.strip() else ""
    if not key:
        return False
    backoff = False
    try:
        if time.time() - os.path.getmtime(JEV_FAILED) < 300:
            with open(JEV_FAILED, encoding="utf-8") as handle:
                backoff = handle.read().startswith("TimeoutError")
    except (OSError, ValueError):
        pass
    if backoff:  # Jev timed out in the last five minutes: don't hold every turn end meanwhile
        deadline = min(deadline, 1)
    import urllib.request  # here, not at the top: most hook calls never reach Jev

    class NoRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):  # following one would send the key wherever it points
            return None

    body = {
        "state": text[-JEV_CHARS:],
        "model": "jev-latest",
        "questions": {
            "waits_on_reader": {
                "type": "noul",
                "instructions": "Does this message end by waiting on the reader before work can continue?",
                "criteria": {
                    "true": "Asks the reader a question, or for a decision, approval or action",
                    "false": "Reports results or status; nothing is needed from the reader",
                },
            }
        },
    }
    answers = []

    def ask():
        try:
            request = urllib.request.Request(
                JEV_URL,
                data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            # The timeout limits each connect and read, so a dead address gives way to the next one.
            with urllib.request.build_opener(NoRedirects).open(request, timeout=2) as response:
                noul = json.load(response)["answers"]["waits_on_reader"]["noul"]
            if type(noul) not in (int, float) or not 0 <= noul <= 1:
                raise ValueError("noul is not a probability")
            answers.append(noul >= 0.5)
        except Exception as error:
            answers.append(error)

    # The deadline covers the whole call, a slow DNS lookup included, which the timeout doesn't. A call still
    # running when it passes ends with the hook, since the thread is a daemon.
    thread = threading.Thread(target=ask, name="jev", daemon=True)
    thread.start()
    thread.join(deadline)
    answer = answers[0] if answers else TimeoutError()
    try:
        if isinstance(answer, bool):
            os.remove(JEV_FAILED)
        elif not (backoff and isinstance(answer, TimeoutError)):  # let the five minutes run out
            # The HTTP status, or the network error's own text. Never other error text: it can quote the request.
            code, reason = getattr(answer, "code", None), getattr(answer, "reason", None)
            detail = f" {code}" if isinstance(code, int) else f" ({reason})" if isinstance(reason, OSError) else ""
            os.makedirs(os.path.dirname(JEV_FAILED), exist_ok=True)
            with open(JEV_FAILED, "w", encoding="utf-8") as handle:
                handle.write(f"{type(answer).__name__}{detail} at {time.strftime('%Y-%m-%d %H:%M')}")
    except OSError:
        pass
    return answer is True


def ask_line(text):
    """The ask to show for `text`, a message Jev says waits on the reader, from the part Jev saw: the last
    sentence of its last question, else of its last plain line, else "reply needed". Code, headings, quotes
    and tables don't count, and list items count only as questions."""
    questions, plain, code, start, end = [], [], False, len(text) - JEV_CHARS, 0
    for raw in text.splitlines(keepends=True):
        end += len(raw)
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            code = not code
        elif line and not code and end > start and not raw.startswith(("    ", "\t", "#", ">", "|")):
            item = re.match(r"(?:[-*+]|\d+[.)])\s+", line)
            line = re.split(r"(?<=[.!])\s+(?=[A-Z])", line[item.end() if item else 0 :].strip("*_ "))[-1]
            if line.endswith("?"):
                questions.append(line)
            elif line and not item:
                plain.append(line)
    return (questions or plain or ["reply needed"])[-1]


def jev_warning():
    """A line for Kevin when the Stop hook can't ask Jev, or "" when it can. Never raises."""
    problems = []
    if typesafe_key(problems):
        try:
            with open(JEV_FAILED, encoding="utf-8") as handle:
                why = "its last call failed: " + handle.read().strip()
        except (OSError, ValueError):
            return ""
    else:
        why = "; ".join(["no usable TypeSafe key", *problems])
    return (
        f"Herdr: Jev isn't working ({why}), so a question an agent forgets to flag won't light up its tab. "
        "See docs/setup.md in herdr-customizations."
    )


def hook(payload):
    if payload.get("agent_id"):
        return {}
    event = payload.get("hook_event_name")
    output = {}
    if event in ("SessionStart", "UserPromptSubmit"):
        output = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": UNBOUND_REMINDER}}
    try:
        pane = resolve_hook_pane(payload)
    except Exception:
        return output
    if not pane:
        return output
    os.environ["HERDR_PANE_ID"] = pane
    if output:
        output["hookSpecificOutput"]["additionalContext"] = REMINDER
    if event == "SessionStart":
        mine, context = session_role()
        output["hookSpecificOutput"]["additionalContext"] += " " + context
        warning = jev_warning()
        if warning:
            output["systemMessage"] = warning
        source = payload.get("source")
        if source in ("startup", "clear"):
            # Both start a fresh task. Keeping the old name on startup leaves
            # a reset/new chat looking occupied even though its status is ready.
            render(current_tab(), READY, "", "👑 orchestrator" if mine else "")
        # Resume and compaction preserve the task and any pending ask.
    elif event == "UserPromptSubmit":
        if set_status(WORKING, clear_needs=from_kevin(payload)):
            wire_ask("codex", payload.get("session_id"))  # fails open, like every hook
    elif event == "PreToolUse" and tool_name(payload) in (
        "request_user_input",
        "request_user_input_async",
    ):
        needs(QUESTION, dialog_ask(payload))
    elif event == "PermissionRequest":
        if read(current_tab())[0] not in (QUESTION, REQUEST):
            needs(REQUEST, permission_ask(payload))
    elif event == "PostToolUse":
        name = tool_name(payload)
        tab = current_tab()
        status, ask, task = read(tab)
        if (name == "request_user_input" and status == QUESTION and ask == clean(dialog_ask(payload), 48)) or (
            status == REQUEST and ask == permission_ask(payload)
        ):
            render(tab, WORKING, "", task)
            wire_ask("codex", payload.get("session_id"))
        # request_user_input_async returns before the human answers. Keep ❓.
    elif event == "Stop":
        # Codex runs this before it takes Kevin's next prompt, so Jev's answer can't land on the next turn.
        try:
            tab = current_tab()
            status, _, name = read(tab)
        except Exception:  # a Herdr hiccup: set_status reads again
            set_status(DONE)
            return output
        if status in (QUESTION, REQUEST):  # a flagged ask already shows; Jev can't add to it
            return output
        if status != DONE:
            render(tab, DONE, "", name)  # now, so the turn reads done even if the hook is cut short
        text = payload.get("last_assistant_message") or ""
        failing = os.path.exists(JEV_FAILED)
        if jev_says_waiting(text) and read(tab)[0] == DONE:  # a prompt or ask that landed meanwhile wins
            needs(QUESTION, ask_line(text))
        if not failing and os.path.exists(JEV_FAILED):  # Jev just started failing: tell Kevin now, once
            output["systemMessage"] = jev_warning()
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("name", "ask", "request"):
        commands.add_parser(command).add_argument("text", nargs="+")
    commands.add_parser("status").add_argument("state", choices=("working", "done", "ready"))
    commands.add_parser("hook")
    clear = commands.add_parser("clear", help="clear only the exact session Kevin approved")
    clear.add_argument("--approved-pane")
    clear.add_argument("--approved-session")
    worker = commands.add_parser("_clear-idle", help=argparse.SUPPRESS)
    for field in ("pane", "session", "terminal"):
        worker.add_argument(field)
    args = parser.parse_args()
    output = {}
    try:
        if os.environ.get("HERDR_ENV") != "1":
            return
        if args.command in ("name", "status", "ask", "request"):
            pane = resolve_hook_pane()
            if not pane:
                raise RuntimeError(
                    "Cannot bind this Codex process to one foreground Herdr pane; no labels were changed. "
                    "Launch or resume terminal Codex with --no-daemon."
                )
            os.environ["HERDR_PANE_ID"] = pane
        if args.command == "hook":
            payload = json.load(sys.stdin)
            if isinstance(payload, dict):
                output = hook(payload)
        elif args.command == "name":
            set_name(" ".join(args.text))
        elif args.command in ("ask", "request"):
            text = " ".join(args.text)
            needs(QUESTION if args.command == "ask" else REQUEST, text)
            mirror("decide" if args.command == "ask" else "act", text)
        elif args.command == "clear":
            clear_when_done(args.approved_pane, args.approved_session)
        elif args.command == "_clear-idle":
            clear_idle(args.pane, args.session, args.terminal)
        elif args.state == "ready":
            render(current_tab(), READY, "", "")
        elif set_status(WORKING if args.state == "working" else DONE, clear_needs=args.state == "working"):
            mirror()
    except Exception as error:
        print(f"herdr-tab: {error}", file=sys.stderr)
        if args.command != "hook":
            raise SystemExit(1) from None
    finally:
        # Stop requires valid JSON even outside Herdr or after an error. No hook
        # returns permission decisions, blocks a tool, or requests another turn.
        if args.command == "hook":
            print(json.dumps(output))


if __name__ == "__main__":
    main()
    if any(thread.daemon for thread in threading.enumerate()):
        # A Jev call is still running. Skip the interpreter's teardown, which can crash under a thread that's
        # inside OpenSSL; nothing is left to clean up.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
