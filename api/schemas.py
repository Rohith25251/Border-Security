"""
Pydantic Schemas for IBVAP FastAPI Backend.
Ensures strict validation, type safety, and standardized response envelopes.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AlertStatusUpdate(BaseModel):
    status: str = Field(..., description="Status must be one of: 'new', 'acknowledged', 'resolved'")

    class Config:
        json_schema_extra = {
            "example": {"status": "acknowledged"}
        }


class AlertResponse(BaseModel):
    id: str
    camera_id: str
    camera_name: str
    timestamp: str
    event_type: str
    object_type: str
    license_plate: Optional[str] = None
    track_id: Optional[int] = None
    confidence: float
    location: str
    image_path: str = ""
    status: str = "new"


class CameraStatusResponse(BaseModel):
    camera_id: str
    camera_name: str
    location: str
    is_running: bool
    is_connected: bool
    fps: float
    inference_time_ms: float
    total_frames_read: int
    total_frames_processed: int
    total_alerts: int
    active_tracks: int
    is_night: bool
    scene_brightness: float


class StatsResponse(BaseModel):
    total_alerts: int
    by_event_type: Dict[str, int]
    by_status: Dict[str, int]
    by_camera: Dict[str, int]
    is_supabase_connected: bool


class WebhookConfigRequest(BaseModel):
    webhook_url: str = Field(..., description="External HTTP/HTTPS URL to receive real-time alert webhooks")
    secret_token: Optional[str] = Field(None, description="Optional bearer token or secret header")
    description: Optional[str] = Field("C2 Command & Control System", description="Optional label for the webhook integration")

    class Config:
        json_schema_extra = {
            "example": {
                "webhook_url": "https://c2-border-command.mil/api/alerts/ingress",
                "description": "Border Patrol HQ Command Integration"
            }
        }


class WebhookConfigResponse(BaseModel):
    id: str
    webhook_url: str
    description: str
    created_at: str
    active: bool


class PersonCreateRequest(BaseModel):
    name: str = Field(..., description="Person full name")
    dob: Optional[str] = Field("", description="Date of birth (e.g. YYYY-MM-DD)")
    description: Optional[str] = Field("", description="Person description or notes")
    image_url: Optional[str] = Field("", description="Photo URL or base64 data")
    face_image_url: Optional[str] = Field(None, description="Fallback face image URL")


class PersonUpdateRequest(BaseModel):
    name: Optional[str] = None
    dob: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    face_image_url: Optional[str] = None


class PersonResponse(BaseModel):
    id: str
    name: str
    dob: Optional[str] = ""
    description: Optional[str] = ""
    image_url: Optional[str] = None
    face_image_url: Optional[str] = None
    timestamp: Optional[str] = ""


