"""
Master IBVAP Analytics Engine.
Integrates Object Detection, Tracking, Face Recognition against Database,
Harmful Weapon Detection, ANPR License Plate Reading, and Behavior Analytics into a unified frame processing pipeline.
"""

import os
import cv2
import time
import logging
import threading
import platform
from typing import List, Tuple, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import numpy as np

from core.models import AlertEvent, TrackedObject, Detection, PersonRecord
from core.detector import ObjectDetector
from core.tracker import CentroidTracker
from core.virtual_fence import VirtualFence
from core.night_enhancer import NightEnhancer
from core.face_detector import FaceDetector
from core.face_recognizer import FaceRecognizer
from core.anpr import ANPRReader
from core.behavior_analytics import BehaviorAnalyzer

logger = logging.getLogger(__name__)


def _play_facial_match_buzzer():
    """Trigger system/hardware buzzer sound on facial recognition match in background thread."""
    try:
        if platform.system() == "Windows":
            import winsound
            for _ in range(3):
                winsound.Beep(850, 150)
                time.sleep(0.05)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass


# Visual theme colors (BGR)
COLOR_HUMAN = (0, 215, 255)         # Gold / Amber for general person
COLOR_MATCHED = (0, 255, 128)       # Bright Emerald Green for Matched Watchlist Subject
COLOR_VEHICLE = (255, 144, 30)      # Sky Blue for Vehicles
COLOR_FENCE = (0, 0, 255)           # Red for Virtual Fence
COLOR_FACE = (255, 0, 255)          # Magenta for Face ROI
COLOR_NIGHT = (0, 255, 255)         # Yellow for Night Mode
COLOR_HARMFUL = (0, 0, 255)         # Bright Red for Armed Weapons
COLOR_TEXT = (255, 255, 255)        # White


class FrameProcessingEngine:
    """
    Unified AI Analytics Engine per camera stream.
    Processes incoming frames, detects and tracks objects, triggers behavioral & security rules,
    performs facial recognition against database persons, and extracts number plates from vehicles.
    """

    def __init__(
        self,
        camera_id: str = "camera1",
        camera_name: str = "Camera 1",
        location: str = "Border Sector A",
        fences: List[VirtualFence] = None,
        enable_anpr: bool = True,
        enable_face_detection: bool = True,
        enable_night_mode: bool = True,
        yolo_model: str = "yolov8n.pt",
        conf_threshold: float = 0.25,
        device: str = "auto",
        supabase_manager: Optional[Any] = None
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.location = location
        self.fences = fences if fences is not None else []
        self.enable_anpr = enable_anpr
        self.enable_face_detection = enable_face_detection
        self.enable_night_mode = enable_night_mode
        self.supabase_manager = supabase_manager

        # AI & Analytics Components
        self.detector = ObjectDetector(model_name=yolo_model, conf_threshold=conf_threshold, device=device)
        self.tracker = CentroidTracker(max_disappeared=25, max_distance=90.0)
        self.night_enhancer = NightEnhancer(brightness_threshold=65.0)
        self.face_detector = FaceDetector() if enable_face_detection else None
        self.face_recognizer = FaceRecognizer() if enable_face_detection else None
        self.anpr_reader = ANPRReader(gpu=False) if enable_anpr else None
        self.behavior_analyzer = BehaviorAnalyzer()
        self.ocr_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"OCR-{camera_id}")

        # Alert memory buffer & cached tracking state
        self.alerts_history: List[AlertEvent] = []
        self.persons_history: List[PersonRecord] = []
        self.matched_alerts_sent: Dict[str, float] = {}
        self.armed_alerts_sent: set = set()
        self.frame_index: int = 0
        self.active_tracks: List[TrackedObject] = []
        self.detected_faces: List[Tuple[int, int, int, int]] = []
        self.detected_objects_raw: List[Detection] = []
        self.is_night: bool = False
        self.on_alert_callback = None
        self.on_person_callback = None
        # Match alert re-notification cooldown (30s per person per track)
        self.match_alert_cooldown: float = 30.0
        # Face recognition frame-skip intervals (frames between attempts)
        # Matched tracks: skip 15 frames before re-confirming identity
        # Unmatched tracks: attempt on every frame (1 frame) for instant match
        self.FACE_SKIP_MATCHED: int = 15
        self.FACE_SKIP_UNMATCHED: int = 1

        # Pre-load known face database profiles on startup
        if self.face_recognizer and self.supabase_manager:
            try:
                self.face_recognizer.sync_database_profiles(self.supabase_manager)
            except Exception as e:
                logger.warning(f"Initial face profile sync: {e}")

    def set_alert_callback(self, callback):
        """Set callback function for asynchronously emitted alerts."""
        self.on_alert_callback = callback

    def set_person_callback(self, callback):
        """Set callback function for captured Persons of Interest."""
        self.on_person_callback = callback

    def _async_anpr_task(self, crop: np.ndarray, track_id: int, timestamp: float):
        """Background OCR worker that extracts license plate without stalling the video feed."""
        if self.anpr_reader is None or crop is None or crop.size == 0:
            return
        try:
            h, w = crop.shape[:2]
            plate_result = self.anpr_reader.extract_plate(crop, (0, 0, w, h))
            if plate_result:
                plate_text, ocr_conf = plate_result
                logger.info(f"[{self.camera_id}] ANPR Plate Detected: {plate_text} (Conf: {ocr_conf*100:.1f}%) on Track #{track_id}")
                if track_id in self.tracker.tracks:
                    self.tracker.tracks[track_id].last_anpr_plate = plate_text

                alert = AlertEvent(
                    camera_id=self.camera_id,
                    camera_name=self.camera_name,
                    event_type="anpr",
                    object_type="vehicle",
                    license_plate=plate_text,
                    track_id=track_id,
                    confidence=round(ocr_conf, 2),
                    location=self.location,
                    details=f"Vehicle Plate Recognized: {plate_text}",
                    metadata={
                        "license_plate": plate_text,
                        "confidence": round(ocr_conf * 100, 1),
                        "plate_number": plate_text,
                        "vehicle_type": "Vehicle"
                    },
                    frame_crop=crop.copy()
                )
                self.alerts_history.append(alert)
                if self.on_alert_callback:
                    self.on_alert_callback([alert], timestamp)
        except Exception as e:
            logger.error(f"Async ANPR error: {e}")

    def process_frame(self, frame: np.ndarray, timestamp: float = None) -> Tuple[np.ndarray, List[AlertEvent], Dict[str, Any]]:
        """
        Process a single video frame through all analytics stages.
        Returns: (annotated_frame, new_alerts, metrics)
        """
        if frame is None or frame.size == 0:
            return frame, [], {}

        if timestamp is None:
            timestamp = time.time()

        self.frame_index += 1
        new_alerts: List[AlertEvent] = []
        start_time = time.perf_counter()
        frame_h, frame_w = frame.shape[:2]

        # 0. Synchronize face database profiles in background thread (non-blocking)
        if self.face_recognizer and self.supabase_manager:
            # Run sync check in background so it never blocks the AI inference loop
            self.ocr_executor.submit(self.face_recognizer.sync_database_profiles, self.supabase_manager)

        # 1. Night Mode Assessment & Enhancement
        enhanced_frame = frame
        is_night = False
        if self.enable_night_mode:
            enhanced_frame, is_night, night_alert = self.night_enhancer.process(
                frame, camera_id=self.camera_id, camera_name=self.camera_name, location=self.location
            )
            if night_alert:
                new_alerts.append(night_alert)

        self.is_night = is_night

        # 2. YOLO Detection (Humans, Vehicles, Weapons)
        raw_detections = self.detector.detect(enhanced_frame, imgsz=640)
        self.detected_objects_raw = raw_detections

        # Split into primary trackable targets vs. weapon/luggage items
        track_detections: List[Detection] = []
        carried_candidates: List[Detection] = []

        for d in raw_detections:
            if d.class_name in ["human", "person"]:
                track_detections.append(Detection(box=d.box, confidence=d.confidence, class_id=0, class_name="human"))
            elif d.class_name in ["car", "truck", "bus", "motorcycle", "vehicle"]:
                track_detections.append(Detection(box=d.box, confidence=d.confidence, class_id=d.class_id, class_name="vehicle"))
            else:
                carried_candidates.append(d)

        # 3. Multi-Object Tracking (Humans & Vehicles)
        active_tracks = self.tracker.update(track_detections, current_time=timestamp)

        # 4. Harmful Weapons Association (Knife, Scissors, Baseball Bat)
        for track in active_tracks:
            if track.class_name == "human":
                tx1, ty1, tx2, ty2 = track.box
                margin = 50
                hx1, hy1, hx2, hy2 = max(0, tx1 - margin), max(0, ty1 - margin), min(frame_w, tx2 + margin), min(frame_h, ty2 + margin)

                current_items = []
                for item in carried_candidates:
                    ix1, iy1, ix2, iy2 = item.box
                    icx, icy = (ix1 + ix2) // 2, (iy1 + iy2) // 2
                    if hx1 <= icx <= hx2 and hy1 <= icy <= hy2:
                        current_items.append(item.class_name)

                if current_items:
                    for c_item in current_items:
                        if c_item not in track.carried_objects:
                            track.carried_objects.append(c_item)

                    harmful_items = [obj for obj in current_items if obj in ["knife", "scissors", "baseball bat"]]
                    if harmful_items:
                        track.harmful_object_alerted = True
                        alert_key = f"armed_{track.track_id}"
                        if alert_key not in self.armed_alerts_sent:
                            self.armed_alerts_sent.add(alert_key)
                            items_str = ", ".join(harmful_items).upper()
                            new_alerts.append(AlertEvent(
                                camera_id=self.camera_id,
                                camera_name=self.camera_name,
                                event_type="harmful_object_detected",
                                object_type="human",
                                track_id=track.track_id,
                                confidence=0.92,
                                location=self.location,
                                metadata={"harmful_objects": harmful_items, "threat": f"Armed Intruder ({items_str})"},
                                frame_crop=enhanced_frame[max(0, ty1):min(frame_h, ty2), max(0, tx1):min(frame_w, tx2)].copy()
                            ))

        # 5. Facial Recognition within Person ROI & Database Comparison
        detected_faces: List[Tuple[int, int, int, int]] = []
        if self.enable_face_detection and self.face_recognizer and self.face_detector:
            for track in active_tracks:
                if track.class_name != "human":
                    continue

                # Determine frame-skip interval for this track
                if track.matched_person_name:
                    skip = self.FACE_SKIP_MATCHED   # already matched — re-confirm lazily
                else:
                    skip = self.FACE_SKIP_UNMATCHED  # unmatched — try every 1-2 frames

                frames_since = self.frame_index - track.face_recog_frame
                if frames_since < skip:
                    if hasattr(track, "cached_face_box") and track.cached_face_box:
                        detected_faces.append(track.cached_face_box)
                    continue

                track.face_recog_frame = self.frame_index
                faces_info = self.face_detector.detect_faces_with_landmarks(enhanced_frame, roi=track.box)

                if faces_info:
                    track.cached_face_box = faces_info[0]["box"]
                    for f_info in faces_info:
                        fx1, fy1, fx2, fy2 = f_info["box"]
                        raw_face = f_info.get("raw_face")
                        detected_faces.append((fx1, fy1, fx2, fy2))

                        face_crop = enhanced_frame[max(0, fy1):min(frame_h, fy2), max(0, fx1):min(frame_w, fx2)]
                        if face_crop.size == 0:
                            continue

                        matched_id, matched_name, sim, is_clear, sharpness = self.face_recognizer.match_face(
                            frame=enhanced_frame,
                            raw_face=raw_face,
                            face_crop=face_crop,
                            camera_id=self.camera_id,
                            camera_name=self.camera_name,
                            carried_objects=track.carried_objects
                        )
                        track.last_face_clarity = sharpness

                        if matched_name:
                            logger.info(
                                f"[{self.camera_id}] Suspect Matched: {matched_name} (ID: {matched_id[:8]}) "
                                f"Confidence: {sim*100:.1f}% Sharpness: {sharpness:.1f}"
                            )
                            track.matched_person_id = matched_id
                            track.matched_person_name = matched_name
                            track.face_recog_consecutive_miss = 0

                            alert_key = f"match_{track.track_id}_{matched_id}"
                            now_ts = timestamp or time.time()
                            if (now_ts - self.matched_alerts_sent.get(alert_key, 0.0)) >= self.match_alert_cooldown:
                                self.matched_alerts_sent[alert_key] = now_ts

                                # Sound the security buzzer alert on facial match
                                threading.Thread(target=_play_facial_match_buzzer, daemon=True).start()

                                # Pull profile data from in-memory cache ONLY — zero network latency
                                prof_entry = self.face_recognizer.known_profiles.get(matched_id, {})
                                db_img = prof_entry.get("image_url") or ""
                                db_dob = prof_entry.get("dob") or ""
                                db_notes = prof_entry.get("description") or ""

                                # Prepare clean crop (body bounding box)
                                crop = None
                                if track.box is not None:
                                    y1, y2 = max(0, track.box[1]), min(frame_h, track.box[3])
                                    x1, x2 = max(0, track.box[0]), min(frame_w, track.box[2])
                                    if y2 > y1 and x2 > x1:
                                        crop = enhanced_frame[y1:y2, x1:x2].copy()
                                if crop is None or crop.size == 0:
                                    crop = enhanced_frame.copy()

                                new_alerts.append(AlertEvent(
                                    camera_id=self.camera_id,
                                    camera_name=self.camera_name,
                                    event_type="face_detected",
                                    object_type="human",
                                    track_id=track.track_id,
                                    confidence=round(sim, 2),
                                    location=self.location,
                                    details=f"Suspect Match: {matched_name}",
                                    metadata={
                                        "matched_person": matched_name,
                                        "person_id": matched_id,
                                        "database_image_url": db_img,
                                        "dob": db_dob,
                                        "notes": db_notes,
                                        "description": db_notes,
                                        "similarity": round(sim * 100, 1),
                                        "threat_level": "Critical Watchlist Match",
                                        "status": "Recognized"
                                    },
                                    frame_crop=crop
                                ))
                        else:
                            # Promptly clear match after 3 consecutive unmatched frames
                            track.face_recog_consecutive_miss += 1
                            if track.face_recog_consecutive_miss > 3 and track.matched_person_name:
                                track.matched_person_name = None
                                track.matched_person_id = None
                                track.face_recog_consecutive_miss = 0

        self.active_tracks = active_tracks
        self.detected_faces = detected_faces

        # 6. ANPR Reader for Vehicles
        if self.enable_anpr and self.anpr_reader:
            for track in active_tracks:
                if track.class_name == "vehicle" and track.last_anpr_plate is None:
                    if timestamp - track.last_anpr_time >= 1.5:
                        track.last_anpr_time = timestamp
                        x1, y1, x2, y2 = track.box
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(frame_w, x2), min(frame_h, y2)
                        vehicle_crop = enhanced_frame[y1:y2, x1:x2].copy()
                        if vehicle_crop.size > 0:
                            self.ocr_executor.submit(self._async_anpr_task, vehicle_crop, track.track_id, timestamp)

        # 7. Virtual Fence Intrusion Checks
        for fence in self.fences:
            for track in active_tracks:
                intrusion_alert = fence.check_intrusion(
                    track,
                    camera_id=self.camera_id,
                    camera_name=self.camera_name,
                    location=self.location,
                    frame_w=frame_w,
                    frame_h=frame_h
                )
                if intrusion_alert:
                    intrusion_alert.frame_crop = enhanced_frame.copy()
                    new_alerts.append(intrusion_alert)

        # 8. Behavior Analytics
        behavior_alerts = self.behavior_analyzer.analyze(
            active_tracks,
            camera_id=self.camera_id,
            camera_name=self.camera_name,
            location=self.location,
            current_time=timestamp
        )
        for b_alert in behavior_alerts:
            # Check if this behavior alert belongs to an identified suspect
            trk = next((t for t in active_tracks if t.track_id == b_alert.track_id), None)
            if trk and trk.matched_person_name:
                # Retain suspect match category and identity for behavioral events on suspect
                b_alert.event_type = "face_detected"
                b_alert.details = f"Suspect Match: {trk.matched_person_name}"
                b_alert.metadata["matched_person"] = trk.matched_person_name
                b_alert.metadata["person_id"] = trk.matched_person_id
                b_alert.metadata["threat_level"] = "Critical Watchlist Match"
            b_alert.frame_crop = enhanced_frame.copy()
            new_alerts.append(b_alert)

        # 9. Record new alerts
        for alert in new_alerts:
            self.alerts_history.append(alert)

        # 10. Render Clean Overlays
        annotated = self._render_overlays(enhanced_frame, active_tracks, detected_faces, self.detected_objects_raw, is_night)

        inference_time_ms = (time.perf_counter() - start_time) * 1000.0
        human_count = sum(1 for t in active_tracks if t.class_name == "human")
        vehicle_count = sum(1 for t in active_tracks if t.class_name == "vehicle")

        metrics = {
            "fps": round(1000.0 / max(inference_time_ms, 1.0), 1),
            "inference_time_ms": round(inference_time_ms, 1),
            "active_tracks": len(active_tracks),
            "humans": human_count,
            "vehicles": vehicle_count,
            "total_alerts": len(self.alerts_history),
            "total_persons": len(self.persons_history),
            "is_night": is_night,
            "scene_brightness": round(self.night_enhancer.last_brightness, 1)
        }

        return annotated, new_alerts, metrics

    def render_hud_on_frame(self, frame: np.ndarray) -> np.ndarray:
        """Draw cached tracking state onto incoming camera frame."""
        if frame is None or frame.size == 0:
            return frame
        return self._render_overlays(frame, self.active_tracks, self.detected_faces, self.detected_objects_raw, self.is_night)

    def _render_overlays(
        self,
        frame: np.ndarray,
        tracks: List[TrackedObject],
        faces: List[Tuple[int, int, int, int]],
        raw_objects: List[Detection],
        is_night: bool
    ) -> np.ndarray:
        """Render clean, high-contrast bounding boxes, database matched identities, harmful objects, and vehicle plates."""
        out = frame.copy()
        frame_h, frame_w = frame.shape[:2]

        # 1. Draw Virtual Fences
        for fence in self.fences:
            if fence.fence_type in ["line", "vertical", "horizontal"] or len(fence.coordinates) >= 2:
                p1, p2 = fence.get_endpoints(frame_w, frame_h)
                cv2.line(out, p1, p2, COLOR_FENCE, 3)
                label = f"FENCE: {fence.name}"
                if fence.fence_type == "vertical":
                    tx = max(10, min(frame_w - 240, p1[0] + 10))
                    ty = 90
                elif fence.fence_type == "horizontal":
                    tx = 20
                    ty = max(25, p1[1] - 10)
                else:
                    tx = p1[0]
                    ty = max(20, p1[1] - 10)
                cv2.putText(out, label, (tx, ty),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_FENCE, 2)
            elif fence.fence_type == "polygon" and fence.np_poly is not None:
                cv2.polylines(out, [fence.np_poly], isClosed=True, color=COLOR_FENCE, thickness=2)
                overlay = out.copy()
                cv2.fillPoly(overlay, [fence.np_poly], (0, 0, 180))
                cv2.addWeighted(overlay, 0.25, out, 0.75, 0, out)
                cv2.putText(out, f"RESTRICTED ZONE: {fence.name}", fence.coordinates[0],
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_FENCE, 2)

        # 2. Draw Harmful Weapons
        for obj in raw_objects:
            if obj.class_name in ["knife", "scissors", "baseball bat"]:
                ox1, oy1, ox2, oy2 = obj.box
                cv2.rectangle(out, (ox1, oy1), (ox2, oy2), COLOR_HARMFUL, 2)
                cv2.putText(out, f"WEAPON: {obj.class_name.upper()}", (ox1, max(15, oy1 - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_HARMFUL, 2)

        # 3. Draw Tracked Objects (Humans & Vehicles)
        for track in tracks:
            x1, y1, x2, y2 = track.box
            
            # Determine color and ASCII title (NO unicode emojis to avoid ???? characters)
            if track.harmful_object_alerted:
                color = COLOR_HARMFUL
                status_title = f"ARMED: {','.join(track.carried_objects).upper()}"
            elif track.matched_person_name:
                color = COLOR_MATCHED
                status_title = f"MATCHED: {track.matched_person_name}"
            elif track.class_name == "human":
                color = COLOR_HUMAN
                status_title = "PERSON"
            else:
                color = COLOR_VEHICLE
                if track.last_anpr_plate:
                    status_title = f"VEHICLE [PLATE: {track.last_anpr_plate}]"
                else:
                    status_title = "VEHICLE"

            # Draw bounding box
            thickness = 3 if (track.harmful_object_alerted or track.matched_person_name) else 2
            cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)

            # Build label tag
            label = f"{status_title}"

            # Label box background
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1)
            cv2.rectangle(out, (x1, max(0, y1 - 24)), (x1 + lw + 8, max(24, y1)), color, -1)
            cv2.putText(out, label, (x1 + 4, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 0, 0), 2, cv2.LINE_AA)

        # 4. Draw Face ROI inside human
        for fx1, fy1, fx2, fy2 in faces:
            cv2.rectangle(out, (fx1, fy1), (fx2, fy2), COLOR_FACE, 1)

        # 5. Clean Top HUD Banner
        human_count = sum(1 for t in tracks if t.class_name == "human")
        vehicle_count = sum(1 for t in tracks if t.class_name == "vehicle")
        hud_bg = (20, 20, 20)
        cv2.rectangle(out, (10, 10), (420, 68), hud_bg, -1)
        cv2.rectangle(out, (10, 10), (420, 68), (80, 80, 80), 1)

        night_status = "NIGHT (CLAHE)" if is_night else "DAY (STANDARD)"
        night_color = COLOR_NIGHT if is_night else (100, 255, 100)
        cv2.putText(out, f"IBVAP | {self.camera_name}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_TEXT, 2)
        cv2.putText(out, f"Mode: {night_status} | Persons: {human_count} | Vehicles: {vehicle_count}", (20, 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, night_color, 1)

        return out
