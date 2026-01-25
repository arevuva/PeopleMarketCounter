import time
from typing import List, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

MODEL_NAME = "yolov8n.pt"
PERSON_CLASS_ID = 0


class PeopleDetector:
    def __init__(self, model_name: str = MODEL_NAME) -> None:
        start_time = time.time()
        self.model = YOLO(model_name)
        self.load_time_ms = int((time.time() - start_time) * 1000)

    def detect_people(
        self,
        image: np.ndarray,
        conf: float = 0.25,
    ) -> Tuple[int, List[dict]]:
        if image is None:
            return 0, []

        results = self.model.predict(image, conf=conf, verbose=False)
        boxes_out: List[dict] = []
        count = 0
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls.item())
                if cls_id != PERSON_CLASS_ID:
                    continue
                xyxy = box.xyxy[0].tolist()
                score = float(box.conf.item())
                boxes_out.append(
                    {
                        "x1": float(xyxy[0]),
                        "y1": float(xyxy[1]),
                        "x2": float(xyxy[2]),
                        "y2": float(xyxy[3]),
                        "conf": score,
                    }
                )
                count += 1
        return count, boxes_out

    def draw_boxes(self, image: np.ndarray, boxes: List[dict]) -> np.ndarray:
        if image is None:
            return image
        output = image.copy()
        for box in boxes:
            x1, y1, x2, y2 = (
                int(box["x1"]),
                int(box["y1"]),
                int(box["x2"]),
                int(box["y2"]),
            )
            conf = box.get("conf", 0.0)
            cv2.rectangle(output, (x1, y1), (x2, y2), (46, 204, 113), 2)
            label = f"person {conf:.2f}"
            cv2.putText(
                output,
                label,
                (x1, max(y1 - 6, 0)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (46, 204, 113),
                2,
            )
        return output


def encode_image_to_jpeg(image: np.ndarray) -> bytes:
    if image is None:
        return b""
    success, buffer = cv2.imencode(".jpg", image)
    if not success:
        return b""
    return buffer.tobytes()


detector = PeopleDetector()


def decode_image_bytes(data: bytes) -> np.ndarray:
    array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    return image
