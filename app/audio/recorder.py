from __future__ import annotations

import numpy as np
import sounddevice as sd


class MicrophoneError(RuntimeError):
    """Raised when microphone recording fails."""


def record_audio(duration_s: int, sample_rate: int, channels: int = 1) -> bytes:
    """Record PCM16 mono/stereo audio and return raw bytes for STT."""
    if duration_s <= 0:
        raise ValueError("duration_s must be > 0")

    try:
        default_input = sd.default.device[0]
        if default_input is None or default_input < 0:
            raise MicrophoneError("Не найдено устройство ввода (микрофон).")
    except Exception as exc:
        raise MicrophoneError("Не удалось определить устройство микрофона.") from exc

    frames = int(duration_s * sample_rate)
    try:
        audio = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            blocking=True,
        )
    except Exception as exc:
        raise MicrophoneError(f"Ошибка записи с микрофона: {exc}") from exc

    pcm = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm * 32767).astype(np.int16)
    return pcm16.tobytes()
