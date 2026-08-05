from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONSTANTS_PATH = PROJECT_ROOT / "local_config" / "constants.py"


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    hf_token: str
    local_adapter_path: Path | None
    freemodel_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    freemodel_base_url: str = "https://api.freemodel.dev/v1"
    freemodel_model: str = "auto"
    local_model_name: str = "Qwen/Qwen3-4B-Instruct-2507"
    embedding_model_name: str = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    default_top_k: int = 3
    default_candidate_k: int = 10
    minimum_reranker_raw_score: float = 0.005
    maximum_question_length: int = 1000
    telegram_network_timeout_seconds: float = 30.0
    per_user_request_limit: int = 5
    per_user_window_seconds: int = 600
    openai_daily_request_limit: int = 100
    freemodel_daily_request_limit: int = 100
    maximum_answer_tokens: int = 384


def _load_local_constants(path: Path) -> ModuleType | None:
    if not path.exists():
        return None

    spec = importlib.util.spec_from_file_location(
        "hw4_local_constants",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не вдалося завантажити constants: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _value(
    name: str,
    constants: ModuleType | None,
    default: str = "",
) -> str:
    environment_value = os.getenv(name)
    if environment_value is not None:
        return environment_value.strip()

    if constants is not None:
        local_value = getattr(constants, name, None)
        if local_value is not None:
            return str(local_value).strip()

    return default


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    constants = _load_local_constants(LOCAL_CONSTANTS_PATH)
    adapter_value = _value("LOCAL_ADAPTER_PATH", constants)

    return Settings(
        telegram_bot_token=_value("TELEGRAM_BOT_TOKEN", constants),
        openai_api_key=_value("OPENAI_API_KEY", constants),
        hf_token=_value("HF_TOKEN", constants),
        local_adapter_path=(
            Path(adapter_value).expanduser()
            if adapter_value
            else None
        ),
        freemodel_api_key=_value("FREEMODEL_API_KEY", constants),
        openai_model=_value(
            "OPENAI_MODEL",
            constants,
            "gpt-4.1-mini",
        ),
        freemodel_base_url=_value(
            "FREEMODEL_BASE_URL",
            constants,
            "https://api.freemodel.dev/v1",
        ),
        freemodel_model=_value(
            "FREEMODEL_MODEL",
            constants,
            "auto",
        ),
        local_model_name=_value(
            "LOCAL_MODEL_NAME",
            constants,
            "Qwen/Qwen3-4B-Instruct-2507",
        ),
    )
