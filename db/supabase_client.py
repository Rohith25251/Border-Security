"""
Supabase Database and Storage Client for IBVAP.
Handles direct CRUD operations on the `alerts` table and JPEG screenshot uploads to Supabase Storage.
"""

import os
import cv2
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import numpy as np
from dotenv import load_dotenv

from core.models import AlertEvent

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "alert-images")


class SupabaseManager:
    """
    Manager for interacting with Supabase Postgres database and Storage bucket.
    """

    def __init__(self, supabase_url: str = None, supabase_key: str = None, bucket_name: str = None):
        self.supabase_url = supabase_url or SUPABASE_URL
        self.supabase_key = supabase_key or SUPABASE_KEY
        self.bucket_name = bucket_name or STORAGE_BUCKET
        self.client = None
        self.is_connected = False

        # Local fallback buffer for offline or mock mode
        self.local_alerts: List[Dict[str, Any]] = []

        self._init_client()

    def _init_client(self):
        """Initialize the Supabase client."""
        if not self.supabase_url or not self.supabase_key or "your-project-id" in self.supabase_url:
            logger.warning("Supabase credentials not configured or placeholder detected in .env. Running in offline/mock mode.")
            self.is_connected = False
            return

        try:
            from supabase import create_client, Client
            self.client: Client = create_client(self.supabase_url, self.supabase_key)
            self.is_connected = True
            logger.info(f"Supabase client successfully initialized for {self.supabase_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}. Falling back to local mode.")
            self.is_connected = False

    def upload_screenshot(self, frame: np.ndarray, file_name: str) -> str:
        """
        Compresses an in-memory frame as JPEG, saves a local cached copy in test_outputs/
        and uploads it to the Supabase Storage bucket if connected.
        Returns the public URL or relative image filename.
        """
        if frame is None or frame.size == 0:
            return ""

        # Ensure local test_outputs directory exists
        os.makedirs("test_outputs", exist_ok=True)
        local_path = os.path.join("test_outputs", file_name)

        # Encode and save locally for 100% reliable local preview
        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            logger.error(f"Failed to encode screenshot {file_name} to JPEG")
            return ""

        file_bytes = buffer.tobytes()
        try:
            with open(local_path, "wb") as f:
                f.write(file_bytes)
        except Exception as e:
            logger.error(f"Failed to write local image cache {local_path}: {e}")

        # Upload to Supabase Storage if connected
        if self.is_connected and self.client is not None:
            try:
                storage_path = f"alerts/{file_name}"
                res = self.client.storage.from_(self.bucket_name).upload(
                    path=storage_path,
                    file=file_bytes,
                    file_options={"content-type": "image/jpeg", "x-upsert": "true"}
                )
                public_url = self.client.storage.from_(self.bucket_name).get_public_url(storage_path)
                logger.info(f"Screenshot uploaded to Supabase Storage: {public_url}")
                return public_url
            except Exception as e:
                logger.error(f"Supabase storage upload failed: {e}. Using local cache.")
                return file_name
        else:
            return file_name

    def insert_alert(self, alert: AlertEvent) -> Dict[str, Any]:
        """
        Uploads screenshot (if attached) and inserts the alert into Supabase `alerts` table.
        """
        alert_dict = alert.to_dict()

        # Handle screenshot upload if a frame crop/screenshot exists
        if alert.frame_crop is not None and not alert_dict.get("image_path"):
            ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            file_name = f"{alert.camera_id}_{alert.event_type}_{ts_str}_{alert.id[:8]}.jpg"
            image_url = self.upload_screenshot(alert.frame_crop, file_name)
            alert_dict["image_path"] = image_url or file_name
            alert.image_path = image_url or file_name

        if self.is_connected and self.client is not None:
            try:
                response = self.client.table("alerts").insert(alert_dict).execute()
                if response.data and len(response.data) > 0:
                    logger.info(f"Alert [{alert.id[:8]}] inserted into Supabase `alerts` table.")
                    return response.data[0]
                return alert_dict
            except Exception as e:
                logger.error(f"Failed to insert alert into Supabase: {e}")
                self.local_alerts.append(alert_dict)
                return alert_dict
        else:
            self.local_alerts.append(alert_dict)
            logger.info(f"[Offline Mode] Alert [{alert.id[:8]}] recorded locally.")
            return alert_dict

    def fetch_alerts(
        self,
        limit: int = 50,
        offset: int = 0,
        camera_id: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch alerts from Supabase with optional filtering, sorted by timestamp descending.
        """
        if self.is_connected and self.client is not None:
            try:
                query = self.client.table("alerts").select("*").order("timestamp", desc=True)
                if camera_id:
                    query = query.eq("camera_id", camera_id)
                if event_type:
                    query = query.eq("event_type", event_type)
                if status:
                    query = query.eq("status", status)

                query = query.range(offset, offset + limit - 1)
                response = query.execute()
                return response.data if response.data is not None else []
            except Exception as e:
                logger.error(f"Error fetching alerts from Supabase: {e}")
                return self._filter_local_alerts(limit, offset, camera_id, event_type, status)
        else:
            return self._filter_local_alerts(limit, offset, camera_id, event_type, status)

    def _filter_local_alerts(
        self,
        limit: int,
        offset: int,
        camera_id: Optional[str],
        event_type: Optional[str],
        status: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Filter in-memory local alerts when offline."""
        filtered = list(self.local_alerts)
        if camera_id:
            filtered = [a for a in filtered if a.get("camera_id") == camera_id]
        if event_type:
            filtered = [a for a in filtered if a.get("event_type") == event_type]
        if status:
            filtered = [a for a in filtered if a.get("status") == status]

        filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return filtered[offset:offset + limit]

    def get_alert_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single alert by its UUID."""
        if self.is_connected and self.client is not None:
            try:
                res = self.client.table("alerts").select("*").eq("id", alert_id).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]
                return None
            except Exception as e:
                logger.error(f"Error getting alert by ID: {e}")
                return None
        else:
            for a in self.local_alerts:
                if a.get("id") == alert_id:
                    return a
            return None

    def update_alert_status(self, alert_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        """
        Update alert status ('new' -> 'acknowledged' -> 'resolved').
        """
        if new_status not in ["new", "acknowledged", "resolved"]:
            raise ValueError(f"Invalid status '{new_status}'. Must be 'new', 'acknowledged', or 'resolved'.")

        if self.is_connected and self.client is not None:
            try:
                res = self.client.table("alerts").update({"status": new_status}).eq("id", alert_id).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]
                return None
            except Exception as e:
                logger.error(f"Error updating alert status in Supabase: {e}")
                return None
        else:
            for a in self.local_alerts:
                if a.get("id") == alert_id:
                    a["status"] = new_status
                    return a
            return None

    def get_statistics(self) -> Dict[str, Any]:
        """
        Calculate summary metrics: total alerts, breakdown by event_type, status, and camera.
        """
        alerts = self.fetch_alerts(limit=1000)

        total_alerts = len(alerts)
        by_event_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {"new": 0, "acknowledged": 0, "resolved": 0}
        by_camera: Dict[str, int] = {}

        for a in alerts:
            etype = a.get("event_type", "unknown")
            stat = a.get("status", "new")
            cam = a.get("camera_id", "unknown")

            by_event_type[etype] = by_event_type.get(etype, 0) + 1
            by_status[stat] = by_status.get(stat, 0) + 1
            by_camera[cam] = by_camera.get(cam, 0) + 1

        return {
            "total_alerts": total_alerts,
            "by_event_type": by_event_type,
            "by_status": by_status,
            "by_camera": by_camera,
            "is_supabase_connected": self.is_connected
        }
