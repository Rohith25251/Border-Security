"""
Pretrained YOLOv8 Object Detection Module.
Detects humans (class 0) and vehicles (classes 2, 3, 5, 7) without model training.
"""

import logging
from typing import List, Tuple, Optional
import numpy as np
from ultralytics import YOLO
from core.models import Detection

logger = logging.getLogger(__name__)

# COCO Class Mapping
# 0: person
# 2: car, 3: motorcycle, 5: bus, 7: truck
COCO_HUMAN_CLASS = 0
COCO_VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
TARGET_CLASSES = [COCO_HUMAN_CLASS] + list(COCO_VEHICLE_CLASSES.keys())


class ObjectDetector:
    """
    YOLOv8 wrapper configured for Border Surveillance object classes (Humans and Vehicles).
    Uses official pretrained COCO weights (yolov8n.pt or yolov8s.pt).
    """

    def __init__(self, model_name: str = "yolov8n.pt", conf_threshold: float = 0.40, device: str = "cpu"):
        self.model_name = model_name
        self.conf_threshold = conf_threshold
        self.device = device
        
        logger.info(f"Loading pretrained YOLOv8 detector '{model_name}' on device '{device}'...")
        self.model = YOLO(model_name)
        logger.info("YOLOv8 detector loaded successfully.")

    def detect(self, frame: np.ndarray, imgsz: int = 640) -> List[Detection]:
        """
        Run inference on the frame and extract human & vehicle detections.
        """
        if frame is None:
            return []

        # Run YOLO inference
        results = self.model.predict(
            source=frame,
            conf=self.conf_threshold,
            classes=TARGET_CLASSES,
            imgsz=imgsz,
            verbose=False,
            device=self.device
        )

        detections: List[Detection] = []

        if not results or len(results) == 0:
            return detections

        result = results[0]
        boxes = result.boxes

        if boxes is None or len(boxes) == 0:
            return detections

        for box in boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            xyxy = box.xyxy[0].cpu().numpy().astype(int)
            x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])

            if cls_id == COCO_HUMAN_CLASS:
                category = "human"
            elif cls_id in COCO_VEHICLE_CLASSES:
                category = "vehicle"
            else:
                continue

            detections.append(Detection(
                box=(x1, y1, x2, y2),
                confidence=conf,
                class_id=cls_id,
                class_name=category
            ))

        return detections
