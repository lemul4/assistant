from __future__ import annotations

import subprocess
import webbrowser
from urllib.parse import quote_plus

from app.commands.intents import ParsedCommand


class CommandExecutor:
    """Executes only commands from a fixed whitelist."""

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

        if action == "type_text" and command.payload:
            return (
                "Команда 'напечатай' распознана. В MVP это заглушка: "
                f"{command.payload}"
            )

        return "Команда не входит в белый список действий"
