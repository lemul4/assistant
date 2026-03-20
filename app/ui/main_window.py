from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.audio.recorder import record_audio
from app.commands.intents import parse_command
from app.executor.safe_executor import CommandExecutor
from app.stt.vosk_recognizer import VoskSpeechRecognizer


class ListenWorker(QObject):
    progress = Signal(str)
    done = Signal(str, str, str)
    complete = Signal()

    def __init__(self, recognizer: VoskSpeechRecognizer, executor: CommandExecutor) -> None:
        super().__init__()
        self._recognizer = recognizer
        self._executor = executor

    @Slot()
    def run(self) -> None:
        recognized_text = ""
        result_text = ""

        try:
            self.progress.emit("Записываю аудио...")
            pcm_audio = record_audio(
                duration_s=config.RECORD_SECONDS,
                sample_rate=config.SAMPLE_RATE,
                channels=config.CHANNELS,
            )

            self.progress.emit("Распознаю речь...")
            recognized_text = self._recognizer.recognize(pcm_audio)

            if not recognized_text:
                result_text = "Не удалось распознать команду. Попробуйте еще раз."
            else:
                parsed = parse_command(recognized_text)
                if parsed is None:
                    result_text = (
                        "Команда не распознана или не поддерживается в MVP. "
                        "Попробуйте одну из разрешенных команд."
                    )
                else:
                    result_text = self._executor.execute(parsed)
        except Exception as exc:
            result_text = f"Ошибка: {exc}"

        timestamp = datetime.now().strftime("%H:%M:%S")
        spoken = recognized_text if recognized_text else "<пусто>"
        log_line = f"[{timestamp}] {spoken} -> {result_text}"
        self.done.emit(recognized_text, result_text, log_line)
        self.complete.emit()


class MainWindow(QMainWindow):
    def __init__(self, recognizer: VoskSpeechRecognizer, executor: CommandExecutor) -> None:
        super().__init__()
        self._recognizer = recognizer
        self._executor = executor
        self._thread: QThread | None = None
        self._worker: ListenWorker | None = None

        self.setWindowTitle(config.APP_TITLE)
        self.resize(760, 520)

        self._build_ui()
        self._bind_shortcut()
        self._set_status("Готов к прослушиванию")

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        top_row = QHBoxLayout()

        self.listen_button = QPushButton("Слушать")
        self.listen_button.clicked.connect(self.on_listen_clicked)
        top_row.addWidget(self.listen_button)

        self.status_label = QLabel("Статус: -")
        top_row.addWidget(self.status_label)
        top_row.addStretch(1)

        layout.addLayout(top_row)

        layout.addWidget(QLabel("Последняя распознанная фраза:"))
        self.recognized_line = QLineEdit()
        self.recognized_line.setReadOnly(True)
        layout.addWidget(self.recognized_line)

        layout.addWidget(QLabel("Результат выполнения:"))
        self.result_line = QLineEdit()
        self.result_line.setReadOnly(True)
        layout.addWidget(self.result_line)

        layout.addWidget(QLabel("Лог последних команд:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

    def _bind_shortcut(self) -> None:
        self.listen_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.listen_shortcut.activated.connect(self.on_listen_clicked)

    @Slot()
    def on_listen_clicked(self) -> None:
        if self._thread is not None:
            return

        self.listen_button.setEnabled(False)
        self._set_status(f"Слушаю ({config.RECORD_SECONDS} сек)...")

        self._thread = QThread(self)
        self._worker = ListenWorker(self._recognizer, self._executor)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._set_status)
        self._worker.done.connect(self._on_worker_done)
        self._worker.complete.connect(self._thread.quit)

        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    @Slot(str)
    def _set_status(self, text: str) -> None:
        self.status_label.setText(f"Статус: {text}")

    @Slot(str, str, str)
    def _on_worker_done(self, recognized: str, result: str, log_line: str) -> None:
        self.recognized_line.setText(recognized)
        self.result_line.setText(result)
        self._append_log(log_line)

    @Slot()
    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()

        self._worker = None
        self._thread = None

        self.listen_button.setEnabled(True)
        self._set_status("Готов к прослушиванию")

    def _append_log(self, line: str) -> None:
        current_lines = [l for l in self.log_text.toPlainText().splitlines() if l.strip()]
        current_lines.append(line)
        current_lines = current_lines[-config.MAX_LOG_LINES :]
        self.log_text.setPlainText("\n".join(current_lines))
