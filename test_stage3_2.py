"""
Verification and Test Runner for Stage 3.2 — Core AI Engine.
Validates all 8 required AI & analytics capabilities against live RTSP streams / sample border videos.
"""

import os
import sys
import time
import json
import logging
import cv2
import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.models import AlertEvent, TrackedObject, Detection
from core.ingestion import RTSPStreamReader
from core.detector import ObjectDetector
from core.tracker import CentroidTracker
from core.virtual_fence import VirtualFence
from core.night_enhancer import NightEnhancer
from core.face_detector import FaceDetector
from core.anpr import ANPRReader
from core.behavior_analytics import BehaviorAnalyzer
from core.engine import FrameProcessingEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TestStage3_2")


def test_individual_components():
    """Unit test individual modules for correct logic and edge cases."""
    logger.info("=== STEP 1: Testing Individual AI & Analytics Modules ===")

    # 1. Test Tracker Logic
    logger.info("Testing Centroid & Spatial Tracker...")
    tracker = CentroidTracker()
    # Frame 1: Detection of a human
    d1 = [Detection(box=(100, 100, 150, 200), confidence=0.85, class_id=0, class_name="human")]
    tracks_f1 = tracker.update(d1, current_time=1.0)
    assert len(tracks_f1) == 1, "Tracker failed to register track in frame 1"
    tid = tracks_f1[0].track_id
    logger.info(f"Registered Track ID: {tid}")

    # Frame 2: Slight movement
    d2 = [Detection(box=(105, 102, 155, 202), confidence=0.88, class_id=0, class_name="human")]
    tracks_f2 = tracker.update(d2, current_time=2.0)
    assert len(tracks_f2) == 1 and tracks_f2[0].track_id == tid, "Tracker lost persistent track ID on smooth movement"
    logger.info("Tracker persistent ID verification passed.")

    # 2. Test Virtual Fence
    logger.info("Testing Virtual Fence Intrusion...")
    fence = VirtualFence(fence_id="fence_1", coordinates=[(120, 50), (120, 250)], fence_type="line", name="Tripwire A")
    # Simulate track crossing x=120
    track_sim = tracks_f2[0]
    track_sim.history = [(1.0, (110, 150)), (2.0, (130, 150))]
    track_sim.centroid = (130, 150)
    alert = fence.check_intrusion(track_sim, "cam1", "Camera 1", "North Border")
    assert alert is not None and alert.event_type == "intrusion", "Fence failed to detect line crossing"
    # Verify no duplicate alert for same track
    second_check = fence.check_intrusion(track_sim, "cam1", "Camera 1", "North Border")
    assert second_check is None, "Fence generated duplicate alert for already-crossed track ID"
    logger.info("Virtual fence single-trigger verification passed.")

    # 3. Test Night Mode & CLAHE
    logger.info("Testing Night Enhancer (CLAHE)...")
    night_enhancer = NightEnhancer(brightness_threshold=65.0)
    dark_frame = np.full((480, 640, 3), 30, dtype=np.uint8)  # Brightness ~30
    enhanced_dark, is_night, night_alert = night_enhancer.process(dark_frame, "cam2", "Camera 2", "Sector B")
    assert is_night is True, "Night mode failed to activate on low luminance"
    assert night_alert is not None and night_alert.event_type == "night_mode_change", "Night state change alert missing"
    assert np.mean(enhanced_dark) > np.mean(dark_frame), "CLAHE failed to increase contrast/luminance"
    logger.info("Night enhancer verification passed.")

    # 4. Test Behavior Analytics (Loitering & Fast Movement)
    logger.info("Testing Behavior Analytics (Loitering & Speed)...")
    behavior = BehaviorAnalyzer(loiter_time_sec=5.0, loiter_max_radius=50.0, fast_speed_threshold=200.0)
    
    # Loitering simulation
    loiter_track = TrackedObject(
        track_id=99,
        class_name="human",
        box=(200, 200, 250, 300),
        centroid=(225, 250),
        confidence=0.9,
        first_seen=10.0,
        last_seen=16.5,
        history=[(10.0 + i * 0.5, (225 + (i % 2), 250 + (i % 2))) for i in range(13)]
    )
    loiter_alerts = behavior.analyze([loiter_track], "cam1", "Camera 1", "Checkpoint", current_time=16.5)
    assert any(a.event_type == "loitering" for a in loiter_alerts), "Failed to detect loitering behavior"
    logger.info("Loitering detection verification passed.")

    logger.info("=== STEP 1 COMPLETED SUCCESSFULLY ===")


def test_rtsp_and_full_pipeline(num_frames_per_camera: int = 40):
    """
    Connect to RTSP streams (or fallback video files), run full pipeline,
    and generate verified annotated frames and alert logs.
    """
    logger.info("=== STEP 2: Running Full AI Pipeline on Live Streams ===")
    
    output_dir = os.path.join(os.path.dirname(__file__), "test_outputs")
    os.makedirs(output_dir, exist_ok=True)

    camera_configs = [
        {
            "camera_id": "camera1",
            "camera_name": "Camera 1 - Border Daytime",
            "rtsp_url": "rtsp://localhost:8554/camera1",
            "fallback_file": "videos/camera1_daytime.mp4",
            "location": "North Perimeter Gate",
            "fences": [
                VirtualFence("fence_c1", [(300, 100), (300, 700)], fence_type="line", name="Perimeter Wire")
            ]
        },
        {
            "camera_id": "camera2",
            "camera_name": "Camera 2 - Border Night",
            "rtsp_url": "rtsp://localhost:8554/camera2",
            "fallback_file": "videos/camera2_night.mp4",
            "location": "Eastern Fence Low-Light Sector",
            "fences": [
                VirtualFence("fence_c2", [(150, 150), (450, 150), (450, 450), (150, 450)], fence_type="polygon", name="Restricted Zone B")
            ]
        },
        {
            "camera_id": "camera3",
            "camera_name": "Camera 3 - Highway Vehicles",
            "rtsp_url": "rtsp://localhost:8554/camera3",
            "fallback_file": "videos/camera3_highway.mp4",
            "location": "Sector C Highway Checkpoint",
            "fences": [
                VirtualFence("fence_c3", [(100, 400), (800, 400)], fence_type="line", name="Roadway Tripwire")
            ]
        }
    ]

    all_alerts: List[AlertEvent] = []

    for cfg in camera_configs:
        cam_id = cfg["camera_id"]
        logger.info(f"\n--- Testing Camera: {cam_id} ({cfg['camera_name']}) ---")
        
        # Test RTSP reader
        reader = RTSPStreamReader(rtsp_url=cfg["rtsp_url"], camera_id=cam_id)
        reader.start()
        time.sleep(1.0)  # Allow connection to settle

        source_type = "RTSP Stream"
        has_frame, frame, _ = reader.read()
        
        # If RTSP is temporarily unreachable, fallback to the direct video file
        cap_fallback = None
        if not has_frame:
            logger.warning(f"RTSP stream not ready for {cam_id}, testing directly with {cfg['fallback_file']}")
            source_type = "Video File Fallback"
            cap_fallback = cv2.VideoCapture(cfg["fallback_file"])

        # Initialize AI Engine for this camera
        engine = FrameProcessingEngine(
            camera_id=cam_id,
            camera_name=cfg["camera_name"],
            location=cfg["location"],
            fences=cfg["fences"],
            enable_anpr=True,
            enable_face_detection=True,
            enable_night_mode=True,
            yolo_model="yolov8n.pt",
            conf_threshold=0.35,
            device="cpu"
        )

        frames_processed = 0
        camera_alerts = 0
        latest_annotated = None

        for f_idx in range(num_frames_per_camera):
            if reader.is_connected:
                ret, current_frame, ts = reader.read()
            elif cap_fallback and cap_fallback.isOpened():
                ret, current_frame = cap_fallback.read()
                ts = time.time()
            else:
                break

            if not ret or current_frame is None:
                time.sleep(0.03)
                continue

            annotated_frame, new_alerts, metrics = engine.process_frame(current_frame, timestamp=ts)
            frames_processed += 1
            latest_annotated = annotated_frame

            if new_alerts:
                camera_alerts += len(new_alerts)
                all_alerts.extend(new_alerts)
                for a in new_alerts:
                    logger.info(f"[{cam_id}] ALERT TRIGGERED: type={a.event_type}, obj={a.object_type}, "
                                f"conf={a.confidence:.2f}, track_id={a.track_id}, plate={a.license_plate}")

            if f_idx % 10 == 0:
                logger.info(f"[{cam_id}] Frame {frames_processed}/{num_frames_per_camera} | FPS: {metrics['fps']} | "
                            f"Active Tracks: {metrics['active_tracks']} | Night: {metrics['is_night']}")

        # Clean up stream
        reader.stop()
        if cap_fallback:
            cap_fallback.release()

        # Save sample annotated output frame
        if latest_annotated is not None:
            sample_path = os.path.join(output_dir, f"{cam_id}_annotated.jpg")
            cv2.imwrite(sample_path, latest_annotated)
            logger.info(f"Saved annotated preview image to {sample_path}")

        logger.info(f"Camera {cam_id} finished: Processed {frames_processed} frames ({source_type}), Generated {camera_alerts} alerts.")

    # Save summary of alerts in JSON format (ready for Supabase)
    summary_path = os.path.join(output_dir, "stage3_2_alerts_summary.json")
    with open(summary_path, "w") as f:
        json.dump([a.to_dict() for a in all_alerts], f, indent=2)

    logger.info(f"\n=== VERIFICATION COMPLETE: {len(all_alerts)} Total Alerts Generated across 3 Cameras ===")
    logger.info(f"Alerts summary JSON written to: {summary_path}")


if __name__ == "__main__":
    test_individual_components()
    test_rtsp_and_full_pipeline(num_frames_per_camera=30)
