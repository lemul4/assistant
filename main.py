from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import config
from app.commands.llm_parser import build_default_llm_parser
from app.executor.safe_executor import CommandExecutor
from app.stt.vosk_recognizer import ModelNotFoundError, VoskSpeechRecognizer
from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    try:
        recognizer = VoskSpeechRecognizer(config.MODEL_PATH, config.SAMPLE_RATE)
    except ModelNotFoundError as exc:
        QMessageBox.critical(None, "Ошибка модели Vosk", str(exc))
        return 1
    except Exception as exc:
        QMessageBox.critical(None, "Ошибка инициализации", str(exc))
        return 1

    executor = CommandExecutor()
    llm_parser = build_default_llm_parser() if config.USE_LOCAL_LLM else None
    window = MainWindow(recognizer, executor, llm_parser=llm_parser)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
