from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np


class ModelNotFoundError(RuntimeError):
    """Raised when local Faster-Whisper model directory cannot be found."""


class FasterWhisperSpeechRecognizer:
    def __init__(
        self,
        model_size_or_path: str,
        sample_rate: int,
        device: str = "cpu",
        compute_type: str = "int8",
        beam_size: int = 5,
        language: str = "ru",
    ) -> None:
        if sample_rate != 16_000:
            raise ValueError("Faster-Whisper expects sample_rate=16000 in this MVP.")

        candidate_path = Path(model_size_or_path)
        if _looks_like_local_path(model_size_or_path) and not candidate_path.exists():
            raise ModelNotFoundError(
                "Не найдена локальная модель Faster-Whisper: "
                f"{candidate_path}."
            )

        self._beam_size = beam_size
        self._language = language
        whisper_model_cls = _resolve_whisper_model_class()
        self._model = whisper_model_cls(
            model_size_or_path,
            device=device,
            compute_type=compute_type,
        )

    def recognize(self, pcm_audio: bytes) -> str:
        if not pcm_audio:
            return ""

        pcm16 = np.frombuffer(pcm_audio, dtype=np.int16)
        if pcm16.size == 0:
            return ""

        audio = pcm16.astype(np.float32) / 32768.0

        segments, _ = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=self._beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
            temperature=0.0,
        )

        parts: list[str] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                parts.append(text)

        return " ".join(parts).strip()


def _looks_like_local_path(value: str) -> bool:
    return any(marker in value for marker in ("/", "\\", "."))


def _import_faster_whisper() -> Any:
    try:
        return importlib.import_module("faster_whisper")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Пакет faster-whisper не установлен или недоступен для этой версии Python. "
            "Для Windows обычно нужен Python 3.11-3.12. "
            "Установите faster-whisper и ctranslate2 в совместимом окружении."
        ) from exc


def _get_whisper_model_class() -> Any:
    module = _import_faster_whisper()
    whisper_model_cls = getattr(module, "WhisperModel", None)
    if whisper_model_cls is None:
        raise RuntimeError("В пакете faster-whisper не найден класс WhisperModel.")
    return whisper_model_cls


def _resolve_whisper_model_class() -> Any:
    return _get_whisper_model_class()
