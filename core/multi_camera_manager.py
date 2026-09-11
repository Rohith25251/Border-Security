"""
Multi-Camera Engine Manager.
Coordinates concurrent ingestion and AI inference threads across all CCTV streams,
synchronizing all camera workers onto a single shared AlertQueueManager,
supporting dynamic runtime IP camera addition, automatic stream parsing, and Supabase persistence.
"""

import os
import re
import json
import time
import logging
from typing import Dict, List, Optional, Any
import numpy as np

from db.supabase_client import SupabaseManager
from db.queue_manager import AlertQueueManager
from core.models import PersonRecord
from core.camera_worker import CameraWorkerThread

logger = logging.getLogger(__name__)


def parse_camera_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Intelligently parses IP address / URL input and auto-generates:
    1. Camera ID slug
    2. Camera display name / label
    3. Location name
    4. Standardized RTSP / HTTP video stream URL
    """
    raw_ip = str(data.get("ip_address") or "").strip()
    raw_url = str(data.get("rtsp_url") or "").strip()

    # If URL provided without IP, extract IP address
    ip_addr = raw_ip
    if not ip_addr and raw_url:
        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', raw_url)
        if ip_match:
            ip_addr = ip_match.group(1)

    # Standardize stream URL from IP address if omitted
    stream_url = raw_url
    if not stream_url and raw_ip:
        if raw_ip.startswith("http://") or raw_ip.startswith("https://") or raw_ip.startswith("rtsp://"):
            stream_url = raw_ip
        elif ":" in raw_ip:
            host, port = raw_ip.split(":", 1)
            ip_addr = host
            if "8080" in port or "4747" in port:
                stream_url = f"http://{raw_ip}/video"
            elif "554" in port:
                stream_url = f"rtsp://{raw_ip}/live"
            else:
                stream_url = f"http://{raw_ip}/video"
        else:
            stream_url = f"http://{raw_ip}:8080/video"

    # Sanitize slug for ID
    if data.get("id"):
        cam_id = data.get("id")
    elif ip_addr:
        safe_ip = ip_addr.replace(".", "_").replace(":", "_").replace("/", "_")
        cam_id = f"cam_{safe_ip}"
    else:
        cam_id = f"cam_{int(time.time())}"

    # Auto generate Label if empty
    name = data.get("name")
    if not name or not str(name).strip():
        name = f"Camera ({ip_addr or cam_id})"

    # Auto generate Location if empty
    location = data.get("location")
    if not location or not str(location).strip():
        location = f"Sector {ip_addr or 'Gate'}"

    return {
        "id": cam_id,
        "name": name,
        "ip_address": ip_addr,
        "rtsp_url": stream_url,
        "location": location,
        "fallback_file": data.get("fallback_file", ""),
        "frame_skip": max(1, int(data.get("frame_skip", 2))),
        "conf_threshold": float(data.get("conf_threshold", 0.25)),
        "target_inference_size": [640, 640],
        "enable_face_detection": bool(data.get("enable_face_detection", True)),
        "enable_anpr": bool(data.get("enable_anpr", True)),
        "enable_night_mode": bool(data.get("enable_night_mode", True)),
        "fences": data.get("fences", []),
        "status": data.get("status", "active")
    }


class MultiCameraManager:
    """
    Master Controller for concurrent multi-camera video analytics.
    Dynamically manages camera worker threads, synchronizes with Supabase DB and local JSON.
    """

    def __init__(
        self,
        config_path: str = "config/cameras.json",
        supabase_manager: Optional[SupabaseManager] = None,
        cooldown_seconds: float = 5.0,
        yolo_model: str = "yolov8n.pt",
        device: str = "cpu"
    ):
        self.config_path = config_path
        self.yolo_model = yolo_model
        self.device = device

        # Initialize shared database & queue infrastructure
        self.supabase_manager = supabase_manager or SupabaseManager()
        self.alert_queue = AlertQueueManager(
            supabase_manager=self.supabase_manager,
            cooldown_seconds=cooldown_seconds
        )

        self.workers: Dict[str, CameraWorkerThread] = {}
        self.is_running = False

        # Load configurations
        self.camera_configs = self._load_config()

    def _load_config(self) -> List[Dict[str, Any]]:
        """Load camera configurations from Supabase database or local JSON file."""
        configs = []

        # 1. Try fetching from Supabase `cameras` table
        if self.supabase_manager and self.supabase_manager.is_connected:
            try:
                db_cams = self.supabase_manager.fetch_cameras()
                if db_cams and len(db_cams) > 0:
                    logger.info(f"Loaded {len(db_cams)} camera(s) from Supabase 'cameras' table.")
                    # Also persist local cache
                    self._save_local_json(db_cams)
                    return db_cams
            except Exception as e:
                logger.warning(f"Failed to fetch cameras from Supabase: {e}")

        # 2. Fallback to local config file
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    configs = json.load(f)
                    logger.info(f"Loaded {len(configs)} camera(s) from local {self.config_path}")
            except Exception as e:
                logger.error(f"Failed to read camera config {self.config_path}: {e}")

        # 3. If Supabase is connected, seed DB with initial configs
        if self.supabase_manager and self.supabase_manager.is_connected and configs:
            try:
                for cfg in configs:
                    self.supabase_manager.insert_camera(cfg)
                logger.info("Synchronized initial camera configs into Supabase 'cameras' table.")
            except Exception as e:
                logger.warning(f"Error seeding Supabase cameras: {e}")

        return configs

    def _save_local_json(self, configs: List[Dict[str, Any]]):
        """Save active configurations to local JSON."""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(configs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write camera config {self.config_path}: {e}")

    def add_camera(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dynamically add a new IP or RTSP camera at runtime:
        1. Auto-configures label, location, and stream URL.
        2. Persists to Supabase and local JSON.
        3. Spawns and starts worker thread immediately with 0 server downtime.
        """
        cfg = parse_camera_config(data)
        cam_id = cfg["id"]

        # Check if already exists; if so, replace/update
        existing_idx = next((i for i, c in enumerate(self.camera_configs) if c.get("id") == cam_id), None)
        if existing_idx is not None:
            self.camera_configs[existing_idx] = cfg
        else:
            self.camera_configs.append(cfg)

        # Persist
        self._save_local_json(self.camera_configs)
        if self.supabase_manager:
            try:
                self.supabase_manager.insert_camera(cfg)
            except Exception as e:
                logger.warning(f"Error saving camera to Supabase: {e}")

        # Stop existing worker if active
        if cam_id in self.workers:
            old_worker = self.workers.pop(cam_id)
            old_worker.stop()

        # Start new worker thread
        worker = CameraWorkerThread(
            config=cfg,
            alert_queue=self.alert_queue,
            supabase_manager=self.supabase_manager,
            yolo_model=self.yolo_model,
            device=self.device
        )
        self.workers[cam_id] = worker
        if self.is_running:
            worker.start()

        logger.info(f"Dynamically added & started camera: [{cam_id}] '{cfg.get('name')}' ({cfg.get('rtsp_url')})")
        return cfg

    def update_camera(self, camera_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update existing camera parameters and restart worker if stream URL changed."""
        cfg = next((c for c in self.camera_configs if c.get("id") == camera_id), None)
        if not cfg:
            return None

        # Apply updates
        for k, v in updates.items():
            if v is not None:
                cfg[k] = v

        parsed = parse_camera_config(cfg)
        parsed["id"] = camera_id

        # Update in list
        for i, c in enumerate(self.camera_configs):
            if c.get("id") == camera_id:
                self.camera_configs[i] = parsed
                break

        self._save_local_json(self.camera_configs)
        if self.supabase_manager:
            try:
                self.supabase_manager.update_camera(camera_id, parsed)
            except Exception as e:
                logger.warning(f"Error updating camera in Supabase: {e}")

        # Restart worker if stream URL changed or running
        if camera_id in self.workers:
            old_worker = self.workers.pop(camera_id)
            old_worker.stop()

        new_worker = CameraWorkerThread(
            config=parsed,
            alert_queue=self.alert_queue,
            supabase_manager=self.supabase_manager,
            yolo_model=self.yolo_model,
            device=self.device
        )
        self.workers[camera_id] = new_worker
        if self.is_running:
            new_worker.start()

        return parsed

    def remove_camera(self, camera_id: str) -> bool:
        """Dynamically stop and delete camera."""
        # Stop worker
        if camera_id in self.workers:
            worker = self.workers.pop(camera_id)
            worker.stop()

        # Remove from configs
        self.camera_configs = [c for c in self.camera_configs if c.get("id") != camera_id]
        self._save_local_json(self.camera_configs)

        # Remove from Supabase
        if self.supabase_manager:
            try:
                self.supabase_manager.delete_camera(camera_id)
            except Exception as e:
                logger.warning(f"Error deleting camera from Supabase: {e}")

        logger.info(f"Removed camera: [{camera_id}]")
        return True

    def initialize_workers(self):
        """Initialize worker threads for all configured cameras."""
        self.workers.clear()
        for cfg in self.camera_configs:
            cam_id = cfg.get("id", "camera1")
            worker = CameraWorkerThread(
                config=cfg,
                alert_queue=self.alert_queue,
                supabase_manager=self.supabase_manager,
                yolo_model=self.yolo_model,
                device=self.device
            )
            self.workers[cam_id] = worker
            logger.info(f"Initialized CameraWorker for {cam_id} ({cfg.get('name')})")

    def start_all(self):
        """Start the shared alert queue writer and all camera processing threads."""
        if self.is_running:
            return

        logger.info("Starting MultiCameraManager...")
        self.alert_queue.start()

        if not self.workers:
            self.initialize_workers()

        for cam_id, worker in self.workers.items():
            worker.start()

        self.is_running = True
        logger.info(f"MultiCameraManager running with {len(self.workers)} camera worker thread(s).")

    def stop_all(self):
        """Gracefully stop all camera workers and the shared alert queue."""
        logger.info("Stopping MultiCameraManager...")
        for cam_id, worker in self.workers.items():
            worker.stop()

        self.alert_queue.stop()
        self.is_running = False
        logger.info("MultiCameraManager stopped.")

    def get_worker(self, camera_id: str) -> Optional[CameraWorkerThread]:
        """Get the worker thread instance for a specific camera."""
        return self.workers.get(camera_id)

    def get_latest_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """Get the latest processed & annotated frame for a camera."""
        worker = self.workers.get(camera_id)
        if worker:
            return worker.get_latest_annotated_frame()
        return None

    def get_latest_raw_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """Get the pure unannotated raw camera frame at native stream FPS."""
        worker = self.workers.get(camera_id)
        if worker:
            return worker.get_latest_raw_frame()
        return None

    def update_face_profile(self, person_id: str, name: str, signature: np.ndarray, record: Optional[PersonRecord] = None):
        """Pre-index face signature across all active camera engines immediately."""
        for worker in self.workers.values():
            if worker.engine and worker.engine.face_recognizer:
                worker.engine.face_recognizer.register_profile_signature(person_id, name, signature, record)

    def remove_face_profile(self, person_id: str):
        """Remove a deleted person from all camera engines instantly."""
        for worker in self.workers.values():
            if worker.engine and worker.engine.face_recognizer:
                worker.engine.face_recognizer.remove_profile(person_id)

    def get_all_statuses(self) -> List[Dict[str, Any]]:
        """Get telemetry and analytics status across all active cameras."""
        statuses = []
        for cam_id, worker in self.workers.items():
            statuses.append(worker.get_status())
        return statuses
