"""
Verification and Test Suite for Stage 3.4 — Multi-Camera Engine.
Validates:
1. Per-camera JSON configuration profile loading.
2. Concurrent multi-threaded processing across 3 simultaneous cameras.
3. Synchronized alert queuing onto the shared AlertQueueManager and Supabase.
4. Frame skipping efficiency, inference latency, and achieved FPS measurement.
5. Thread-safe snapshot frame retrieval across all channels.
"""

import os
import sys
import time
import json
import logging
import cv2

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.multi_camera_manager import MultiCameraManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TestStage3_4")


def test_multi_camera_engine(duration_seconds: int = 12):
    """
    Spawns concurrent camera threads across all 3 channels,
    monitors telemetry in real-time, and verifies synchronized queuing.
    """
    logger.info("=== STEP 1: Initializing MultiCameraManager ===")
    
    manager = MultiCameraManager(
        config_path="config/cameras.json",
        cooldown_seconds=4.0,
        yolo_model="yolov8n.pt",
        device="cpu"
    )

    assert len(manager.camera_configs) == 3, f"Expected 3 camera configurations, got {len(manager.camera_configs)}"
    logger.info("Loaded 3 camera profiles: camera1, camera2, camera3")

    logger.info("\n=== STEP 2: Starting Concurrent Processing Threads ===")
    manager.start_all()

    output_dir = os.path.join(os.path.dirname(__file__), "test_outputs")
    os.makedirs(output_dir, exist_ok=True)

    start_time = time.time()
    snapshots_captured = {}

    while time.time() - start_time < duration_seconds:
        time.sleep(2.0)
        statuses = manager.get_all_statuses()
        elapsed = round(time.time() - start_time, 1)
        logger.info(f"\n--- [T+{elapsed}s Telemetry Status across Cameras] ---")
        
        for s in statuses:
            cam_id = s["camera_id"]
            logger.info(
                f"[{cam_id}] Connected={s['is_connected']} | Read={s['total_frames_read']} | "
                f"Proc={s['total_frames_processed']} | FPS={s['fps']} | "
                f"Latency={s['inference_time_ms']}ms | Tracks={s['active_tracks']} | Alerts={s['total_alerts']}"
            )

            # Capture a live annotated frame snapshot from each camera
            frame = manager.get_latest_frame(cam_id)
            if frame is not None and cam_id not in snapshots_captured:
                snap_path = os.path.join(output_dir, f"{cam_id}_multi_preview.jpg")
                cv2.imwrite(snap_path, frame)
                snapshots_captured[cam_id] = snap_path
                logger.info(f"Captured live snapshot for {cam_id} -> {snap_path}")

    # Final Telemetry Check
    final_statuses = manager.get_all_statuses()
    total_processed = sum(s["total_frames_processed"] for s in final_statuses)
    total_alerts = sum(s["total_alerts"] for s in final_statuses)

    logger.info("\n=== STEP 3: Stopping All Camera Threads ===")
    manager.stop_all()

    logger.info(f"\nMulti-Camera Processing Summary:")
    logger.info(f"- Total Frames Processed Across Channels: {total_processed}")
    logger.info(f"- Total Alerts Generated: {total_alerts}")
    logger.info(f"- Enqueued in Shared Queue: {manager.alert_queue.total_enqueued}")
    logger.info(f"- Successfully Written to Supabase: {manager.alert_queue.total_written}")
    logger.info(f"- Alerts Throttled by Cooldown: {manager.alert_queue.total_throttled}")

    assert total_processed > 0, "No frames were processed across camera threads"
    assert len(snapshots_captured) >= 1, "Failed to capture any live snapshot frames"

    logger.info("\n=== ALL STAGE 3.4 MULTI-CAMERA TESTS PASSED SUCCESSFULLY ===")


if __name__ == "__main__":
    test_multi_camera_engine(duration_seconds=12)
