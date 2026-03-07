import json
import os
import shutil
import subprocess
import time
import uuid
from typing import Any, Optional


class AgentBrowserError(RuntimeError):
    pass


def _agent_browser_executable() -> str:
    candidates = [
        os.environ.get("AGENT_BROWSER_BIN"),
        shutil.which("agent-browser"),
        "/opt/homebrew/bin/agent-browser",
        "/usr/local/bin/agent-browser",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    raise AgentBrowserError("Could not locate Vercel agent-browser executable")


def agent_browser_available() -> bool:
    try:
        _agent_browser_executable()
        return True
    except AgentBrowserError:
        return False


def _run_agent_browser(
    args: list[str],
    *,
    timeout_seconds: int = 45,
) -> str:
    result = subprocess.run(
        [_agent_browser_executable(), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise AgentBrowserError(result.stderr.strip() or result.stdout.strip() or "agent-browser failed")
    return result.stdout.strip()


def _decode_eval_output(output: str) -> Any:
    value = output.strip()
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, str):
        try:
            return json.loads(parsed)
        except json.JSONDecodeError:
            return parsed
    return parsed


def browser_eval_json(
    url: str,
    script: str,
    *,
    wait_ms: int = 0,
    retries: int = 3,
    retry_delay_seconds: float = 1.5,
) -> Any:
    session = f"mesim-{uuid.uuid4().hex[:10]}"
    try:
        _run_agent_browser(["--session", session, "open", url, "--json"])
        if wait_ms > 0:
            _run_agent_browser(["--session", session, "wait", str(wait_ms)])
        last_error: Optional[Exception] = None
        for attempt in range(max(1, retries)):
            if attempt:
                time.sleep(retry_delay_seconds)
            try:
                output = _run_agent_browser(["--session", session, "eval", script])
                return _decode_eval_output(output)
            except AgentBrowserError as exc:
                last_error = exc
                message = str(exc).lower()
                if "execution context was destroyed" in message:
                    continue
                raise
        raise AgentBrowserError(str(last_error or "agent-browser eval failed"))
    finally:
        try:
            _run_agent_browser(["--session", session, "close"], timeout_seconds=10)
        except Exception:
            pass


def browser_get_text(
    url: str,
    *,
    wait_ms: int = 0,
    retries: int = 2,
    retry_delay_seconds: float = 1.5,
    max_output: int = 8000,
) -> str:
    session = f"mesim-{uuid.uuid4().hex[:10]}"
    try:
        _run_agent_browser(["--session", session, "open", url, "--json"])
        if wait_ms > 0:
            _run_agent_browser(["--session", session, "wait", str(wait_ms)])
        last_error: Optional[Exception] = None
        for attempt in range(max(1, retries)):
            if attempt:
                time.sleep(retry_delay_seconds)
            try:
                return _run_agent_browser(
                    ["--session", session, "get", "text", "body", "--max-output", str(max_output)]
                )
            except AgentBrowserError as exc:
                last_error = exc
                message = str(exc).lower()
                if "execution context was destroyed" in message:
                    continue
                raise
        raise AgentBrowserError(str(last_error or "agent-browser get text failed"))
    finally:
        try:
            _run_agent_browser(["--session", session, "close"], timeout_seconds=10)
        except Exception:
            pass
