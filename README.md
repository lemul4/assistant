# Voice Command MVP (Windows)

MVP desktop-приложение на Python для голосовых команд в Windows.

## Возможности

- Кнопка Слушать и горячая клавиша Ctrl+Space
- Короткая запись с микрофона (по умолчанию 4 секунды)
- Офлайн-распознавание русской речи через Faster-Whisper (CPU, int8, beam size 5)
- Разбор команд через локальную LLM (Ollama через LangChain) с fallback на rule-based
- Безопасное выполнение только команд из белого списка
- Отображение статуса, распознанной фразы, результата и лога

## Поддерживаемые команды

- открой блокнот
- открой калькулятор
- открой браузер
- открой google
- открой youtube
- найди в гугле <запрос>
- напечатай <текст> (в MVP как заглушка: текст только показывается в UI)

## Установка

- Установите Python 3.11+.
- Для Faster-Whisper на Windows рекомендуется Python 3.11-3.12 (на 3.13 может отсутствовать совместимый `ctranslate2`).
- В корне проекта создайте виртуальное окружение и активируйте его. Примеры для Windows:

- PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

- cmd (Command Prompt):

```bat
python -m venv .venv
.\.venv\Scripts\activate.bat
```
- Установите зависимости:

```bash
python -m pip install -r requirements.txt
```

- Faster-Whisper загрузит модель автоматически при первом запуске.
- По умолчанию используется модель `small` на CPU с `compute_type=int8` и `beam_size=5`.
- Параметры можно менять в `app/config.py` через:
	- `FASTER_WHISPER_MODEL`
	- `FASTER_WHISPER_DEVICE`
	- `FASTER_WHISPER_COMPUTE_TYPE`
	- `FASTER_WHISPER_BEAM_SIZE`
	- `FASTER_WHISPER_LANGUAGE`

## Запуск

```bash
python main.py
```

## Локальная LLM (Ollama + LangChain)

Приложение умеет отправлять распознанную фразу в локальную модель и получать
из нее структуру команды в формате JSON. Выполнение все равно проходит через
белый список действий в `app/executor/safe_executor.py`.

По умолчанию используется:

- URL: `http://localhost:11434/api/generate`
- Model: `hf.co/Qwen/Qwen3-0.6B-GGUF:latest`

Параметры настраиваются в `app/config.py`:

- `USE_LOCAL_LLM`
- `OLLAMA_URL`
- `OLLAMA_MODEL`
- `OLLAMA_TIMEOUT_S`
- `OLLAMA_NUM_PREDICT`

Если локальная LLM недоступна или вернула невалидный ответ, приложение
автоматически использует существующий rule-based разбор команд.

## Примечание по безопасности

Приложение не выполняет произвольные shell-команды и использует только фиксированный белый список действий.

## Langflow: логи и статистика

В приложение добавлена телеметрия команд с локальной статистикой и опциональной отправкой событий в Langflow.

- Логи событий: `logs/langflow_events.jsonl`
- Сводная статистика: `logs/langflow_stats.json`

Настройки в `app/config.py`:

- `LANGFLOW_ENABLED` — включает/выключает телеметрию
- `LANGFLOW_ENDPOINT_URL` — URL webhook/API Langflow (если не задан, события пишутся только локально)
- `LANGFLOW_API_KEY` — токен для `Authorization: Bearer`
- `LANGFLOW_FLOW_ID` — идентификатор flow (опционально)
- `LANGFLOW_TIMEOUT_S` — таймаут отправки
- `LANGFLOW_EVENTS_FILE` и `LANGFLOW_STATS_FILE` — пути для локальных файлов
