# People Counter MVP

A minimal FastAPI + YOLOv8 app for counting people on images, videos, or live streams.

## Features

- Upload image and get people count.
- Upload video and receive live updates over WebSocket.
- Provide RTSP/HTTP stream URL and receive live updates over WebSocket.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open: http://localhost:8000

## Notes

- The YOLOv8n model will be downloaded on first run.
- Upload size is limited to 200 MB in `app/main.py` and `app/jobs.py`.
