import os
import cv2
import time
import logging
import threading
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# Ensure OpenCV uses TCP for reliable RTSP streaming without packet drop artifacts
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|max_delay;500000"
# Configure OpenCV single-threaded decoding per capture stream to avoid libavcodec pthread contention
try:
    cv2.setNumThreads(1)
except Exception:
    pass


class RTSPStreamReader:
    """
    Threaded RTSP Stream reader that continuously grabs frames to prevent buffer lag,
    with automatic exponential-backoff reconnection logic on stream dropouts.
    """

    def __init__(self, rtsp_url: str, camera_id: str = "camera1", reconnect_delay: float = 2.0):
        self.rtsp_url = rtsp_url
        self.camera_id = camera_id
        self.reconnect_delay = reconnect_delay
        
        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.frame_timestamp: float = 0.0
        self.is_connected: bool = False
        self.is_running: bool = False
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        
        # Performance metrics
        self.fps: float = 0.0
        self.frame_count: int = 0
        self.reconnect_count: int = 0
        self._fps_calc_start: float = time.time()
        self._fps_frame_count: int = 0

    def start(self) -> "RTSPStreamReader":
        """Start the background ingestion thread."""
        if self.is_running:
            return self
        self.is_running = True
        self.thread = threading.Thread(target=self._capture_loop, name=f"RTSPReader-{self.camera_id}", daemon=True)
        self.thread.start()
        logger.info(f"[{self.camera_id}] Ingestion thread started for {self.rtsp_url}")
        return self

    def _connect(self) -> bool:
        """Attempt to connect or reconnect to the RTSP stream."""
        if not self.is_running:
            return False

        with self.lock:
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None

        logger.info(f"[{self.camera_id}] Connecting to stream/camera source: {self.rtsp_url}")
        
        try:
            # Check if source is a USB/webcam device index (e.g. 0, "0", 1)
            source = self.rtsp_url
            if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
                dev_index = int(source)
                backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
                new_cap = cv2.VideoCapture(dev_index, backend)
            else:
                new_cap = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG)
                new_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if new_cap.isOpened():
                ret, frame = new_cap.read()
                if ret and frame is not None:
                    with self.lock:
                        self.cap = new_cap
                        self.latest_frame = frame
                        self.frame_timestamp = time.time()
                        self.is_connected = True
                    logger.info(f"[{self.camera_id}] Successfully connected to source {self.rtsp_url} ({frame.shape[1]}x{frame.shape[0]})")
                    return True
                else:
                    new_cap.release()
        except Exception as e:
            logger.warning(f"[{self.camera_id}] Connection attempt failed: {e}")

        self.is_connected = False
        return False

    def _capture_loop(self):
        """Continuous frame grabbing loop running in the background thread."""
        current_delay = self.reconnect_delay
        
        while self.is_running:
            if not self.is_connected or self.cap is None or not self.cap.isOpened():
                self.reconnect_count += 1
                logger.warning(f"[{self.camera_id}] Stream disconnected. Retrying in {current_delay:.1f}s...")
                time.sleep(current_delay)
                
                if self._connect():
                    current_delay = self.reconnect_delay
                else:
                    # Exponential backoff capped at 10 seconds
                    current_delay = min(current_delay * 1.5, 10.0)
                continue

            if not self.is_running:
                break

            try:
                cap = self.cap
                if cap is None or not self.is_running:
                    break

                # Grab latest frame
                ret, frame = cap.read()
                
                if not ret or frame is None:
                    if self.is_running:
                        logger.warning(f"[{self.camera_id}] Frame read failed or stream closed by server.")
                    self.is_connected = False
                    continue

                with self.lock:
                    self.latest_frame = frame
                    self.frame_timestamp = time.time()
                    self.frame_count += 1
                    self._fps_frame_count += 1

                # Periodic FPS calculation (every 1 second)
                now = time.time()
                elapsed = now - self._fps_calc_start
                if elapsed >= 1.0:
                    self.fps = self._fps_frame_count / elapsed
                    self._fps_frame_count = 0
                    self._fps_calc_start = now

            except Exception as e:
                logger.error(f"[{self.camera_id}] Error reading frame: {e}")
                self.is_connected = False

    def read(self) -> Tuple[bool, Optional[np.ndarray], float]:
        """
        Thread-safe retrieval of the latest available frame.
        Returns: (is_valid, frame, timestamp)
        """
        with self.lock:
            if self.latest_frame is None:
                return False, None, 0.0
            return True, self.latest_frame.copy(), self.frame_timestamp

    def stop(self):
        """Stop capture loop and release resources cleanly."""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
        with self.lock:
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
        self.is_connected = False
        logger.info(f"[{self.camera_id}] Stream ingestion stopped.")
