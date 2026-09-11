"""
Individual Camera Worker Thread.
Runs a dedicated processing loop for a single camera feed, applying frame-skipping,
640x640 inference optimization, multi-object tracking, behavioral analytics,
and synchronizing alerts onto the shared AlertQueueManager.
"""

import cv2
import time
import logging
import threading
from typing import Dict, Any, Optional, List, Tuple
import numpy as np

from core.models import AlertEvent
from core.virtual_fence import VirtualFence
from core.ingestion import RTSPStreamReader
from core.engine import FrameProcessingEngine
from db.queue_manager import AlertQueueManager

logger = logging.getLogger(__name__)


class CameraWorkerThread:
    """
    Dedicated worker thread per camera stream.
    Synchronizes with the shared AlertQueueManager and provides thread-safe annotated frames for API streaming.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        alert_queue: AlertQueueManager,
        yolo_model: str = "yolov8n.pt",
        device: str = "cpu"
    ):
        self.config = config
        self.camera_id = config.get("id", "camera1")
        self.camera_name = config.get("name", f"Camera {self.camera_id}")
        self.rtsp_url = config.get("rtsp_url", "")
        self.fallback_file = config.get("fallback_file", "")
        self.location = config.get("location", "Border Sector")
        self.frame_skip = max(1, int(config.get("frame_skip", 2)))
        self.conf_threshold = float(config.get("conf_threshold", 0.40))
        self.target_size = tuple(config.get("target_inference_size", [640, 640]))
        self.alert_queue = alert_queue

        # Parse virtual fences
        fences: List[VirtualFence] = []
        for f_data in config.get("fences", []):
            coords = [tuple(pt) for pt in f_data.get("coordinates", [])]
            fences.append(VirtualFence(
                fence_id=f_data.get("id", f"fence_{self.camera_id}"),
                coordinates=coords,
                fence_type=f_data.get("type", "line"),
                name=f_data.get("name", "Boundary Zone")
            ))

        # Ingestion reader
        self.reader = RTSPStreamReader(rtsp_url=self.rtsp_url, camera_id=self.camera_id)

        # AI Engine instance
        self.engine = FrameProcessingEngine(
            camera_id=self.camera_id,
            camera_name=self.camera_name,
            location=self.location,
            fences=fences,
            enable_anpr=config.get("enable_anpr", True),
            enable_face_detection=config.get("enable_face_detection", True),
            enable_night_mode=config.get("enable_night_mode", True),
            yolo_model=yolo_model,
            conf_threshold=self.conf_threshold,
            device=device
        )

        # Threading & status
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        
        # Frame and metrics buffers
        self.latest_annotated_frame: Optional[np.ndarray] = None
        self.latest_raw_frame: Optional[np.ndarray] = None
        self.frame_counter = 0
        self.processed_counter = 0
        self.fps = 0.0
        self.avg_inference_time_ms = 0.0
        self.last_metrics: Dict[str, Any] = {}
        self.total_alerts_generated = 0
        self.is_connected = False

    def start(self) -> "CameraWorkerThread":
        """Start the camera ingestion and processing worker thread."""
        if self.is_running:
            return self
        
        # Start ingestion reader
        self.reader.start()
        
        self.is_running = True
        self.thread = threading.Thread(
            target=self._processing_loop,
            name=f"CameraWorker-{self.camera_id}",
            daemon=True
        )
        self.thread.start()
        logger.info(f"[{self.camera_id}] CameraWorker thread started.")
        return self

    def _processing_loop(self):
        """Continuous frame processing and analytics loop."""
        fps_start = time.perf_counter()
        fps_frames = 0

        while self.is_running:
            frame: Optional[np.ndarray] = None
            timestamp = time.time()

            # 1. Grab frame from RTSP reader
            if self.reader.is_connected:
                ret, frame, ts = self.reader.read()
                if ret and frame is not None:
                    timestamp = ts
                    self.is_connected = True
                else:
                    self.is_connected = False
            else:
                self.is_connected = False

            if frame is None or not self.is_connected:
                with self.lock:
                    self.latest_annotated_frame = None
                    self.latest_raw_frame = None
                    self.fps = 0.0
                time.sleep(0.05)
                continue

            self.frame_counter += 1

            # 2. Frame skipping check
            # Process full AI inference every `frame_skip` frames
            if (self.frame_counter % self.frame_skip) != 0:
                with self.lock:
                    self.latest_raw_frame = frame
                time.sleep(0.005)
                continue

            # 3. Process frame through Master AI Engine
            # Pre-resize large 4K streams to max 1920 or target size for smooth throughput
            h, w = frame.shape[:2]
            if w > 1920:
                scale = 1920.0 / w
                proc_frame = cv2.resize(frame, (1920, int(h * scale)))
            else:
                proc_frame = frame

            annotated_frame, new_alerts, metrics = self.engine.process_frame(proc_frame, timestamp=timestamp)
            self.processed_counter += 1
            fps_frames += 1

            # 4. Push alerts to shared AlertQueueManager
            if new_alerts:
                self.total_alerts_generated += len(new_alerts)
                self.alert_queue.push_alerts(new_alerts, current_time=timestamp)

            # 5. Store thread-safe annotated snapshot
            with self.lock:
                self.latest_annotated_frame = annotated_frame
                self.latest_raw_frame = frame
                self.last_metrics = metrics
                self.avg_inference_time_ms = metrics.get("inference_time_ms", 0.0)

            # Periodic FPS measurement
            now = time.perf_counter()
            elapsed = now - fps_start
            if elapsed >= 1.0:
                self.fps = round(fps_frames / elapsed, 1)
                fps_frames = 0
                fps_start = now

    def get_latest_annotated_frame(self) -> Optional[np.ndarray]:
        """Thread-safe retrieval of latest annotated frame."""
        with self.lock:
            if self.latest_annotated_frame is None:
                return None
            return self.latest_annotated_frame.copy()

    def get_latest_raw_frame(self) -> Optional[np.ndarray]:
        """Thread-safe retrieval of pure, unannotated raw camera frame at native FPS."""
        with self.lock:
            if self.latest_raw_frame is not None:
                return self.latest_raw_frame.copy()
        # Fallback to direct reader frame if available
        if self.reader and self.reader.is_connected and self.reader.latest_frame is not None:
            return self.reader.latest_frame.copy()
        return None

    def get_status(self) -> Dict[str, Any]:
        """Retrieve real-time camera telemetry and processing statistics."""
        with self.lock:
            return {
                "camera_id": self.camera_id,
                "camera_name": self.camera_name,
                "location": self.location,
                "is_running": self.is_running,
                "is_connected": self.is_connected,
                "fps": self.fps,
                "inference_time_ms": self.avg_inference_time_ms,
                "total_frames_read": self.frame_counter,
                "total_frames_processed": self.processed_counter,
                "total_alerts": self.total_alerts_generated,
                "active_tracks": self.last_metrics.get("active_tracks", 0),
                "is_night": self.last_metrics.get("is_night", False),
                "scene_brightness": self.last_metrics.get("scene_brightness", 128.0)
            }

    def stop(self):
        """Stop worker and release camera stream."""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.reader.stop()
        logger.info(f"[{self.camera_id}] CameraWorker stopped.")
