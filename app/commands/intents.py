from __future__ import annotations

from dataclasses import dataclass

from app.utils.text import normalize_text


@dataclass(slots=True)
class ParsedCommand:
    action: str
    payload: str | None
    raw_text: str


OPEN_NOTEPAD = {
    "открой блокнот",
    "запусти блокнот",
    "открыть блокнот",
}
OPEN_CALCULATOR = {
    "открой калькулятор",
    "запусти калькулятор",
    "открыть калькулятор",
}
OPEN_BROWSER = {
    "открой браузер",
    "запусти браузер",
    "открыть браузер",
}
OPEN_GOOGLE = {
    "открой google",
    "открой гугл",
    "запусти google",
    "запусти гугл",
}
OPEN_YOUTUBE = {
    "открой youtube",
    "открой ютуб",
    "запусти youtube",
    "запусти ютуб",
}

SEARCH_PREFIXES = (
    "найди в гугле ",
    "поищи в гугле ",
    "найди в google ",
    "поищи в google ",
)

TYPE_PREFIXES = (
    "напечатай ",
    "введи текст ",
)

WEBSITE_PREFIXES = (
    "открой сайт ",
    "открыть сайт ",
    "зайди на сайт ",
    "перейди на сайт ",
    "открой страницу ",
    "зайди на ",
    "перейди на ",
)


def parse_command(text: str) -> ParsedCommand | None:
    normalized = normalize_text(text)
    if not normalized:
        return None

    if normalized in OPEN_NOTEPAD:
        return ParsedCommand(action="open_notepad", payload=None, raw_text=text)
    if normalized in OPEN_CALCULATOR:
        return ParsedCommand(action="open_calculator", payload=None, raw_text=text)
    if normalized in OPEN_BROWSER:
        return ParsedCommand(action="open_browser", payload=None, raw_text=text)
    if normalized in OPEN_GOOGLE:
        return ParsedCommand(action="open_google", payload=None, raw_text=text)
    if normalized in OPEN_YOUTUBE:
        return ParsedCommand(action="open_youtube", payload=None, raw_text=text)

    for prefix in SEARCH_PREFIXES:
        if normalized.startswith(prefix):
            query = normalized[len(prefix) :].strip()
            if query:
                return ParsedCommand(action="search_google", payload=query, raw_text=text)
            return None

    for prefix in TYPE_PREFIXES:
        if normalized.startswith(prefix):
            to_type = normalized[len(prefix) :].strip()
            if to_type:
                return ParsedCommand(action="type_text", payload=to_type, raw_text=text)
            return None

    for prefix in WEBSITE_PREFIXES:
        if normalized.startswith(prefix):
            website = normalized[len(prefix) :].strip(" .,!?:;\"'()[]{}")
            if website:
                return ParsedCommand(action="open_website", payload=website, raw_text=text)
            return None

    return None
