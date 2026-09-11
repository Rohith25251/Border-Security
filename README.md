# IBVAP — Intelligent Border Video Analytics Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-orange.svg)](https://docs.ultralytics.com/)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL%20%2B%20Storage-3ECF8E.svg)](https://supabase.com/)
[![License](https://img.shields.io/badge/License-Proprietary%20%2F%20Defense-red.svg)]()

> **Problem Statement EUK26-10 Solution:** A software-defined AI video analytics platform that turns existing IP-based CCTV cameras into an intelligent threat detection and surveillance system without requiring proprietary FRS/ANPR/smart-camera hardware.

---

## 📋 Table of Contents
- [1. Overview & Key Capabilities](#1-overview--key-capabilities)
- [2. System Architecture](#2-system-architecture)
- [3. Prerequisites](#3-prerequisites)
- [4. Quick Start & Installation](#4-quick-start--installation)
- [5. Database & Storage Setup](#5-database--storage-setup)
- [6. Running the System](#6-running-the-system)
- [7. Verification & Benchmark Suite](#7-verification--benchmark-suite)
- [8. API Reference](#8-api-reference)
- [9. Configuration Guide](#9-configuration-guide)
- [10. Edge & Jetson Deployment Notes](#10-edge--jetson-deployment-notes)

---

## 1. Overview & Key Capabilities

IBVAP ingests live video streams from standard RTSP/IP cameras and runs an optimized multi-threaded AI analytics pipeline providing 8 core surveillance capabilities:

| # | Capability | Description | AI / Mathematical Method |
|---|------------|-------------|--------------------------|
| 1 | **Human & Vehicle Detection** | Classifies targets with bounding boxes and confidence scores | Pretrained YOLOv8n (COCO classes 0, 2, 3, 5, 7) |
| 2 | **Spatial Object Tracking** | Tracks individual identities across frames with movement trajectory history | Centroid Euclidean distance + IoU overlap matching |
| 3 | **Virtual Fence / Zone Intrusion** | Triggers alerts upon crossing perimeter lines or entering restricted polygon zones | Vector cross-product math & ray-casting algorithms |
| 4 | **Night Mode Enhancement** | Enhances low-light video feeds automatically | Average scene luminance calculation + LAB CLAHE equalization |
| 5 | **Face Detection (Cropped)** | Detects human faces inside detected person bounding boxes | OpenCV Haar Cascade / ResNet (strictly detection-only) |
| 6 | **License Plate Recognition (ANPR)** | Extracts alphanumeric license plate text from vehicles | Pretrained EasyOCR with regex validation |
| 7 | **Behavior Analytics** | Detects loitering (>5s stationary), high velocity, and group gathering ($N \ge 3$) | Spatial temporal trajectory analysis & Euclidean clustering |
| 8 | **Real-Time Visual HUD Overlay** | Renders color-coded bounding boxes, track labels, and virtual fences on live video | High-speed OpenCV graphical HUD renderer |

---

## 2. System Architecture

IBVAP operates with a decoupled, asynchronous architecture:

```
[ IP CCTV Cameras ] (RTSP / TCP)
        │
        ▼
[ Ingestion Layer ] (RTSPStreamReader - Zero Latency Buffer)
        │
        ▼
[ Multi-Camera AI Engine ] (Concurrent Camera Worker Threads)
  ├─ CLAHE Night Enhancer
  ├─ YOLOv8n Object Detector (640x640)
  ├─ Centroid + IoU Multi-Object Tracker
  ├─ Virtual Fence / Polygon Intrusion
  ├─ OpenCV Face Detector & EasyOCR ANPR
  └─ Loitering & Group Behavior Analytics
        │
        ▼
[ Alert Queue Manager ] (Thread-Safe FIFO + 5s Deduplication Cooldown)
        │
        ├──► [ Supabase Storage ] (Alert screenshot crops in 'alert-images' bucket)
        ├──► [ Supabase PostgreSQL ] ('alerts' table + Realtime Broadcast)
        └──► [ C2 Dispatcher ] (External Command & Control Webhooks)
        │
        ▼
[ FastAPI Backend ] (REST Endpoints & Live MJPEG Video Stream)
        │
        ▼
[ Operations Web Dashboard ] (Light-Themed Defense Command Center UI)
```

For full architectural specifications and component breakdowns, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 3. Prerequisites

- **Operating System:** Windows 10/11, Ubuntu 20.04/22.04 LTS, or NVIDIA Jetpack Linux.
- **Python:** Python 3.10 or higher.
- **RTSP Source:** MediaMTX RTSP Server + FFmpeg (for simulated streams) or live IP CCTV cameras.
- **Supabase Account:** Free or Pro tier project (PostgreSQL database & Storage bucket).

---

## 4. Quick Start & Installation

### Step 1: Clone Repository
```bash
git clone <repository-url>
cd "Border Security"
```

### Step 2: Create and Activate Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env` and fill in your Supabase credentials:
```bash
cp .env.example .env
```

Edit `.env`:
```ini
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-supabase-anon-or-service-role-key
MEDIA_SERVER_HOST=localhost
MEDIA_SERVER_PORT=8554
C2_WEBHOOK_URL=http://localhost:8000/api/c2/mock-webhook
```

---

## 5. Database & Storage Setup

1. Log into your [Supabase Dashboard](https://supabase.com/dashboard).
2. Navigate to the **SQL Editor**.
3. Copy and run the entire script from [`supabase_schema.sql`](supabase_schema.sql):
   - Creates the `alerts` table with indices.
   - Configures the `alert-images` public storage bucket.
   - Enables Row Level Security (RLS) policies.
   - Adds the `alerts` table to the `supabase_realtime` publication for live dashboard syncing.

---

## 6. Running the System

### Step 1: Start RTSP Streams (Simulated via MediaMTX & FFmpeg)
If using simulated video streams:
```bash
# Start MediaMTX RTSP Server
cd mediamtx
./mediamtx.exe

# In separate terminals, publish video streams using FFmpeg:
ffmpeg -re -stream_loop -1 -i "videos/camera1.mp4" -c copy -f rtsp rtsp://localhost:8554/camera1
ffmpeg -re -stream_loop -1 -i "videos/camera2.mp4" -c copy -f rtsp rtsp://localhost:8554/camera2
ffmpeg -re -stream_loop -1 -i "videos/camera3.mp4" -c copy -f rtsp rtsp://localhost:8554/camera3
```

### Step 2: Launch the Unified IBVAP Backend & Web Dashboard
```bash
python main.py
```
*Or using Uvicorn directly:*
```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Step 3: Access the Web Dashboard
Open your browser and navigate to:
```
http://localhost:8000
```
- **Live Surveillance Grid:** View all 3 cameras with AI HUD overlays in real-time.
- **Threat Event Feed:** Live stream of color-coded intrusion, loitering, and ANPR alerts.
- **Incident Management:** Click alerts to inspect captured screenshot crops, view telemetry, and acknowledge or dismiss events.
- **Analytics & C2 Dispatch:** View threat breakdown charts and configure external Command & Control webhooks.

---

## 7. Verification & Benchmark Suite

Execute the dedicated test suite to verify every component independently or run the complete end-to-end benchmark:

```bash
# 1. Verify Core AI Engine (All 8 capabilities on single frame/stream)
python test_stage3_2.py

# 2. Verify Supabase Database, Storage Uploads, and Alert Queue Cooldown
python test_stage3_3.py

# 3. Verify Multi-Camera Concurrency & Worker Synchronization
python test_stage3_4.py

# 4. Verify FastAPI Endpoints & REST API
python test_stage3_5.py

# 5. Full End-to-End Integration & Multi-Camera FPS Benchmarking Suite
python test_stage3_7_benchmarks.py
```

---

## 8. API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the Light-Themed Web Dashboard |
| `GET` | `/api/cameras` | List of configured cameras and current worker status |
| `GET` | `/api/cameras/{id}/stream` | Live MJPEG video stream with HUD overlays |
| `GET` | `/api/alerts` | Paginated list of threat events (filterable by camera, severity, status) |
| `GET` | `/api/alerts/{id}` | Detailed alert event metadata |
| `PUT` | `/api/alerts/{id}/status` | Update alert status (`acknowledged`, `dismissed`, `escalated`) |
| `GET` | `/api/stats` | Real-time surveillance statistics (total alerts, severity breakdown, active cameras) |
| `POST` | `/api/c2/webhook-config` | Update external C2 Command & Control webhook destination URL |

---

## 9. Configuration Guide

Per-camera parameters, virtual tripwires, polygon zones, and processing options are configured declaratively in [`config/cameras.json`](config/cameras.json):

```json
{
  "camera_id": "camera1",
  "name": "Perimeter North Gate",
  "rtsp_url": "rtsp://localhost:8554/camera1",
  "frame_skip": 2,
  "virtual_fences": [
    {
      "id": "fence_north_line",
      "type": "line",
      "p1": [100, 300],
      "p2": [540, 300],
      "name": "North Boundary Line"
    }
  ],
  "enable_face_detection": true,
  "enable_anpr": true,
  "night_mode_threshold": 65.0
}
```

---

## 10. Edge & Jetson Deployment Notes

- **Frame Skipping:** `frame_skip: 2` (processes every 3rd frame) maintains real-time tracking while reducing compute load by 66%.
- **Inference Resizing:** YOLOv8 runs at `640x640`, optimizing TensorRT/CUDA throughput.
- **OpenCV Optimization:** Built with multithreading isolation and zero-copy MJPEG encoding for edge hardware.
- **Offline Resilience:** Alerts are queued locally in memory and synced to Supabase as network availability permits.

---

## 🛡️ License & Acknowledgments
Developed for Border Surveillance & Critical Infrastructure Defense Operations (Problem Statement EUK26-10). Uses open-source pretrained models from Ultralytics YOLOv8 and EasyOCR.
