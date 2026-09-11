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
    Can be a 2-point line (tripwire) or an N-point polygon.
    """

    def __init__(self, fence_id: str, coordinates: List[Tuple[int, int]], fence_type: str = "line", name: str = "Boundary A"):
        self.fence_id = fence_id
        self.coordinates = coordinates  # e.g., [(x1, y1), (x2, y2)] or polygon vertices
        self.fence_type = fence_type    # "line" or "polygon"
        self.name = name
        self.np_poly = np.array(coordinates, dtype=np.int32).reshape((-1, 1, 2)) if len(coordinates) >= 3 else None
        self.crossed_ids: set = set()

    def check_intrusion(self, track: TrackedObject, camera_id: str, camera_name: str, location: str) -> Optional[AlertEvent]:
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

        if self.fence_type == "line" and len(self.coordinates) >= 2:
            p1, p2 = self.coordinates[0], self.coordinates[1]
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
