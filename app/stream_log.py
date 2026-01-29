import json
import os
import threading
import time
from typing import List

STREAM_LOG_PATH = os.path.join("data", "stream_log.json")
_lock = threading.Lock()


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(STREAM_LOG_PATH), exist_ok=True)


def _read_stream_log() -> List[dict]:
    if not os.path.exists(STREAM_LOG_PATH):
        return []
    try:
        with open(STREAM_LOG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def list_stream_log() -> List[dict]:
    with _lock:
        return _read_stream_log()


def append_stream_log(entry: dict, limit: int = 1000) -> None:
    _ensure_dir()
    with _lock:
        data = _read_stream_log()
        entry["timestamp"] = entry.get("timestamp") or time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        data.append(entry)
        if limit and len(data) > limit:
            data = data[-limit:]
        with open(STREAM_LOG_PATH, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
