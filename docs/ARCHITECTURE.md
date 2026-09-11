# IBVAP System Architecture Documentation

The **Intelligent Border Video Analytics Platform (IBVAP)** is a modular, software-defined AI video analytics platform designed to turn legacy IP-based CCTV cameras into an intelligent threat detection and surveillance system without requiring proprietary smart-camera hardware.

---

## 1. High-Level Architecture Diagram Description

*(Use this description to render in draw.io, Lucidchart, PlantUML, or Visio)*

```
+----------------------------------------------------------------------------------------------------+
|                                      VIDEO INGESTION LAYER                                         |
|  +--------------------------------+ +--------------------------------+ +------------------------+  |
|  | IP CCTV Camera 1 (Daytime 4K)  | | IP CCTV Camera 2 (Night Sector)| | IP CCTV Camera 3 (Hwy) |  |
|  | rtsp://localhost:8554/camera1  | | rtsp://localhost:8554/camera2  | | rtsp://localhost:8554|  |
|  +--------------------------------+ +--------------------------------+ +------------------------+  |
+-------------------------------------------------┬--------------------------------------------------+
                                                  │ RTSP TCP Stream
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                     MULTI-CAMERA AI ENGINE                                         |
|                                                                                                    |
|  +---------------------------+  +---------------------------+  +--------------------------------+  |
|  |  Camera Worker Thread 1   |  |  Camera Worker Thread 2   |  |     Camera Worker Thread 3     |  |
|  |  - Ingestion (Buffer = 1) |  |  - Ingestion (Buffer = 1) |  |     - Ingestion (Buffer = 1)   |  |
|  |  - Frame Skip (k = 2)     |  |  - Frame Skip (k = 2)     |  |     - Frame Skip (k = 2)       |  |
|  |  - Resize to 640x640      |  |  - LAB CLAHE Night Mode   |  |     - Resize to 640x640        |  |
|  |  - YOLOv8 (Human/Vehicle) |  |  - YOLOv8 (Human/Vehicle) |  |     - YOLOv8 (Human/Vehicle)   |  |
|  |  - Centroid/IoU Tracker   |  |  - Centroid/IoU Tracker   |  |     - Centroid/IoU Tracker     |  |
|  |  - Virtual Fence (Line)   |  |  - Restricted Zone (Poly) |  |     - Roadway Fence (Line)     |  |
|  |  - OpenCV Face Detector   |  |  - EasyOCR ANPR Pipeline  |  |     - Behavior Analytics       |  |
|  |  - Behavior Analytics     |  |  - Behavior Analytics     |  |       (Loitering, Clustering)  |  |
|  +---------------------------+  +---------------------------+  +--------------------------------+  |
+-------------------------------------------------┬--------------------------------------------------+
                                                  │ Thread-Safe Alerts Batch
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                  DATABASE & QUEUE SYNCHRONIZER                                     |
|  +----------------------------------------------------------------------------------------------+  |
|  |  AlertQueueManager (Thread-Safe FIFO Queue + Per-Track Cooldown Suppression [5.0s])           |  |
|  +----------------------------------------------┬-----------------------------------------------+  |
|                                                 │ Asynchronous Worker
|                         ┌───────────────────────┴──────────────────────┐
|                         ▼                                              ▼
|             +-----------------------+                      +-----------------------+
|             |   Supabase Storage    |                      |  Supabase PostgreSQL  |
|             |  (Bucket: alert-images|                      |     (Table: alerts)   |
|             |   JPEG Compression)   |                      |  (Realtime Broadcast) |
|             +-----------------------+                      +-----------------------+
+-------------------------------------------------┬--------------------------------------------------+
                                                  │ Realtime Event Stream & REST
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                      BACKEND APPLICATION LAYER                                     |
|  FastAPI Server (api/app.py)                                                                       |
|  - GET / (Dashboard HTML)                                                                          |
|  - GET /api/cameras & /api/cameras/{id}/stream (Live MJPEG Video Feeds)                            |
|  - GET /api/alerts, GET /api/alerts/{id}, PUT /api/alerts/{id}/status                              |
|  - GET /api/stats (Real-time surveillance analytics)                                              |
|  - POST /api/c2/webhook-config (C2 Command & Control Dispatcher)                                   |
+----------------------------------------┬─────────────────────────────┬------------------------------+
                                         │                             │
                                         ▼                             ▼
+---------------------------------------------------+       +----------------------------------------+
|               OPERATIONS WEB DASHBOARD            |       |     COMMAND & CONTROL (C2) SYSTEMS     |
|  - Multi-Camera Surveillance Grid                 |       |  - External Sector HQ Webhooks         |
|  - Color-Coded Real-Time Threat Feed              |       |  - Automated Tactical Incident Alerts  |
|  - Interactive Status Updates & Snapshot Modal    |       |  - Dispatch Forwarding via HTTP POST   |
|  - Chart.js Threat Distribution & Telemetry       |       +----------------------------------------+
+---------------------------------------------------+
```

---

## 2. Component Breakdown

### 2.1 Video Ingestion Module (`core/ingestion.py`)
- **Transport**: RTSP over TCP (`rtsp_transport;tcp`) eliminating UDP packet drop artifacts.
- **Latency Control**: Zero-buffer-lag strategy (`cv2.CAP_PROP_BUFFERSIZE = 1`).
- **Resilience**: Asynchronous connection loop with exponential backoff on network dropouts.

### 2.2 Pretrained AI Analytics Pipeline (`core/`)
- **Object Detection (`core/detector.py`)**: Uses pretrained `YOLOv8n` on COCO dataset, filtering Humans (`class 0`) and Vehicles (`classes 2, 3, 5, 7`). Input frames resized to 640x640 for real-time throughput.
- **Multi-Object Tracker (`core/tracker.py`)**: Centroid Euclidean distance + IoU association tracker maintaining persistent track IDs, trajectory history, and occlusion tolerance.
- **Virtual Fence Intrusion (`core/virtual_fence.py`)**: Vector crossing math for tripwire lines and ray-casting for restricted polygon zones with single-trigger tracking per track ID.
- **Night Mode Enhancement (`core/night_enhancer.py`)**: Mean scene luminance calculator with automatic LAB-space CLAHE contrast enhancement for low-light camera feeds.
- **Face Detection (`core/face_detector.py`)**: OpenCV frontal face detector running on human bounding box crops (strictly detection only, no identity matching).
- **ANPR Pipeline (`core/anpr.py`)**: Pretrained `EasyOCR` pipeline extracting alphanumeric license plate strings with regex validation.
- **Behavior Analytics (`core/behavior_analytics.py`)**: Algorithmic detection of Loitering (>5s stationary check), Fast Movement (velocity threshold), and Group Clustering ($N \ge 3$ proximate centroids).

### 2.3 Database & Event Queue (`db/`)
- **Queue Manager (`db/queue_manager.py`)**: Thread-safe FIFO queue decoupling AI frame processing from network latency. Enforces a 5.0-second per-track cooldown to prevent spam alerts.
- **Supabase Manager (`db/supabase_client.py`)**: Persists alert records in PostgreSQL and uploads JPEG screenshot crops to Supabase Storage bucket `alert-images`.

### 2.4 FastAPI Backend (`api/`)
- Exposes REST endpoints, serves the light-themed Ops Web Dashboard, streams live MJPEG video with AI HUD bounding boxes, and provides C2 webhook integration.

### 2.5 Web Dashboard (`frontend/`)
- Modern, light-themed defense command center interface with real-time video feeds, color-coded threat table, interactive status updating, Chart.js analytics, and Supabase Realtime synchronization.
