from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path

import requests

from ..config import get_settings
from ..schemas import AnalyticsFilterOptionsResponse, AudioTranscriptWord
from .llm import (
    LLMConfigurationError,
    LLMServiceError,
    normalize_transcribed_query_text,
)


class SpeechToTextConfigurationError(RuntimeError):
    pass


class SpeechToTextServiceError(RuntimeError):
    pass


SUPPORTED_AUDIO_EXTENSIONS = frozenset({".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"})


@dataclass(frozen=True)
class TranscriptionResult:
    provider: str
    model: str
    raw_text: str
    normalized_text: str
    correction_applied: bool
    language: str | None
    duration_seconds: float | None
    words: list[AudioTranscriptWord]
    warning: str | None = None


def transcribe_audio_file(
    audio_path: Path,
    *,
    filter_options: AnalyticsFilterOptionsResponse | None = None,
) -> TranscriptionResult:
    settings = get_settings()
    provider = settings.whisper_provider
    if provider == "api":
        raw = _transcribe_via_api(audio_path)
    elif provider == "local":
        raw = _transcribe_via_local_whisper(audio_path)
    else:
        raise SpeechToTextConfigurationError(f"Unsupported whisper provider: {provider}")

    warning = None
    normalized_text = raw.raw_text
    correction_applied = False
    if settings.whisper_postprocess_with_llm and raw.raw_text.strip():
        try:
            normalization = normalize_transcribed_query_text(
                raw_text=raw.raw_text,
                filter_options=filter_options,
            )
            normalized_text = normalization.normalized_text
            correction_applied = normalization.changed
        except (LLMConfigurationError, LLMServiceError) as exc:
            warning = (
                "Транскрипция выполнена, но дополнительная нормализация запроса через LLM недоступна. "
                f"Причина: {exc}"
            )

    return TranscriptionResult(
        provider=raw.provider,
        model=raw.model,
        raw_text=raw.raw_text,
        normalized_text=normalized_text,
        correction_applied=correction_applied,
        language=raw.language,
        duration_seconds=raw.duration_seconds,
        words=raw.words,
        warning=warning,
    )


def _transcribe_via_api(audio_path: Path) -> TranscriptionResult:
    settings = get_settings()
    if not settings.whisper_api_key:
        raise SpeechToTextConfigurationError("Whisper API key is not configured.")

    form_fields: dict[str, str] = {
        "model": settings.whisper_api_model,
        "temperature": str(settings.whisper_temperature),
        "response_format": settings.whisper_response_format,
    }
    if settings.whisper_language:
        form_fields["language"] = settings.whisper_language
    if settings.whisper_response_format == "verbose_json" and settings.whisper_timestamp_granularity:
        form_fields["timestamp_granularities"] = settings.whisper_timestamp_granularity
    if settings.whisper_diarize:
        form_fields["diarize"] = "true"

    content_type = _guess_audio_content_type(audio_path)

    try:
        with audio_path.open("rb") as audio_file:
            response = requests.post(
                settings.whisper_api_base_url,
                headers={"Authorization": f"Bearer {settings.whisper_api_key}"},
                data=form_fields,
                files={"file": (audio_path.name, audio_file, content_type)},
                timeout=settings.whisper_timeout_seconds,
            )
    except requests.RequestException as exc:
        raise SpeechToTextServiceError(f"Whisper API request failed: {exc}") from exc

    if response.status_code >= 400:
        raise SpeechToTextServiceError(
            f"Whisper API request failed with status {response.status_code}: {response.text}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise SpeechToTextServiceError("Whisper API returned a non-JSON response.") from exc

    text = str(payload.get("text") or "").strip()
    if not text and payload.get("duration") not in {0, 0.0, "0", "0.0"}:
        raise SpeechToTextServiceError("Whisper API returned an empty transcription.")
    words = [_word_from_mapping(item) for item in payload.get("words") or [] if isinstance(item, dict)]
    return TranscriptionResult(
        provider="api",
        model=settings.whisper_api_model,
        raw_text=text,
        normalized_text=text,
        correction_applied=False,
        language=_optional_string(payload.get("language")),
        duration_seconds=_optional_float(payload.get("duration")),
        words=words,
    )


def _transcribe_via_local_whisper(audio_path: Path) -> TranscriptionResult:
    settings = get_settings()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SpeechToTextConfigurationError(
            "Local Whisper requires the 'faster-whisper' package to be installed."
        ) from exc

    device = _resolve_local_device(settings.whisper_device)
    try:
        model = WhisperModel(
            settings.whisper_local_model,
            device=device,
            compute_type=settings.whisper_compute_type,
        )
    except Exception as exc:  # pragma: no cover - depends on local runtime/model cache
        raise SpeechToTextServiceError(f"Local Whisper model could not be initialized: {exc}") from exc
    try:
        segments, info = model.transcribe(
            str(audio_path),
            language=settings.whisper_language or None,
            temperature=settings.whisper_temperature,
            word_timestamps=settings.whisper_timestamp_granularity == "word",
            vad_filter=settings.whisper_vad_filter,
        )
    except Exception as exc:  # pragma: no cover - depends on runtime/audio backend
        raise SpeechToTextServiceError(f"Local Whisper transcription failed: {exc}") from exc

    pieces: list[str] = []
    words: list[AudioTranscriptWord] = []
    for segment in segments:
        segment_text = (segment.text or "").strip()
        if segment_text:
            pieces.append(segment_text)
        for word in getattr(segment, "words", []) or []:
            words.append(
                AudioTranscriptWord(
                    word=str(getattr(word, "word", "")).strip(),
                    start=_optional_float(getattr(word, "start", None)),
                    end=_optional_float(getattr(word, "end", None)),
                )
            )

    text = " ".join(piece for piece in pieces if piece).strip()
    duration = _optional_float(getattr(info, "duration", None))
    language = _optional_string(getattr(info, "language", None))
    return TranscriptionResult(
        provider="local",
        model=settings.whisper_local_model,
        raw_text=text,
        normalized_text=text,
        correction_applied=False,
        language=language,
        duration_seconds=duration,
        words=words,
    )

def _resolve_local_device(raw_device: str) -> str:
    if raw_device != "auto":
        return raw_device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _guess_audio_content_type(audio_path: Path) -> str:
    extension = audio_path.suffix.lower()
    if extension == ".wav":
        return "audio/wav"
    if extension == ".webm":
        return "audio/webm"
    if extension in {".mp3", ".mpeg", ".mpga"}:
        return "audio/mpeg"
    if extension in {".m4a", ".mp4"}:
        return "audio/mp4"
    guessed = mimetypes.guess_type(audio_path.name)[0]
    return guessed or "application/octet-stream"


def _word_from_mapping(item: dict) -> AudioTranscriptWord:
    return AudioTranscriptWord(
        word=str(item.get("word") or "").strip(),
        start=_optional_float(item.get("start")),
        end=_optional_float(item.get("end")),
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
