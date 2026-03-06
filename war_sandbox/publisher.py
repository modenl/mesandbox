import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .service import SandboxService, bootstrap_state
from .webapp import render_static_snapshot


class PublishError(RuntimeError):
    pass


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PublishError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")
    return result


def export_snapshot(service: SandboxService, output_dir: Path) -> Path:
    state = service.dashboard_state()
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "index.html"
    html_path.write_text(render_static_snapshot(state), encoding="utf-8")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    return html_path


def stage_docs_if_changed(repo_root: Path, output_dir: Path) -> bool:
    _run_git(["add", str(output_dir)], cwd=repo_root)
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", str(output_dir)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return diff.returncode == 1


def publish_once(
    service: SandboxService,
    repo_root: Path,
    output_dir: Path,
    remote: str,
    branch: str,
    commit_message_prefix: str,
    tick: bool = True,
) -> Dict[str, Any]:
    if tick:
        service.tick()
    html_path = export_snapshot(service, output_dir)
    changed = stage_docs_if_changed(repo_root, output_dir)
    if not changed:
        return {
            "status": "no_changes",
            "output": str(html_path),
        }

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    message = f"{commit_message_prefix} {timestamp}"
    _run_git(["commit", "-m", message], cwd=repo_root)
    _run_git(["push", remote, f"HEAD:{branch}"], cwd=repo_root)
    return {
        "status": "published",
        "output": str(html_path),
        "remote": remote,
        "branch": branch,
        "commit_message": message,
    }


def publish_loop(
    service: SandboxService,
    repo_root: Path,
    output_dir: Path,
    remote: str,
    branch: str,
    commit_message_prefix: str,
    sleep_seconds: int,
) -> None:
    while True:
        result = publish_once(
            service=service,
            repo_root=repo_root,
            output_dir=output_dir,
            remote=remote,
            branch=branch,
            commit_message_prefix=commit_message_prefix,
            tick=True,
        )
        print(json.dumps(result, ensure_ascii=False), flush=True)
        time.sleep(max(30, int(sleep_seconds)))


def build_service(rss_path: str, model: Optional[str]) -> SandboxService:
    bootstrap_state(rss_path=rss_path)
    return SandboxService(rss_path=rss_path, model=model)
