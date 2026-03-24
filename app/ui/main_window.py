from __future__ import annotations

from datetime import datetime
from time import perf_counter

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.audio.recorder import record_audio
from app.commands.intents import parse_command
from app.commands.llm_parser import LocalLLMCommandParser
from app.executor.safe_executor import CommandExecutor
from app.observability.langflow_telemetry import (
    CommandTelemetryEvent,
    LangflowTelemetry,
    NoOpTelemetry,
)
from app.stt.faster_whisper_recognizer import FasterWhisperSpeechRecognizer


class ListenWorker(QObject):
    progress = Signal(str)
    done = Signal(str, str)
    complete = Signal()

    def __init__(
        self,
        recognizer: FasterWhisperSpeechRecognizer,
        executor: CommandExecutor,
        llm_parser: LocalLLMCommandParser | None = None,
        telemetry: LangflowTelemetry | NoOpTelemetry | None = None,
    ) -> None:
        super().__init__()
        self._recognizer = recognizer
        self._executor = executor
        self._llm_parser = llm_parser
        self._telemetry = telemetry or NoOpTelemetry()

    @Slot()
    def run(self) -> None:
        started = perf_counter()
        recognized_text = ""
        result_text = ""
        llm_raw_response: str | None = None
        llm_error: str | None = None
        parse_source = "none"
        parsed_action: str | None = None
        parsed_payload: str | None = None

        try:
            self.progress.emit("Слушаю голос...")
            pcm_audio = record_audio(
                duration_s=config.RECORD_SECONDS,
                sample_rate=config.SAMPLE_RATE,
                channels=config.CHANNELS,
            )

            self.progress.emit("Транскрибирую голос...")
            recognized_text = self._recognizer.recognize(pcm_audio)

            if not recognized_text:
                result_text = "Не удалось распознать команду. Попробуйте еще раз."
            else:
                parsed = parse_command(recognized_text)
                if parsed is not None:
                    parse_source = "rule"

                if (
                    parsed is None
                    and self._llm_parser is not None
                    and not self._llm_parser.is_website_request(recognized_text)
                ):
                    parsed = self._llm_parser.match_desktop_from_transcription(recognized_text)
                    if parsed is not None:
                        parse_source = "desktop_fuzzy"

                if parsed is None and self._llm_parser is not None:
                    self.progress.emit("Обрабатываю текст через LLM...")
                    llm_result = self._llm_parser.parse(recognized_text)
                    parsed = llm_result.command
                    llm_error = llm_result.error
                    llm_raw_response = llm_result.raw_response
                    parse_source = llm_result.source

                if parsed is None:
                    base_message = (
                        "Команда не распознана или не поддерживается в MVP. "
                        "Попробуйте одну из разрешенных команд."
                    )
                    if llm_error:
                        result_text = f"{base_message} (LLM: {llm_error})"
                    else:
                        result_text = base_message
                else:
                    parsed_action = parsed.action
                    parsed_payload = parsed.payload
                    result_text = self._executor.execute(parsed)
        except Exception as exc:
            result_text = f"Ошибка: {exc}"

        duration_ms = int((perf_counter() - started) * 1000)
        success = bool(parsed_action) and not result_text.startswith("Ошибка")
        self._telemetry.log(
            CommandTelemetryEvent(
                timestamp_utc=datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                duration_ms=duration_ms,
                recognized_text=recognized_text,
                parsed_action=parsed_action,
                parsed_payload=parsed_payload,
                parse_source=parse_source,
                llm_error=llm_error,
                llm_raw_response=llm_raw_response,
                execution_result=result_text,
                success=success,
            )
        )

        self.done.emit(recognized_text, result_text)
        self.complete.emit()


class MainWindow(QMainWindow):
    def __init__(
        self,
        recognizer: FasterWhisperSpeechRecognizer,
        executor: CommandExecutor,
        llm_parser: LocalLLMCommandParser | None = None,
        telemetry: LangflowTelemetry | NoOpTelemetry | None = None,
    ) -> None:
        super().__init__()
        self._recognizer = recognizer
        self._executor = executor
        self._llm_parser = llm_parser
        self._telemetry = telemetry
        self._thread: QThread | None = None
        self._worker: ListenWorker | None = None
        self._startup_animation: QPropertyAnimation | None = None
        self._listen_pulse: QPropertyAnimation | None = None
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._tick_listening_status)
        self._base_listening_status = ""
        self._status_tick = 0

        self.setWindowTitle(config.APP_TITLE)
        self.resize(860, 560)

        self._build_ui()
        self._apply_theme()
        self._setup_animations()
        self._bind_shortcut()
        self._set_status("Готово")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._startup_animation is not None and self.windowOpacity() < 1.0:
            self._startup_animation.start()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("Root")
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header_card = QFrame()
        header_card.setObjectName("CardHeader")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(20, 16, 20, 16)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        self.title_label = QLabel("Voice Assistant")
        self.title_label.setObjectName("Title")
        self.subtitle_label = QLabel("Минималистичный интерфейс управления голосом")
        self.subtitle_label.setObjectName("Subtitle")
        title_col.addWidget(self.title_label)
        title_col.addWidget(self.subtitle_label)

        self.status_label = QLabel("Готово")
        self.status_label.setObjectName("StatusPill")

        header_layout.addLayout(title_col)
        header_layout.addStretch(1)
        header_layout.addWidget(self.status_label)
        layout.addWidget(header_card)

        self.recognized_card = QFrame()
        self.recognized_card.setObjectName("Card")
        recognized_layout = QVBoxLayout(self.recognized_card)
        recognized_layout.setContentsMargins(20, 16, 20, 16)
        recognized_layout.setSpacing(8)
        recognized_title = QLabel("Распознанная фраза")
        recognized_title.setObjectName("SectionLabel")
        self.recognized_line = QLineEdit()
        self.recognized_line.setObjectName("InputView")
        self.recognized_line.setReadOnly(True)
        self.recognized_line.setPlaceholderText("Здесь появится текст после записи")
        recognized_layout.addWidget(recognized_title)
        recognized_layout.addWidget(self.recognized_line)
        layout.addWidget(self.recognized_card)

        self.result_card = QFrame()
        self.result_card.setObjectName("Card")
        result_layout = QVBoxLayout(self.result_card)
        result_layout.setContentsMargins(20, 16, 20, 16)
        result_layout.setSpacing(8)
        result_title = QLabel("Результат")
        result_title.setObjectName("SectionLabel")
        self.result_line = QLineEdit()
        self.result_line.setObjectName("InputView")
        self.result_line.setReadOnly(True)
        self.result_line.setPlaceholderText("Результат выполнения команды")
        result_layout.addWidget(result_title)
        result_layout.addWidget(self.result_line)
        layout.addWidget(self.result_card)

        controls_card = QFrame()
        controls_card.setObjectName("Card")
        controls_layout = QHBoxLayout(controls_card)
        controls_layout.setContentsMargins(20, 16, 20, 16)
        controls_layout.setSpacing(14)

        self.listen_button = QPushButton("Начать прослушивание")
        self.listen_button.setObjectName("ListenButton")
        self.listen_button.clicked.connect(self.on_listen_clicked)
        self.listen_hint = QLabel("Ctrl+Space для быстрого старта")
        self.listen_hint.setObjectName("Hint")

        controls_layout.addWidget(self.listen_button)
        controls_layout.addWidget(self.listen_hint)
        controls_layout.addStretch(1)
        layout.addWidget(controls_card)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QWidget#Root {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f4f5f7,
                    stop:1 #ece9e5);
            }
            QFrame#CardHeader, QFrame#Card {
                background-color: rgba(255, 255, 255, 228);
                border: 1px solid rgba(20, 20, 20, 24);
                border-radius: 16px;
            }
            QLabel#Title {
                color: #1b1d22;
                font-size: 30px;
                font-weight: 700;
            }
            QLabel#Subtitle {
                color: #5f646d;
                font-size: 13px;
            }
            QLabel#SectionLabel {
                color: #4f5560;
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.4px;
            }
            QLabel#StatusPill {
                background: #eef5ec;
                color: #2d6e34;
                border-radius: 14px;
                border: 1px solid #d2e7cf;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QLineEdit#InputView {
                background-color: rgba(255, 255, 255, 245);
                border: 1px solid #d5dbe3;
                border-radius: 10px;
                color: #1d2025;
                padding: 10px 12px;
                font-size: 14px;
            }
            QPushButton#ListenButton {
                background-color: #202328;
                color: #ffffff;
                border: none;
                border-radius: 12px;
                padding: 10px 16px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton#ListenButton:hover {
                background-color: #2a2f36;
            }
            QPushButton#ListenButton:disabled {
                background-color: #8a9099;
                color: #f4f4f4;
            }
            QLabel#Hint {
                color: #6d7380;
                font-size: 12px;
            }
            """
        )

    def _setup_animations(self) -> None:
        self.setWindowOpacity(0.0)
        self._startup_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._startup_animation.setDuration(550)
        self._startup_animation.setStartValue(0.0)
        self._startup_animation.setEndValue(1.0)
        self._startup_animation.setEasingCurve(QEasingCurve.OutCubic)

        self._listen_opacity = QGraphicsOpacityEffect(self.listen_button)
        self.listen_button.setGraphicsEffect(self._listen_opacity)
        self._listen_opacity.setOpacity(1.0)

        self._listen_pulse = QPropertyAnimation(self._listen_opacity, b"opacity", self)
        self._listen_pulse.setDuration(900)
        self._listen_pulse.setStartValue(0.6)
        self._listen_pulse.setEndValue(1.0)
        self._listen_pulse.setEasingCurve(QEasingCurve.InOutQuad)
        self._listen_pulse.setLoopCount(-1)

    def _animate_feedback_cards(self) -> None:
        recognized_effect = QGraphicsOpacityEffect(self.recognized_card)
        self.recognized_card.setGraphicsEffect(recognized_effect)
        recognized_anim = QPropertyAnimation(recognized_effect, b"opacity", self)
        recognized_anim.setDuration(420)
        recognized_anim.setStartValue(0.3)
        recognized_anim.setEndValue(1.0)
        recognized_anim.setEasingCurve(QEasingCurve.OutCubic)

        result_effect = QGraphicsOpacityEffect(self.result_card)
        self.result_card.setGraphicsEffect(result_effect)
        result_anim = QPropertyAnimation(result_effect, b"opacity", self)
        result_anim.setDuration(450)
        result_anim.setStartValue(0.35)
        result_anim.setEndValue(1.0)
        result_anim.setEasingCurve(QEasingCurve.OutCubic)

        sequence = QSequentialAnimationGroup(self)
        sequence.addAnimation(recognized_anim)
        sequence.addAnimation(result_anim)
        sequence.start(QSequentialAnimationGroup.DeleteWhenStopped)

    def _set_listening_state(self, active: bool) -> None:
        if active:
            self.listen_button.setEnabled(False)
            self.listen_button.setText("Слушаю...")
            if self._listen_pulse is not None:
                self._listen_pulse.start()
            self._base_listening_status = f"Слушаю ({config.RECORD_SECONDS} сек)"
            self._status_tick = 0
            self._status_timer.start(280)
        else:
            if self._listen_pulse is not None:
                self._listen_pulse.stop()
            self._status_timer.stop()
            if hasattr(self, "_listen_opacity"):
                self._listen_opacity.setOpacity(1.0)
            self.listen_button.setEnabled(True)
            self.listen_button.setText("Начать прослушивание")

    def _tick_listening_status(self) -> None:
        dots = "." * (self._status_tick % 4)
        self._set_status(f"{self._base_listening_status}{dots}")
        self._status_tick += 1

    def _bind_shortcut(self) -> None:
        self.listen_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.listen_shortcut.activated.connect(self.on_listen_clicked)

    @Slot()
    def on_listen_clicked(self) -> None:
        if self._thread is not None:
            return

        self._set_listening_state(True)

        self._thread = QThread(self)
        self._worker = ListenWorker(
            self._recognizer,
            self._executor,
            self._llm_parser,
            telemetry=self._telemetry,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.done.connect(self._on_worker_done)
        self._worker.complete.connect(self._thread.quit)

        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    @Slot(str)
    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        if text.startswith("Ошибка"):
            self.status_label.setStyleSheet(
                "background: #fff3f1; color: #9d2f22; border: 1px solid #f2c7c1; "
                "border-radius: 14px; padding: 6px 12px; font-size: 12px; font-weight: 600;"
            )
        elif text.startswith("Слушаю"):
            self.status_label.setStyleSheet(
                "background: #f5f0e8; color: #8a5218; border: 1px solid #ecd8be; "
                "border-radius: 14px; padding: 6px 12px; font-size: 12px; font-weight: 600;"
            )
        else:
            self.status_label.setStyleSheet(
                "background: #eef5ec; color: #2d6e34; border: 1px solid #d2e7cf; "
                "border-radius: 14px; padding: 6px 12px; font-size: 12px; font-weight: 600;"
            )

    @Slot(str)
    def _on_worker_progress(self, text: str) -> None:
        listening_stage = text.startswith("Слушаю")
        if listening_stage:
            if not self._status_timer.isActive():
                self._base_listening_status = f"Слушаю голос ({config.RECORD_SECONDS} сек)"
                self._status_tick = 0
                self._status_timer.start(280)
            self.listen_button.setText("Слушаю...")
            if self._listen_pulse is not None and self._listen_pulse.state() != QPropertyAnimation.Running:
                self._listen_pulse.start()
        else:
            self._status_timer.stop()
            if self._listen_pulse is not None:
                self._listen_pulse.stop()
            if hasattr(self, "_listen_opacity"):
                self._listen_opacity.setOpacity(1.0)

            if text.startswith("Транскрибирую"):
                self.listen_button.setText("Транскрибация...")
            elif "LLM" in text:
                self.listen_button.setText("Обработка LLM...")
            else:
                self.listen_button.setText("Обработка...")

        self._set_status(text)

    @Slot(str, str)
    def _on_worker_done(self, recognized: str, result: str) -> None:
        self.recognized_line.setText(recognized)
        self.result_line.setText(result)
        self._animate_feedback_cards()
        if result.startswith("Ошибка"):
            self._set_status("Ошибка выполнения")
        else:
            self._set_status("Готово")

    @Slot()
    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()

        self._worker = None
        self._thread = None

        self._set_listening_state(False)
