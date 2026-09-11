"""
FastAPI Application for IBVAP (Intelligent Border Video Analytics Platform).
Provides REST endpoints, live MJPEG video streaming, and C2 webhook integration.
"""

import os
import io
import cv2
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Path, Body, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
import numpy as np

try:
    cv2.setNumThreads(1)
except Exception:
    pass

from core.models import AlertEvent, PersonRecord
from core.multi_camera_manager import MultiCameraManager
from db.supabase_client import SupabaseManager
from api.schemas import (
    AlertResponse,
    AlertStatusUpdate,
    CameraStatusResponse,
    StatsResponse,
    WebhookConfigRequest,
    WebhookConfigResponse,
    PersonCreateRequest,
    PersonUpdateRequest,
    PersonResponse,
)
from api.c2_webhook import C2WebhookDispatcher

logger = logging.getLogger("IBVAP_API")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Global System Managers
supabase_mgr = SupabaseManager()
c2_dispatcher = C2WebhookDispatcher()
camera_manager = MultiCameraManager(
    config_path="config/cameras.json",
    supabase_manager=supabase_mgr,
    cooldown_seconds=4.0
)

# Intercept queue writes to also trigger C2 webhooks
original_insert = supabase_mgr.insert_alert


def hooked_insert_alert(alert: AlertEvent) -> Dict[str, Any]:
    res = original_insert(alert)
    # Asynchronously dispatch to registered C2 webhooks
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(c2_dispatcher.dispatch_alert(res))
    except Exception:
        pass
    return res


supabase_mgr.insert_alert = hooked_insert_alert


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager: starts cameras on boot, gracefully stops on termination."""
    logger.info("Starting IBVAP Backend API & Multi-Camera Engine...")
    camera_manager.start_all()
    yield
    logger.info("Shutting down IBVAP Backend API & Camera Engine...")
    camera_manager.stop_all()


app = FastAPI(
    title="IBVAP — Intelligent Border Video Analytics Platform API",
    description="Software-defined AI surveillance platform turning CCTV streams into intelligent border security monitoring.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for Web Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# 1. System Health & Dashboard Frontend (React Single Page App)
# ==============================================================================
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
dist_dir = os.path.join(base_dir, "frontend", "dist")
frontend_dir = dist_dir if os.path.exists(dist_dir) else os.path.join(base_dir, "frontend")
assets_dir = os.path.join(dist_dir, "assets")

# Mount React static assets (/assets/...)
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="react_assets")

if os.path.exists(dist_dir):
    app.mount("/dashboard", StaticFiles(directory=dist_dir, html=True), name="frontend_dist")
elif os.path.exists(frontend_dir):
    app.mount("/dashboard", StaticFiles(directory=frontend_dir, html=True), name="frontend")


@app.get("/", tags=["System"])
async def root():
    """Serves the IBVAP Operations Web Dashboard (React Single Page App)."""
    dist_index = os.path.join(base_dir, "frontend", "dist", "index.html")
    if os.path.exists(dist_index):
        return FileResponse(
            dist_index,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    fallback_index = os.path.join(base_dir, "frontend", "index.html")
    if os.path.exists(fallback_index):
        return FileResponse(fallback_index)
    return {
        "platform": "IBVAP — Intelligent Border Video Analytics Platform",
        "status": "online",
        "version": "1.0.0",
        "supabase_connected": supabase_mgr.is_connected,
        "active_cameras": len(camera_manager.workers),
        "timestamp": time.time()
    }


@app.get("/api/health", tags=["System"])
async def health_check():
    """API health status and diagnostics."""
    return {
        "status": "online",
        "platform": "IBVAP",
        "supabase_connected": supabase_mgr.is_connected,
        "active_cameras": len(camera_manager.workers),
        "timestamp": time.time()
    }


# ==============================================================================
# 2. Camera Management & Live Video Feeds
# ==============================================================================
@app.get("/api/cameras", response_model=List[CameraStatusResponse], tags=["Cameras"])
async def get_cameras():
    """List all registered cameras with real-time telemetry metrics."""
    return camera_manager.get_all_statuses()


def generate_mjpeg_stream(camera_id: str, mode: str = "hud"):
    """
    Generator for streaming live MJPEG frames with instant transmission and zero lag.
    - mode="hud": real-time AI bounding box HUD (Live Detection pipeline)
    - mode="raw": direct CCTV stream at exact native camera feed FPS
    """
    worker = camera_manager.get_worker(camera_id)
    if not worker:
        return

    encode_params = [cv2.IMWRITE_JPEG_QUALITY, 75]

    while worker.is_running:
        if mode == "raw":
            frame = worker.get_latest_raw_frame()
        else:
            frame = worker.get_latest_annotated_frame()

        if frame is None:
            # Fallback blank frame with 'Connecting...' placeholder
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            msg = f"Direct CCTV: Connecting to {camera_id}..." if mode == "raw" else f"Connecting to {camera_id}..."
            cv2.putText(frame, msg, (50, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
            success, buffer = cv2.imencode('.jpg', frame, encode_params)
            if success:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.05)
            continue

        # Fast JPEG encoding for instantaneous transmission
        success, buffer = cv2.imencode('.jpg', frame, encode_params)
        if not success:
            time.sleep(0.002)
            continue

        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # Ultra-low yield sleep (2ms) to prevent CPU thrashing while delivering maximum FPS
        time.sleep(0.002)


@app.get("/api/cameras/{camera_id}/stream", tags=["Cameras"])
async def stream_camera(
    camera_id: str = Path(..., description="Camera ID"),
    mode: str = Query("hud", description="Stream mode: 'hud' (AI overlays) or 'raw' (direct feed)")
):
    """Live MJPEG video stream with AI analytics overlays (hud) or clean direct CCTV (raw)."""
    worker = camera_manager.get_worker(camera_id)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")

    return StreamingResponse(
        generate_mjpeg_stream(camera_id, mode=mode),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/cameras/{camera_id}/raw-stream", tags=["Cameras"])
async def stream_camera_raw(camera_id: str = Path(..., description="Camera ID")):
    """Live MJPEG direct raw CCTV stream at native FPS without AI annotations."""
    worker = camera_manager.get_worker(camera_id)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")

    return StreamingResponse(
        generate_mjpeg_stream(camera_id, mode="raw"),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/cameras/{camera_id}/snapshot", tags=["Cameras"])
async def get_camera_snapshot(
    camera_id: str = Path(..., description="Camera ID"),
    mode: str = Query("hud", description="Snapshot mode: 'hud' or 'raw'")
):
    """Retrieve the latest snapshot (annotated or raw) as a JPEG image."""
    if mode == "raw":
        frame = camera_manager.get_latest_raw_frame(camera_id)
    else:
        frame = camera_manager.get_latest_frame(camera_id)

    if frame is None:
        raise HTTPException(status_code=404, detail=f"No frame currently available for camera '{camera_id}'")

    success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not success:
        raise HTTPException(status_code=500, detail="Failed to encode frame")

    return Response(content=buffer.tobytes(), media_type="image/jpeg")


# ==============================================================================
# 3. Alert Management & Real-time Logs
# ==============================================================================
@app.get("/api/alerts", response_model=List[AlertResponse], tags=["Alerts"])
async def get_alerts(
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    status: Optional[str] = Query(None, description="Filter by status (new, acknowledged, resolved)")
):
    """Retrieve alerts with multi-criteria filtering, sorted newest first."""
    alerts = supabase_mgr.fetch_alerts(
        limit=limit,
        offset=offset,
        camera_id=camera_id,
        event_type=event_type,
        status=status
    )
    return alerts


@app.get("/api/alerts/{alert_id}", response_model=AlertResponse, tags=["Alerts"])
async def get_alert_by_id(alert_id: str = Path(..., description="Alert UUID")):
    """Retrieve a single alert record by UUID."""
    alert = supabase_mgr.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return alert


@app.put("/api/alerts/{alert_id}/status", response_model=AlertResponse, tags=["Alerts"])
async def update_alert_status(
    alert_id: str = Path(..., description="Alert UUID"),
    body: AlertStatusUpdate = Body(...)
):
    """Update alert status ('new' -> 'acknowledged' -> 'resolved')."""
    valid_statuses = ["new", "acknowledged", "resolved"]
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status '{body.status}'. Must be one of {valid_statuses}")

    updated = supabase_mgr.update_alert_status(alert_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return updated


@app.get("/api/alerts/image/{filename}", tags=["Alerts"])
async def get_alert_image(filename: str = Path(..., description="Image filename")):
    """Image proxy retrieving alert screenshot from Supabase Storage or local cache."""
    # Check test_outputs local cache
    local_path = os.path.join("test_outputs", filename)
    if os.path.exists(local_path):
        return FileResponse(local_path, media_type="image/jpeg")

    # If Supabase is connected, redirect to public Supabase Storage URL
    if supabase_mgr.is_connected:
        public_url = f"{supabase_mgr.supabase_url}/storage/v1/object/public/{supabase_mgr.bucket_name}/alerts/{filename}"
        return JSONResponse({"url": public_url})

    raise HTTPException(status_code=404, detail="Image not found")


# ==============================================================================
# 4. Statistics & Analytics
# ==============================================================================
@app.get("/api/stats", response_model=StatsResponse, tags=["Analytics"])
async def get_statistics():
    """Retrieve aggregate surveillance metrics across all cameras and event types."""
    stats = supabase_mgr.get_statistics()
    return stats


# ==============================================================================
# 5. Command & Control (C2) Webhook Integration
# ==============================================================================
@app.post("/api/c2/webhook-config", response_model=WebhookConfigResponse, tags=["C2 Integration"])
async def register_c2_webhook(config: WebhookConfigRequest):
    """
    Register an external Command & Control (C2) webhook endpoint.
    IBVAP forwards every newly detected security event to registered webhooks in real time.
    """
    record = c2_dispatcher.register_webhook(
        webhook_url=config.webhook_url,
        description=config.description or "C2 System",
        secret_token=config.secret_token
    )
    return record


@app.get("/api/c2/webhook-config", response_model=List[WebhookConfigResponse], tags=["C2 Integration"])
async def list_c2_webhooks():
    """List all registered Command & Control (C2) webhook endpoints."""
    return c2_dispatcher.list_webhooks()


@app.delete("/api/c2/webhook-config/{webhook_id}", tags=["C2 Integration"])
async def delete_c2_webhook(webhook_id: str = Path(..., description="Webhook ID")):
    """Deregister an external C2 webhook endpoint."""
    success = c2_dispatcher.delete_webhook(webhook_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Webhook '{webhook_id}' not found")
    return {"status": "deleted", "id": webhook_id}


# ==============================================================================
# 6. Person Records & Profile Management (Name, DOB, Description, Image)
# ==============================================================================
@app.get("/api/persons", response_model=List[PersonResponse], tags=["Persons"])
async def get_persons(
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    search: Optional[str] = Query(None, description="Search by name or description")
):
    """Retrieve list of registered person profiles."""
    records = supabase_mgr.fetch_persons(
        limit=limit,
        offset=offset,
        search_query=search
    )
    return records


@app.post("/api/persons", response_model=PersonResponse, tags=["Persons"])
async def create_person(body: PersonCreateRequest = Body(...)):
    """Add a new person profile (Name, DOB, Description, Image)."""
    record = PersonRecord(
        name=body.name,
        dob=body.dob or "",
        description=body.description or "",
        image_url=body.image_url or body.face_image_url or "",
        face_image_url=body.image_url or body.face_image_url or ""
    )
    res = supabase_mgr.insert_person(record)
    return res


@app.patch("/api/persons/{person_id}", response_model=PersonResponse, tags=["Persons"])
async def update_person(
    person_id: str = Path(..., description="Person ID"),
    body: PersonUpdateRequest = Body(...)
):
    """Update person details (Name, DOB, Description, Image)."""
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.dob is not None:
        updates["dob"] = body.dob
    if body.description is not None:
        updates["description"] = body.description
    if body.image_url is not None:
        updates["image_url"] = body.image_url
        updates["face_image_url"] = body.image_url

    updated = supabase_mgr.update_person(person_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found")
    return updated


@app.delete("/api/persons/{person_id}", tags=["Persons"])
async def delete_person(person_id: str = Path(..., description="Person ID")):
    """
    Permanently delete a person record from the database and remove associated photo.
    """
    success = supabase_mgr.delete_person(person_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Failed to delete person '{person_id}'")
    return {"status": "deleted", "id": person_id}


@app.get("/api/persons/image/{folder}/{filename}", tags=["Persons of Interest"])
async def get_person_image(
    folder: str = Path(..., description="Image folder ('faces' or 'full')"),
    filename: str = Path(..., description="Image filename")
):
    """Retrieve person thumbnail or full context frame image."""
    local_path = os.path.join("test_outputs", folder, filename)
    if os.path.exists(local_path):
        return FileResponse(local_path, media_type="image/jpeg")

    alt_path = os.path.join("test_outputs", filename)
    if os.path.exists(alt_path):
        return FileResponse(alt_path, media_type="image/jpeg")

    if supabase_mgr.is_connected:
        public_url = f"{supabase_mgr.supabase_url}/storage/v1/object/public/{supabase_mgr.persons_bucket}/{folder}/{filename}"
        return JSONResponse({"url": public_url})

    raise HTTPException(status_code=404, detail="Person image not found")

