from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request

from app import config


@dataclass(slots=True)
class CommandTelemetryEvent:
    timestamp_utc: str
    duration_ms: int
    recognized_text: str
    parsed_action: str | None
    parsed_payload: str | None
    parse_source: str
    llm_error: str | None
    llm_raw_response: str | None
    execution_result: str
    success: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "duration_ms": self.duration_ms,
            "recognized_text": self.recognized_text,
            "parsed_action": self.parsed_action,
            "parsed_payload": self.parsed_payload,
            "parse_source": self.parse_source,
            "llm_error": self.llm_error,
            "llm_raw_response": self.llm_raw_response,
            "execution_result": self.execution_result,
            "success": self.success,
        }


class LangflowTelemetry:
    def __init__(
        self,
        enabled: bool,
        endpoint_url: str | None,
        api_key: str | None,
        flow_id: str | None,
        timeout_s: int,
        events_file: Path,
        stats_file: Path,
    ) -> None:
        self._enabled = enabled
        self._endpoint_url = endpoint_url.strip() if endpoint_url else None
        self._api_key = api_key.strip() if api_key else None
        self._flow_id = flow_id.strip() if flow_id else None
        self._timeout_s = timeout_s
        self._events_file = events_file
        self._stats_file = stats_file
        self._lock = threading.Lock()

        self._events_file.parent.mkdir(parents=True, exist_ok=True)
        self._stats_file.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: CommandTelemetryEvent) -> None:
        if not self._enabled:
            return

        data = event.as_dict()
        with self._lock:
            self._append_event_line(data)
            self._update_stats(data)

        if self._endpoint_url:
            self._push_to_langflow(data)

    def _append_event_line(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        with self._events_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _update_stats(self, payload: dict[str, Any]) -> None:
        stats = {
            "updated_at_utc": _now_utc_iso(),
            "total_commands": 0,
            "successful_commands": 0,
            "failed_commands": 0,
            "by_action": {},
            "by_parse_source": {},
            "average_duration_ms": 0,
            "total_duration_ms": 0,
        }

        if self._stats_file.exists():
            try:
                loaded = json.loads(self._stats_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    stats.update(loaded)
            except Exception:
                # If stats file is corrupted, rebuild counters from current event stream.
                pass

        total_commands = int(stats.get("total_commands", 0)) + 1
        successful_commands = int(stats.get("successful_commands", 0))
        failed_commands = int(stats.get("failed_commands", 0))
        total_duration_ms = int(stats.get("total_duration_ms", 0)) + int(payload["duration_ms"])

        if payload.get("success"):
            successful_commands += 1
        else:
            failed_commands += 1

        action = str(payload.get("parsed_action") or "unparsed")
        source = str(payload.get("parse_source") or "unknown")

        by_action = stats.get("by_action")
        if not isinstance(by_action, dict):
            by_action = {}
        by_action[action] = int(by_action.get(action, 0)) + 1

        by_parse_source = stats.get("by_parse_source")
        if not isinstance(by_parse_source, dict):
            by_parse_source = {}
        by_parse_source[source] = int(by_parse_source.get(source, 0)) + 1

        stats["updated_at_utc"] = _now_utc_iso()
        stats["total_commands"] = total_commands
        stats["successful_commands"] = successful_commands
        stats["failed_commands"] = failed_commands
        stats["by_action"] = by_action
        stats["by_parse_source"] = by_parse_source
        stats["total_duration_ms"] = total_duration_ms
        stats["average_duration_ms"] = int(total_duration_ms / max(total_commands, 1))

        self._stats_file.write_text(
            json.dumps(stats, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _push_to_langflow(self, payload: dict[str, Any]) -> None:
        body: dict[str, Any] = {
            "event": payload,
        }
        if self._flow_id:
            body["flow_id"] = self._flow_id

        payload_bytes = json.dumps(body, ensure_ascii=True).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = request.Request(
            self._endpoint_url,
            data=payload_bytes,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._timeout_s) as response:
                response.read(1)
        except Exception as exc:
            print(f"[LangflowTelemetry] Failed to send event: {exc}")


class NoOpTelemetry:
    def log(self, event: CommandTelemetryEvent) -> None:
        _ = event


def build_default_langflow_telemetry() -> LangflowTelemetry | NoOpTelemetry:
    if not config.LANGFLOW_ENABLED:
        return NoOpTelemetry()

    events_file = Path(config.LANGFLOW_EVENTS_FILE)
    stats_file = Path(config.LANGFLOW_STATS_FILE)

    return LangflowTelemetry(
        enabled=True,
        endpoint_url=config.LANGFLOW_ENDPOINT_URL,
        api_key=config.LANGFLOW_API_KEY,
        flow_id=config.LANGFLOW_FLOW_ID,
        timeout_s=config.LANGFLOW_TIMEOUT_S,
        events_file=events_file,
        stats_file=stats_file,
    )


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
