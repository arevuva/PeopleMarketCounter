# Looped MJPEG stream

Этот сервер поднимает MJPEG-поток из зацикленного видео `videos/EC.webm`.

## Запуск

```bash
python stream/ec_stream.py
```

По умолчанию поток доступен по адресу:

- `http://localhost:9001/ec.mjpg`

## Использование в веб-приложении

1. Запустите основной backend:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
2. Запустите MJPEG-сервер (см. выше).
3. Откройте веб-интерфейс и введите URL потока:
   - `http://localhost:9001/ec.mjpg`

## Параметры

```bash
python stream/ec_stream.py --video videos/EC.webm --fps 10 --quality 80 --port 9001
```
