"""
Automatic Number Plate Recognition (ANPR) Module.
Utilizes pretrained EasyOCR with multi-scale contrast preprocessing, adaptive enhancement,
and multi-token license plate concatenation to extract vehicle license plates in both day and night conditions.
"""

import re
import cv2
import logging
from typing import Optional, Tuple, List
import numpy as np
import easyocr

logger = logging.getLogger(__name__)

# Basic alphanumeric plate regex filter (typically 3-12 alphanumeric characters)
PLATE_REGEX = re.compile(r'^[A-Z0-9]{3,12}$')
IGNORE_WORDS = {
    'POLICE', 'SECURITY', 'BORDER', 'STOP', 'HONDA', 'TOYOTA', 'FORD', 'TRUCK',
    'BUS', 'CAR', 'INDIA', 'STATE', 'HIGHWAY', 'SLOW', 'ZONE', 'CAUTION'
}


class ANPRReader:
    """
    High-Performance ANPR Pipeline for vehicle bounding boxes using pretrained EasyOCR.
    """

    def __init__(self, languages: List[str] = None, gpu: bool = False):
        if languages is None:
            languages = ['en']
        logger.info(f"Initializing EasyOCR Reader for languages: {languages} (gpu={gpu})...")
        self.reader = easyocr.Reader(languages, gpu=gpu, verbose=False)
        logger.info("EasyOCR Reader initialized.")

    def _preprocess_variants(self, img: np.ndarray) -> List[np.ndarray]:
        """Generate high-contrast variants (upscaled, CLAHE, thresholded) to maximize OCR recall."""
        h, w = img.shape[:2]
        if w == 0 or h == 0:
            return []

        # Upscale if small for better character stroke definition
        working_img = img
        if w < 320:
            scale = 320.0 / max(1, w)
            working_img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(working_img, cv2.COLOR_BGR2GRAY) if len(working_img.shape) == 3 else working_img

        # Contrast-limited adaptive histogram equalization for night / glare
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        norm = clahe.apply(gray)

        # Bilateral smoothing + adaptive threshold
        filtered = cv2.bilateralFilter(norm, 9, 25, 25)

        return [working_img, norm, filtered]

    def extract_plate(self, frame: np.ndarray, vehicle_box: Tuple[int, int, int, int]) -> Optional[Tuple[str, float]]:
        """
        Preprocesses vehicle crop, generates multi-scale enhanced variants, and runs OCR.
        Returns: (plate_text, confidence) or None.
        """
        if frame is None or frame.size == 0:
            return None

        vx1, vy1, vx2, vy2 = vehicle_box
        h, w = frame.shape[:2]
        vx1, vy1 = max(0, int(vx1)), max(0, int(vy1))
        vx2, vy2 = min(w, int(vx2)), min(h, int(vy2))

        vw, vh = vx2 - vx1, vy2 - vy1
        if vw < 30 or vh < 20:
            return None

        # Build candidate crops: Full vehicle crop and Lower 65% bumper region
        crops = [frame[vy1:vy2, vx1:vx2]]
        lower_y1 = vy1 + int(vh * 0.35)
        if vy2 - lower_y1 >= 20:
            crops.append(frame[lower_y1:vy2, vx1:vx2])

        best_plate: Optional[str] = None
        best_conf: float = 0.0

        for crop in crops:
            for variant in self._preprocess_variants(crop):
                try:
                    results = self.reader.readtext(variant, detail=1, paragraph=False)
                    if not results:
                        continue

                    # 1. Parse individual text tokens
                    tokens = []
                    for bbox, text, conf in results:
                        cleaned = re.sub(r'[^A-Za-z0-9]', '', str(text)).upper()
                        if cleaned and cleaned not in IGNORE_WORDS and len(cleaned) >= 2:
                            tokens.append((bbox, cleaned, float(conf)))
                            if 3 <= len(cleaned) <= 12 and conf > 0.20:
                                if any(c.isdigit() for c in cleaned):
                                    if conf > best_conf:
                                        best_plate = cleaned
                                        best_conf = float(conf)

                    # 2. Parse multi-token concatenated license plates (e.g. 'KA 01 AB 1234')
                    if len(tokens) >= 2:
                        sorted_tokens = sorted(tokens, key=lambda t: t[0][0][0])
                        combined = "".join(t[1] for t in sorted_tokens)
                        avg_conf = sum(t[2] for t in tokens) / len(tokens)
                        if 3 <= len(combined) <= 12 and avg_conf > 0.20 and any(c.isdigit() for c in combined):
                            if avg_conf > best_conf or best_plate is None:
                                best_plate = combined
                                best_conf = avg_conf

                    # If high-confidence plate already discovered, exit early
                    if best_plate and best_conf >= 0.55:
                        return best_plate, float(best_conf)

                except Exception as e:
                    logger.debug(f"EasyOCR extraction exception: {e}")

        if best_plate:
            return best_plate, float(best_conf)

        return None
