import asyncio
import time
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl, conint, confloat

import base64

from app.detector import decode_image_bytes, detector, encode_image_to_jpeg
from app.jobs import job_manager, save_upload_to_tempfile

MAX_UPLOAD_BYTES = 200 * 1024 * 1024

app = FastAPI(title="People Counter")

app.mount("/static", StaticFiles(directory="web"), name="static")


class StreamRequest(BaseModel):
    url: HttpUrl
    fps: confloat(gt=0, le=30) = 5.0
    max_seconds: conint(ge=0) = 0


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
    job = job_manager.create_job()
    job_manager.process_stream(
        job.job_id,
        str(payload.url),
        float(payload.fps),
        int(payload.max_seconds),
    )
    return JSONResponse({"job_id": job.job_id})


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
