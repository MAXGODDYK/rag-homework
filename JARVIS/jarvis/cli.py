from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path

import psutil
import uvicorn


def _bootstrap_path(name: str, environment_name: str) -> None:
    """Apply packaged path arguments before config modules resolve their roots."""
    try:
        index = sys.argv.index(name)
        value = sys.argv[index + 1]
    except (ValueError, IndexError):
        return
    os.environ[environment_name] = value


_bootstrap_path("--config-root", "JARVIS_CONFIG_ROOT")
_bootstrap_path("--state-root", "JARVIS_STATE_ROOT")

from .api import create_app
from .runtime import build_runtime


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="jarvis", description="JARVIS local agent administrator")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    commands.add_parser("status")
    commands.add_parser("users")
    commands.add_parser("roots")
    commands.add_parser("approvals")
    commands.add_parser("emergency-shutdown")
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--with-telegram", action="store_true")
    serve.add_argument("--parent-pid", type=int)
    serve.add_argument("--config-root")
    serve.add_argument("--state-root")
    add_user = commands.add_parser("add-user")
    add_user.add_argument("user_id")
    add_user.add_argument("display_name")
    add_project = commands.add_parser("add-project")
    add_project.add_argument("name")
    add_project.add_argument("root_path")
    import_project = commands.add_parser("import-project")
    import_project.add_argument("project_id")
    import_project.add_argument("--user-id", default="desktop-owner")
    reindex = commands.add_parser("reindex")
    reindex.add_argument("project_id")
    reindex.add_argument("--user-id", default="desktop-owner")
    local_code = commands.add_parser("approval-code")
    local_code.add_argument("approval_id")
    return root


def _watch_parent(parent_pid: int) -> None:
    """Terminate a packaged backend when its desktop owner no longer exists."""
    try:
        parent = psutil.Process(parent_pid)
        created_at = parent.create_time()
    except (psutil.Error, OSError):
        os._exit(0)
    while True:
        time.sleep(1.0)
        try:
            if not parent.is_running() or parent.create_time() != created_at:
                os._exit(0)
        except (psutil.Error, OSError):
            os._exit(0)


def main() -> int:
    args = parser().parse_args()
    runtime = build_runtime()
    if args.command == "migrate":
        runtime.database.initialize()
        print(f"Database ready: {runtime.config.database_path}")
    elif args.command == "status":
        print(
            json.dumps(
                {
                    "database": str(runtime.config.database_path),
                    "tools": runtime.registry.catalog(),
                    "free_gb": round(__import__("shutil").disk_usage(runtime.config.project_root).free / 1024**3, 2),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "users":
        print(json.dumps(runtime.database.query_all("SELECT * FROM users ORDER BY created_at"), ensure_ascii=False, indent=2))
    elif args.command == "roots":
        print(json.dumps([str(path) for path in runtime.config.allowed_roots], ensure_ascii=False, indent=2))
    elif args.command == "approvals":
        print(json.dumps(runtime.database.query_all("SELECT id,session_id,status,high_risk,preview,expires_at FROM approvals ORDER BY created_at DESC"), ensure_ascii=False, indent=2))
    elif args.command == "emergency-shutdown":
        pid_path = runtime.config.state_root / "backend.pid"
        if not pid_path.exists():
            print("No running backend PID is registered")
        else:
            pid = int(pid_path.read_text(encoding="ascii").strip())
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass
            pid_path.unlink(missing_ok=True)
            print(f"Emergency shutdown requested for PID {pid}")
    elif args.command == "serve":
        if args.parent_pid:
            threading.Thread(
                target=_watch_parent,
                args=(args.parent_pid,),
                name="jarvis-parent-watch",
                daemon=True,
            ).start()
        token = os.getenv("JARVIS_IPC_TOKEN") or secrets.token_urlsafe(32)
        if args.port == 0:
            import socket

            with socket.socket() as probe:
                probe.bind((args.host, 0))
                port = probe.getsockname()[1]
        else:
            port = args.port
        print(json.dumps({"host": args.host, "port": port, "ipc_token": token}), flush=True)
        pid_path = runtime.config.state_root / "backend.pid"
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()), encoding="ascii")
        try:
            uvicorn.run(
                create_app(runtime, token, enable_telegram=args.with_telegram),
                host=args.host,
                port=port,
                log_level="info",
            )
        finally:
            pid_path.unlink(missing_ok=True)
    elif args.command == "add-user":
        runtime.database.ensure_user(args.user_id, args.display_name)
        print(f"User ready: {args.user_id}")
    elif args.command == "add-project":
        path = Path(args.root_path).expanduser().resolve()
        if not path.is_dir():
            raise SystemExit(f"Project path is not a directory: {path}")
        project = runtime.database.create_project("desktop-owner", args.name, str(path))
        print(json.dumps(project, ensure_ascii=False, indent=2))
    elif args.command == "import-project":
        project = runtime.database.query_one(
            "SELECT * FROM projects WHERE id=? AND user_id=?", (args.project_id, args.user_id)
        )
        if not project or not project.get("root_path"):
            raise SystemExit("Project not found or has no root path")
        result = runtime.ingestion.import_project(
            Path(project["root_path"]), user_id=args.user_id, project_id=args.project_id
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "reindex":
        runtime.ingestion.rebuild_vector_index(args.user_id, args.project_id)
        print(f"Reindexed project: {args.project_id}")
    elif args.command == "approval-code":
        print(runtime.agent.local_approval_code(args.approval_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
