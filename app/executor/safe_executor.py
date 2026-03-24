from __future__ import annotations

import os
import re
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

from app.commands.intents import ParsedCommand


class CommandExecutor:
    """Executes supported actions from parser and local LLM."""

    def execute(self, command: ParsedCommand) -> str:
        action = command.action

        if action == "open_notepad":
            subprocess.Popen(["notepad.exe"])
            return "Открыт Блокнот"

        if action == "open_calculator":
            subprocess.Popen(["calc.exe"])
            return "Открыт Калькулятор"

        if action == "open_browser":
            webbrowser.open("https://www.google.com")
            return "Открыт браузер по умолчанию"

        if action == "open_google":
            webbrowser.open("https://www.google.com")
            return "Открыт Google"

        if action == "open_youtube":
            webbrowser.open("https://www.youtube.com")
            return "Открыт YouTube"

        if action == "search_google" and command.payload:
            query = quote_plus(command.payload)
            webbrowser.open(f"https://www.google.com/search?q={query}")
            return f"Поиск в Google: {command.payload}"

        if action == "open_website" and command.payload:
            url = self._normalize_url(command.payload)
            webbrowser.open(url)
            return f"Открыт сайт: {url}"

        if action == "open_app" and command.payload:
            opened_path = self._open_desktop_match(command.payload)
            if opened_path is not None:
                return f"Открыт файл/ярлык: {opened_path.name}"

            # Fallback: try to run the app name directly if it exists in PATH.
            try:
                subprocess.Popen([command.payload])
                return f"Запущено приложение: {command.payload}"
            except OSError:
                return (
                    "Не нашел совпадений на рабочем столе и не смог запустить "
                    f"приложение напрямую: {command.payload}"
                )

        if action == "type_text" and command.payload:
            return (
                "Команда 'напечатай' распознана. В MVP это заглушка: "
                f"{command.payload}"
            )

        return "Команда не входит в белый список действий"

    def _normalize_url(self, raw_value: str) -> str:
        candidate = raw_value.strip()
        if not candidate:
            return "https://www.google.com"

        if candidate.startswith(("http://", "https://")):
            return candidate

        # If model gave a domain without scheme, add https.
        if "." in candidate and " " not in candidate:
            return f"https://{candidate}"

        # As a last resort, interpret payload as search query.
        return f"https://www.google.com/search?q={quote_plus(candidate)}"

    def _open_desktop_match(self, app_name_en: str) -> Path | None:
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            return None

        raw_query = app_name_en.strip()
        query = re.sub(r"\s+", " ", raw_query.lower())
        if not query:
            return None

        # If payload is a relative path from desktop catalog, open it directly.
        direct_rel = Path(raw_query.replace("/", os.sep).replace("\\", os.sep))
        direct_path = (desktop / direct_rel).resolve()
        try:
            direct_path.relative_to(desktop.resolve())
        except ValueError:
            direct_path = Path("")

        if direct_path and direct_path.exists():
            os.startfile(str(direct_path))
            return direct_path

        candidates: list[tuple[int, int, Path]] = []
        for path in desktop.rglob("*"):
            if not path.is_file() and not path.is_dir():
                continue

            name = path.name.lower()
            stem = path.stem.lower()

            if query not in name and query not in stem:
                continue

            score = 1
            if stem == query or name == query:
                score = 4
            elif stem.startswith(query) or name.startswith(query):
                score = 3
            elif query in stem:
                score = 2

            extension_priority = {
                ".lnk": 0,
                ".url": 1,
                ".exe": 2,
                ".bat": 3,
                ".cmd": 3,
                ".msi": 4,
            }.get(path.suffix.lower(), 9)

            candidates.append((score, -extension_priority, path))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best_path = candidates[0][2]
        os.startfile(str(best_path))
        return best_path
