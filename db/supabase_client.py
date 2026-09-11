"""
Supabase Database and Storage Client for IBVAP.
Handles direct CRUD operations on the `alerts` table and JPEG screenshot uploads to Supabase Storage.
"""

import os
import cv2
import time
import uuid
import base64
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import numpy as np
from dotenv import load_dotenv

from core.models import AlertEvent, PersonRecord

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "alert-images")
PERSONS_BUCKET = os.getenv("SUPABASE_PERSONS_BUCKET", "person-records")


class SupabaseManager:
    """
    Manager for interacting with Supabase Postgres database and Storage buckets
    (`alerts`, `persons_of_interest`, `alert-images`, `person-records`).
    """

    def __init__(self, supabase_url: str = None, supabase_key: str = None, bucket_name: str = None, persons_bucket: str = None):
        self.supabase_url = supabase_url or SUPABASE_URL
        self.supabase_key = supabase_key or SUPABASE_KEY
        self.bucket_name = bucket_name or STORAGE_BUCKET
        self.persons_bucket = persons_bucket or PERSONS_BUCKET
        self.client = None
        self.is_connected = False

        # Local fallback buffer and high-speed memory caches
        self.local_alerts: List[Dict[str, Any]] = []
        self.local_persons: List[Dict[str, Any]] = []
        self.cached_persons: Optional[List[Dict[str, Any]]] = None
        self.cached_persons_time: float = 0.0

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

    def upload_screenshot(self, frame: np.ndarray, file_name: str, bucket: str = None, folder: str = "alerts") -> str:
        """
        Compresses an in-memory frame as JPEG, saves a local cached copy in test_outputs/
        and uploads it to the Supabase Storage bucket if connected.
        Returns the public URL or relative image filename.
        """
        if frame is None or frame.size == 0:
            return ""

        target_bucket = bucket or self.bucket_name
        local_dir = os.path.join("test_outputs", folder)
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, file_name)

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
                storage_path = f"{folder}/{file_name}"
                res = self.client.storage.from_(target_bucket).upload(
                    path=storage_path,
                    file=file_bytes,
                    file_options={"content-type": "image/jpeg", "x-upsert": "true"}
                )
                public_url = self.client.storage.from_(target_bucket).get_public_url(storage_path)
                logger.info(f"Image uploaded to Supabase Storage [{target_bucket}]: {public_url}")
                return public_url
            except Exception as e:
                logger.error(f"Supabase storage upload failed to [{target_bucket}]: {e}. Using local cache.")
                return f"/api/persons/image/{folder}/{file_name}"
        else:
            return f"/api/persons/image/{folder}/{file_name}"

    def upload_base64_image(self, base64_str: str, file_name: str, bucket: str = None, folder: str = "faces") -> str:
        """Decode base64 image data URL, save locally and upload to Supabase Storage."""
        if not base64_str or not base64_str.startswith("data:image/"):
            return base64_str

        try:
            header, encoded = base64_str.split(",", 1)
            image_bytes = base64.b64decode(encoded)

            target_bucket = bucket or self.persons_bucket
            local_dir = os.path.join("test_outputs", folder)
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, file_name)

            with open(local_path, "wb") as f:
                f.write(image_bytes)

            if self.is_connected and self.client is not None:
                try:
                    storage_path = f"{folder}/{file_name}"
                    self.client.storage.from_(target_bucket).upload(
                        path=storage_path,
                        file=image_bytes,
                        file_options={"content-type": "image/jpeg", "x-upsert": "true"}
                    )
                    public_url = self.client.storage.from_(target_bucket).get_public_url(storage_path)
                    logger.info(f"Base64 image uploaded to Supabase Storage [{target_bucket}]: {public_url}")
                    return public_url
                except Exception as e:
                    logger.warning(f"Failed to upload decoded base64 to Supabase storage: {e}. Using local proxy.")
                    return f"/api/persons/image/{folder}/{file_name}"
            else:
                return f"/api/persons/image/{folder}/{file_name}"
        except Exception as e:
            logger.error(f"Failed to process base64 image: {e}")
            return ""

    def insert_alert(self, alert: AlertEvent) -> Dict[str, Any]:
        """
        Uploads screenshot (if attached) and inserts the alert into Supabase `alerts` table.
        """
        alert_dict = alert.to_dict()

        # Handle screenshot upload if a frame crop/screenshot exists
        if alert.frame_crop is not None and not alert_dict.get("image_path"):
            ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            file_name = f"{alert.camera_id}_{alert.event_type}_{ts_str}_{alert.id[:8]}.jpg"
            image_url = self.upload_screenshot(alert.frame_crop, file_name, bucket=self.bucket_name, folder="alerts")
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

    # ==============================================================================
    # Persons of Interest CRUD Operations (Name, DOB, Description, Image)
    # ==============================================================================
    def _normalize_person_record(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize person record fields across different database versions."""
        rec = dict(raw)
        person_id = rec.get("id") or rec.get("person_id") or str(uuid.uuid4())
        rec["id"] = person_id
        rec["person_id"] = person_id
        
        name = rec.get("name") or "Unidentified Subject"
        rec["name"] = name

        # Extract DOB and Description from notes if needed
        notes = rec.get("notes") or ""
        dob = rec.get("dob") or ""
        desc = rec.get("description") or ""

        if not dob and notes.startswith("[DOB:"):
            try:
                dob_part = notes.split("]")[0].replace("[DOB:", "").strip()
                dob = dob_part
                if not desc:
                    desc = notes.split("]", 1)[1].strip()
            except Exception:
                pass

        if not desc and notes:
            desc = notes

        rec["dob"] = dob
        rec["description"] = desc
        
        img = rec.get("image_url") or rec.get("face_image_url") or rec.get("full_image_url") or ""
        rec["image_url"] = img
        rec["face_image_url"] = img
        return rec

    def insert_person(self, person: PersonRecord) -> Dict[str, Any]:
        """
        Uploads face crop to `person-records` bucket and inserts person record
        into Supabase `persons_of_interest` table.
        """
        person_dict = person.to_dict()
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Handle base64 image data URL (from browser upload)
        raw_img = person_dict.get("image_url") or person_dict.get("face_image_url") or ""
        if raw_img and raw_img.startswith("data:image/"):
            safe_name = "".join(c for c in person.name if c.isalnum() or c in (' ', '_', '-')).rstrip().replace(' ', '_')
            face_fname = f"{safe_name}_{ts_str}_{person.id[:8]}.jpg"
            saved_url = self.upload_base64_image(raw_img, face_fname, bucket=self.persons_bucket, folder="faces")
            person_dict["image_url"] = saved_url
            person_dict["face_image_url"] = saved_url
            person.image_url = saved_url
            person.face_image_url = saved_url

        # Upload face crop if attached
        if person.face_crop is not None and not person_dict.get("image_url"):
            safe_name = "".join(c for c in person.name if c.isalnum() or c in (' ', '_', '-')).rstrip().replace(' ', '_')
            face_fname = f"{safe_name}_{ts_str}_{person.id[:8]}.jpg"
            face_url = self.upload_screenshot(person.face_crop, face_fname, bucket=self.persons_bucket, folder="faces")
            person_dict["image_url"] = face_url
            person_dict["face_image_url"] = face_url
            person.image_url = face_url
            person.face_image_url = face_url

        # Notes fallback encoding
        notes_val = f"[DOB: {person.dob}] {person.description}".strip() if person.dob else (person.description or "")
        person_dict["notes"] = notes_val
        person_dict["person_id"] = person.id
        person_dict["camera_id"] = "camera1"
        person_dict["camera_name"] = "Camera 1"
        person_dict["threat_level"] = "Suspicious"

        if self.is_connected and self.client is not None:
            try:
                # Try inserting full dictionary
                response = self.client.table("persons_of_interest").insert(person_dict).execute()
                if response.data and len(response.data) > 0:
                    logger.info(f"Person [{person.name}] inserted into `persons_of_interest`.")
                    return self._normalize_person_record(response.data[0])
            except Exception as e:
                # Fallback to schema without newly added columns if table hasn't run migration yet
                try:
                    legacy_dict = {
                        "id": person.id,
                        "person_id": person.id,
                        "name": person.name,
                        "camera_id": "camera1",
                        "camera_name": "Camera 1",
                        "notes": notes_val,
                        "face_image_url": person.image_url or person.face_image_url,
                        "threat_level": "Suspicious"
                    }
                    response = self.client.table("persons_of_interest").insert(legacy_dict).execute()
                    if response.data and len(response.data) > 0:
                        logger.info(f"Person [{person.name}] inserted using legacy columns.")
                        return self._normalize_person_record(response.data[0])
                except Exception as e2:
                    logger.error(f"Failed to insert person into Supabase: {e2}")

            self.cached_persons = None
            self.local_persons.append(self._normalize_person_record(person_dict))
            return self._normalize_person_record(person_dict)
        else:
            self.cached_persons = None
            normalized = self._normalize_person_record(person_dict)
            self.local_persons.append(normalized)
            logger.info(f"[Offline Mode] Person [{person.name}] saved locally.")
            return normalized

    def fetch_persons(
        self,
        limit: int = 50,
        offset: int = 0,
        search_query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch persons from memory cache or Supabase with sub-millisecond response."""
        now = time.time()
        # Fast cache check for standard listing without search filter
        if not search_query and self.cached_persons is not None and (now - self.cached_persons_time < 3.5):
            return self.cached_persons[offset:offset + limit]

        if self.is_connected and self.client is not None:
            try:
                query = self.client.table("persons_of_interest").select("*").order("created_at", desc=True)
                if search_query:
                    query = query.or_(f"name.ilike.%{search_query}%,notes.ilike.%{search_query}%")

                query = query.range(offset, offset + limit - 1)
                res = query.execute()
                raw_list = res.data if res.data is not None else []
                normalized_list = [self._normalize_person_record(p) for p in raw_list]
                
                # Update memory cache
                if not search_query and offset == 0:
                    self.cached_persons = normalized_list
                    self.cached_persons_time = now

                return normalized_list
            except Exception as e:
                logger.error(f"Error fetching persons from Supabase: {e}")
                return self._filter_local_persons(limit, offset, search_query)
        else:
            return self._filter_local_persons(limit, offset, search_query)

    def _filter_local_persons(
        self,
        limit: int,
        offset: int,
        search_query: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Filter local persons list when in offline mode."""
        res = [self._normalize_person_record(p) for p in self.local_persons]
        if search_query:
            sq = search_query.lower()
            res = [p for p in res if sq in str(p.get("name", "")).lower() or sq in str(p.get("description", "")).lower()]
        res.sort(key=lambda x: x.get("timestamp", x.get("created_at", "")), reverse=True)
        return res[offset:offset + limit]

    def update_person(self, person_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update person record (name, dob, description, image_url)."""
        allowed = {"name", "dob", "description", "image_url", "face_image_url", "notes"}
        filtered = {k: v for k, v in updates.items() if k in allowed}

        # Handle base64 image data URL
        raw_img = filtered.get("image_url") or filtered.get("face_image_url") or ""
        if raw_img and raw_img.startswith("data:image/"):
            ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            face_fname = f"update_{ts_str}_{person_id[:8]}.jpg"
            saved_url = self.upload_base64_image(raw_img, face_fname, bucket=self.persons_bucket, folder="faces")
            filtered["image_url"] = saved_url
            filtered["face_image_url"] = saved_url

        # Keep notes in sync
        if "description" in filtered or "dob" in filtered:
            dob_val = filtered.get("dob", "")
            desc_val = filtered.get("description", "")
            filtered["notes"] = f"[DOB: {dob_val}] {desc_val}".strip() if dob_val else desc_val

        self.cached_persons = None
        if self.is_connected and self.client is not None:
            try:
                res = self.client.table("persons_of_interest").update(filtered).or_(f"id.eq.{person_id},person_id.eq.{person_id}").execute()
                if res.data and len(res.data) > 0:
                    return self._normalize_person_record(res.data[0])
            except Exception as e:
                # Fallback to legacy columns update
                try:
                    legacy_updates = {}
                    if "name" in filtered:
                        legacy_updates["name"] = filtered["name"]
                    if "notes" in filtered:
                        legacy_updates["notes"] = filtered["notes"]
                    if "image_url" in filtered or "face_image_url" in filtered:
                        legacy_updates["face_image_url"] = filtered.get("image_url") or filtered.get("face_image_url")

                    res = self.client.table("persons_of_interest").update(legacy_updates).or_(f"id.eq.{person_id},person_id.eq.{person_id}").execute()
                    if res.data and len(res.data) > 0:
                        return self._normalize_person_record(res.data[0])
                except Exception as e2:
                    logger.error(f"Error updating person in Supabase: {e2}")

            # Also update local copy
            for p in self.local_persons:
                if p.get("id") == person_id or p.get("person_id") == person_id:
                    p.update(filtered)
                    return self._normalize_person_record(p)
            return None
        else:
            for p in self.local_persons:
                if p.get("id") == person_id or p.get("person_id") == person_id:
                    p.update(filtered)
                    return self._normalize_person_record(p)
            return None

    def delete_person(self, person_id: str) -> bool:
        """
        Deletes a person record from `persons_of_interest` table AND removes
        associated images from the `person-records` storage bucket.
        """
        self.cached_persons = None
        # First retrieve image paths to delete from storage
        person_record = None
        if self.is_connected and self.client is not None:
            try:
                res = self.client.table("persons_of_interest").select("*").or_(f"id.eq.{person_id},person_id.eq.{person_id}").execute()
                if res.data and len(res.data) > 0:
                    person_record = res.data[0]
            except Exception:
                pass

        if not person_record:
            for p in self.local_persons:
                if p.get("id") == person_id or p.get("person_id") == person_id:
                    person_record = p
                    break

        # Delete image files from Supabase Storage if found
        if person_record and self.is_connected and self.client is not None:
            try:
                paths_to_delete = []
                for key in ["face_image_url", "full_image_url"]:
                    url = person_record.get(key, "")
                    if url and "person-records" in url:
                        # Extract storage relative path e.g. "faces/POI-001_face_..."
                        parts = url.split("person-records/")
                        if len(parts) > 1:
                            paths_to_delete.append(parts[1])
                if paths_to_delete:
                    self.client.storage.from_(self.persons_bucket).remove(paths_to_delete)
                    logger.info(f"Deleted storage files: {paths_to_delete}")
            except Exception as e:
                logger.warning(f"Failed to delete files from storage bucket: {e}")

        # Delete record from database
        if self.is_connected and self.client is not None:
            try:
                res = self.client.table("persons_of_interest").delete().or_(f"id.eq.{person_id},person_id.eq.{person_id}").execute()
                self.local_persons = [p for p in self.local_persons if p.get("id") != person_id and p.get("person_id") != person_id]
                logger.info(f"Person record [{person_id}] deleted from database.")
                return True
            except Exception as e:
                logger.error(f"Failed to delete person record from Supabase: {e}. Removing from local cache.")
                self.local_persons = [p for p in self.local_persons if p.get("id") != person_id and p.get("person_id") != person_id]
                return True
        else:
            self.local_persons = [p for p in self.local_persons if p.get("id") != person_id and p.get("person_id") != person_id]
            logger.info(f"[Offline Mode] Person [{person_id}] deleted locally.")
            return True

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
        persons = self.fetch_persons(limit=1000)

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
            "total_persons_of_interest": len(persons),
            "by_event_type": by_event_type,
            "by_status": by_status,
            "by_camera": by_camera,
            "is_supabase_connected": self.is_connected
        }

    # ==============================================================================
    # Camera Management Operations
    # ==============================================================================
    def fetch_cameras(self) -> List[Dict[str, Any]]:
        """Retrieve list of registered cameras from Supabase or local config fallback."""
        if self.is_connected and self.client is not None:
            try:
                res = self.client.table("cameras").select("*").order("created_at", desc=False).execute()
                if res.data is not None:
                    return res.data
            except Exception as e:
                logger.error(f"Error fetching cameras from Supabase: {e}")
        return []

    def insert_camera(self, camera_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or upsert a new camera record into Supabase."""
        allowed_cols = {
            "id", "name", "ip_address", "rtsp_url", "fallback_file", "location",
            "frame_skip", "conf_threshold", "enable_face_detection", "enable_anpr",
            "enable_night_mode", "fences", "status"
        }
        filtered = {k: v for k, v in camera_data.items() if k in allowed_cols}
        if self.is_connected and self.client is not None:
            try:
                res = self.client.table("cameras").upsert(filtered).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]
            except Exception as e:
                logger.error(f"Error inserting camera into Supabase: {e}")
        return camera_data

    def update_camera(self, camera_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing camera configuration."""
        allowed_cols = {
            "name", "ip_address", "rtsp_url", "fallback_file", "location",
            "frame_skip", "conf_threshold", "enable_face_detection", "enable_anpr",
            "enable_night_mode", "fences", "status", "updated_at"
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_cols}
        filtered["updated_at"] = datetime.now(timezone.utc).isoformat()
        if self.is_connected and self.client is not None:
            try:
                res = self.client.table("cameras").update(filtered).eq("id", camera_id).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]
            except Exception as e:
                logger.error(f"Error updating camera in Supabase: {e}")
        return updates

    def delete_camera(self, camera_id: str) -> bool:
        """Delete a camera record from Supabase."""
        if self.is_connected and self.client is not None:
            try:
                self.client.table("cameras").delete().eq("id", camera_id).execute()
                return True
            except Exception as e:
                logger.error(f"Error deleting camera from Supabase: {e}")
                return False
        return True

