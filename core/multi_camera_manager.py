"""
Multi-Camera Engine Manager.
Coordinates concurrent ingestion and AI inference threads across all CCTV streams,
synchronizing all camera workers onto a single shared AlertQueueManager.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
import numpy as np

from db.supabase_client import SupabaseManager
from db.queue_manager import AlertQueueManager
from core.camera_worker import CameraWorkerThread

logger = logging.getLogger(__name__)


class MultiCameraManager:
    """
    Master Controller for concurrent multi-camera video analytics.
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
        """Load camera configurations from file."""
        if not os.path.exists(self.config_path):
            logger.warning(f"Config file not found at {self.config_path}. Using default configuration.")
            return []

        try:
            with open(self.config_path, "r") as f:
                configs = json.load(f)
                logger.info(f"Loaded {len(configs)} camera configuration(s) from {self.config_path}")
                return configs
        except Exception as e:
            logger.error(f"Failed to read camera config {self.config_path}: {e}")
            return []

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
        # Start shared alert queue
        self.alert_queue.start()

        # Initialize and start each camera worker
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

    def get_all_statuses(self) -> List[Dict[str, Any]]:
        """Get telemetry and analytics status across all active cameras."""
        statuses = []
        for cam_id, worker in self.workers.items():
            statuses.append(worker.get_status())
        return statuses
