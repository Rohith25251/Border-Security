"""
Verification and Test Suite for Stage 3.5 — Backend API.
Tests all FastAPI endpoints using TestClient:
1. Root health & platform overview.
2. Cameras list and snapshot retrieval.
3. Alert retrieval, multi-filter querying, single-alert fetch, and status updates.
4. Statistics endpoint.
5. C2 Command & Control webhook registration, listing, and deletion.
"""

import os
import sys
import logging
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from api.app import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TestStage3_5")

client = TestClient(app)


def test_api_endpoints():
    logger.info("=== STEP 1: Testing Root & Camera Endpoints ===")
    
    # 1. Test Root (Dashboard HTML)
    res_root = client.get("/")
    assert res_root.status_code == 200, f"Root endpoint failed: {res_root.text}"
    assert "IBVAP" in res_root.text
    logger.info("GET / passed: Successfully served Web Dashboard HTML.")

    # Test /api/health
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    data_health = res_health.json()
    assert data_health["status"] == "online"
    logger.info(f"GET /api/health passed: status='{data_health['status']}', supabase_connected={data_health['supabase_connected']}")

    # 2. Test GET /api/cameras
    res_cams = client.get("/api/cameras")
    assert res_cams.status_code == 200, f"GET /api/cameras failed: {res_cams.text}"
    cams = res_cams.json()
    assert len(cams) >= 3, f"Expected at least 3 cameras, got {len(cams)}"
    logger.info(f"GET /api/cameras passed: Found {len(cams)} camera profiles.")

    # 3. Test GET /api/cameras/camera1/snapshot
    res_snap = client.get("/api/cameras/camera1/snapshot")
    logger.info(f"GET /api/cameras/camera1/snapshot status: {res_snap.status_code}")

    logger.info("\n=== STEP 2: Testing Alert Endpoints ===")
    
    # 4. Test GET /api/alerts
    res_alerts = client.get("/api/alerts?limit=10")
    assert res_alerts.status_code == 200, f"GET /api/alerts failed: {res_alerts.text}"
    alerts = res_alerts.json()
    logger.info(f"GET /api/alerts passed: Retrieved {len(alerts)} alerts.")

    target_alert_id = None
    if len(alerts) > 0:
        target_alert_id = alerts[0]["id"]
        # 5. Test GET /api/alerts/{id}
        res_single = client.get(f"/api/alerts/{target_alert_id}")
        assert res_single.status_code == 200, f"GET /api/alerts/{target_alert_id} failed: {res_single.text}"
        logger.info(f"GET /api/alerts/{target_alert_id} passed: {res_single.json()['event_type']}")

        # 6. Test PUT /api/alerts/{id}/status
        res_update = client.put(f"/api/alerts/{target_alert_id}/status", json={"status": "acknowledged"})
        assert res_update.status_code == 200, f"PUT status update failed: {res_update.text}"
        assert res_update.json()["status"] == "acknowledged"
        logger.info(f"PUT /api/alerts/{target_alert_id}/status passed: new status = acknowledged")

    logger.info("\n=== STEP 3: Testing Statistics Endpoint ===")
    
    # 7. Test GET /api/stats
    res_stats = client.get("/api/stats")
    assert res_stats.status_code == 200, f"GET /api/stats failed: {res_stats.text}"
    stats = res_stats.json()
    assert "total_alerts" in stats and "by_event_type" in stats
    logger.info(f"GET /api/stats passed: Total Alerts = {stats['total_alerts']}, Event Types = {list(stats['by_event_type'].keys())}")

    logger.info("\n=== STEP 4: Testing C2 Webhook Management ===")
    
    # 8. Test POST /api/c2/webhook-config
    webhook_payload = {
        "webhook_url": "https://c2-command.border-patrol.mil/alerts",
        "description": "Sector HQ Integration Webhook",
        "secret_token": "c2-secret-key-xyz"
    }
    res_post_hook = client.post("/api/c2/webhook-config", json=webhook_payload)
    assert res_post_hook.status_code == 200, f"POST /api/c2/webhook-config failed: {res_post_hook.text}"
    hook_data = res_post_hook.json()
    hook_id = hook_data["id"]
    logger.info(f"POST /api/c2/webhook-config passed: registered webhook {hook_id}")

    # 9. Test GET /api/c2/webhook-config
    res_list_hooks = client.get("/api/c2/webhook-config")
    assert res_list_hooks.status_code == 200, f"GET /api/c2/webhook-config failed: {res_list_hooks.text}"
    hooks = res_list_hooks.json()
    assert any(h["id"] == hook_id for h in hooks)
    logger.info(f"GET /api/c2/webhook-config passed: {len(hooks)} active webhook(s)")

    # 10. Test DELETE /api/c2/webhook-config/{id}
    res_del_hook = client.delete(f"/api/c2/webhook-config/{hook_id}")
    assert res_del_hook.status_code == 200, f"DELETE /api/c2/webhook-config/{hook_id} failed: {res_del_hook.text}"
    logger.info(f"DELETE /api/c2/webhook-config/{hook_id} passed.")

    logger.info("\n=== ALL STAGE 3.5 API TESTS PASSED SUCCESSFULLY ===")


if __name__ == "__main__":
    with client:
        test_api_endpoints()
