from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import config
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
    window = MainWindow(recognizer, executor)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
