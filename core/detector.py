"""
Pretrained YOLOv8 Object Detection Module.
Detects humans (class 0) and vehicles (classes 2, 3, 5, 7) without model training.
Optimized for ultra-low latency real-time surveillance inference.
"""

import os
import logging
from typing import List, Tuple, Optional
import numpy as np
import torch
from ultralytics import YOLO
from core.models import Detection

logger = logging.getLogger(__name__)

# Optimize PyTorch CPU parallelism for maximum throughput
try:
    cpu_count = os.cpu_count() or 4
    torch.set_num_threads(max(2, min(cpu_count, 8)))
except Exception:
    pass

# COCO Class Mapping
# 0: person
# 2: car, 3: motorcycle, 5: bus, 7: truck
# 34: baseball bat, 43: knife, 76: scissors (Harmful / Weapons)
# 24: backpack, 26: handbag, 28: suitcase, 39: bottle, 77: cell phone (Luggage / Items)
COCO_HUMAN_CLASS = 0
COCO_VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
COCO_HARMFUL_CLASSES = {34: "baseball bat", 43: "knife", 76: "scissors"}
COCO_LUGGAGE_CLASSES = {24: "backpack", 26: "handbag", 28: "suitcase", 39: "bottle", 77: "cell phone"}

TARGET_CLASSES = (
    [COCO_HUMAN_CLASS] + 
    list(COCO_VEHICLE_CLASSES.keys()) + 
    list(COCO_HARMFUL_CLASSES.keys()) + 
    list(COCO_LUGGAGE_CLASSES.keys())
)


class ObjectDetector:
    """
    YOLOv8 wrapper configured for Border Surveillance object classes
    (Humans, Vehicles, Harmful Weapons/Tools, and Suspicious Luggage).
    Uses official pretrained COCO weights (yolov8n.pt or yolov8s.pt).
    """

    def __init__(self, model_name: str = "yolov8n.pt", conf_threshold: float = 0.25, device: str = "auto"):
        self.model_name = model_name
        self.conf_threshold = conf_threshold
        
        # Auto-detect optimal device
        if device == "auto" or device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        
        logger.info(f"Loading pretrained YOLOv8 detector '{model_name}' on device '{self.device}'...")
        self.model = YOLO(model_name)
        
        # Warmup model with dummy frame for instant first-frame response
        try:
            dummy = np.zeros((480, 640, 3), dtype=np.uint8)
            self.model.predict(source=dummy, conf=self.conf_threshold, classes=TARGET_CLASSES, imgsz=480, verbose=False, device=self.device)
            logger.info("YOLOv8 detector loaded and warmed up successfully.")
        except Exception as e:
            logger.warning(f"Detector warmup: {e}")

    @torch.inference_mode()
    def detect(self, frame: np.ndarray, imgsz: int = 480) -> List[Detection]:
        """
        Run low-latency inference on the frame and extract human, vehicle & object detections.
        """
        if frame is None or frame.size == 0:
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
                category = COCO_VEHICLE_CLASSES[cls_id]
            elif cls_id in COCO_HARMFUL_CLASSES:
                category = COCO_HARMFUL_CLASSES[cls_id]
            elif cls_id in COCO_LUGGAGE_CLASSES:
                category = COCO_LUGGAGE_CLASSES[cls_id]
            else:
                continue

            detections.append(Detection(
                box=(x1, y1, x2, y2),
                confidence=conf,
                class_id=cls_id,
                class_name=category
            ))

        return detections


