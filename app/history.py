import json
import os
import threading
import time
from io import BytesIO
from typing import List

from openpyxl import Workbook

HISTORY_PATH = os.path.join("data", "history.json")
_lock = threading.Lock()


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)


def _read_history() -> List[dict]:
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def list_history() -> List[dict]:
    with _lock:
        return _read_history()


def append_history(entry: dict, limit: int = 500) -> None:
    _ensure_dir()
    with _lock:
        data = _read_history()
        entry["timestamp"] = entry.get("timestamp") or time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        data.append(entry)
        if limit and len(data) > limit:
            data = data[-limit:]
        with open(HISTORY_PATH, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)


def export_history_xlsx() -> bytes:
    data = list_history()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "History"
    headers = ["Тип", "Файл", "Длительность, сек", "Количество людей", "Время"]
    sheet.append(headers)
    for item in data:
        sheet.append(
            [
                item.get("type") or "",
                item.get("filename") or "",
                item.get("duration_seconds") if item.get("duration_seconds") is not None else "",
                item.get("count") if item.get("count") is not None else "",
                item.get("timestamp") or "",
            ]
        )
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
