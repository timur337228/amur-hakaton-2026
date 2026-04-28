from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _sync_database_url() -> str:
    sync_url = os.getenv("DATABASE_SYNC_URL")
    if sync_url:
        return sync_url

    url = os.getenv("DATABASE_URL")
    if not url:
        return "postgresql+psycopg://budget_app:budget_app_dev@localhost:5432/budget_analytics"

    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


def _load_yaml_config(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}

    result: dict[str, object] = {}
    stack: list[tuple[int, dict[str, object]]] = [(-1, result)]

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]
        if not value:
            nested: dict[str, object] = {}
            parent[key] = nested
            stack.append((indent, nested))
        else:
            parent[key] = value.strip('"').strip("'")

    return result


def _yaml_value(config: dict[str, object], *path: str) -> str | None:
    current: object = config
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current if isinstance(current, str) else None


@dataclass(frozen=True)
class Settings:
    project_root: Path
    storage_dir: Path
    database_url: str
    deploy_mode: bool
    allow_local_import: bool
    cors_allowed_origins: tuple[str, ...]
    llm_model: str | None
    llm_api_key: str | None
    llm_base_url: str
    llm_timeout_seconds: int
    whisper_provider: str
    whisper_api_key: str | None
    whisper_api_base_url: str
    whisper_api_model: str
    whisper_local_model: str
    whisper_language: str | None
    whisper_temperature: float
    whisper_response_format: str
    whisper_timestamp_granularity: str
    whisper_diarize: bool
    whisper_timeout_seconds: int
    whisper_device: str
    whisper_compute_type: str
    whisper_vad_filter: bool
    whisper_postprocess_with_llm: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[3]
    _load_env_file(project_root / ".env")
    yaml_config = _load_yaml_config(project_root / "config.yaml")

    storage_dir = Path(os.getenv("STORAGE_DIR", "storage"))
    if not storage_dir.is_absolute():
        storage_dir = project_root / storage_dir

    llm_model = (
        _yaml_value(yaml_config, "llm", "model")
        or _yaml_value(yaml_config, "model")
        or os.getenv("LLM_MODEL")
    )
    llm_api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("THREE_ZERO_TWO_API_KEY")
        or os.getenv("API_KEY_302AI")
    )
    whisper_provider = (
        os.getenv("WHISPER_PROVIDER")
        or _yaml_value(yaml_config, "whisper", "provider")
        or ("local" if _as_bool(_yaml_value(yaml_config, "whisper", "local"), default=False) else "api")
    ).strip().lower()
    whisper_model_name = _yaml_value(yaml_config, "whisper", "model_name")
    whisper_api_model = (
        _yaml_value(yaml_config, "whisper", "api_model")
        or (whisper_model_name if whisper_provider == "api" else None)
        or os.getenv("WHISPER_API_MODEL")
        or "whisper-v3-turbo"
    )
    whisper_local_model = (
        _yaml_value(yaml_config, "whisper", "local_model")
        or (whisper_model_name if whisper_provider == "local" else None)
        or os.getenv("WHISPER_LOCAL_MODEL")
        or "large-v3-turbo"
    )
    whisper_api_key = (
        os.getenv("WHISPER_API_KEY")
        or os.getenv("THREE_ZERO_TWO_API_KEY")
        or os.getenv("API_KEY_302AI")
        or llm_api_key
    )
    cors_allow_origins = _split_csv_env(
        os.getenv(
            "CORS_ALLOW_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8001,http://127.0.0.1:8001",
        )
    )

    return Settings(
        project_root=project_root,
        storage_dir=storage_dir,
        database_url=_sync_database_url(),
        deploy_mode=_as_bool(os.getenv("DEPLOY_MODE", _yaml_value(yaml_config, "deploy")), default=False),
        allow_local_import=os.getenv("ALLOW_LOCAL_IMPORT", "true").lower() in {"1", "true", "yes", "on"},
        cors_allowed_origins=tuple(cors_allow_origins),
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.302.ai/v1/chat/completions"),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        whisper_provider=whisper_provider,
        whisper_api_key=whisper_api_key,
        whisper_api_base_url=os.getenv("WHISPER_API_BASE_URL", "https://api.302.ai/v1/audio/transcriptions"),
        whisper_api_model=whisper_api_model,
        whisper_local_model=whisper_local_model,
        whisper_language=_yaml_value(yaml_config, "whisper", "language") or os.getenv("WHISPER_LANGUAGE") or "ru",
        whisper_temperature=float(
            os.getenv(
                "WHISPER_TEMPERATURE",
                _yaml_value(yaml_config, "whisper", "temperature") or "0",
            )
        ),
        whisper_response_format=(
            _yaml_value(yaml_config, "whisper", "response_format")
            or os.getenv("WHISPER_RESPONSE_FORMAT")
            or "verbose_json"
        ),
        whisper_timestamp_granularity=(
            _yaml_value(yaml_config, "whisper", "timestamp_granularity")
            or os.getenv("WHISPER_TIMESTAMP_GRANULARITY")
            or "word"
        ),
        whisper_diarize=_as_bool(
            os.getenv("WHISPER_DIARIZE", _yaml_value(yaml_config, "whisper", "diarize")),
            default=False,
        ),
        whisper_timeout_seconds=int(
            os.getenv(
                "WHISPER_TIMEOUT_SECONDS",
                _yaml_value(yaml_config, "whisper", "timeout_seconds") or "120",
            )
        ),
        whisper_device=(
            _yaml_value(yaml_config, "whisper", "device")
            or os.getenv("WHISPER_DEVICE")
            or "auto"
        ),
        whisper_compute_type=(
            _yaml_value(yaml_config, "whisper", "compute_type")
            or os.getenv("WHISPER_COMPUTE_TYPE")
            or "int8"
        ),
        whisper_vad_filter=_as_bool(
            os.getenv("WHISPER_VAD_FILTER", _yaml_value(yaml_config, "whisper", "vad_filter")),
            default=True,
        ),
        whisper_postprocess_with_llm=_as_bool(
            os.getenv(
                "WHISPER_POSTPROCESS_WITH_LLM",
                _yaml_value(yaml_config, "whisper", "postprocess_with_llm"),
            ),
            default=False,
        ),
    )


def _split_csv_env(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip().rstrip("/") for item in raw_value.split(",") if item.strip()]


def _as_bool(raw_value: str | None, *, default: bool) -> bool:
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}
