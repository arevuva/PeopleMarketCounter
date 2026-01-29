import asyncio
import logging
from io import BytesIO
import time
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AnyUrl, BaseModel, conint, confloat

import base64
import cv2
import yt_dlp

from app.detector import decode_image_bytes, detector, encode_image_to_jpeg
from app.history import append_history, export_history_xlsx, list_history
from app.jobs import job_manager, save_upload_to_tempfile
from app.stream_log import list_stream_log

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
STREAM_LOG_LIMIT = 200

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="People Counter")

app.mount("/static", StaticFiles(directory="web"), name="static")


class StreamRequest(BaseModel):
    url: AnyUrl
    fps: confloat(gt=0, le=30) = 5.0
    max_seconds: conint(ge=0) = 0


def _resolve_youtube_url(url: str) -> Optional[str]:
    def _extract(opts: dict) -> Optional[dict]:
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                return ydl.extract_info(url, download=False)
            except yt_dlp.utils.DownloadError:
                return None

    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    info = _extract({**base_opts, "format": "best[protocol^=http]"})
    if not info:
        info = _extract(base_opts)
    if not info:
        return None
    if "url" in info:
        return info["url"]
    formats = info.get("formats") or []
    for fmt in formats:
        if fmt.get("protocol", "").startswith("http") and fmt.get("url"):
            return fmt["url"]
    return None


def _get_video_duration(file_path: str) -> Optional[float]:
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return None
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
    cap.release()
    if fps <= 0:
        return None
    return round(frames / fps, 2)




@app.on_event("startup")
async def startup_event() -> None:
    job_manager.set_loop(asyncio.get_running_loop())


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("web/index.html")


@app.post("/api/process/image")
async def process_image(
    image: UploadFile = File(...),
    conf: Optional[confloat(ge=0, le=1)] = 0.25,
) -> JSONResponse:
    data = await image.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    decoded = decode_image_bytes(data)
    if decoded is None:
        raise HTTPException(status_code=400, detail="Invalid image")
    start = time.time()
    count, boxes = detector.detect_people(decoded, conf=float(conf))
    annotated = detector.draw_boxes(decoded, boxes)
    image_bytes = encode_image_to_jpeg(annotated)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8") if image_bytes else ""
    elapsed_ms = int((time.time() - start) * 1000)
    append_history(
        {
            "type": "image",
            "filename": image.filename or "image",
            "duration_seconds": None,
            "count": count,
        }
    )
    return JSONResponse(
        {
            "count": count,
            "boxes": boxes,
            "time_ms": elapsed_ms,
            "image_b64": image_b64,
        }
    )


@app.post("/api/process/video")
async def process_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    fps: Optional[confloat(gt=0, le=30)] = 5.0,
    max_seconds: Optional[conint(ge=0)] = 0,
) -> JSONResponse:
    try:
        file_path = save_upload_to_tempfile(video, max_bytes=MAX_UPLOAD_BYTES)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    job = job_manager.create_job()
    job.source_type = "video"
    job.source_name = video.filename or "video"
    job.duration_seconds = _get_video_duration(file_path)
    background_tasks.add_task(
        job_manager.process_video_file,
        job.job_id,
        file_path,
        float(fps or 5.0),
        int(max_seconds or 0),
    )
    return JSONResponse({"job_id": job.job_id})


@app.post("/api/process/stream")
async def process_stream(payload: StreamRequest) -> JSONResponse:
    host = payload.url.host or ""
    if "youtube.com" in host or "youtu.be" in host:
        resolved = _resolve_youtube_url(str(payload.url))
        if not resolved:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Failed to resolve YouTube stream URL. "
                    "Provide a direct stream URL (RTSP/MJPEG/HLS) instead."
                ),
            )
        stream_url = resolved
    else:
        stream_url = str(payload.url)
    job = job_manager.create_job()
    job_manager.process_stream(
        job.job_id,
        stream_url,
        float(payload.fps),
        int(payload.max_seconds),
    )
    return JSONResponse(
        {
            "job_id": job.job_id,
            "mjpeg_url": f"/api/job/{job.job_id}/mjpeg",
        }
    )


@app.get("/api/job/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(
        {
            "job_id": job.job_id,
            "status": job.status,
            "current_count": job.current_count,
            "max_count": job.max_count,
            "frames": job.frames,
            "error": job.error,
            "video_url": f"/api/job/{job_id}/video" if job.output_path else None,
        }
    )


@app.get("/api/history")
async def get_history() -> JSONResponse:
    return JSONResponse(list_history())


@app.get("/api/stream-log")
async def get_stream_log(
    limit: conint(ge=1, le=1000) = STREAM_LOG_LIMIT,
) -> JSONResponse:
    items = list_stream_log()
    if limit and len(items) > limit:
        items = items[-int(limit) :]
    return JSONResponse(items)


@app.get("/api/history/excel")
async def get_history_excel() -> StreamingResponse:
    content = export_history_xlsx()
    filename = "history.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.get("/api/job/{job_id}/video")
async def get_job_video(job_id: str) -> FileResponse:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done" or not job.output_path:
        raise HTTPException(status_code=404, detail="Processed video not available")
    media_type = job.output_media_type or "video/mp4"
    filename = job.output_filename or f"{job_id}.mp4"
    return FileResponse(job.output_path, media_type=media_type, filename=filename)


@app.get("/api/job/{job_id}/mjpeg")
async def get_job_mjpeg(job_id: str) -> StreamingResponse:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    boundary = "frame"

    def stream() -> bytes:
        last_id = 0
        while True:
            current = job_manager.get_job(job_id)
            if not current:
                break
            if current.last_frame_id != last_id and current.last_frame:
                last_id = current.last_frame_id
                frame = current.last_frame
                headers = (
                    f"--{boundary}\r\n"
                    "Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame)}\r\n\r\n"
                ).encode("utf-8")
                yield headers + frame + b"\r\n"
            if current.status in ("done", "error"):
                time.sleep(0.1)
                if current.last_frame_id == last_id:
                    break
            time.sleep(0.1)

    return StreamingResponse(
        stream(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
    )


@app.websocket("/ws/job/{job_id}")
async def websocket_job(websocket: WebSocket, job_id: str) -> None:
    job = job_manager.get_job(job_id)
    if not job:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Job not found"})
        await websocket.close()
        return
    await job_manager.register(job_id, websocket)
    await websocket.send_json(
        {
            "type": "status",
            "status": job.status,
            "current_count": job.current_count,
            "max_count": job.max_count,
            "done": job.status == "done",
        }
    )
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        job_manager.unregister(job_id, websocket)
