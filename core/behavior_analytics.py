"""
Suspicious Behavior Analytics Module.
Algorithmic detection of Loitering, Fast Movement, and Group Clustering
based on multi-object tracker history.
"""

import math
import time
import numpy as np
from typing import List, Tuple, Dict, Optional, Set
from core.models import TrackedObject, AlertEvent


class BehaviorAnalyzer:
    """
    Suspicious behavior analyzer operating on TrackedObject spatial-temporal histories.
    """

    def __init__(
        self,
        loiter_time_sec: float = 5.0,
        loiter_max_radius: float = 80.0,
        fast_speed_threshold: float = 220.0,  # pixels per second
        cluster_radius: float = 160.0,        # pixels
        cluster_min_people: int = 3,
        cluster_cooldown: float = 10.0
    ):
        self.loiter_time_sec = loiter_time_sec
        self.loiter_max_radius = loiter_max_radius
        self.fast_speed_threshold = fast_speed_threshold
        self.cluster_radius = cluster_radius
        self.cluster_min_people = cluster_min_people
        self.cluster_cooldown = cluster_cooldown
        
        self.last_cluster_alert_time: float = 0.0

    def analyze(
        self,
        tracks: List[TrackedObject],
        camera_id: str,
        camera_name: str,
        location: str,
        current_time: float = None
    ) -> List[AlertEvent]:
        """
        Analyze all active tracks for suspicious behaviors.
        Returns a list of generated AlertEvents.
        """
        if current_time is None:
            current_time = time.time()

        alerts: List[AlertEvent] = []
        human_tracks: List[TrackedObject] = [t for t in tracks if t.class_name == "human"]

        # 1. Per-track analysis (Loitering & Fast Movement)
        for track in tracks:
            # Check Loitering (Human only, duration > 5s with small displacement variance)
            if track.class_name == "human" and not track.loitering_alerted:
                if track.age >= self.loiter_time_sec and len(track.history) >= 10:
                    pts = np.array([pt for _, pt in track.history])
                    # Standard deviation of positions
                    std_dev = np.std(pts, axis=0)
                    variance_radius = math.hypot(float(std_dev[0]), float(std_dev[1]))

                    if variance_radius <= self.loiter_max_radius:
                        track.loitering_alerted = True
                        alerts.append(AlertEvent(
                            camera_id=camera_id,
                            camera_name=camera_name,
                            event_type="loitering",
                            object_type="human",
                            track_id=track.track_id,
                            confidence=0.88,
                            location=location,
                            metadata={"duration_sec": round(track.age, 1), "variance_radius": round(variance_radius, 1)}
                        ))

            # Check Fast Movement (Speed threshold)
            if not track.fast_movement_alerted and len(track.history) >= 4:
                # Measure velocity over the last 1.0 second (or last 10 frames)
                sub_history = track.history[-10:]
                t_start, pt_start = sub_history[0]
                t_end, pt_end = sub_history[-1]
                dt = t_end - t_start

                if dt >= 0.2:
                    dist = math.hypot(pt_end[0] - pt_start[0], pt_end[1] - pt_start[1])
                    speed_px_per_sec = dist / dt

                    if speed_px_per_sec >= self.fast_speed_threshold:
                        track.fast_movement_alerted = True
                        alerts.append(AlertEvent(
                            camera_id=camera_id,
                            camera_name=camera_name,
                            event_type="fast_movement",
                            object_type=track.class_name,
                            track_id=track.track_id,
                            confidence=min(1.0, speed_px_per_sec / 300.0),
                            location=location,
                            metadata={"speed_px_per_sec": round(speed_px_per_sec, 1)}
                        ))

        # 2. Multi-track analysis (Group Clustering)
        if len(human_tracks) >= self.cluster_min_people:
            if current_time - self.last_cluster_alert_time >= self.cluster_cooldown:
                # Find connected components within cluster_radius
                centroids = [t.centroid for t in human_tracks]
                n = len(centroids)
                adj = [[] for _ in range(n)]

                for i in range(n):
                    for j in range(i + 1, n):
                        d = math.hypot(centroids[i][0] - centroids[j][0], centroids[i][1] - centroids[j][1])
                        if d <= self.cluster_radius:
                            adj[i].append(j)
                            adj[j].append(i)

                visited = set()
                for i in range(n):
                    if i not in visited:
                        # BFS cluster component
                        cluster = []
                        queue = [i]
                        visited.add(i)
                        while queue:
                            curr = queue.pop(0)
                            cluster.append(curr)
                            for neighbor in adj[curr]:
                                if neighbor not in visited:
                                    visited.add(neighbor)
                                    queue.append(neighbor)

                        if len(cluster) >= self.cluster_min_people:
                            self.last_cluster_alert_time = current_time
                            cluster_track_ids = [human_tracks[idx].track_id for idx in cluster]
                            alerts.append(AlertEvent(
                                camera_id=camera_id,
                                camera_name=camera_name,
                                event_type="group_clustering",
                                object_type="human",
                                confidence=0.92,
                                location=location,
                                metadata={
                                    "cluster_size": len(cluster),
                                    "member_track_ids": cluster_track_ids
                                }
                            ))
                            break

        return alerts
