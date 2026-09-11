"""
Data models for IBVAP (Intelligent Border Video Analytics Platform).
Maps directly to internal analytics representations and Supabase alerts schema.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any
import uuid
import numpy as np


@dataclass
class Detection:
    """Raw bounding box detection from object detector or face detector."""
    box: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    class_id: int
    class_name: str  # 'human', 'car', 'truck', 'bus', 'motorcycle', 'face'


@dataclass
class TrackedObject:
    """State of an object tracked across multiple frames."""
    track_id: int
    class_name: str  # 'human' or 'vehicle'
    box: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    centroid: Tuple[int, int]  # (cx, cy)
    confidence: float
    first_seen: float  # timestamp in seconds
    last_seen: float   # timestamp in seconds
    history: List[Tuple[float, Tuple[int, int]]] = field(default_factory=list)  # [(timestamp, (cx, cy))]
    disappeared_count: int = 0
    crossed_fences: set = field(default_factory=set)  # Set of fence IDs crossed
    loitering_alerted: bool = False
    fast_movement_alerted: bool = False
    last_anpr_plate: Optional[str] = None
    last_anpr_time: float = 0.0
    last_face_time: float = 0.0
    last_face_clarity: float = 0.0
    matched_person_id: Optional[str] = None
    matched_person_name: Optional[str] = None
    carried_objects: List[str] = field(default_factory=list)  # e.g. ['knife', 'backpack']
    harmful_object_alerted: bool = False

    @property
    def age(self) -> float:
        """Total duration this object has been actively tracked in seconds."""
        return self.last_seen - self.first_seen


@dataclass
class PersonRecord:
    """
    Person profile record.
    Schema matches Supabase table: persons_of_interest
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Unidentified Subject"
    dob: str = ""
    description: str = ""
    image_url: str = ""
    face_image_url: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    face_crop: Optional[np.ndarray] = None  # In-memory face crop

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for Supabase insertion."""
        return {
            "id": self.id,
            "name": self.name,
            "dob": self.dob,
            "description": self.description,
            "image_url": self.image_url or self.face_image_url,
            "face_image_url": self.face_image_url or self.image_url,
            "timestamp": self.timestamp,
        }



@dataclass
class AlertEvent:
    """
    Standard Alert Event structure ready for Supabase database insertion.
    Schema matches Supabase table: alerts
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    camera_id: str = "camera1"
    camera_name: str = "Camera 1"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str = "intrusion"  # intrusion, anpr, loitering, fast_movement, group_clustering, face_detected, harmful_object_detected, night_mode_change
    object_type: str = "human"    # human, vehicle, n/a
    license_plate: Optional[str] = None
    track_id: Optional[int] = None
    confidence: float = 0.0
    location: str = "Border Sector A"
    image_path: str = ""
    status: str = "new"  # new -> acknowledged -> resolved
    metadata: Dict[str, Any] = field(default_factory=dict)
    frame_crop: Optional[np.ndarray] = None  # In-memory cropped or marked frame for screenshot upload

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for Supabase insertion (excluding raw image arrays)."""
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "object_type": self.object_type,
            "license_plate": self.license_plate,
            "track_id": self.track_id,
            "confidence": round(float(self.confidence), 4),
            "location": self.location,
            "image_path": self.image_path,
            "status": self.status,
            "metadata": self.metadata
        }

