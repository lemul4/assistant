from pathlib import Path

APP_TITLE = "Voice Command MVP"
SAMPLE_RATE = 16_000
CHANNELS = 1
RECORD_SECONDS = 4
MODEL_PATH = Path("models/vosk-model-small-ru-0.22")
MAX_LOG_LINES = 30

# Local LLM command parsing (Ollama)
USE_LOCAL_LLM = True
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "hf.co/Qwen/Qwen3-0.6B-GGUF:latest"
OLLAMA_TIMEOUT_S = 8
OLLAMA_NUM_PREDICT = 366
