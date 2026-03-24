from pathlib import Path

APP_TITLE = "Voice Command MVP"
SAMPLE_RATE = 16_000
CHANNELS = 1
RECORD_SECONDS = 4
MODEL_PATH = Path("models/vosk-model-small-ru-0.22")
MAX_LOG_LINES = 30

# STT (Faster-Whisper)
FASTER_WHISPER_MODEL = "small"
FASTER_WHISPER_DEVICE = "cpu"
FASTER_WHISPER_COMPUTE_TYPE = "int8"
FASTER_WHISPER_BEAM_SIZE = 5
FASTER_WHISPER_LANGUAGE = None

# Local LLM command parsing (Ollama)
USE_LOCAL_LLM = True
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "hf.co/Qwen/Qwen3-0.6B-GGUF:latest"
OLLAMA_TIMEOUT_S = 8
OLLAMA_NUM_PREDICT = 366

# Desktop catalog injected into LLM prompt to improve fuzzy app matching.
LLM_DESKTOP_PROMPT_MAX_CHARS = 24_000
