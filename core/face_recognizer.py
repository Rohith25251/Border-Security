"""
Face Recognition & Clarity Assessment Module for IBVAP.
Evaluates face image sharpness/resolution, extracts feature signatures,
and matches/registers Persons of Interest (POI) profiles for surveillance intelligence.
"""

import os
import cv2
import time
import base64
import logging
import numpy as np
import urllib.request
from typing import Tuple, Optional, Dict, Any, List
from core.models import PersonRecord

logger = logging.getLogger(__name__)


class FaceRecognizer:
    """
    Evaluates face clarity, extracts invariant face signatures,
    synchronizes with database records, and recognizes registered subjects in real time.
    """

    def __init__(self, min_size: int = 28, min_sharpness: float = 38.0, similarity_threshold: float = 0.65):
        self.min_size = min_size
        self.min_sharpness = min_sharpness
        self.similarity_threshold = similarity_threshold
        
        # In-memory POI signature index:
        # { person_id: { "name": str, "signature": np.ndarray, "record": PersonRecord } }
        self.known_profiles: Dict[str, Dict[str, Any]] = {}
        self.profile_counter = 100
        self.last_sync_time = 0.0

    def sync_database_profiles(self, supabase_mgr):
        """
        Synchronize registered persons from Supabase / local storage into face recognition memory.
        """
        if supabase_mgr is None:
            return

        now = time.time()
        # Avoid syncing too frequently
        if now - self.last_sync_time < 8.0:
            return

        self.last_sync_time = now

        try:
            persons = supabase_mgr.fetch_persons(limit=200)
            for p in persons:
                pid = p.get("id") or p.get("person_id")
                name = p.get("name") or "Subject"
                if not pid:
                    continue

                # If already registered and have signature, skip re-computation
                if pid in self.known_profiles and self.known_profiles[pid].get("signature") is not None:
                    # Keep name updated
                    self.known_profiles[pid]["name"] = name
                    continue

                # Try loading image to compute feature vector
                img_path_or_url = p.get("image_url") or p.get("face_image_url") or ""
                img = None

                if img_path_or_url:
                    if img_path_or_url.startswith("data:image/"):
                        try:
                            header, encoded = img_path_or_url.split(",", 1)
                            raw_bytes = base64.b64decode(encoded)
                            nparr = np.frombuffer(raw_bytes, np.uint8)
                            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        except Exception:
                            pass
                    elif img_path_or_url.startswith("/api/persons/image/"):
                        # Extract local path from URL
                        subpath = img_path_or_url.replace("/api/persons/image/", "")
                        local_file = os.path.join("test_outputs", subpath)
                        if os.path.exists(local_file):
                            img = cv2.imread(local_file)
                    elif os.path.exists(img_path_or_url):
                        img = cv2.imread(img_path_or_url)
                    elif img_path_or_url.startswith("http"):
                        # Check local cache first
                        fname = img_path_or_url.split("/")[-1]
                        local_cache = os.path.join("test_outputs", "faces", fname)
                        if os.path.exists(local_cache):
                            img = cv2.imread(local_cache)
                        else:
                            try:
                                resp = urllib.request.urlopen(img_path_or_url, timeout=2)
                                raw_bytes = resp.read()
                                nparr = np.frombuffer(raw_bytes, np.uint8)
                                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            except Exception:
                                pass

                if img is not None and img.size > 0:
                    vec = self.extract_feature_vector(img)
                    self.known_profiles[pid] = {
                        "name": name,
                        "signature": vec,
                        "record": PersonRecord(
                            id=pid,
                            name=name,
                            dob=p.get("dob", ""),
                            description=p.get("description", ""),
                            image_url=img_path_or_url
                        )
                    }
                    logger.info(f"Loaded facial signature for registered subject: [{name}] ({pid[:8]})")
        except Exception as e:
            logger.warning(f"Error synchronizing face database profiles: {e}")

    def evaluate_clarity(self, face_crop: np.ndarray) -> Tuple[bool, float]:
        """
        Check if the detected face crop has sufficient resolution and sharpness for recognition.
        Returns: (is_clear, sharpness_score)
        """
        if face_crop is None or face_crop.size == 0:
            return False, 0.0

        h, w = face_crop.shape[:2]
        if h < self.min_size or w < self.min_size:
            return False, 0.0

        # Convert to grayscale
        if len(face_crop.shape) == 3:
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = face_crop

        # Calculate Laplacian variance (sharpness metric)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        sharpness = float(laplacian.var())

        is_clear = sharpness >= self.min_sharpness
        return is_clear, round(sharpness, 2)

    def extract_feature_vector(self, face_crop: np.ndarray) -> np.ndarray:
        """
        Extract normalized color and structural gradient feature descriptor.
        Resizes to 64x64, computes color & gradient histograms for fast invariant matching.
        """
        if face_crop is None or face_crop.size == 0:
            return np.zeros(128, dtype=np.float32)

        # Standardize face crop
        resized = cv2.resize(face_crop, (64, 64))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if len(resized.shape) == 3 else resized

        # 1. 2D DCT / frequency vector
        dct = cv2.dct(np.float32(gray))
        low_freq = dct[:8, :8].flatten()

        # 2. Local gradient histograms
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=1)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=1)
        mag, ang = cv2.cartToPolar(gx, gy, angleInDegrees=True)
        hist, _ = np.histogram(ang, bins=16, range=(0, 360), weights=mag)

        # 3. HSV Color histogram
        if len(face_crop.shape) == 3:
            hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
            h_hist, _ = np.histogram(hsv[:, :, 0], bins=16, range=(0, 180))
            s_hist, _ = np.histogram(hsv[:, :, 1], bins=16, range=(0, 256))
            color_feat = np.concatenate([h_hist, s_hist]).astype(np.float32)
            if np.linalg.norm(color_feat) > 0:
                color_feat /= np.linalg.norm(color_feat)
        else:
            color_feat = np.zeros(32, dtype=np.float32)

        # 4. Concatenate and L2 normalize
        feature_vec = np.concatenate([low_freq, hist, color_feat]).astype(np.float32)
        norm = np.linalg.norm(feature_vec)
        if norm > 0:
            feature_vec /= norm

        return feature_vec

    def match_face(
        self,
        face_crop: np.ndarray,
        camera_id: str = "camera1",
        camera_name: str = "Camera 1",
        carried_objects: List[str] = None
    ) -> Tuple[Optional[str], Optional[str], float, bool, float]:
        """
        Matches a face crop against all enrolled database profiles.
        Returns: (matched_person_id, matched_person_name, similarity, is_clear, sharpness)
        """
        is_clear, sharpness = self.evaluate_clarity(face_crop)
        if not is_clear:
            return None, None, 0.0, False, sharpness

        features = self.extract_feature_vector(face_crop)

        best_match_id = None
        best_match_name = None
        best_sim = 0.0

        for pid, data in self.known_profiles.items():
            known_vec = data.get("signature")
            if known_vec is not None:
                sim = float(np.dot(features, known_vec))
                if sim > best_sim:
                    best_sim = sim
                    best_match_id = pid
                    best_match_name = data.get("name", "Subject")

        if best_match_id and best_sim >= self.similarity_threshold:
            return best_match_id, best_match_name, best_sim, True, sharpness

        return None, None, best_sim, True, sharpness

    def match_or_create_person(
        self,
        face_crop: np.ndarray,
        full_frame: np.ndarray,
        camera_id: str,
        camera_name: str,
        carried_objects: List[str] = None,
        notes: str = ""
    ) -> Tuple[PersonRecord, bool]:
        """
        Matches a clear face against known POI profiles, or registers a new PersonRecord.
        Returns: (person_record, is_new_subject)
        """
        if carried_objects is None:
            carried_objects = []

        pid, name, sim, is_clear, sharpness = self.match_face(
            face_crop, camera_id=camera_id, camera_name=camera_name, carried_objects=carried_objects
        )

        if pid and pid in self.known_profiles:
            matched_record: PersonRecord = self.known_profiles[pid]["record"]
            return matched_record, False

        # Create new Person profile
        self.profile_counter += 1
        new_pid = f"POI-{self.profile_counter:04d}"
        new_name = f"Subject #{self.profile_counter:03d}"

        new_record = PersonRecord(
            id=new_pid,
            name=new_name,
            dob="Not Specified",
            description=notes or f"Identified at {camera_name}",
            face_crop=face_crop.copy() if face_crop is not None else None
        )

        features = self.extract_feature_vector(face_crop)
        self.known_profiles[new_pid] = {
            "name": new_name,
            "signature": features,
            "record": new_record
        }

        return new_record, True
