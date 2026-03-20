from __future__ import annotations

import json
from pathlib import Path

from vosk import KaldiRecognizer, Model


class ModelNotFoundError(RuntimeError):
    """Raised when Vosk model directory cannot be found."""


class VoskSpeechRecognizer:
    def __init__(self, model_path: Path, sample_rate: int) -> None:
        if not model_path.exists():
            raise ModelNotFoundError(
                "Не найдена модель Vosk. Скачайте русскую модель и поместите в "
                f"{model_path}."
            )
        self._model = Model(str(model_path))
        self._sample_rate = sample_rate

    def recognize(self, pcm_audio: bytes) -> str:
        recognizer = KaldiRecognizer(self._model, self._sample_rate)
        recognizer.SetWords(False)
        recognizer.AcceptWaveform(pcm_audio)

        final_result = recognizer.FinalResult()
        data = json.loads(final_result)
        return data.get("text", "").strip()
