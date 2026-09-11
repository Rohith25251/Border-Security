"""
Master IBVAP Analytics Engine.
Integrates Object Detection, Tracking, Face Detection, Facial Recognition against Database,
Harmful Weapon Telemetry, ANPR, Virtual Fence, Night Mode CLAHE, and Behavior Analytics into a unified frame processing pipeline.
"""

import os
import cv2
import time
import logging
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

# Visual theme colors (BGR)
COLOR_HUMAN = (0, 215, 255)         # Gold / Amber
COLOR_MATCHED = (0, 255, 128)       # Bright Emerald Green for Matched DB Person
COLOR_VEHICLE = (255, 144, 30)      # Blue
COLOR_FENCE = (0, 0, 255)           # Red
COLOR_FACE_CLEAR = (255, 0, 255)    # Magenta
COLOR_FACE_UNCLEAR = (128, 128, 128)# Dim Gray
COLOR_NIGHT = (0, 255, 255)         # Yellow
COLOR_HARMFUL = (0, 0, 255)         # Bright Red for weapons
COLOR_LUGGAGE = (255, 191, 0)       # Deep Sky Blue
COLOR_TEXT = (255, 255, 255)        # White


class FrameProcessingEngine:
    """
    Unified AI Analytics Engine per camera stream.
    Processes incoming frames, detects and tracks objects, triggers behavioral & security rules,
    performs facial recognition against database persons, and returns annotated frames.
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
        self.frame_index: int = 0
        self.active_tracks: List[TrackedObject] = []
        self.detected_faces: List[Tuple[int, int, int, int]] = []
        self.detected_objects_raw: List[Detection] = []
        self.is_night: bool = False
        self.on_alert_callback = None
        self.on_person_callback = None

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
                if track_id in self.tracker.tracks:
                    self.tracker.tracks[track_id].last_anpr_plate = plate_text
                
                alert = AlertEvent(
                    camera_id=self.camera_id,
                    camera_name=self.camera_name,
                    event_type="anpr",
                    object_type="vehicle",
                    license_plate=plate_text,
                    track_id=track_id,
                    confidence=ocr_conf,
                    location=self.location,
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

        # 0. Synchronize face database profiles periodically
        if self.face_recognizer and self.supabase_manager:
            self.face_recognizer.sync_database_profiles(self.supabase_manager)

        # 1. Night Mode Assessment & CLAHE Enhancement
        enhanced_frame = frame
        is_night = False
        if self.enable_night_mode:
            enhanced_frame, is_night, night_alert = self.night_enhancer.process(
                frame, camera_id=self.camera_id, camera_name=self.camera_name, location=self.location
            )
            if night_alert:
                new_alerts.append(night_alert)

        self.is_night = is_night

        # 2. Low-latency Object & Weapon/Luggage Detection
        raw_detections = self.detector.detect(enhanced_frame, imgsz=480)
        self.detected_objects_raw = raw_detections

        # Split into primary trackable targets vs. carried/nearby objects
        track_detections: List[Detection] = []
        carried_candidates: List[Detection] = []

        for d in raw_detections:
            if d.class_name in ["human", "car", "truck", "bus", "motorcycle", "vehicle"]:
                track_detections.append(d)
            else:
                carried_candidates.append(d)

        # 3. Robust Face & Close-up Person Detection
        detected_faces: List[Tuple[int, int, int, int]] = []
        if self.enable_face_detection and self.face_detector:
            # Run fast face detector across the frame
            full_frame_faces = self.face_detector.detect(enhanced_frame)
            if full_frame_faces:
                detected_faces.extend(full_frame_faces)

                # Ensure every detected face has a corresponding human tracking box
                for fx1, fy1, fx2, fy2 in full_frame_faces:
                    fw, fh = fx2 - fx1, fy2 - fy1
                    fcx, fcy = (fx1 + fx2) // 2, (fy1 + fy2) // 2

                    # Check if any existing human detection already covers this face
                    has_covering_human = False
                    for hd in track_detections:
                        if hd.class_name == "human":
                            hx1, hy1, hx2, hy2 = hd.box
                            if hx1 <= fcx <= hx2 and hy1 <= fcy <= hy2:
                                has_covering_human = True
                                break

                    # If no YOLO human box covers this face, construct upper-body person box
                    if not has_covering_human:
                        px1 = max(0, fx1 - int(fw * 0.75))
                        py1 = max(0, fy1 - int(fh * 0.25))
                        px2 = min(frame_w, fx2 + int(fw * 0.75))
                        py2 = min(frame_h, fy2 + int(fh * 3.5))
                        track_detections.append(Detection(
                            box=(px1, py1, px2, py2),
                            confidence=0.88,
                            class_id=0,
                            class_name="human"
                        ))

        # 4. Multi-Object Tracking (Humans & Vehicles)
        active_tracks = self.tracker.update(track_detections, current_time=timestamp)

        # 5. Harmful Weapons & Luggage Association
        for track in active_tracks:
            if track.class_name == "human":
                tx1, ty1, tx2, ty2 = track.box
                margin = 35
                hx1, hy1, hx2, hy2 = max(0, tx1 - margin), max(0, ty1 - margin), tx2 + margin, ty2 + margin

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

                    # Check for harmful weapons/tools (knife, scissors, baseball bat)
                    harmful_items = [obj for obj in current_items if obj in ["knife", "scissors", "baseball bat"]]
                    if harmful_items and not track.harmful_object_alerted:
                        track.harmful_object_alerted = True
                        new_alerts.append(AlertEvent(
                            camera_id=self.camera_id,
                            camera_name=self.camera_name,
                            event_type="harmful_object_detected",
                            object_type="human",
                            track_id=track.track_id,
                            confidence=0.92,
                            location=self.location,
                            metadata={"harmful_objects": harmful_items, "threat": "Armed Threat"},
                            frame_crop=enhanced_frame[max(0, ty1):min(frame_h, ty2), max(0, tx1):min(frame_w, tx2)].copy()
                        ))

        # 6. Facial Recognition & Database Comparison
        if self.enable_face_detection and self.face_recognizer and self.face_detector:
            for track in active_tracks:
                if track.class_name == "human":
                    # Locate faces within the upper half of the track ROI
                    roi_faces = self.face_detector.detect_in_roi(enhanced_frame, track.box)
                    if not roi_faces:
                        # Fallback: check if any detected global face falls within track box
                        tx1, ty1, tx2, ty2 = track.box
                        for fx1, fy1, fx2, fy2 in detected_faces:
                            fcx, fcy = (fx1 + fx2) // 2, (fy1 + fy2) // 2
                            if tx1 <= fcx <= tx2 and ty1 <= fcy <= ty2:
                                roi_faces.append((fx1, fy1, fx2, fy2))

                    for fx1, fy1, fx2, fy2 in roi_faces:
                        if (fx1, fy1, fx2, fy2) not in detected_faces:
                            detected_faces.append((fx1, fy1, fx2, fy2))

                        face_crop = enhanced_frame[max(0, fy1):min(frame_h, fy2), max(0, fx1):min(frame_w, fx2)]
                        if face_crop.size > 0:
                            matched_id, matched_name, sim, is_clear, sharpness = self.face_recognizer.match_face(
                                face_crop=face_crop,
                                camera_id=self.camera_id,
                                camera_name=self.camera_name,
                                carried_objects=track.carried_objects
                            )
                            track.last_face_clarity = sharpness

                            if matched_name:
                                track.matched_person_id = matched_id
                                track.matched_person_name = matched_name
                            elif is_clear and (timestamp - track.last_face_time >= 3.0):
                                track.last_face_time = timestamp
                                # Auto-register unidentified subject with clear face
                                person_rec, is_new = self.face_recognizer.match_or_create_person(
                                    face_crop=face_crop,
                                    full_frame=enhanced_frame,
                                    camera_id=self.camera_id,
                                    camera_name=self.camera_name,
                                    carried_objects=track.carried_objects,
                                    notes=f"Unregistered subject at {self.location}"
                                )
                                track.matched_person_id = person_rec.id
                                if is_new:
                                    self.persons_history.append(person_rec)
                                    if self.on_person_callback:
                                        self.on_person_callback(person_rec)

                                new_alerts.append(AlertEvent(
                                    camera_id=self.camera_id,
                                    camera_name=self.camera_name,
                                    event_type="face_detected",
                                    object_type="human",
                                    track_id=track.track_id,
                                    confidence=0.90,
                                    location=self.location,
                                    frame_crop=enhanced_frame[max(0, track.box[1]):track.box[3], max(0, track.box[0]):track.box[2]].copy()
                                ))

        self.active_tracks = active_tracks
        self.detected_faces = detected_faces

        # 7. ANPR Reader
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

        # 8. Virtual Fence Intrusion Checks
        for fence in self.fences:
            for track in active_tracks:
                intrusion_alert = fence.check_intrusion(
                    track, camera_id=self.camera_id, camera_name=self.camera_name, location=self.location
                )
                if intrusion_alert:
                    intrusion_alert.frame_crop = enhanced_frame.copy()
                    new_alerts.append(intrusion_alert)

        # 9. Behavior Analytics (Loitering, Fast Movement, Group Clustering)
        behavior_alerts = self.behavior_analyzer.analyze(
            active_tracks,
            camera_id=self.camera_id,
            camera_name=self.camera_name,
            location=self.location,
            current_time=timestamp
        )
        for b_alert in behavior_alerts:
            b_alert.frame_crop = enhanced_frame.copy()
            new_alerts.append(b_alert)

        # 10. Record new alerts
        for alert in new_alerts:
            self.alerts_history.append(alert)

        # 11. Render Overlays
        annotated = self._render_overlays(enhanced_frame, active_tracks, detected_faces, self.detected_objects_raw, is_night)

        inference_time_ms = (time.perf_counter() - start_time) * 1000.0
        metrics = {
            "fps": round(1000.0 / max(inference_time_ms, 1.0), 1),
            "inference_time_ms": round(inference_time_ms, 1),
            "active_tracks": len(active_tracks),
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
        """Render HUD, bounding boxes, database matched identities, harmful objects, and fences."""
        out = frame.copy()

        # 1. Draw Virtual Fences
        for fence in self.fences:
            if fence.fence_type == "line" and len(fence.coordinates) >= 2:
                p1, p2 = fence.coordinates[0], fence.coordinates[1]
                cv2.line(out, p1, p2, COLOR_FENCE, 3)
                cv2.putText(out, f"FENCE: {fence.name}", (p1[0], max(20, p1[1] - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_FENCE, 2)
            elif fence.fence_type == "polygon" and fence.np_poly is not None:
                cv2.polylines(out, [fence.np_poly], isClosed=True, color=COLOR_FENCE, thickness=2)
                overlay = out.copy()
                cv2.fillPoly(overlay, [fence.np_poly], (0, 0, 180))
                cv2.addWeighted(overlay, 0.25, out, 0.75, 0, out)
                cv2.putText(out, f"RESTRICTED ZONE: {fence.name}", fence.coordinates[0],
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_FENCE, 2)

        # 2. Draw Harmful Weapons & Luggage Objects
        for obj in raw_objects:
            if obj.class_name in ["knife", "scissors", "baseball bat"]:
                ox1, oy1, ox2, oy2 = obj.box
                cv2.rectangle(out, (ox1, oy1), (ox2, oy2), COLOR_HARMFUL, 2)
                cv2.putText(out, f"WEAPON: {obj.class_name.upper()}", (ox1, max(15, oy1 - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_HARMFUL, 2)
            elif obj.class_name in ["backpack", "handbag", "suitcase"]:
                ox1, oy1, ox2, oy2 = obj.box
                cv2.rectangle(out, (ox1, oy1), (ox2, oy2), COLOR_LUGGAGE, 1)

        # 3. Draw Tracked Objects (Humans & Vehicles)
        for track in tracks:
            x1, y1, x2, y2 = track.box
            
            # Determine color and title
            if track.harmful_object_alerted:
                color = COLOR_HARMFUL
                status_title = "ARMED THREAT"
            elif track.matched_person_name:
                color = COLOR_MATCHED
                status_title = f"MATCHED: {track.matched_person_name}"
            elif track.class_name == "human":
                color = COLOR_HUMAN
                if track.last_face_clarity >= 38.0:
                    status_title = "HUMAN (CLEAR FACE)"
                elif track.last_face_clarity > 0.0:
                    status_title = "HUMAN (UNCLEAR FACE)"
                else:
                    status_title = "HUMAN TARGET"
            else:
                color = COLOR_VEHICLE
                status_title = "VEHICLE"

            # Draw bounding box
            thickness = 3 if (track.harmful_object_alerted or track.matched_person_name) else 2
            cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)

            # Build label details
            plate_tag = f" [{track.last_anpr_plate}]" if track.last_anpr_plate else ""
            loiter_tag = " [LOITERING]" if track.loitering_alerted else ""
            fast_tag = " [FAST]" if track.fast_movement_alerted else ""
            carried_tag = f" [{', '.join(track.carried_objects).upper()}]" if track.carried_objects else ""

            label = f"ID:{track.track_id} | {status_title}{plate_tag}{carried_tag}{loiter_tag}{fast_tag}"

            # Label box background
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(out, (x1, max(0, y1 - 22)), (x1 + lw + 8, max(22, y1)), color, -1)
            cv2.putText(out, label, (x1 + 4, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

            # Draw trajectory path
            if len(track.history) > 1:
                pts = np.array([pt for _, pt in track.history[-25:]], np.int32).reshape((-1, 1, 2))
                cv2.polylines(out, [pts], isClosed=False, color=color, thickness=2)

        # 4. Draw Detected Face Region Highlights
        for fx1, fy1, fx2, fy2 in faces:
            cv2.rectangle(out, (fx1, fy1), (fx2, fy2), COLOR_FACE_CLEAR, 2)
            cv2.putText(out, "FACE REGION", (fx1, max(15, fy1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.40, COLOR_FACE_CLEAR, 1)

        # 5. Status HUD Banner (Top left)
        hud_bg = (20, 20, 20)
        cv2.rectangle(out, (10, 10), (370, 75), hud_bg, -1)
        cv2.rectangle(out, (10, 10), (370, 75), (80, 80, 80), 1)

        night_status = "NIGHT (CLAHE)" if is_night else "DAY (STANDARD)"
        night_color = COLOR_NIGHT if is_night else (100, 255, 100)
        cv2.putText(out, f"IBVAP | {self.camera_name}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.58, COLOR_TEXT, 2)
        cv2.putText(out, f"Mode: {night_status}", (20, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.42, night_color, 1)
        cv2.putText(out, f"Tracks: {len(tracks)} | Alerts: {len(self.alerts_history)} | POIs: {len(self.persons_history)}", (20, 66),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (200, 200, 200), 1)

        return out
