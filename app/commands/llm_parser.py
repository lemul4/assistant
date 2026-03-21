from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from app import config
from app.commands.intents import ParsedCommand


SYSTEM_PROMPT = (
    "Ты преобразуешь русскую голосовую фразу в одну команду из белого списка. "
    "Верни только JSON. "
    'Формат: {"action": string|null, "payload": string|null}. '
    "Разрешенные action: open_notepad, open_calculator, open_browser, "
    "open_google, open_youtube, search_google, type_text. "
    'Если команда не подходит, верни {"action": null, "payload": null}. '
    "Никаких пояснений. Никакого текста вне JSON. /no_think"
)


ALLOWED_ACTIONS = {
    "open_notepad",
    "open_calculator",
    "open_browser",
    "open_google",
    "open_youtube",
    "search_google",
    "type_text",
}


@dataclass(slots=True)
class LLMParseResult:
    command: ParsedCommand | None
    source: str
    error: str | None = None
    raw_response: str | None = None


class LocalLLMCommandParser:
    def __init__(
        self,
        url: str,
        model: str,
        timeout_s: int = 8,
        num_predict: int = 48,
    ) -> None:
        self._url = url
        self._model = model
        self._timeout_s = timeout_s
        self._num_predict = num_predict

    def parse(self, text: str) -> LLMParseResult:
        user_prompt = f'Фраза пользователя: "{text}"'

        try:
            response = requests.post(
                self._url,
                json={
                    "model": self._model,
                    "system": SYSTEM_PROMPT,
                    "prompt": user_prompt,
                    "format": "json",
                    "think": False,
                    "stream": False,
                    "keep_alive": "15m",
                    "options": {
                        "num_predict": self._num_predict,
                        "temperature": 0,
                    },
                },
                timeout=self._timeout_s,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return LLMParseResult(
                command=None,
                source="llm",
                error=str(exc),
                raw_response=None,
            )

        raw = str(payload.get("response", "")).strip()

        # Если Ollama вернул thinking отдельно, игнорируем его.
        # Для thinking-capable models reasoning может приходить в отдельном поле.
        data = _extract_json(raw)
        if data is None:
            return LLMParseResult(
                command=None,
                source="llm",
                error="LLM вернула невалидный JSON",
                raw_response=raw,
            )

        action = data.get("action")
        parsed_payload = data.get("payload")

        if action is None:
            return LLMParseResult(command=None, source="llm", raw_response=raw)

        if action not in ALLOWED_ACTIONS:
            return LLMParseResult(
                command=None,
                source="llm",
                error=f"Недопустимый action от LLM: {action}",
                raw_response=raw,
            )

        normalized_payload = None if parsed_payload is None else str(parsed_payload).strip() or None

        return LLMParseResult(
            command=ParsedCommand(action=action, payload=normalized_payload, raw_text=text),
            source="llm",
            raw_response=raw,
        )


def build_default_llm_parser() -> LocalLLMCommandParser:
    return LocalLLMCommandParser(
        url=config.OLLAMA_URL,
        model=config.OLLAMA_MODEL,
        timeout_s=config.OLLAMA_TIMEOUT_S,
        num_predict=config.OLLAMA_NUM_PREDICT,
    )


def _extract_json(raw: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, dict):
        return None

    return parsed