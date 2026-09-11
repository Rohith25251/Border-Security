"""
Automatic Number Plate Recognition (ANPR) Module.
Utilizes pretrained EasyOCR to extract alphanumeric license plate characters from vehicle crops.
"""

import re
import cv2
import logging
from typing import Optional, Tuple, List
import numpy as np
import easyocr
from core.models import AlertEvent, TrackedObject

logger = logging.getLogger(__name__)

# Basic alphanumeric plate regex filter (typically 4-10 alphanumeric characters)
PLATE_REGEX = re.compile(r'^[A-Z0-9]{4,10}$')


class ANPRReader:
    """
    ANPR Pipeline for vehicle bounding boxes using pretrained EasyOCR.
    """

    def __init__(self, languages: List[str] = None, gpu: bool = False):
        if languages is None:
            languages = ['en']
        logger.info(f"Initializing EasyOCR Reader for languages: {languages} (gpu={gpu})...")
        # verbose=False avoids unicode progress bar charmap errors on Windows consoles
        self.reader = easyocr.Reader(languages, gpu=gpu, verbose=False)
        logger.info("EasyOCR Reader initialized.")

    def extract_plate(self, frame: np.ndarray, vehicle_box: Tuple[int, int, int, int]) -> Optional[Tuple[str, float]]:
        """
        Preprocesses vehicle crop and runs OCR to detect potential license plate text.
        Returns: (plate_text, confidence) or None.
        """
        if frame is None:
            return None

        vx1, vy1, vx2, vy2 = vehicle_box
        h, w = frame.shape[:2]
        vx1, vy1 = max(0, vx1), max(0, vy1)
        vx2, vy2 = min(w, vx2), min(h, vy2)

        if vx2 - vx1 < 50 or vy2 - vy1 < 30:
            return None

        # Number plates are typically located in the lower 60% of the vehicle
        crop_y1 = vy1 + int((vy2 - vy1) * 0.40)
        crop = frame[crop_y1:vy2, vx1:vx2]

        if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 40:
            return None

        # Preprocessing: grayscale, bilateral filter, contrast enhancement
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        filtered = cv2.bilateralFilter(gray, 11, 17, 17)

        # Run OCR
        try:
            results = self.reader.readtext(filtered, detail=1, paragraph=False)
        except Exception as e:
            logger.error(f"EasyOCR error: {e}")
            return None

        best_plate = None
        best_conf = 0.0

        for bbox, text, conf in results:
            cleaned = re.sub(r'[^A-Za-z0-9]', '', text).upper()
            if 4 <= len(cleaned) <= 10 and conf > 0.30:
                if conf > best_conf:
                    best_plate = cleaned
                    best_conf = conf

        if best_plate:
            return best_plate, float(best_conf)

        return None
