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

from app.detector import detector, encode_image_to_jpeg
from app.history import append_history


@dataclass
class JobState:
    job_id: str
    status: str = "idle"
    current_count: int = 0
    max_count: int = 0
    frames: int = 0
    error: Optional[str] = None
    source_name: Optional[str] = None
    source_type: Optional[str] = None
    duration_seconds: Optional[float] = None
    output_path: Optional[str] = None
    output_media_type: Optional[str] = None
    output_filename: Optional[str] = None
    last_frame: Optional[bytes] = None
    last_frame_id: int = 0
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
        cap = self._open_capture(source, is_file)

        if cap is None or not cap.isOpened():
            scheme = source.split("://")[0].lower() if "://" in source else "unknown"
            state.status = "error"
            state.error = (
                "Failed to open video source. "
                f"URL scheme: {scheme}. "
                "Check the URL/credentials and network access."
            )
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
        writer = None
        last_boxes = []
        last_count = 0
        frame_skip = 0
        frame_duration = 0.0

        if is_file:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            output_fps = source_fps if source_fps > 0 else (fps if fps > 0 else 5.0)
            if source_fps > 0:
                frame_duration = 1.0 / source_fps
            if source_fps > 0 and fps > 0:
                frame_skip = max(1, int(round(source_fps / fps)))
            else:
                frame_skip = 1
            if width > 0 and height > 0:
                candidates = [
                    (".mp4", "avc1", "video/mp4"),
                    (".mp4", "H264", "video/mp4"),
                    (".mp4", "X264", "video/mp4"),
                    (".webm", "VP80", "video/webm"),
                    (".mp4", "mp4v", "video/mp4"),
                ]
                for suffix, fourcc_tag, media_type in candidates:
                    output_path = tempfile.NamedTemporaryFile(delete=False, suffix=suffix).name
                    fourcc = cv2.VideoWriter_fourcc(*fourcc_tag)
                    writer = cv2.VideoWriter(output_path, fourcc, output_fps, (width, height))
                    if writer.isOpened():
                        state.output_path = output_path
                        state.output_media_type = media_type
                        state.output_filename = f"{job_id}{suffix}"
                        break
                    writer.release()
                    writer = None

        try:
            while True:
                if max_seconds and (time.time() - start_time) > max_seconds:
                    break
                success, frame = cap.read()
                if not success:
                    break
                now = time.time()
                frame_index += 1
                state.frames = frame_index

                if is_file:
                    do_detect = frame_skip <= 1 or frame_index % frame_skip == 0
                else:
                    do_detect = interval == 0.0 or (now - last_emit) >= interval
                if do_detect:
                    last_emit = now
                    last_count, last_boxes = detector.detect_people(frame)
                    state.current_count = last_count
                    state.max_count = max(state.max_count, last_count)

                annotated = detector.draw_boxes(frame, last_boxes) if last_boxes else frame
                if writer:
                    writer.write(annotated)

                frame_bytes = encode_image_to_jpeg(annotated)
                if frame_bytes:
                    state.last_frame = frame_bytes
                    state.last_frame_id += 1

                if do_detect:
                    payload = {
                        "type": "frame",
                        "frame_index": frame_index,
                        "count": last_count,
                        "max_count": state.max_count,
                        "timestamp_ms": int(now * 1000),
                        "done": False,
                    }
                    self._schedule_broadcast(job_id, payload)
                if is_file and frame_duration > 0:
                    expected_time = start_time + frame_index * frame_duration
                    delay = expected_time - time.time()
                    if delay > 0:
                        time.sleep(delay)
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
            if writer:
                writer.release()
            if is_file:
                try:
                    os.remove(source)
                except OSError:
                    pass

        state.status = "done" if state.status != "error" else state.status
        if is_file and state.source_type == "video" and state.status == "done":
            append_history(
                {
                    "type": "video",
                    "filename": state.source_name or "video",
                    "duration_seconds": state.duration_seconds,
                    "count": state.max_count,
                }
            )
        done_payload = {
            "type": "done",
            "max_count": state.max_count,
            "frames": state.frames,
            "done": True,
        }
        if state.output_path:
            done_payload["video_url"] = f"/api/job/{job_id}/video"
        self._schedule_broadcast(job_id, done_payload)

    def _open_capture(
        self,
        source: str,
        is_file: bool,
        open_timeout_ms: Optional[int] = None,
        ffmpeg_timeout_us: Optional[int] = None,
    ) -> Optional[cv2.VideoCapture]:
        if not is_file and source.lower().startswith("rtsp://"):
            timeout_us = ffmpeg_timeout_us if ffmpeg_timeout_us else 5000000
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                f"rtsp_transport;tcp|stimeout;{timeout_us}"
            )
        if is_file:
            backends = [getattr(cv2, "CAP_FFMPEG", None), getattr(cv2, "CAP_ANY", None)]
        else:
            backends = [
                getattr(cv2, "CAP_FFMPEG", None),
                getattr(cv2, "CAP_GSTREAMER", None),
                getattr(cv2, "CAP_MSMF", None),
                getattr(cv2, "CAP_ANY", None),
            ]
        for backend in backends:
            if backend is None:
                continue
            cap = cv2.VideoCapture(source, backend)
            if not is_file:
                timeout_ms = open_timeout_ms if open_timeout_ms else 5000
                if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
                if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)
            if cap.isOpened():
                return cap
            cap.release()
        cap = cv2.VideoCapture(source)
        if cap.isOpened():
            return cap
        cap.release()
        return None


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
