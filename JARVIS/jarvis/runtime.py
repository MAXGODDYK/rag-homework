from __future__ import annotations

from dataclasses import dataclass

from .config import JarvisConfig, load_jarvis_config
from .database import Database
from .events import EventBus
from .ingestion import IngestionService
from .rag_service import DesktopRagService
from .retrieval import DynamicRetriever
from .sessions import SessionPolicyStore


@dataclass
class Runtime:
    config: JarvisConfig
    database: Database
    events: EventBus
    policies: SessionPolicyStore
    ingestion: IngestionService
    retriever: DynamicRetriever
    rag: DesktopRagService


def build_runtime() -> Runtime:
    config = load_jarvis_config()
    database = Database(config.database_path)
    database.initialize()
    events = EventBus()
    policies = SessionPolicyStore()
    ingestion = IngestionService(config, database)
    retriever = DynamicRetriever(config, database)
    rag = DesktopRagService(
        database=database,
        retriever=retriever,
        policies=policies,
    )
    database.ensure_user("desktop-owner", "Desktop owner")
    return Runtime(
        config=config,
        database=database,
        events=events,
        policies=policies,
        ingestion=ingestion,
        retriever=retriever,
        rag=rag,
    )
