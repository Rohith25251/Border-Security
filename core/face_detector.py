"""
Pretrained Face Detection Module.
Detects faces in video frames or within human bounding box crops using OpenCV's built-in detectors.
Strictly detection only — NO identity recognition or biometric matching.
"""

import os
import cv2
import time
import logging
from typing import List, Tuple, Optional
import numpy as np
from core.models import Detection, AlertEvent

logger = logging.getLogger(__name__)


class FaceDetector:
    """
    OpenCV-based Face Detector.
    Supports Haar Cascade and DNN YuNet face detection without external model training.
    """

    def __init__(self, min_confidence: float = 0.5, min_face_size: Tuple[int, int] = (25, 25)):
        self.min_confidence = min_confidence
        self.min_face_size = min_face_size
        
        # Resolve Haar cascade path
        project_model_dir = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "models")
        os.makedirs(project_model_dir, exist_ok=True)
        local_cascade = os.path.join(project_model_dir, "haarcascade_frontalface_default.xml")

        if not os.path.exists(local_cascade):
            # Check cv2.data fallback
            cv2_data_path = getattr(cv2, "data", None)
            if cv2_data_path and hasattr(cv2_data_path, "haarcascades"):
                cv2_cascade = os.path.join(cv2_data_path.haarcascades, "haarcascade_frontalface_default.xml")
                if os.path.exists(cv2_cascade):
                    local_cascade = cv2_cascade

        if not os.path.exists(local_cascade):
            import urllib.request
            logger.info("Downloading official OpenCV Haar cascade XML...")
            url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
            urllib.request.urlretrieve(url, local_cascade)

        self.face_cascade = cv2.CascadeClassifier(local_cascade)
        logger.info(f"Loaded OpenCV Face Detector from {local_cascade}")

    def detect_in_roi(self, frame: np.ndarray, roi: Tuple[int, int, int, int]) -> List[Tuple[int, int, int, int]]:
        """
        Detect faces within a specific Region of Interest (e.g., human bounding box).
        Returns list of absolute bounding boxes (x1, y1, x2, y2).
        """
        if frame is None:
            return []

        rx1, ry1, rx2, ry2 = roi
        h, w = frame.shape[:2]
        rx1, ry1 = max(0, rx1), max(0, ry1)
        rx2, ry2 = min(w, rx2), min(h, ry2)

        if rx2 - rx1 < self.min_face_size[0] or ry2 - ry1 < self.min_face_size[1]:
            return []

        # Focus primarily on the upper half of the human box where faces reside
        upper_ry2 = ry1 + int((ry2 - ry1) * 0.55)
        crop = frame[ry1:upper_ry2, rx1:rx2]
        if crop.size == 0:
            return []

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=self.min_face_size
        )

        global_faces = []
        for (fx, fy, fw, fh) in faces:
            global_faces.append((rx1 + fx, ry1 + fy, rx1 + fx + fw, ry1 + fy + fh))

        return global_faces

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Run face detection across the full frame."""
        if frame is None:
            return []

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.15,
            minNeighbors=5,
            minSize=self.min_face_size
        )

        return [(x, y, x + w, y + h) for (x, y, w, h) in faces]
