import asyncio
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

import cv2
from fastapi import WebSocket

from app.detector import detector


@dataclass
class JobState:
    job_id: str
    status: str = "idle"
    current_count: int = 0
    max_count: int = 0
    frames: int = 0
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class JobManager:
    def __init__(self) -> None:
        self.jobs: Dict[str, JobState] = {}
        self.websockets: Dict[str, Set[WebSocket]] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def create_job(self) -> JobState:
        job_id = str(uuid.uuid4())
        state = JobState(job_id=job_id, status="processing")
        self.jobs[job_id] = state
        self.websockets[job_id] = set()
        return state

    def get_job(self, job_id: str) -> Optional[JobState]:
        return self.jobs.get(job_id)

    async def register(self, job_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.websockets.setdefault(job_id, set()).add(websocket)

    def unregister(self, job_id: str, websocket: WebSocket) -> None:
        if job_id in self.websockets:
            self.websockets[job_id].discard(websocket)

    async def broadcast(self, job_id: str, payload: dict) -> None:
        sockets = list(self.websockets.get(job_id, set()))
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                self.websockets[job_id].discard(ws)

    def _schedule_broadcast(self, job_id: str, payload: dict) -> None:
        if not self.loop:
            return
        asyncio.run_coroutine_threadsafe(
            self.broadcast(job_id, payload),
            self.loop,
        )

    def process_video_file(
        self,
        job_id: str,
        file_path: str,
        fps: float = 5.0,
        max_seconds: int = 0,
    ) -> None:
        thread = threading.Thread(
            target=self._process_capture,
            args=(job_id, file_path, fps, max_seconds, True),
            daemon=True,
        )
        thread.start()

    def process_stream(
        self,
        job_id: str,
        stream_url: str,
        fps: float = 5.0,
        max_seconds: int = 0,
    ) -> None:
        thread = threading.Thread(
            target=self._process_capture,
            args=(job_id, stream_url, fps, max_seconds, False),
            daemon=True,
        )
        thread.start()

    def _process_capture(
        self,
        job_id: str,
        source: str,
        fps: float,
        max_seconds: int,
        is_file: bool,
    ) -> None:
        state = self.jobs.get(job_id)
        if not state:
            return
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            state.status = "error"
            state.error = "Failed to open video source"
            self._schedule_broadcast(
                job_id,
                {
                    "type": "error",
                    "message": state.error,
                    "done": True,
                },
            )
            return

        start_time = time.time()
        last_emit = 0.0
        frame_index = 0
        interval = 1.0 / fps if fps > 0 else 0.0

        try:
            while True:
                if max_seconds and (time.time() - start_time) > max_seconds:
                    break
                success, frame = cap.read()
                if not success:
                    break
                now = time.time()
                if interval and (now - last_emit) < interval:
                    continue
                last_emit = now
                frame_index += 1

                count, _ = detector.detect_people(frame)
                state.current_count = count
                state.max_count = max(state.max_count, count)
                state.frames = frame_index

                payload = {
                    "type": "frame",
                    "frame_index": frame_index,
                    "count": count,
                    "max_count": state.max_count,
                    "timestamp_ms": int(now * 1000),
                    "done": False,
                }
                self._schedule_broadcast(job_id, payload)
        except Exception as exc:
            state.status = "error"
            state.error = str(exc)
            self._schedule_broadcast(
                job_id,
                {
                    "type": "error",
                    "message": state.error,
                    "done": True,
                },
            )
        finally:
            cap.release()
            if is_file:
                try:
                    os.remove(source)
                except OSError:
                    pass

        state.status = "done" if state.status != "error" else state.status
        done_payload = {
            "type": "done",
            "max_count": state.max_count,
            "frames": state.frames,
            "done": True,
        }
        self._schedule_broadcast(job_id, done_payload)


job_manager = JobManager()


def save_upload_to_tempfile(upload_file, max_bytes: int = 200 * 1024 * 1024) -> str:
    suffix = os.path.splitext(upload_file.filename or "video")[1]
    total = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                tmp.close()
                os.remove(tmp.name)
                raise ValueError("File size exceeds limit")
            tmp.write(chunk)
    return tmp.name
