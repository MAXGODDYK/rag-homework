from __future__ import annotations

import argparse
import json
import os
import secrets
from pathlib import Path

import uvicorn

from .api import create_app
from .runtime import build_runtime


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="jarvis", description="JARVIS local agent administrator")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    commands.add_parser("status")
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=0)
    add_user = commands.add_parser("add-user")
    add_user.add_argument("user_id")
    add_user.add_argument("display_name")
    add_project = commands.add_parser("add-project")
    add_project.add_argument("name")
    add_project.add_argument("root_path")
    import_project = commands.add_parser("import-project")
    import_project.add_argument("project_id")
    import_project.add_argument("--user-id", default="desktop-owner")
    local_code = commands.add_parser("approval-code")
    local_code.add_argument("approval_id")
    return root


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
    elif args.command == "serve":
        token = os.getenv("JARVIS_IPC_TOKEN") or secrets.token_urlsafe(32)
        if args.port == 0:
            import socket

            with socket.socket() as probe:
                probe.bind((args.host, 0))
                port = probe.getsockname()[1]
        else:
            port = args.port
        print(json.dumps({"host": args.host, "port": port, "ipc_token": token}))
        uvicorn.run(create_app(runtime, token), host=args.host, port=port, log_level="info")
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
    elif args.command == "approval-code":
        print(runtime.agent.local_approval_code(args.approval_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
