"""
Virtual Fence Intrusion Detection Module.
Supports configurable tripwire lines and restricted polygon zones.
Guarantees exactly one intrusion alert per crossing per Track ID.
"""

from typing import List, Tuple, Dict, Optional, Union
import numpy as np
import cv2
from core.models import TrackedObject, AlertEvent


def ccw(A: Tuple[float, float], B: Tuple[float, float], C: Tuple[float, float]) -> bool:
    """Check if three points are listed in counter-clockwise order."""
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])


def lines_intersect(p1: Tuple[float, float], p2: Tuple[float, float],
                    p3: Tuple[float, float], p4: Tuple[float, float]) -> bool:
    """Return True if line segment (p1, p2) intersects segment (p3, p4)."""
    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)) and (ccw(p1, p2, p3) != ccw(p1, p2, p4))


class VirtualFence:
    """
    Virtual boundary definition and intrusion monitor.
    Can be a 2-point line (tripwire), vertical/horizontal fence line, or an N-point polygon.
    """

    def __init__(
        self,
        fence_id: str,
        coordinates: List[Tuple[int, int]] = None,
        fence_type: str = "line",
        name: str = "Boundary A",
        position: Optional[float] = 50.0
    ):
        self.fence_id = fence_id
        self.coordinates = coordinates or []
        self.fence_type = (fence_type or "line").lower()
        self.name = name
        self.position = float(position) if position is not None else 50.0
        self.np_poly = np.array(coordinates, dtype=np.int32).reshape((-1, 1, 2)) if coordinates and len(coordinates) >= 3 else None
        self.crossed_ids: set = set()

    def get_endpoints(self, frame_w: int = 1280, frame_h: int = 720) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """Compute pixel endpoints for line/vertical/horizontal fences."""
        if self.fence_type == "vertical":
            pos = self.position if self.position is not None else 50.0
            x = int(frame_w * (pos / 100.0)) if pos <= 100.0 else int(pos)
            return (x, 0), (x, frame_h)
        elif self.fence_type == "horizontal":
            pos = self.position if self.position is not None else 50.0
            y = int(frame_h * (pos / 100.0)) if pos <= 100.0 else int(pos)
            return (0, y), (frame_w, y)
        elif len(self.coordinates) >= 2:
            return self.coordinates[0], self.coordinates[1]
        else:
            # Fallback vertical 50%
            pos = self.position if self.position is not None else 50.0
            x = int(frame_w * (pos / 100.0)) if pos <= 100.0 else int(pos)
            return (x, 0), (x, frame_h)

    def check_intrusion(
        self,
        track: TrackedObject,
        camera_id: str,
        camera_name: str,
        location: str,
        frame_w: int = 1280,
        frame_h: int = 720
    ) -> Optional[AlertEvent]:
        """
        Check if the given track crossed or entered the virtual fence.
        Returns an AlertEvent if a new intrusion occurred, else None.
        """
        if self.fence_id in track.crossed_fences:
            return None

        if len(track.history) < 2:
            # Check point-in-polygon on initial appearance if inside
            if self.fence_type == "polygon" and self.np_poly is not None:
                inside = cv2.pointPolygonTest(self.np_poly, (float(track.centroid[0]), float(track.centroid[1])), False) >= 0
                if inside:
                    track.crossed_fences.add(self.fence_id)
                    return self._create_alert(track, camera_id, camera_name, location)
            return None

        # Compare previous centroid with current centroid
        prev_pt = track.history[-2][1]
        curr_pt = track.centroid

        if self.fence_type in ["line", "vertical", "horizontal"] or len(self.coordinates) >= 2:
            p1, p2 = self.get_endpoints(frame_w=frame_w, frame_h=frame_h)
            if lines_intersect(prev_pt, curr_pt, p1, p2):
                track.crossed_fences.add(self.fence_id)
                return self._create_alert(track, camera_id, camera_name, location)

        elif self.fence_type == "polygon" and self.np_poly is not None:
            prev_inside = cv2.pointPolygonTest(self.np_poly, (float(prev_pt[0]), float(prev_pt[1])), False) >= 0
            curr_inside = cv2.pointPolygonTest(self.np_poly, (float(curr_pt[0]), float(curr_pt[1])), False) >= 0

            # Triggered when moving from outside -> inside
            if not prev_inside and curr_inside:
                track.crossed_fences.add(self.fence_id)
                return self._create_alert(track, camera_id, camera_name, location)

        return None

    def _create_alert(self, track: TrackedObject, camera_id: str, camera_name: str, location: str) -> AlertEvent:
        """Create an intrusion AlertEvent."""
        return AlertEvent(
            camera_id=camera_id,
            camera_name=camera_name,
            event_type="intrusion",
            object_type=track.class_name,
            track_id=track.track_id,
            confidence=track.confidence,
            location=f"{location} - {self.name}",
            metadata={"fence_id": self.fence_id, "fence_name": self.name}
        )
