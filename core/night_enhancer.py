"""
Night Mode & Low-Light Enhancement Module.
Measures mean frame luminance, automatically triggers CLAHE enhancement,
and notifies the engine of night mode transitions.
"""

from typing import Tuple, Optional
import cv2
import numpy as np
from core.models import AlertEvent


class NightEnhancer:
    """
    Adaptive Night Mode Controller.
    Uses Contrast Limited Adaptive Histogram Equalization (CLAHE) on LAB color space.
    """

    def __init__(self, brightness_threshold: float = 65.0, clip_limit: float = 2.5, tile_grid_size: Tuple[int, int] = (8, 8)):
        self.brightness_threshold = brightness_threshold
        self.clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
        self.is_night_mode: bool = False
        self.last_brightness: float = 128.0
        self._check_counter: int = 0

    def process(self, frame: np.ndarray, camera_id: str = "camera1", camera_name: str = "Camera 1", location: str = "Border Sector") -> Tuple[np.ndarray, bool, Optional[AlertEvent]]:
        """
        Calculates frame luminance. If below threshold, applies CLAHE enhancement.
        Returns: (processed_frame, is_night_mode, state_change_alert_or_none)
        """
        if frame is None or frame.size == 0:
            return frame, False, None

        self._check_counter += 1
        
        # Fast luminance calculation using fast downsampling step
        # Only recalculate average luminance every 5 frames to maximize FPS
        if self._check_counter % 5 == 1:
            sample = frame[::16, ::16]
            mean_brightness = float(cv2.mean(sample)[0])
            self.last_brightness = mean_brightness
            new_night_state = mean_brightness < self.brightness_threshold
        else:
            new_night_state = self.is_night_mode

        state_change_alert: Optional[AlertEvent] = None

        # State transition check
        if new_night_state != self.is_night_mode:
            self.is_night_mode = new_night_state
            mode_str = "NIGHT (CLAHE Active)" if self.is_night_mode else "DAY (Standard)"
            state_change_alert = AlertEvent(
                camera_id=camera_id,
                camera_name=camera_name,
                event_type="night_mode_change",
                object_type="n/a",
                confidence=1.0,
                location=location,
                frame_crop=frame.copy(),
                metadata={"brightness": round(self.last_brightness, 2), "mode": mode_str}
            )

        if self.is_night_mode:
            # Convert BGR to LAB color space
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE to L-channel
            cl = self.clahe.apply(l)
            
            # Merge back and convert to BGR
            enhanced_lab = cv2.merge((cl, a, b))
            enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
            return enhanced_bgr, True, state_change_alert

        return frame, False, state_change_alert

