"""
Master IBVAP Analytics Engine.
Integrates Object Detection, Tracking, Face Detection, ANPR, Virtual Fence,
Night Mode CLAHE, and Behavior Analytics into a unified frame processing pipeline.
"""

import cv2
import time
import logging
from typing import List, Tuple, Optional, Dict, Any
import numpy as np

from core.models import AlertEvent, TrackedObject, Detection
from core.detector import ObjectDetector
from core.tracker import CentroidTracker
from core.virtual_fence import VirtualFence
from core.night_enhancer import NightEnhancer
from core.face_detector import FaceDetector
from core.anpr import ANPRReader
from core.behavior_analytics import BehaviorAnalyzer

logger = logging.getLogger(__name__)

# Visual theme colors (BGR)
COLOR_HUMAN = (0, 215, 255)      # Amber / Gold
COLOR_VEHICLE = (255, 144, 30)   # Blue
COLOR_FENCE = (0, 0, 255)        # Red
COLOR_FACE = (255, 0, 255)       # Magenta
COLOR_NIGHT = (0, 255, 255)      # Yellow
COLOR_TEXT = (255, 255, 255)     # White


class FrameProcessingEngine:
    """
    Unified AI Analytics Engine per camera stream.
    Processes incoming frames, detects and tracks objects, triggers behavioral & security rules,
    and returns annotated frames along with structured AlertEvents.
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
        conf_threshold: float = 0.40,
        device: str = "cpu"
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.location = location
        self.fences = fences if fences is not None else []
        self.enable_anpr = enable_anpr
        self.enable_face_detection = enable_face_detection
        self.enable_night_mode = enable_night_mode

        # AI & Analytics Components
        self.detector = ObjectDetector(model_name=yolo_model, conf_threshold=conf_threshold, device=device)
        self.tracker = CentroidTracker(max_disappeared=25, max_distance=90.0)
        self.night_enhancer = NightEnhancer(brightness_threshold=65.0)
        self.face_detector = FaceDetector() if enable_face_detection else None
        self.anpr_reader = ANPRReader(gpu=False) if enable_anpr else None
        self.behavior_analyzer = BehaviorAnalyzer()

        # Alert memory buffer
        self.alerts_history: List[AlertEvent] = []
        self.frame_index: int = 0

    def process_frame(self, frame: np.ndarray, timestamp: float = None) -> Tuple[np.ndarray, List[AlertEvent], Dict[str, Any]]:
        """
        Process a single video frame through all analytics stages.
        Returns: (annotated_frame, new_alerts, metrics)
        """
        if frame is None:
            return frame, [], {}

        if timestamp is None:
            timestamp = time.time()

        self.frame_index += 1
        new_alerts: List[AlertEvent] = []
        start_time = time.perf_counter()

        # 1. Night Mode Assessment & CLAHE Enhancement
        enhanced_frame = frame
        is_night = False
        if self.enable_night_mode:
            enhanced_frame, is_night, night_alert = self.night_enhancer.process(
                frame, camera_id=self.camera_id, camera_name=self.camera_name, location=self.location
            )
            if night_alert:
                new_alerts.append(night_alert)

        # 2. Object Detection (Humans & Vehicles) on enhanced frame
        detections = self.detector.detect(enhanced_frame)

        # 3. Multi-Object Tracking
        active_tracks = self.tracker.update(detections, current_time=timestamp)

        # 4. Face Detection (run selectively on human bounding boxes)
        detected_faces: List[Tuple[int, int, int, int]] = []
        if self.enable_face_detection and self.face_detector:
            for track in active_tracks:
                if track.class_name == "human":
                    # Check face detection periodically (every 1.5s per track)
                    if timestamp - track.last_face_time >= 1.5:
                        faces = self.face_detector.detect_in_roi(enhanced_frame, track.box)
                        if faces:
                            track.last_face_time = timestamp
                            detected_faces.extend(faces)
                            new_alerts.append(AlertEvent(
                                camera_id=self.camera_id,
                                camera_name=self.camera_name,
                                event_type="face_detected",
                                object_type="human",
                                track_id=track.track_id,
                                confidence=0.85,
                                location=self.location,
                                frame_crop=enhanced_frame[max(0, track.box[1]):track.box[3], max(0, track.box[0]):track.box[2]].copy()
                            ))

        # 5. ANPR (Automatic Number Plate Recognition on Vehicles)
        if self.enable_anpr and self.anpr_reader:
            for track in active_tracks:
                if track.class_name == "vehicle" and track.last_anpr_plate is None:
                    # Run ANPR on vehicle ROI if not yet recognized or periodically
                    if timestamp - track.last_anpr_time >= 1.0:
                        track.last_anpr_time = timestamp
                        plate_result = self.anpr_reader.extract_plate(enhanced_frame, track.box)
                        if plate_result:
                            plate_text, ocr_conf = plate_result
                            track.last_anpr_plate = plate_text
                            new_alerts.append(AlertEvent(
                                camera_id=self.camera_id,
                                camera_name=self.camera_name,
                                event_type="anpr",
                                object_type="vehicle",
                                license_plate=plate_text,
                                track_id=track.track_id,
                                confidence=ocr_conf,
                                location=self.location,
                                frame_crop=enhanced_frame[max(0, track.box[1]):track.box[3], max(0, track.box[0]):track.box[2]].copy()
                            ))

        # 6. Virtual Fence Intrusion Checks
        for fence in self.fences:
            for track in active_tracks:
                intrusion_alert = fence.check_intrusion(
                    track, camera_id=self.camera_id, camera_name=self.camera_name, location=self.location
                )
                if intrusion_alert:
                    intrusion_alert.frame_crop = enhanced_frame.copy()
                    new_alerts.append(intrusion_alert)

        # 7. Behavior Analytics (Loitering, Fast Movement, Group Clustering)
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

        # 8. Record new alerts in history
        for alert in new_alerts:
            self.alerts_history.append(alert)

        # 9. Render Visual Overlays
        annotated = self._render_overlays(enhanced_frame, active_tracks, detected_faces, is_night)

        inference_time_ms = (time.perf_counter() - start_time) * 1000.0
        metrics = {
            "fps": round(1000.0 / max(inference_time_ms, 1.0), 1),
            "inference_time_ms": round(inference_time_ms, 1),
            "active_tracks": len(active_tracks),
            "total_alerts": len(self.alerts_history),
            "is_night": is_night,
            "scene_brightness": round(self.night_enhancer.last_brightness, 1)
        }

        return annotated, new_alerts, metrics

    def _render_overlays(
        self,
        frame: np.ndarray,
        tracks: List[TrackedObject],
        faces: List[Tuple[int, int, int, int]],
        is_night: bool
    ) -> np.ndarray:
        """Render HUD, bounding boxes, track IDs, fences, and status badges."""
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
                # Overlay semi-transparent fill
                overlay = out.copy()
                cv2.fillPoly(overlay, [fence.np_poly], (0, 0, 180))
                cv2.addWeighted(overlay, 0.25, out, 0.75, 0, out)
                cv2.putText(out, f"RESTRICTED ZONE: {fence.name}", fence.coordinates[0],
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_FENCE, 2)

        # 2. Draw Tracked Objects
        for track in tracks:
            x1, y1, x2, y2 = track.box
            color = COLOR_HUMAN if track.class_name == "human" else COLOR_VEHICLE

            # Bounding box
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

            # Label tag
            plate_tag = f" [{track.last_anpr_plate}]" if track.last_anpr_plate else ""
            loiter_tag = " [LOITERING]" if track.loitering_alerted else ""
            fast_tag = " [FAST]" if track.fast_movement_alerted else ""
            label = f"ID:{track.track_id} {track.class_name.upper()} {int(track.confidence * 100)}%{plate_tag}{loiter_tag}{fast_tag}"

            # Label background box
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(out, (x1, max(0, y1 - 22)), (x1 + lw + 6, max(22, y1)), color, -1)
            cv2.putText(out, label, (x1 + 3, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

            # Draw trajectory path
            if len(track.history) > 1:
                pts = np.array([pt for _, pt in track.history[-25:]], np.int32).reshape((-1, 1, 2))
                cv2.polylines(out, [pts], isClosed=False, color=color, thickness=2)

        # 3. Draw Detected Faces
        for fx1, fy1, fx2, fy2 in faces:
            cv2.rectangle(out, (fx1, fy1), (fx2, fy2), COLOR_FACE, 2)
            cv2.putText(out, "FACE", (fx1, max(15, fy1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_FACE, 1)

        # 4. Status HUD Banner (Top left)
        hud_bg = (20, 20, 20)
        cv2.rectangle(out, (10, 10), (340, 75), hud_bg, -1)
        cv2.rectangle(out, (10, 10), (340, 75), (80, 80, 80), 1)

        night_status = "NIGHT (CLAHE)" if is_night else "DAY (STANDARD)"
        night_color = COLOR_NIGHT if is_night else (100, 255, 100)
        cv2.putText(out, f"IBVAP | {self.camera_name}", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_TEXT, 2)
        cv2.putText(out, f"Mode: {night_status}", (20, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.45, night_color, 1)
        cv2.putText(out, f"Active Tracks: {len(tracks)} | Alerts: {len(self.alerts_history)}", (20, 68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)

        return out
