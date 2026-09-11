"""
Thread-safe Alert Queue Manager and Background Database Writer.
Provides asynchronous queuing between AI camera processing threads and Supabase,
enforcing a per-track-ID alert cooldown to prevent duplicate alert spamming.
"""

import time
import queue
import logging
import threading
from typing import Dict, Tuple, Optional, List, Any
from core.models import AlertEvent
from db.supabase_client import SupabaseManager

logger = logging.getLogger(__name__)


class AlertQueueManager:
    """
    Thread-Safe Alert Ingestion Queue with configurable cooldown and background Supabase persistence.
    """

    def __init__(
        self,
        supabase_manager: Optional[SupabaseManager] = None,
        cooldown_seconds: float = 5.0,
        max_queue_size: int = 500
    ):
        self.supabase_manager = supabase_manager or SupabaseManager()
        self.cooldown_seconds = cooldown_seconds
        self.queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        
        # Cooldown state: (camera_id, track_id_or_none, event_type) -> last_alert_time
        self.cooldown_tracker: Dict[Tuple[str, Optional[int], str], float] = {}
        self.cooldown_lock = threading.Lock()

        # Worker thread
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None

        # Statistics
        self.total_enqueued = 0
        self.total_written = 0
        self.total_throttled = 0

    def start(self) -> "AlertQueueManager":
        """Start the background database writer thread."""
        if self.is_running:
            return self
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._writer_loop, name="SupabaseAlertWriter", daemon=True)
        self.worker_thread.start()
        logger.info("AlertQueueManager background writer started.")
        return self

    def push_alert(self, alert: AlertEvent, current_time: float = None) -> bool:
        """
        Check per-track cooldown. If within cooldown window, suppress/throttle.
        If valid, enqueue for asynchronous writing to Supabase.
        Returns: True if enqueued, False if suppressed by cooldown.
        """
        if alert is None:
            return False

        if current_time is None:
            current_time = time.time()

        cooldown_key = (alert.camera_id, alert.track_id, alert.event_type)

        with self.cooldown_lock:
            last_time = self.cooldown_tracker.get(cooldown_key, 0.0)
            if current_time - last_time < self.cooldown_seconds:
                self.total_throttled += 1
                logger.debug(f"Alert throttled (cooldown active): {alert.event_type} for track_id={alert.track_id} on {alert.camera_id}")
                return False

            # Update cooldown timestamp
            self.cooldown_tracker[cooldown_key] = current_time

        try:
            self.queue.put_nowait(alert)
            self.total_enqueued += 1
            logger.info(f"Enqueued alert [{alert.event_type}] for track {alert.track_id} on {alert.camera_id} (Queue size: {self.queue.qsize()})")
            return True
        except queue.Full:
            logger.warning(f"Alert queue full ({self.queue.maxsize}). Dropping oldest alert to prioritize new events.")
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(alert)
                return True
            except Exception:
                return False

    def push_alerts(self, alerts: List[AlertEvent], current_time: float = None) -> int:
        """Push a batch of alerts. Returns the count of successfully enqueued alerts."""
        if not alerts:
            return 0
        count = 0
        for a in alerts:
            if self.push_alert(a, current_time=current_time):
                count += 1
        return count

    def _writer_loop(self):
        """Worker loop extracting alerts and writing to Supabase."""
        logger.info("Supabase worker loop running...")
        while self.is_running:
            try:
                alert: AlertEvent = self.queue.get(timeout=0.5)
                if alert is None:
                    continue

                # Insert into Supabase (uploading image screenshot first)
                self.supabase_manager.insert_alert(alert)
                self.total_written += 1
                self.queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in Supabase writer loop: {e}")

    def stop(self, timeout: float = 2.0):
        """Flush and gracefully stop the worker thread."""
        self.is_running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=timeout)
        logger.info(f"AlertQueueManager stopped. (Enqueued: {self.total_enqueued}, Written: {self.total_written}, Throttled: {self.total_throttled})")
