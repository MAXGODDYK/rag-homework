from __future__ import annotations

from dataclasses import dataclass

from .agent import AgentService
from .approvals import ApprovalManager
from .config import JarvisConfig, load_jarvis_config
from .database import Database
from .events import EventBus
from .ingestion import IngestionService
from .retrieval import DynamicRetriever
from .security import SessionPolicyStore
from .tool_runner import ToolRunner
from .tools import ToolRegistry, build_default_registry


@dataclass
class Runtime:
    config: JarvisConfig
    database: Database
    events: EventBus
    policies: SessionPolicyStore
    approvals: ApprovalManager
    registry: ToolRegistry
    runner: ToolRunner
    ingestion: IngestionService
    retriever: DynamicRetriever
    agent: AgentService


def build_runtime() -> Runtime:
    config = load_jarvis_config()
    database = Database(config.database_path)
    database.initialize()
    events = EventBus()
    policies = SessionPolicyStore()
    approvals = ApprovalManager(database)
    registry = build_default_registry(config)
    runner = ToolRunner(database, registry, approvals)
    ingestion = IngestionService(config, database)
    retriever = DynamicRetriever(config, database)
    agent = AgentService(
        config=config,
        database=database,
        registry=registry,
        runner=runner,
        approvals=approvals,
        retriever=retriever,
        policies=policies,
    )
    database.ensure_user("desktop-owner", "Desktop owner")
    return Runtime(
        config=config,
        database=database,
        events=events,
        policies=policies,
        approvals=approvals,
        registry=registry,
        runner=runner,
        ingestion=ingestion,
        retriever=retriever,
        agent=agent,
    )
