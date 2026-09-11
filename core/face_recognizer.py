"""
Face Recognition & Clarity Assessment Module for IBVAP.
Uses OpenCV SFace Deep Neural Network (128-D Invariant Embeddings) and YuNet Landmark Alignment
to provide high-precision, low-latency facial identification against enrolled database profiles.
"""

import os
import cv2
import time
import base64
import logging
import threading
import urllib.request
import numpy as np
from typing import Tuple, Optional, Dict, Any, List
from core.models import PersonRecord
from core.face_detector import FaceDetector

logger = logging.getLogger(__name__)

# SFace Model Constants
SFACE_MODEL_FILENAME = "face_recognition_sface_2021dec.onnx"
SFACE_DOWNLOAD_URL = "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx"


class FaceRecognizer:
    """
    High-precision Face Recognition Engine.
    Leverages OpenCV SFace deep neural network embeddings with YuNet landmark alignment
    for zero-shot facial matching against enrolled database profiles.
    """

    def __init__(
        self,
        min_size: int = 25,
        min_sharpness: float = 12.0,
        similarity_threshold: float = 0.35
    ):
        self.min_size = min_size
        self.min_sharpness = min_sharpness
        self.similarity_threshold = similarity_threshold

        # In-memory POI signature index:
        # { person_id: { "name": str, "signature": np.ndarray (1, 128), "record": PersonRecord,
        #                "image_url": str, "dob": str, "description": str } }
        self.known_profiles: Dict[str, Dict[str, Any]] = {}
        self.last_sync_time: float = 0.0
        self._sync_lock = threading.Lock()
        self.face_detector = FaceDetector()

        # Initialize SFace Deep Recognition Model
        self.sface: Optional[cv2.FaceRecognizerSF] = None
        self._init_sface_model()

    def _init_sface_model(self):
        """Locate or download the SFace ONNX deep face model."""
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        models_dir = os.path.join(project_root, "models")
        os.makedirs(models_dir, exist_ok=True)
        sface_path = os.path.join(models_dir, SFACE_MODEL_FILENAME)

        if not os.path.exists(sface_path) or os.path.getsize(sface_path) < 1000000:
            try:
                logger.info("Downloading official SFace deep face recognition ONNX model...")
                req = urllib.request.Request(SFACE_DOWNLOAD_URL, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    with open(sface_path, "wb") as f:
                        f.write(resp.read())
                logger.info(f"SFace model downloaded ({os.path.getsize(sface_path)} bytes).")
            except Exception as e:
                logger.error(f"Failed to download SFace model: {e}")

        if os.path.exists(sface_path) and os.path.getsize(sface_path) > 1000000:
            try:
                self.sface = cv2.FaceRecognizerSF.create(sface_path, "")
                logger.info(f"SFace Deep Face Recognizer initialized from {sface_path}")
            except Exception as e:
                logger.error(f"Error loading SFace ONNX: {e}")
                self.sface = None
        else:
            logger.warning("SFace ONNX model not found. Fallback feature extraction active.")

    def evaluate_clarity(self, face_crop: np.ndarray) -> Tuple[bool, float]:
        """
        Check if the detected face crop has sufficient resolution and sharpness.
        Returns: (is_clear, sharpness_score)
        """
        if face_crop is None or face_crop.size == 0:
            return False, 0.0

        h, w = face_crop.shape[:2]
        if h < self.min_size or w < self.min_size:
            return False, 0.0

        if len(face_crop.shape) == 3:
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = face_crop

        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        sharpness = float(laplacian.var())
        is_clear = sharpness >= self.min_sharpness
        return is_clear, round(sharpness, 2)

    def extract_feature_vector(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract 128-D deep neural network embedding from face crop,
        leveraging YuNet 5-point landmark alignment for rotation & pose invariance.
        """
        if face_crop is None or face_crop.size == 0:
            return None

        h, w = face_crop.shape[:2]

        if self.sface is not None:
            try:
                # Attempt landmark alignment via YuNet
                raw_faces = self.face_detector.detect_raw(face_crop)
                if raw_faces is not None and len(raw_faces) > 0:
                    aligned = self.sface.alignCrop(face_crop, raw_faces[0])
                    feat = self.sface.feature(aligned)
                    return feat

                # Fallback resize if landmarks not detected inside tight crop
                resized = cv2.resize(face_crop, (112, 112))
                if len(resized.shape) == 2:
                    resized = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)
                feat = self.sface.feature(resized)
                return feat
            except Exception as e:
                logger.debug(f"SFace feature extraction error: {e}")

        # Fallback structural feature vector
        resized = cv2.resize(face_crop, (112, 112))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if len(resized.shape) == 3 else resized
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        norm_gray = clahe.apply(gray)
        dct = cv2.dct(np.float32(norm_gray))
        feat = dct[:8, :16].flatten().astype(np.float32)
        feat -= np.mean(feat)
        norm = np.linalg.norm(feat)
        if norm > 0:
            feat /= norm
        return feat.reshape(1, -1)

    def process_and_extract_face_from_image(self, image_input: Any) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Pre-process raw uploaded image on database entry:
        1. Decodes image (base64, URL, path, or ndarray).
        2. Detects and isolates primary face bounding box.
        3. Computes normalized 128-D deep feature signature.
        Returns: (face_crop, feature_signature)
        """
        img: Optional[np.ndarray] = None

        if isinstance(image_input, np.ndarray):
            img = image_input
        elif isinstance(image_input, str):
            if image_input.startswith("data:image/"):
                try:
                    header, encoded = image_input.split(",", 1)
                    raw_bytes = base64.b64decode(encoded)
                    nparr = np.frombuffer(raw_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception as e:
                    logger.warning(f"Base64 decode error: {e}")
            elif image_input.startswith("http://") or image_input.startswith("https://"):
                try:
                    req = urllib.request.Request(image_input, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=6) as resp:
                        raw_bytes = resp.read()
                    nparr = np.frombuffer(raw_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception as e:
                    logger.warning(f"HTTP image load error: {e}")
            elif os.path.exists(image_input):
                img = cv2.imread(image_input)

        if img is None or img.size == 0:
            return None, None

        # Detect face inside the image
        faces = self.face_detector.detect(img)
        if faces and len(faces) > 0:
            largest_face = max(faces, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))
            fx1, fy1, fx2, fy2 = largest_face
            h, w = img.shape[:2]
            pw, ph = int((fx2 - fx1) * 0.15), int((fy2 - fy1) * 0.15)
            cx1, cy1 = max(0, fx1 - pw), max(0, fy1 - ph)
            cx2, cy2 = min(w, fx2 + pw), min(h, fy2 + ph)
            face_crop = img[cy1:cy2, cx1:cx2].copy()
        else:
            face_crop = img.copy()

        # Compute deep signature
        signature = self.extract_feature_vector(face_crop)
        return face_crop, signature

    def register_profile_signature(
        self,
        person_id: str,
        name: str,
        signature: np.ndarray,
        record: Optional[PersonRecord] = None,
        image_url: str = "",
        dob: str = "",
        description: str = ""
    ):
        """Pre-index a known person's deep signature into recognition memory."""
        if signature is None:
            return
        self.known_profiles[person_id] = {
            "name": name,
            "signature": signature,
            "record": record,
            "image_url": image_url or (record.image_url if record else "") or (record.face_image_url if record else ""),
            "dob": dob or (record.dob if record else ""),
            "description": description or (record.description if record else ""),
        }
        logger.info(f"Facial signature indexed in memory for: [{name}] ({person_id[:8]})")

    def remove_profile(self, person_id: str):
        """Remove a deleted person profile from recognition memory."""
        if person_id in self.known_profiles:
            removed = self.known_profiles.pop(person_id, None)
            if removed:
                logger.info(f"Removed facial signature for: [{removed.get('name')}] ({person_id[:8]})")

    def sync_database_profiles(self, supabase_mgr):
        """
        Synchronize registered persons from Supabase / local storage into memory.
        Only runs every 8s to prevent overhead. Thread-safe — safe to call from background threads.
        """
        if supabase_mgr is None:
            return

        now = time.time()
        if now - self.last_sync_time < 8.0:
            return

        if not self._sync_lock.acquire(blocking=False):
            return

        try:
            self.last_sync_time = now
            persons = supabase_mgr.fetch_persons(limit=200)
            active_ids = set()

            for p in persons:
                pid = p.get("id") or p.get("person_id")
                name = p.get("name") or "Subject"
                if not pid:
                    continue

                active_ids.add(pid)
                p_img = p.get("image_url") or p.get("face_image_url") or ""
                p_dob = p.get("dob") or ""
                p_desc = p.get("description") or p.get("notes") or ""

                # If already indexed with valid signature, just update flat metadata
                if pid in self.known_profiles and self.known_profiles[pid].get("signature") is not None:
                    self.known_profiles[pid]["name"] = name
                    self.known_profiles[pid]["image_url"] = p_img
                    self.known_profiles[pid]["dob"] = p_dob
                    self.known_profiles[pid]["description"] = p_desc
                    continue

                if p_img:
                    face_crop, signature = self.process_and_extract_face_from_image(p_img)
                    if signature is not None:
                        self.register_profile_signature(
                            person_id=pid,
                            name=name,
                            signature=signature,
                            record=PersonRecord(
                                id=pid,
                                name=name,
                                dob=p_dob,
                                description=p_desc,
                                image_url=p_img
                            ),
                            image_url=p_img,
                            dob=p_dob,
                            description=p_desc
                        )

            # Prune deleted profiles
            cached_ids = list(self.known_profiles.keys())
            for cid in cached_ids:
                if cid not in active_ids and not cid.startswith("POI-"):
                    self.remove_profile(cid)

        except Exception as e:
            logger.warning(f"Error synchronizing face database profiles: {e}")
        finally:
            self._sync_lock.release()

    def match_face(
        self,
        face_crop: np.ndarray,
        camera_id: str = "camera1",
        camera_name: str = "Camera 1",
        carried_objects: List[str] = None
    ) -> Tuple[Optional[str], Optional[str], float, bool, float]:
        """
        Matches a detected face crop against all enrolled database profiles.
        Returns: (matched_person_id, matched_person_name, similarity, is_clear, sharpness)
        """
        is_clear, sharpness = self.evaluate_clarity(face_crop)
        if len(self.known_profiles) == 0:
            return None, None, 0.0, is_clear, sharpness

        live_feature = self.extract_feature_vector(face_crop)
        if live_feature is None:
            return None, None, 0.0, is_clear, sharpness

        best_match_id: Optional[str] = None
        best_match_name: Optional[str] = None
        best_sim: float = -1.0

        for pid, data in self.known_profiles.items():
            known_sig = data.get("signature")
            if known_sig is None:
                continue

            if self.sface is not None:
                try:
                    sim = float(self.sface.match(live_feature, known_sig, cv2.FaceRecognizerSF_FR_COSINE))
                except Exception:
                    sim = float(np.dot(live_feature.flatten(), known_sig.flatten()) / (
                        np.linalg.norm(live_feature) * np.linalg.norm(known_sig) + 1e-6
                    ))
            else:
                sim = float(np.dot(live_feature.flatten(), known_sig.flatten()) / (
                    np.linalg.norm(live_feature) * np.linalg.norm(known_sig) + 1e-6
                ))

            if sim > best_sim:
                best_sim = sim
                best_match_id = pid
                best_match_name = data.get("name", "Subject")

        if best_match_id and best_sim >= self.similarity_threshold:
            return best_match_id, best_match_name, best_sim, True, sharpness

        return None, None, max(0.0, best_sim), True, sharpness
