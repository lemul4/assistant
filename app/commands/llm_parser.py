from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from dataclasses import dataclass
from pathlib import Path

import requests

from app import config
from app.commands.intents import ParsedCommand
from app.utils.text import normalize_text


SYSTEM_PROMPT = (
    "Ты преобразуешь русскую голосовую фразу в одну команду из белого списка. "
    "Верни только JSON. "
    'Формат: {"action": string|null, "payload": string|null}. '
    "Разрешенные action: open_notepad, open_calculator, open_browser, "
    "open_google, open_youtube, search_google, type_text, open_app, open_website. "
    "Правила: "
    "1) Для запуска приложения action=open_app, payload=название приложения на английском (например steam, discord, telegram). "
    "2) Для открытия сайта action=open_website, payload может быть полным URL (https://...) или названием сайта/бренда (например яндекс, yandex, github). "
    "3) Для open_app сначала пытайся сопоставить запрос с элементом из списка Desktop (он передается в prompt ниже), даже при ошибках транскрипции. "
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
    "open_app",
    "open_website",
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
        self._desktop_items = self._collect_desktop_items()
        self._desktop_catalog_prompt = self._build_desktop_catalog_prompt(self._desktop_items)
        self._log_desktop_items(self._desktop_items)

    def parse(self, text: str) -> LLMParseResult:
        user_prompt = self._build_user_prompt(text)

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

        # Safety net: if user clearly asked to open a website, do not allow open_app.
        if _looks_like_website_request(text) and action == "open_app":
            action = "open_website"
            website_payload = _extract_website_candidate_from_text(text) or normalized_payload
            normalized_payload = website_payload

        return LLMParseResult(
            command=ParsedCommand(action=action, payload=normalized_payload, raw_text=text),
            source="llm",
            raw_response=raw,
        )

    def is_website_request(self, text: str) -> bool:
        return _looks_like_website_request(text)

    def match_desktop_from_transcription(self, text: str) -> ParsedCommand | None:
        """Try to map transcription words to desktop entry stem and skip LLM if matched."""
        if not self._desktop_items:
            return None

        words = _extract_candidate_words(text)
        if not words:
            return None

        best_item: str | None = None
        best_score = 0.0

        for item in self._desktop_items:
            stem = Path(item).stem
            stem_norm = normalize_text(stem)
            if not stem_norm:
                continue

            for word in words:
                score = _fuzzy_match_score(word, stem_norm)
                if score > best_score:
                    best_item = item
                    best_score = score

        if best_item is None or best_score < 0.90:
            return None

        print(
            "[DesktopMatch] Транскрипция сопоставлена с Desktop: "
            f"{best_item} (score={best_score:.3f})"
        )
        return ParsedCommand(action="open_app", payload=best_item, raw_text=text)

    def _build_user_prompt(self, text: str) -> str:
        if not self._desktop_catalog_prompt:
            return f'Фраза пользователя: "{text}"'

        return (
            f'Фраза пользователя: "{text}"\n'
            "Ниже список элементов Desktop. Для команды open_app выбирай наиболее близкое совпадение из списка.\n"
            f"{self._desktop_catalog_prompt}"
        )

    def _collect_desktop_items(self) -> list[str]:
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            return []

        items: list[str] = []
        for path in desktop.rglob("*"):
            if not path.is_file() and not path.is_dir():
                continue

            try:
                rel = path.relative_to(desktop).as_posix()
            except ValueError:
                rel = path.name

            if rel:
                items.append(rel)

        items.sort(key=str.lower)
        return items

    def _build_desktop_catalog_prompt(self, items: list[str]) -> str:
        if not items:
            return ""

        lines = ["Список Desktop:"] + [f"- {item}" for item in items]
        catalog_text = "\n".join(lines)

        max_chars = max(500, int(config.LLM_DESKTOP_PROMPT_MAX_CHARS))
        if len(catalog_text) <= max_chars:
            return catalog_text

        trimmed = catalog_text[: max_chars - 64].rsplit("\n", 1)[0]
        return f"{trimmed}\n- ... (список обрезан по лимиту символов)"

    def _log_desktop_items(self, items: list[str]) -> None:
        print("[DesktopIndex] Старт индексации Desktop для LLM")
        if not items:
            print("[DesktopIndex] Desktop пуст или не найден")
            return

        print(f"[DesktopIndex] Найдено элементов: {len(items)}")
        print("[DesktopIndex] Полный список Desktop:")
        for idx, item in enumerate(items, start=1):
            print(f"[DesktopIndex] {idx:04d}. {item}")


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


_DESKTOP_MATCH_STOPWORDS = {
    "открой",
    "открыть",
    "запусти",
    "запустить",
    "включи",
    "пожалуйста",
    "приложение",
    "программу",
    "программа",
    "файл",
    "мне",
    "сайт",
    "страницу",
    "страница",
    "вебсайт",
    "веб",
}


_WEBSITE_PREFIX_PATTERNS = (
    re.compile(
        r"^(?:пожалуйста\s+)?(?:открой|открыть|зайди|перейди|запусти)\s+"
        r"(?:(?:на|в)\s+)?(?:сайт|страницу|страница|вебсайт|веб\s*сайт)\s+(.+)$"
    ),
    re.compile(r"^(?:пожалуйста\s+)?(?:зайди|перейди)\s+(?:на\s+)?(.+)$"),
)


def _looks_like_website_request(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False

    if any(pattern.match(normalized) for pattern in _WEBSITE_PREFIX_PATTERNS):
        return True

    website_words = {"сайт", "вебсайт", "страницу", "страница"}
    has_open_verb = any(word in normalized for word in ("открой", "открыть", "зайди", "перейди"))
    has_website_word = any(word in normalized for word in website_words)
    return has_open_verb and has_website_word


def _extract_website_candidate_from_text(text: str) -> str | None:
    normalized = normalize_text(text)
    if not normalized:
        return None

    for pattern in _WEBSITE_PREFIX_PATTERNS:
        match = pattern.match(normalized)
        if not match:
            continue
        value = match.group(1).strip(" .,!?:;\"'()[]{}")
        if value:
            return value

    return None


def _extract_candidate_words(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    words = re.findall(r"[a-zа-я0-9]+", normalized)
    result: list[str] = []
    for word in words:
        if len(word) < 3:
            continue
        if word in _DESKTOP_MATCH_STOPWORDS:
            continue
        result.append(word)

    # Keep unique words but preserve order.
    return list(dict.fromkeys(result))


_CYR_TO_LAT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

_LATIN_VOWELS = set("aeiouy")


def _to_latin(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if "а" <= ch <= "я" or ch == "ё":
            out.append(_CYR_TO_LAT.get(ch, ch))
        else:
            out.append(ch)
    return "".join(out)


def _phonetic_skeleton(text: str) -> str:
    letters = [ch for ch in text if "a" <= ch <= "z" or "0" <= ch <= "9"]
    if not letters:
        return ""

    no_vowels = [ch for ch in letters if ch not in _LATIN_VOWELS]
    base = no_vowels if no_vowels else letters

    compressed: list[str] = []
    for ch in base:
        if not compressed or compressed[-1] != ch:
            compressed.append(ch)
    return "".join(compressed)


def _fuzzy_match_score(word: str, stem: str) -> float:
    if word in stem:
        return 1.0

    word_lat = _to_latin(word)
    stem_lat = _to_latin(stem)

    if word_lat and word_lat in stem_lat:
        return 0.98

    direct_ratio = SequenceMatcher(None, word_lat, stem_lat).ratio()

    word_skel = _phonetic_skeleton(word_lat)
    stem_skel = _phonetic_skeleton(stem_lat)
    skeleton_ratio = 0.0
    if word_skel and stem_skel:
        skeleton_ratio = SequenceMatcher(None, word_skel, stem_skel).ratio()

    score = max(direct_ratio, skeleton_ratio * 0.97)
    if word_lat[:2] and stem_lat.startswith(word_lat[:2]):
        score = min(1.0, score + 0.03)

    return score