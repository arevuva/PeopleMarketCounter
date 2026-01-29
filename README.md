# Подсчет людей поосетителей в магазине

FastAPI + YOLOv8 app for counting people on images, videos, or live streams.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Windows setup

PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

CMD:

```bat
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open: http://localhost:8000

Для запуска стрима на linux используйте python stream/ec_stream.py

