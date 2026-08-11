from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from jarvis.agent import AgentError
from jarvis.models import AgentMode, FileScope, SessionPolicy
from jarvis.runtime import Runtime
from jarvis.tools import ToolExecutionError
from scripts.telegram_bot.handlers import _send_long_message, question_handler as legacy_question_handler


def _runtime(context: ContextTypes.DEFAULT_TYPE) -> Runtime:
    return context.application.bot_data["jarvis_runtime"]


def _authorized(update: Update, runtime: Runtime) -> bool:
    user = update.effective_user
    return bool(user and user.id in runtime.config.authorized_telegram_user_ids)


async def _require_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    runtime = _runtime(context)
    if _authorized(update, runtime):
        return True
    await update.effective_message.reply_text(
        "Повний agent mode доступний лише Telegram ID з локального allowlist. "
        "Ваш ID можна переглянути командою /whoami."
    )
    return False


def _identity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, str, str]:
    runtime = _runtime(context)
    user = update.effective_user
    assert user is not None
    user_id = f"telegram:{user.id}"
    display = user.full_name or user.username or str(user.id)
    runtime.database.ensure_user(user_id, display)
    runtime.database.execute(
        "INSERT OR REPLACE INTO identities(interface,external_id,user_id,is_admin) VALUES('telegram',?,?,?)",
        (str(user.id), user_id, int(user.id in runtime.config.admin_telegram_user_ids)),
    )
    project_id = context.user_data.get("jarvis_project_id")
    project = runtime.database.query_one(
        "SELECT * FROM projects WHERE id=? AND user_id=?", (project_id, user_id)
    ) if project_id else None
    if project is None:
        project = runtime.database.query_one(
            "SELECT * FROM projects WHERE user_id=? ORDER BY created_at LIMIT 1", (user_id,)
        )
    if project is None:
        project = runtime.database.create_project(user_id, "Telegram files", None)
    project_id = project["id"]
    context.user_data["jarvis_project_id"] = project_id

    session_id = context.user_data.get("jarvis_session_id")
    session = runtime.database.query_one(
        "SELECT * FROM sessions WHERE id=? AND user_id=?", (session_id, user_id)
    ) if session_id else None
    if session is None or session.get("project_id") != project_id:
        session = runtime.database.create_session(user_id, project_id, "Telegram task")
        runtime.policies.reset(session["id"])
    context.user_data["jarvis_session_id"] = session["id"]
    return user_id, project_id, session["id"]


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    runtime = _runtime(context)
    allowed = user.id in runtime.config.authorized_telegram_user_ids
    admin = user.id in runtime.config.admin_telegram_user_ids
    await update.effective_message.reply_text(
        f"Telegram ID: {user.id}\nAgent allowlist: {'yes' if allowed else 'no'}\nAdmin: {'yes' if admin else 'no'}"
    )


async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context): return
    user_id, project_id, _ = _identity(update, context)
    rows = _runtime(context).database.query_all(
        "SELECT display_name,relative_path,size_bytes,status FROM documents WHERE user_id=? AND project_id=? ORDER BY relative_path",
        (user_id, project_id),
    )
    if not rows:
        await update.effective_message.reply_text("У поточному проєкті ще немає файлів.")
        return
    lines = ["Файли поточного проєкту:"] + [
        f"- {row['relative_path']} ({row['size_bytes'] / 1024:.1f} KB, {row['status']})" for row in rows
    ]
    await _send_long_message(update, "\n".join(lines))


async def uploadinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = _runtime(context)
    await update.effective_message.reply_text(
        "Надішліть документ або ZIP/TAR/7z/RAR як Telegram document.\n"
        f"Upload: до {runtime.config.max_upload_bytes // 1024**2} MB; "
        f"розпакування: до {runtime.config.max_extracted_bytes // 1024**2} MB; "
        f"файлів в архіві: до {runtime.config.max_archive_files}.\n"
        "Код з файлів не виконується. Вкладені архіви, binaries, secrets та path traversal відхиляються."
    )


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context): return
    message = update.effective_message
    if message is None or message.document is None: return
    runtime = _runtime(context)
    if message.document.file_size and message.document.file_size > runtime.config.max_upload_bytes:
        await message.reply_text("Файл перевищує локальний upload limit.")
        return
    user_id, project_id, _ = _identity(update, context)
    telegram_file = await context.bot.get_file(message.document.file_id)
    suffix = Path(message.document.file_name or "upload").suffix
    with tempfile.TemporaryDirectory(dir=runtime.config.state_root) as directory:
        temporary = Path(directory) / f"telegram{suffix}"
        await telegram_file.download_to_drive(custom_path=temporary)
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        try:
            records = await asyncio.to_thread(
                runtime.ingestion.ingest_upload,
                temporary,
                user_id=user_id,
                project_id=project_id,
                display_name=message.document.file_name or "upload",
            )
        except Exception as error:
            await message.reply_text(f"Індексацію відхилено: {error}")
            return
    ready = sum(item.get("status") in {"ready", "unchanged"} for item in records)
    rejected = len(records) - ready
    await message.reply_text(f"Індексацію завершено: ready={ready}, rejected={rejected}. Використайте /files або поставте запитання.")


async def use_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context): return
    user_id, project_id, session_id = _identity(update, context)
    if not context.args:
        await update.effective_message.reply_text("Використання: /use auto|all|<project-or-file>")
        return
    selector = " ".join(context.args).strip()
    runtime = _runtime(context)
    if selector not in {"auto", "all"}:
        project = runtime.database.query_one(
            "SELECT * FROM projects WHERE user_id=? AND lower(name)=lower(?)", (user_id, selector)
        )
        if project:
            context.user_data["jarvis_project_id"] = project["id"]
            context.user_data.pop("jarvis_session_id", None)
            _identity(update, context)
            await update.effective_message.reply_text(f"Активний проєкт: {project['name']}")
            return
        file = runtime.database.query_one(
            "SELECT relative_path FROM documents WHERE user_id=? AND project_id=? AND (lower(display_name)=lower(?) OR lower(relative_path)=lower(?))",
            (user_id, project_id, selector, selector),
        )
        if not file:
            await update.effective_message.reply_text("Проєкт або файл не знайдено.")
            return
        selector = file["relative_path"]
    current = runtime.policies.get(session_id)
    runtime.policies.set(session_id, current.model_copy(update={"source_selector": selector}))
    await update.effective_message.reply_text(f"Corpus selector: {selector}")


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context): return
    if not context.args or context.args[0] not in {"safe", "autonomous"}:
        await update.effective_message.reply_text("Використання: /mode safe|autonomous")
        return
    _, _, session_id = _identity(update, context)
    runtime = _runtime(context)
    current = runtime.policies.get(session_id)
    updated = current.model_copy(update={"mode": AgentMode(context.args[0])})
    runtime.policies.set(session_id, updated)
    await update.effective_message.reply_text(f"Agent mode: {updated.mode.value}")


async def scope_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context): return
    if not context.args or context.args[0] not in {"workspace", "roots", "computer"}:
        await update.effective_message.reply_text("Використання: /scope workspace|roots|computer")
        return
    _, _, session_id = _identity(update, context)
    runtime = _runtime(context)
    current = runtime.policies.get(session_id)
    updated = current.model_copy(update={"scope": FileScope(context.args[0])})
    runtime.policies.set(session_id, updated)
    await update.effective_message.reply_text(f"Filesystem scope: {updated.scope.value}")


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context): return
    if not context.args:
        await update.effective_message.reply_text("Використання: /delete <file>")
        return
    user_id, project_id, _ = _identity(update, context)
    name = " ".join(context.args)
    runtime = _runtime(context)
    row = runtime.database.query_one(
        "SELECT id FROM documents WHERE user_id=? AND project_id=? AND (lower(display_name)=lower(?) OR lower(relative_path)=lower(?))",
        (user_id, project_id, name, name),
    )
    if not row:
        await update.effective_message.reply_text("Файл не знайдено.")
        return
    await asyncio.to_thread(runtime.ingestion.delete_document, row["id"], user_id=user_id)
    await update.effective_message.reply_text(f"Видалено з corpus: {name}")


async def clearfiles_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context): return
    user_id, project_id, _ = _identity(update, context)
    runtime = _runtime(context)
    rows = runtime.database.query_all(
        "SELECT id FROM documents WHERE user_id=? AND project_id=?", (user_id, project_id)
    )
    for row in rows:
        await asyncio.to_thread(runtime.ingestion.delete_document, row["id"], user_id=user_id)
    await update.effective_message.reply_text(f"Corpus очищено: {len(rows)} file(s).")


async def approvals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context): return
    _, _, session_id = _identity(update, context)
    rows = _runtime(context).database.query_all(
        "SELECT id,status,high_risk,preview,expires_at FROM approvals WHERE session_id=? AND status IN ('pending','button_confirmed') ORDER BY created_at DESC",
        (session_id,),
    )
    if not rows:
        await update.effective_message.reply_text("Немає активних approvals.")
        return
    await _send_long_message(update, "\n\n".join(f"{r['id']}\n{r['preview']}\nstatus={r['status']}, high_risk={bool(r['high_risk'])}" for r in rows))


async def jarvis_sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    answer = context.user_data.get("last_agent_answer")
    if answer is None:
        return False
    lines = ["JARVIS sources:"]
    for citation in answer.citations:
        location = f"page {citation.page}" if citation.page else f"lines {citation.line_start}-{citation.line_end}" if citation.line_start else citation.cell_range or "chunk"
        lines.append(f"- {citation.source_path} · {location} · {citation.chunk_id}")
    if not answer.citations:
        lines.append("General model knowledge — not grounded in your files.")
    await _send_long_message(update, "\n".join(lines))
    return True


async def jarvis_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _authorized(update, _runtime(context)):
        _, _, session_id = _identity(update, context)
        _runtime(context).policies.reset(session_id)
    for key in ("last_agent_answer", "last_result", "last_tool_result", "jarvis_session_id"):
        context.user_data.pop(key, None)
    context.user_data["provider"] = "openai"
    await update.effective_message.reply_text("Сесію скинуто до safe + workspace; останні результати очищено.")


async def jarvis_question_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = _runtime(context)
    if not _authorized(update, runtime):
        await legacy_question_handler(update, context)
        return
    message = update.effective_message
    if message is None or not message.text: return
    _, _, session_id = _identity(update, context)
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        answer = await asyncio.to_thread(runtime.agent.answer, session_id, message.text.strip())
    except (AgentError, ToolExecutionError) as error:
        await message.reply_text(f"JARVIS: {error}")
        return
    context.user_data["last_agent_answer"] = answer
    text = answer.answer
    if answer.citations:
        text += "\n\nДжерела:\n" + "\n".join(f"- {item.source_path}" for item in answer.citations)
    if answer.pending_approval_id:
        text += f"\n\nApproval: {answer.pending_approval_id}\nВикористайте desktop для Confirm/Cancel; high-risk code Telegram не показує."
    await _send_long_message(update, text)
