from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.api.app.services.speech_to_text import (
    SpeechToTextServiceError,
    _transcribe_via_api,
    transcribe_audio_file,
)


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class SpeechToTextTests(unittest.TestCase):
    def test_transcribe_audio_skips_llm_postprocess_when_disabled(self) -> None:
        settings = SimpleNamespace(whisper_provider="api", whisper_postprocess_with_llm=False)
        raw_result = SimpleNamespace(
            provider="api",
            model="whisper-v3-turbo",
            raw_text="покажи лимиты по благовещ",
            normalized_text="покажи лимиты по благовещ",
            correction_applied=False,
            language="ru",
            duration_seconds=1.0,
            words=[],
        )

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(b"RIFFfake")
            temp_path = Path(temp_file.name)

        try:
            with patch("core.api.app.services.speech_to_text.get_settings", return_value=settings):
                with patch("core.api.app.services.speech_to_text._transcribe_via_api", return_value=raw_result):
                    with patch("core.api.app.services.speech_to_text.normalize_transcribed_query_text") as mocked_norm:
                        result = transcribe_audio_file(temp_path, filter_options=None)
        finally:
            temp_path.unlink(missing_ok=True)

        self.assertEqual(result.raw_text, "покажи лимиты по благовещ")
        self.assertEqual(result.normalized_text, "покажи лимиты по благовещ")
        self.assertFalse(result.correction_applied)
        mocked_norm.assert_not_called()

    def test_api_transcription_uses_requests_multipart_and_parses_words(self) -> None:
        settings = SimpleNamespace(
            whisper_api_key="secret",
            whisper_api_base_url="https://api.302.ai/v1/audio/transcriptions",
            whisper_api_model="whisper-v3-turbo",
            whisper_temperature=0,
            whisper_response_format="verbose_json",
            whisper_timestamp_granularity="word",
            whisper_diarize=False,
            whisper_language="ru",
            whisper_timeout_seconds=30,
        )
        response = _FakeResponse(
            status_code=200,
            payload={
                "text": "Покажи лимиты по Благовещенску",
                "language": "ru",
                "duration": 1.5,
                "words": [{"word": "Благовещенску", "start": 0.6, "end": 1.2}],
            },
        )

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(b"RIFFfake")
            temp_path = Path(temp_file.name)

        try:
            with patch("core.api.app.services.speech_to_text.get_settings", return_value=settings):
                with patch("core.api.app.services.speech_to_text.requests.post", return_value=response) as mocked_post:
                    result = _transcribe_via_api(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        self.assertEqual(result.raw_text, "Покажи лимиты по Благовещенску")
        self.assertEqual(result.language, "ru")
        self.assertEqual(result.duration_seconds, 1.5)
        self.assertEqual(result.words[0].word, "Благовещенску")

        self.assertEqual(mocked_post.call_args.kwargs["data"]["model"], "whisper-v3-turbo")
        self.assertEqual(mocked_post.call_args.kwargs["data"]["response_format"], "verbose_json")
        self.assertEqual(mocked_post.call_args.kwargs["data"]["timestamp_granularities"], "word")
        self.assertEqual(mocked_post.call_args.kwargs["data"]["language"], "ru")
        self.assertNotIn("diarize", mocked_post.call_args.kwargs["data"])
        self.assertEqual(mocked_post.call_args.kwargs["files"]["file"][2], "audio/wav")

    def test_api_transcription_raises_service_error_for_http_failure(self) -> None:
        settings = SimpleNamespace(
            whisper_api_key="secret",
            whisper_api_base_url="https://api.302.ai/v1/audio/transcriptions",
            whisper_api_model="whisper-v3-turbo",
            whisper_temperature=0,
            whisper_response_format="verbose_json",
            whisper_timestamp_granularity="word",
            whisper_diarize=False,
            whisper_language="ru",
            whisper_timeout_seconds=30,
        )
        response = _FakeResponse(status_code=403, text='{"error":"bad params"}')

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(b"RIFFfake")
            temp_path = Path(temp_file.name)

        try:
            with patch("core.api.app.services.speech_to_text.get_settings", return_value=settings):
                with patch("core.api.app.services.speech_to_text.requests.post", return_value=response):
                    with self.assertRaises(SpeechToTextServiceError) as error:
                        _transcribe_via_api(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        self.assertIn("status 403", str(error.exception))


if __name__ == "__main__":
    unittest.main()
