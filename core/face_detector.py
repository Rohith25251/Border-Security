"""
Pretrained Face Detection Module.
Detects faces in video frames or within human bounding box crops using OpenCV's built-in detectors.
Configured with robust scale factors and neighbor thresholds to eliminate background texture false positives.
"""

import os
import cv2
import time
import logging
from typing import List, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)


class FaceDetector:
    """
    OpenCV-based Face Detector.
    Supports Haar Cascade face detection without external model training.
    """

    def __init__(self, min_confidence: float = 0.5, min_face_size: Tuple[int, int] = (45, 45)):
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

        rw, rh = rx2 - rx1, ry2 - ry1
        if rw < self.min_face_size[0] or rh < self.min_face_size[1]:
            return []

        # Focus on the upper portion of the person where the face is located
        upper_ry2 = ry1 + int(rh * 0.70)
        crop = frame[ry1:upper_ry2, rx1:rx2]
        if crop.size == 0:
            return []

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        # Apply histogram equalization to stabilize lighting
        gray = cv2.equalizeHist(gray)

        min_w = max(self.min_face_size[0], int(rw * 0.25))
        min_h = max(self.min_face_size[1], int(rh * 0.20))

        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=6,
            minSize=(min_w, min_h)
        )

        global_faces = []
        for (fx, fy, fw, fh) in faces:
            global_faces.append((rx1 + fx, ry1 + fy, rx1 + fx + fw, ry1 + fy + fh))

        return global_faces

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Run high-precision face detection across the full frame.
        Uses stricter thresholds (minSize=70x70, minNeighbors=8) to prevent false positives on background grids.
        """
        if frame is None or frame.size == 0:
            return []

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.12,
            minNeighbors=8,
            minSize=(70, 70)
        )

        return [(x, y, x + w, y + h) for (x, y, w, h) in faces]
