from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Iterator, Optional

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import uvicorn

DEFAULT_VIDEO_PATH = (
    Path(__file__).resolve().parents[1] / "videos" / "EC.webm"
).resolve()
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 9001
DEFAULT_JPEG_QUALITY = 80
DEFAULT_LOG_PATH = (Path(__file__).resolve().parent / "stream.log").resolve()


def _setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(log_path, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def _mjpeg_stream(
    video_path: Path,
    target_fps: Optional[float],
    jpeg_quality: int,
    boundary: str,
) -> Iterator[bytes]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Failed to open video source")
    try:
        native_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        fps = target_fps if target_fps and target_fps > 0 else native_fps
        if not fps or fps <= 0:
            fps = 25.0
        frame_interval = 1.0 / fps
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)]
        logger = logging.getLogger("ec_stream")
        last_log = time.monotonic()
        frames_sent = 0
        bytes_sent = 0

        while True:
            ok, frame = cap.read()
            if not ok:
                logger.warning("Video ended or read failed; restarting stream loop")
                cap.release()
                cap = cv2.VideoCapture(str(video_path))
                if not cap.isOpened():
                    time.sleep(0.5)
                continue
            ok, buffer = cv2.imencode(".jpg", frame, encode_params)
            if not ok:
                continue
            payload = buffer.tobytes()
            headers = (
                f"--{boundary}\r\n"
                "Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(payload)}\r\n\r\n"
            ).encode("utf-8")
            yield headers + payload + b"\r\n"
            frames_sent += 1
            bytes_sent += len(payload)
            now = time.monotonic()
            if now - last_log >= 10.0:
                elapsed = now - last_log
                avg_fps = frames_sent / elapsed if elapsed > 0 else 0.0
                avg_kbps = (bytes_sent * 8) / (elapsed * 1000) if elapsed > 0 else 0.0
                logger.info(
                    "Stream sample: frames=%d avg_fps=%.2f avg_kbps=%.1f",
                    frames_sent,
                    avg_fps,
                    avg_kbps,
                )
                last_log = now
                frames_sent = 0
                bytes_sent = 0
            if frame_interval > 0:
                time.sleep(frame_interval)
    finally:
        cap.release()


def create_app(
    video_path: Path = DEFAULT_VIDEO_PATH,
    target_fps: Optional[float] = None,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    log_path: Path = DEFAULT_LOG_PATH,
) -> FastAPI:
    app = FastAPI(title="Looped MJPEG stream")
    video_path = video_path.resolve()
    _setup_logging(log_path)
    boundary = "frame"

    @app.get("/")
    def root() -> dict:
        return {
            "status": "ok",
            "stream": "/ec.mjpg",
            "video": str(video_path),
        }

    @app.get("/ec.mjpg")
    def ec_stream() -> StreamingResponse:
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")
        test_cap = cv2.VideoCapture(str(video_path))
        if not test_cap.isOpened():
            test_cap.release()
            raise HTTPException(status_code=500, detail="Failed to open video source")
        test_cap.release()
        return StreamingResponse(
            _mjpeg_stream(video_path, target_fps, jpeg_quality, boundary),
            media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        )

    return app


app = create_app()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Serve a looped MJPEG stream from videos/EC.webm"
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=DEFAULT_VIDEO_PATH,
        help="Path to the source video file",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Target FPS for the MJPEG stream (defaults to video FPS)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=DEFAULT_JPEG_QUALITY,
        help="JPEG quality (1-100)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to the stream log file",
    )
    parser.add_argument("--host", type=str, default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    app = create_app(args.video, args.fps, args.quality, args.log_file)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
