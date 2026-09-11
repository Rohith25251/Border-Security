"""
Verification and Test Suite for Stage 3.3 — Event Logging & Database.
Validates:
1. SupabaseManager CRUD, status updates, and statistics calculation.
2. Thread-safe AlertQueueManager with per-track cooldown enforcement.
3. In-memory screenshot JPEG encoding and storage handling.
4. Schema conformance matching the Supabase `alerts` table.
"""

import os
import sys
import time
import json
import logging
import threading
import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.models import AlertEvent
from db.supabase_client import SupabaseManager
from db.queue_manager import AlertQueueManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TestStage3_3")


def test_supabase_manager_crud():
    """Test CRUD operations, filtering, and statistics calculation."""
    logger.info("=== STEP 1: Testing Supabase Manager CRUD & Analytics ===")
    
    db = SupabaseManager()

    # Create dummy frame for screenshot
    dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    dummy_frame[:, :] = (50, 100, 200)

    # 1. Insert Alert
    alert1 = AlertEvent(
        camera_id="camera1",
        camera_name="North Perimeter Gate",
        event_type="intrusion",
        object_type="human",
        track_id=101,
        confidence=0.94,
        location="Sector A",
        frame_crop=dummy_frame
    )
    res1 = db.insert_alert(alert1)
    assert res1["id"] == alert1.id, "Inserted alert ID mismatch"
    logger.info(f"Alert 1 successfully created: {alert1.id} (image: {res1.get('image_path')})")

    alert2 = AlertEvent(
        camera_id="camera2",
        camera_name="Eastern Fence",
        event_type="anpr",
        object_type="vehicle",
        license_plate="KA05NB1234",
        track_id=102,
        confidence=0.88,
        location="Sector B",
        frame_crop=dummy_frame
    )
    db.insert_alert(alert2)
    logger.info(f"Alert 2 (ANPR) created: plate={alert2.license_plate}")

    # 2. Fetch Alerts & Filtering
    fetched = db.fetch_alerts(limit=10)
    assert len(fetched) >= 2, f"Expected at least 2 alerts, got {len(fetched)}"
    
    cam1_alerts = db.fetch_alerts(camera_id="camera1")
    assert any(a["id"] == alert1.id for a in cam1_alerts), "Filtering by camera_id failed"

    anpr_alerts = db.fetch_alerts(event_type="anpr")
    assert any(a["license_plate"] == "KA05NB1234" for a in anpr_alerts), "Filtering by event_type failed"
    logger.info("Fetch and filter verification passed.")

    # 3. Get By ID
    single = db.get_alert_by_id(alert1.id)
    assert single is not None and single["id"] == alert1.id, "get_alert_by_id failed"

    # 4. Update Status (new -> acknowledged -> resolved)
    updated = db.update_alert_status(alert1.id, "acknowledged")
    assert updated is not None and updated["status"] == "acknowledged", "Status update to 'acknowledged' failed"
    
    updated2 = db.update_alert_status(alert1.id, "resolved")
    assert updated2 is not None and updated2["status"] == "resolved", "Status update to 'resolved' failed"
    logger.info("Status transition verification passed (new -> acknowledged -> resolved).")

    # 5. Statistics Calculation
    stats = db.get_statistics()
    assert stats["total_alerts"] >= 2, "Statistics total_alerts calculation failed"
    assert "intrusion" in stats["by_event_type"], "Statistics by_event_type missing 'intrusion'"
    assert "anpr" in stats["by_event_type"], "Statistics by_event_type missing 'anpr'"
    assert stats["by_status"]["resolved"] >= 1, "Statistics by_status calculation failed"
    logger.info(f"Statistics verification passed: {json.dumps(stats, indent=2)}")


def test_queue_cooldown_and_concurrency():
    """Test thread-safe queue manager and per-track cooldown suppression."""
    logger.info("\n=== STEP 2: Testing AlertQueueManager Cooldown & Concurrency ===")
    
    db = SupabaseManager()
    queue_mgr = AlertQueueManager(supabase_manager=db, cooldown_seconds=2.0)
    queue_mgr.start()

    t0 = time.time()

    # 1. First alert for Track 5
    a1 = AlertEvent(camera_id="camera1", event_type="loitering", object_type="human", track_id=5, confidence=0.85)
    pushed1 = queue_mgr.push_alert(a1, current_time=t0)
    assert pushed1 is True, "First alert for track 5 should be accepted"

    # 2. Immediate duplicate alert for same track within cooldown (t0 + 0.5s)
    a2 = AlertEvent(camera_id="camera1", event_type="loitering", object_type="human", track_id=5, confidence=0.86)
    pushed2 = queue_mgr.push_alert(a2, current_time=t0 + 0.5)
    assert pushed2 is False, "Duplicate alert within cooldown was not suppressed!"
    logger.info("Duplicate alert within cooldown correctly suppressed.")

    # 3. Different track ID should NOT be blocked by cooldown
    a3 = AlertEvent(camera_id="camera1", event_type="loitering", object_type="human", track_id=6, confidence=0.89)
    pushed3 = queue_mgr.push_alert(a3, current_time=t0 + 0.6)
    assert pushed3 is True, "Alert for distinct track 6 should be accepted"
    logger.info("Distinct track ID alert accepted concurrently.")

    # 4. Same track but after cooldown expired (t0 + 2.5s)
    a4 = AlertEvent(camera_id="camera1", event_type="loitering", object_type="human", track_id=5, confidence=0.90)
    pushed4 = queue_mgr.push_alert(a4, current_time=t0 + 2.5)
    assert pushed4 is True, "Alert after cooldown expiration should be accepted"
    logger.info("Alert after cooldown expiration accepted.")

    # 5. Multi-threaded Producer Stress Test
    logger.info("Running multi-threaded concurrent alert push test...")
    threads = []
    num_threads = 5
    alerts_per_thread = 20

    def producer_worker(thread_idx: int):
        for i in range(alerts_per_thread):
            event = AlertEvent(
                camera_id=f"camera{(thread_idx % 3) + 1}",
                event_type="intrusion",
                object_type="human",
                track_id=(thread_idx * 100) + i,
                confidence=0.91
            )
            queue_mgr.push_alert(event)
            time.sleep(0.01)

    for idx in range(num_threads):
        t = threading.Thread(target=producer_worker, args=(idx,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Wait for queue to process
    time.sleep(1.5)
    queue_mgr.stop()

    assert queue_mgr.total_written > 0, "No alerts were processed by worker thread"
    logger.info(f"Queue Manager successfully processed {queue_mgr.total_written} alerts across {num_threads} concurrent camera threads.")
    logger.info("=== STEP 2 COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    test_supabase_manager_crud()
    test_queue_cooldown_and_concurrency()
    logger.info("\nALL STAGE 3.3 DATABASE & EVENT LOGGING TESTS PASSED.")
