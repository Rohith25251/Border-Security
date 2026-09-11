"""
Centroid & Spatial Multi-Object Tracker.
Assigns persistent track IDs across frames with occlusion/missed-frame tolerance,
maintaining position histories and velocities for downstream behavior analytics.
"""

import time
import math
import numpy as np
from typing import Dict, List, Tuple
from core.models import Detection, TrackedObject


def calculate_iou(boxA: Tuple[int, int, int, int], boxB: Tuple[int, int, int, int]) -> float:
    """Calculate Intersection over Union (IoU) between two bounding boxes."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    inter_width = max(0, xB - xA)
    inter_height = max(0, yB - yA)
    inter_area = inter_width * inter_height

    boxA_area = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxB_area = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    union_area = float(boxA_area + boxB_area - inter_area)

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


class CentroidTracker:
    """
    Multi-Object Tracker combining Centroid Distance and IoU.
    Maintains persistent track IDs and trajectory history for behavior analytics.
    """

    def __init__(self, max_disappeared: int = 25, max_distance: float = 90.0, min_iou: float = 0.15):
        self.next_track_id: int = 1
        self.tracks: Dict[int, TrackedObject] = {}
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance
        self.min_iou = min_iou

    def update(self, detections: List[Detection], current_time: float = None) -> List[TrackedObject]:
        """
        Update tracker with new detections in the current frame.
        Returns the list of currently active tracked objects.
        """
        if current_time is None:
            current_time = time.time()

        # If no detections in this frame, increment disappeared count for all existing tracks
        if len(detections) == 0:
            tracks_to_delete = []
            for track_id, track in self.tracks.items():
                track.disappeared_count += 1
                if track.disappeared_count > self.max_disappeared:
                    tracks_to_delete.append(track_id)
            for track_id in tracks_to_delete:
                del self.tracks[track_id]
            return [t for t in self.tracks.values() if t.disappeared_count == 0]

        # Extract centroids and boxes from incoming detections
        input_centroids = []
        input_boxes = []
        input_classes = []
        input_confs = []

        for d in detections:
            cx = int((d.box[0] + d.box[2]) / 2.0)
            cy = int((d.box[1] + d.box[3]) / 2.0)
            input_centroids.append((cx, cy))
            input_boxes.append(d.box)
            input_classes.append(d.class_name)
            input_confs.append(d.confidence)

        # If currently tracking no objects, register all detections as new tracks
        if len(self.tracks) == 0:
            for i in range(len(detections)):
                self._register_track(
                    box=input_boxes[i],
                    centroid=input_centroids[i],
                    class_name=input_classes[i],
                    confidence=input_confs[i],
                    timestamp=current_time
                )
            return list(self.tracks.values())

        # Match existing tracks to new detections
        track_ids = list(self.tracks.keys())
        existing_centroids = [self.tracks[tid].centroid for tid in track_ids]
        existing_boxes = [self.tracks[tid].box for tid in track_ids]

        # Cost matrix: Euclidean distance between centroids
        D = np.zeros((len(track_ids), len(input_centroids)), dtype=np.float32)
        for r, ec in enumerate(existing_centroids):
            for c, ic in enumerate(input_centroids):
                dist = math.hypot(ec[0] - ic[0], ec[1] - ic[1])
                # IoU bonus (lower cost for high IoU)
                iou = calculate_iou(existing_boxes[r], input_boxes[c])
                class_penalty = 0.0 if self.tracks[track_ids[r]].class_name == input_classes[c] else 500.0
                D[r, c] = dist - (iou * 40.0) + class_penalty

        # Hungarian / greedy association: sort rows by minimum distance
        rows = D.min(axis=1).argsort()
        cols = D.argmin(axis=1)[rows]

        assigned_rows = set()
        assigned_cols = set()

        for row, col in zip(rows, cols):
            if row in assigned_rows or col in assigned_cols:
                continue

            # Check if association is within distance/IoU threshold
            cost = D[row, col]
            iou = calculate_iou(existing_boxes[row], input_boxes[col])
            centroid_dist = math.hypot(existing_centroids[row][0] - input_centroids[col][0],
                                       existing_centroids[row][1] - input_centroids[col][1])

            if centroid_dist > self.max_distance and iou < self.min_iou:
                continue

            # Update existing track
            tid = track_ids[row]
            track = self.tracks[tid]
            track.box = input_boxes[col]
            track.centroid = input_centroids[col]
            track.confidence = input_confs[col]
            track.class_name = input_classes[col]
            track.last_seen = current_time
            track.disappeared_count = 0
            track.history.append((current_time, input_centroids[col]))
            
            # Keep history trimmed to last 150 frames (approx 5-6s)
            if len(track.history) > 150:
                track.history = track.history[-150:]

            assigned_rows.add(row)
            assigned_cols.add(col)

        # Handle unassigned existing tracks (disappeared)
        unassigned_rows = set(range(len(track_ids))) - assigned_rows
        for row in unassigned_rows:
            tid = track_ids[row]
            self.tracks[tid].disappeared_count += 1
            if self.tracks[tid].disappeared_count > self.max_disappeared:
                del self.tracks[tid]

        # Handle unassigned new detections (new tracks)
        unassigned_cols = set(range(len(input_centroids))) - assigned_cols
        for col in unassigned_cols:
            self._register_track(
                box=input_boxes[col],
                centroid=input_centroids[col],
                class_name=input_classes[col],
                confidence=input_confs[col],
                timestamp=current_time
            )

        return [t for t in self.tracks.values() if t.disappeared_count == 0]

    def _register_track(self, box: Tuple[int, int, int, int], centroid: Tuple[int, int],
                        class_name: str, confidence: float, timestamp: float):
        """Register a brand new tracked object."""
        self.tracks[self.next_track_id] = TrackedObject(
            track_id=self.next_track_id,
            class_name=class_name,
            box=box,
            centroid=centroid,
            confidence=confidence,
            first_seen=timestamp,
            last_seen=timestamp,
            history=[(timestamp, centroid)],
            disappeared_count=0
        )
        self.next_track_id += 1
