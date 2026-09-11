import React, { useState } from 'react';
import { Camera, Moon, Sun, Users, Activity, Eye, Maximize2, Radio, AlertTriangle } from 'lucide-react';

export default function CameraGrid({ cameras, onSelectSnapshot }) {
  const [selectedFilter, setSelectedFilter] = useState('all');
  const [streamKeys, setStreamKeys] = useState({});

  const reloadStream = (cameraId) => {
    setStreamKeys((prev) => ({
      ...prev,
      [cameraId]: Date.now()
    }));
  };

  const filteredCameras = selectedFilter === 'all'
    ? cameras
    : cameras.filter((c) => c.camera_id === selectedFilter);

  return (
    <div className="camera-grid-section">
      <div className="section-header">
        <div>
          <h2 className="section-title">
            <Radio size={22} color="#ef4444" />
            Active Detection Channels
          </h2>
          <p style={{ fontSize: '0.85rem', color: '#64748b', marginTop: '2px' }}>
            Real-time multi-channel video streams with HUD threat detection overlays
          </p>
        </div>

        <div className="section-actions">
          <select
            className="filter-select"
            value={selectedFilter}
            onChange={(e) => setSelectedFilter(e.target.value)}
          >
            <option value="all">All Channels ({cameras.length} Feeds)</option>
            {cameras.map((cam) => (
              <option key={cam.camera_id} value={cam.camera_id}>
                {cam.name || cam.camera_id}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="camera-grid">
        {filteredCameras.map((cam) => {
          const streamUrl = `/api/cameras/${cam.camera_id}/stream${streamKeys[cam.camera_id] ? `?t=${streamKeys[cam.camera_id]}` : ''}`;
          const isNight = cam.night_mode_active || cam.is_night;
          const isOffline = cam.is_connected === false;

          return (
            <div key={cam.camera_id} className="camera-card">
              {/* Header */}
              <div className="camera-card-header">
                <div className="camera-name-box">
                  <Camera size={16} color="#2563eb" />
                  <span className="camera-name">{cam.name || cam.camera_id}</span>
                  <span className="camera-id-badge">{cam.camera_id}</span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {isOffline ? (
                    <span className="threat-badge intrusion" style={{ fontSize: '0.68rem', padding: '2px 6px' }}>
                      <AlertTriangle size={11} /> Stream Offline
                    </span>
                  ) : isNight ? (
                    <span className="threat-badge night" style={{ fontSize: '0.68rem', padding: '2px 6px' }}>
                      <Moon size={11} /> CLAHE Night Mode
                    </span>
                  ) : (
                    <span className="threat-badge safe" style={{ fontSize: '0.68rem', padding: '2px 6px' }}>
                      <Sun size={11} /> Day Mode
                    </span>
                  )}
                </div>
              </div>

              {/* Video Player */}
              <div className="camera-video-container">
                <img
                  src={streamUrl}
                  alt={`Live Stream - ${cam.camera_id}`}
                  className="camera-video-feed"
                  onError={(e) => {
                    e.target.style.display = 'none';
                    if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex';
                  }}
                  onLoad={(e) => {
                    e.target.style.display = 'block';
                    if (e.target.nextSibling) e.target.nextSibling.style.display = 'none';
                  }}
                />

                <div className="camera-video-placeholder" style={{ display: 'none' }}>
                  <Activity size={32} />
                  <span>CCTV Offline: Connecting to {cam.name || cam.camera_id}...</span>
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ marginTop: '8px' }}
                    onClick={() => reloadStream(cam.camera_id)}
                  >
                    Retry Connection
                  </button>
                </div>

                {/* Video HUD Overlays */}
                <div className="video-hud-overlay">
                  <div className="hud-pill">
                    <span className="pulse-dot hud-live-tag" style={{ backgroundColor: isOffline ? '#ef4444' : '#10b981' }}></span>
                    <span>{isOffline ? 'OFFLINE' : 'LIVE'}</span>
                    <span style={{ color: '#94a3b8' }}>|</span>
                    <span>{(cam.current_fps || cam.fps || 0).toFixed(1)} FPS</span>
                  </div>

                  <div className="hud-pill">
                    <Users size={12} color="#38bdf8" />
                    <span>{cam.active_tracks || 0} Targets</span>
                  </div>
                </div>
              </div>

              {/* Telemetry Footer */}
              <div className="camera-card-footer">
                <div className="telemetry-item">
                  <span style={{ color: '#64748b' }}>Latency:</span>
                  <span className="telemetry-val">{Math.round(cam.inference_latency_ms || 0)} ms</span>
                </div>

                <div className="telemetry-item">
                  <span style={{ color: '#64748b' }}>Brightness:</span>
                  <span className="telemetry-val">{(cam.current_brightness || 0).toFixed(1)} Lux</span>
                </div>

                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => onSelectSnapshot && onSelectSnapshot({
                      image_url: `/api/cameras/${cam.camera_id}/snapshot?t=${Date.now()}`,
                      event_type: 'live_snapshot',
                      camera_id: cam.camera_id,
                      timestamp: new Date().toISOString(),
                      details: `Manual snapshot capture for ${cam.name || cam.camera_id}`
                    })}
                    title="Capture Instant Frame Snapshot"
                  >
                    <Eye size={13} /> Snapshot
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
