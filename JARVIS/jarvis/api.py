from __future__ import annotations

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import aiofiles
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .models import Event, LocalSettingsUpdate, MessageCreate, ProjectCreate, SessionCreate, SessionPolicy
from .ingestion.service import IngestionError
from .rag_service import RagServiceError
from .runtime import Runtime, build_runtime
from .settings_store import public_settings_status, update_local_settings


def create_app(
    runtime: Runtime | None = None,
    ipc_token: str | None = None,
) -> FastAPI:
    runtime = runtime or build_runtime()
    token = ipc_token or os.getenv("JARVIS_IPC_TOKEN") or secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield

    app = FastAPI(
        title="JARVIS Desktop RAG API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.state.ipc_token = token
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "http://localhost:1420",
            "http://127.0.0.1:1420",
        ],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Jarvis-Token"],
    )

    def authorize(x_jarvis_token: str = Header(default="")) -> str:
        if not secrets.compare_digest(x_jarvis_token, token):
            raise HTTPException(status_code=401, detail="Invalid local IPC token")
        return "desktop-owner"

    @app.get("/v1/health")
    def health(_: str = Depends(authorize)):
        return {
            "status": "ok",
            "version": app.version,
            "database": str(runtime.config.database_path),
            "config_root": str(runtime.config.project_root),
            "mode": "desktop-rag-only",
        }

    @app.get("/v1/settings")
    def local_settings(_: str = Depends(authorize)):
        return public_settings_status(runtime.config, runtime.rag)

    @app.post("/v1/settings")
    def save_local_settings(payload: LocalSettingsUpdate, _: str = Depends(authorize)):
        update_local_settings(runtime.config, payload)
        runtime.rag.reload_providers()
        return public_settings_status(runtime.config, runtime.rag)

    @app.post("/v1/google-sheets/connect")
    def connect_google_sheets(_: str = Depends(authorize)):
        try:
            return runtime.ingestion.chunk_store.connect()
        except Exception as error:
            raise HTTPException(status_code=422, detail="Google Sheets connection could not be created") from error

    @app.post("/v1/projects")
    def create_project(payload: ProjectCreate, user_id: str = Depends(authorize)):
        root_path = None
        if payload.root_path:
            path = Path(payload.root_path).expanduser().resolve()
            if not path.is_dir():
                raise HTTPException(status_code=422, detail="Project root is not a directory")
            root_path = str(path)
        return runtime.database.create_project(user_id, payload.name, root_path)

    @app.get("/v1/projects")
    def projects(user_id: str = Depends(authorize)):
        return runtime.database.query_all(
            "SELECT * FROM projects WHERE user_id=? ORDER BY updated_at DESC", (user_id,)
        )

    @app.post("/v1/sessions")
    def create_session(payload: SessionCreate, user_id: str = Depends(authorize)):
        if payload.user_id != user_id:
            raise HTTPException(status_code=403, detail="Desktop can create only its owner sessions")
        if payload.project_id:
            project = runtime.database.query_one(
                "SELECT id FROM projects WHERE id=? AND user_id=?", (payload.project_id, user_id)
            )
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
        session = runtime.database.create_session(user_id, payload.project_id, payload.title)
        runtime.policies.reset(session["id"])
        return session

    @app.get("/v1/sessions")
    def sessions(user_id: str = Depends(authorize)):
        return runtime.database.query_all(
            "SELECT * FROM sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,)
        )

    @app.get("/v1/sessions/{session_id}/messages")
    def messages(session_id: str, user_id: str = Depends(authorize)):
        session = runtime.database.query_one(
            "SELECT id, project_id FROM sessions WHERE id=? AND user_id=?", (session_id, user_id)
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return runtime.database.query_all(
            "SELECT * FROM messages WHERE session_id=? ORDER BY created_at", (session_id,)
        )

    @app.post("/v1/sessions/{session_id}/policy")
    def set_policy(session_id: str, payload: SessionPolicy, user_id: str = Depends(authorize)):
        session = runtime.database.query_one(
            "SELECT id FROM sessions WHERE id=? AND user_id=?", (session_id, user_id)
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return runtime.policies.set(session_id, payload)

    async def _send_message(session_id: str, payload: MessageCreate, user_id: str):
        session = runtime.database.query_one(
            "SELECT id FROM sessions WHERE id=? AND user_id=?", (session_id, user_id)
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        await runtime.events.publish(user_id, Event(type="chat.started", session_id=session_id))
        if session["project_id"]:
            await runtime.events.publish(user_id, Event(type="project.syncing", session_id=session_id))
            try:
                summary = await asyncio.to_thread(
                    runtime.ingestion.sync_project,
                    user_id=user_id,
                    project_id=session["project_id"],
                )
            except IngestionError as error:
                await runtime.events.publish(
                    user_id, Event(type="chat.failed", session_id=session_id, payload={"error": str(error)})
                )
                raise HTTPException(status_code=422, detail=str(error)) from error
            await runtime.events.publish(
                user_id, Event(type="project.synced", session_id=session_id, payload=summary.public())
            )
        try:
            answer = await asyncio.to_thread(runtime.rag.answer, session_id, payload.content)
        except RagServiceError as error:
            await runtime.events.publish(
                user_id, Event(type="chat.failed", session_id=session_id, payload={"error": str(error)})
            )
            raise HTTPException(status_code=422, detail=str(error)) from error
        await runtime.events.publish(
            user_id,
            Event(
                type="retrieval.completed",
                session_id=session_id,
                payload={
                    "source_selector": answer.source_selector,
                    "retrieved_chunks": answer.retrieved_chunks,
                    "citations": len(answer.citations),
                    "fallback": answer.fallback,
                },
            ),
        )
        for offset in range(0, len(answer.answer), 96):
            await runtime.events.publish(
                user_id,
                Event(
                    type="chat.delta",
                    session_id=session_id,
                    payload={"delta": answer.answer[offset : offset + 96]},
                ),
            )
        await runtime.events.publish(
            user_id,
            Event(
                type="chat.completed",
                session_id=session_id,
                payload=answer.model_dump(mode="json"),
            ),
        )
        return answer

    @app.post("/v1/messages/{session_id}")
    async def send_message(session_id: str, payload: MessageCreate, user_id: str = Depends(authorize)):
        return await _send_message(session_id, payload, user_id)

    @app.post("/v1/messages")
    async def send_message_contract(
        payload: MessageCreate,
        session_id: str = Query(...),
        user_id: str = Depends(authorize),
    ):
        return await _send_message(session_id, payload, user_id)

    @app.post("/v1/uploads")
    async def upload(
        project_id: str = Query(...),
        file: UploadFile = File(...),
        user_id: str = Depends(authorize),
    ):
        project = runtime.database.query_one(
            "SELECT id FROM projects WHERE id=? AND user_id=?", (project_id, user_id)
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        incoming = runtime.config.state_root / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        temporary = incoming / f"{secrets.token_hex(12)}.upload"
        size = 0
        try:
            async with aiofiles.open(temporary, "wb") as output:
                while block := await file.read(1024 * 1024):
                    size += len(block)
                    if size > runtime.config.max_upload_bytes:
                        raise HTTPException(status_code=413, detail="Upload exceeds configured limit")
                    await output.write(block)
            records = await asyncio.to_thread(
                runtime.ingestion.ingest_upload,
                temporary,
                user_id=user_id,
                project_id=project_id,
                display_name=file.filename or "upload",
            )
            return {"records": records}
        finally:
            temporary.unlink(missing_ok=True)

    @app.post("/v1/projects/{project_id}/import")
    async def import_project(project_id: str, user_id: str = Depends(authorize)):
        project = runtime.database.query_one(
            "SELECT * FROM projects WHERE id=? AND user_id=?", (project_id, user_id)
        )
        if not project or not project.get("root_path"):
            raise HTTPException(status_code=404, detail="Project with local root not found")
        records = await asyncio.to_thread(
            runtime.ingestion.import_project,
            Path(project["root_path"]),
            user_id=user_id,
            project_id=project_id,
        )
        return {"records": records}

    @app.get("/v1/projects/{project_id}/files")
    def project_files(project_id: str, user_id: str = Depends(authorize)):
        return runtime.database.query_all(
            "SELECT id,display_name,relative_path,media_type,language,size_bytes,status,updated_at FROM documents WHERE user_id=? AND project_id=? ORDER BY relative_path",
            (user_id, project_id),
        )

    @app.get("/v1/projects/{project_id}/graph")
    def project_graph(project_id: str, user_id: str = Depends(authorize)):
        project = runtime.database.query_one(
            "SELECT id FROM projects WHERE id=? AND user_id=?", (project_id, user_id)
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        nodes = runtime.database.query_all(
            "SELECT id,relative_path,display_name,language FROM documents WHERE project_id=? AND user_id=? ORDER BY relative_path",
            (project_id, user_id),
        )
        edges = runtime.database.query_all(
            "SELECT id,source_document_id,target_ref,edge_type FROM graph_edges WHERE project_id=? ORDER BY source_document_id",
            (project_id,),
        )
        symbols = runtime.database.query_all(
            "SELECT document_id,name,kind,qualified_name,line_start,line_end FROM symbols WHERE project_id=? ORDER BY document_id,line_start LIMIT 5000",
            (project_id,),
        )
        return {"nodes": nodes, "edges": edges, "symbols": symbols}

    @app.get("/v1/files/{document_id}/content")
    def file_content(document_id: str, user_id: str = Depends(authorize)):
        row = runtime.database.query_one(
            """
            SELECT d.*,v.extracted_text_path FROM documents d
            JOIN document_versions v ON v.document_id=d.id
            WHERE d.id=? AND d.user_id=? ORDER BY v.created_at DESC LIMIT 1
            """,
            (document_id, user_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        text = Path(row["extracted_text_path"]).read_text(encoding="utf-8")
        return {"document": row, "content": text}

    @app.delete("/v1/files/{document_id}")
    def delete_file(document_id: str, user_id: str = Depends(authorize)):
        try:
            runtime.ingestion.delete_document(document_id, user_id=user_id)
            return {"deleted": document_id}
        except Exception as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.websocket("/v1/events")
    async def events(websocket: WebSocket, token_query: str = Query(alias="token")):
        if not secrets.compare_digest(token_query, token):
            await websocket.close(code=4401)
            return
        user_id = "desktop-owner"
        await websocket.accept()
        queue = await runtime.events.subscribe(user_id)
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            await runtime.events.unsubscribe(user_id, queue)

    return app


app = create_app()
