"""
Pretrained Deep Face Detection Module for IBVAP.
Uses OpenCV YuNet Deep Neural Network (cv2.FaceDetectorYN) for high-precision,
scale-invariant, and rotation-invariant face detection with 5-point facial landmark localization.
Maintains Haar Cascade as an automated fallback.
"""

import os
import cv2
import time
import urllib.request
import logging
from typing import List, Tuple, Optional, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)

YUNET_MODEL_FILENAME = "face_detection_yunet_2023mar.onnx"
YUNET_DOWNLOAD_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"


class FaceDetector:
    """
    High-Precision Deep Face Detector.
    Leverages OpenCV YuNet ONNX model for real-time face localization
    and 5 facial landmarks for alignment.
    """

    def __init__(self, min_confidence: float = 0.50, min_face_size: Tuple[int, int] = (30, 30)):
        self.min_confidence = min_confidence
        self.min_face_size = min_face_size

        project_model_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))
        os.makedirs(project_model_dir, exist_ok=True)

        # 1. Initialize YuNet DNN Face Detector
        self.yunet: Optional[cv2.FaceDetectorYN] = None
        self._init_yunet_model(project_model_dir)

        # 2. Initialize Haar Cascade Fallback
        self.face_cascade: Optional[cv2.CascadeClassifier] = None
        self._init_haar_cascade(project_model_dir)

    def _init_yunet_model(self, model_dir: str):
        """Locate or download the official OpenCV YuNet ONNX model."""
        yunet_path = os.path.join(model_dir, YUNET_MODEL_FILENAME)
        yunet_alt_path = os.path.join(model_dir, "face_detection_yunet.onnx")

        chosen_path = None
        for p in [yunet_path, yunet_alt_path]:
            if os.path.exists(p) and os.path.getsize(p) > 50000:
                chosen_path = p
                break

        if not chosen_path:
            try:
                logger.info("Downloading official OpenCV YuNet face detection ONNX model...")
                req = urllib.request.Request(YUNET_DOWNLOAD_URL, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                    if len(data) > 50000:
                        with open(yunet_path, "wb") as f:
                            f.write(data)
                        chosen_path = yunet_path
                        logger.info(f"YuNet model downloaded successfully ({len(data)} bytes).")
            except Exception as e:
                logger.warning(f"Failed to download YuNet model: {e}")

        if chosen_path and os.path.exists(chosen_path) and os.path.getsize(chosen_path) > 50000:
            try:
                self.yunet = cv2.FaceDetectorYN.create(
                    chosen_path,
                    "",
                    (320, 320),
                    score_threshold=self.min_confidence,
                    nms_threshold=0.3
                )
                logger.info(f"YuNet Deep Face Detector initialized from {chosen_path}")
            except Exception as e:
                logger.error(f"Error creating YuNet detector: {e}")
                self.yunet = None

    def _init_haar_cascade(self, model_dir: str):
        """Initialize Haar cascade as a backup detector."""
        local_cascade = os.path.join(model_dir, "haarcascade_frontalface_default.xml")
        if not os.path.exists(local_cascade):
            cv2_data_path = getattr(cv2, "data", None)
            if cv2_data_path and hasattr(cv2_data_path, "haarcascades"):
                cv2_cascade = os.path.join(cv2_data_path.haarcascades, "haarcascade_frontalface_default.xml")
                if os.path.exists(cv2_cascade):
                    local_cascade = cv2_cascade

        if not os.path.exists(local_cascade):
            try:
                url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
                urllib.request.urlretrieve(url, local_cascade)
            except Exception as e:
                logger.warning(f"Haar cascade download error: {e}")

        if os.path.exists(local_cascade):
            self.face_cascade = cv2.CascadeClassifier(local_cascade)
            logger.info(f"Haar Cascade fallback loaded from {local_cascade}")

    def detect_faces_with_landmarks(
        self,
        frame: np.ndarray,
        roi: Optional[Tuple[int, int, int, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Detect faces in frame or ROI, returning bounding box, confidence, and 15-element raw landmark array.
        Returns: list of {"box": (x1, y1, x2, y2), "raw_face": np.ndarray, "confidence": float}
        """
        if frame is None or frame.size == 0:
            return []

        h, w = frame.shape[:2]
        rx1, ry1, rx2, ry2 = (0, 0, w, h) if roi is None else roi
        rx1, ry1 = max(0, int(rx1)), max(0, int(ry1))
        rx2, ry2 = min(w, int(rx2)), min(h, int(ry2))

        rw, rh = rx2 - rx1, ry2 - ry1
        if rw < self.min_face_size[0] or rh < self.min_face_size[1]:
            return []

        # If ROI is human body, check top 85% where face is located
        if roi is not None:
            upper_h = max(self.min_face_size[1], int(rh * 0.85))
            upper_ry2 = min(h, ry1 + upper_h)
            crop = frame[ry1:upper_ry2, rx1:rx2]
        else:
            crop = frame

        if crop.size == 0:
            return []

        ch, cw = crop.shape[:2]
        results: List[Dict[str, Any]] = []

        if self.yunet is not None:
            try:
                self.yunet.setInputSize((cw, ch))
                _, faces = self.yunet.detect(crop)
                if faces is not None and len(faces) > 0:
                    for f in faces:
                        score = float(f[14])
                        if score < self.min_confidence:
                            continue

                        fx, fy, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
                        x1 = max(0, rx1 + fx)
                        y1 = max(0, ry1 + fy)
                        x2 = min(w, rx1 + fx + fw)
                        y2 = min(h, ry1 + fy + fh)

                        if (x2 - x1) >= self.min_face_size[0] and (y2 - y1) >= self.min_face_size[1]:
                            # Map landmark coords to global frame
                            global_raw = f.copy()
                            global_raw[0] += rx1
                            global_raw[1] += ry1
                            for k in range(4, 14, 2):
                                global_raw[k] += rx1
                                global_raw[k + 1] += ry1

                            results.append({
                                "box": (x1, y1, x2, y2),
                                "raw_face": global_raw,
                                "confidence": score
                            })
                    if results:
                        return results
            except Exception as e:
                logger.debug(f"YuNet detect error: {e}")

        # Fallback Haar cascade
        if self.face_cascade is not None:
            try:
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                gray = cv2.equalizeHist(gray)
                faces = self.face_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=self.min_face_size
                )
                for (fx, fy, fw, fh) in faces:
                    x1 = max(0, rx1 + int(fx))
                    y1 = max(0, ry1 + int(fy))
                    x2 = min(w, rx1 + int(fx + fw))
                    y2 = min(h, ry1 + int(fy + fh))
                    results.append({
                        "box": (x1, y1, x2, y2),
                        "raw_face": None,
                        "confidence": 0.70
                    })
            except Exception as e:
                logger.debug(f"Haar fallback detect error: {e}")

        return results

    def detect_in_roi(self, frame: np.ndarray, roi: Tuple[int, int, int, int]) -> List[Tuple[int, int, int, int]]:
        """Detect faces within person ROI. Returns list of (x1, y1, x2, y2) bounding boxes."""
        items = self.detect_faces_with_landmarks(frame, roi=roi)
        return [item["box"] for item in items]

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect faces across entire frame. Returns list of (x1, y1, x2, y2) bounding boxes."""
        items = self.detect_faces_with_landmarks(frame, roi=None)
        return [item["box"] for item in items]
