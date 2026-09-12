import React, { useState } from 'react';
import { Camera, Moon, Sun, Users, Activity, Eye, Radio, AlertTriangle, Plus, Trash2, Globe, MapPin } from 'lucide-react';
import AddCameraModal from './AddCameraModal';

export default function CameraGrid({ cameras, onSelectSnapshot, onRefreshCameras }) {
  const [selectedFilter, setSelectedFilter] = useState('all');
  const [streamKeys, setStreamKeys] = useState({});
  const [showAddModal, setShowAddModal] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  const reloadStream = (cameraId) => {
    setStreamKeys((prev) => ({
      ...prev,
      [cameraId]: Date.now()
    }));
  };

  const handleDeleteCamera = async (camId, camName) => {
    if (!window.confirm(`Are you sure you want to remove camera channel '${camName || camId}'?`)) {
      return;
    }
    setDeletingId(camId);
    try {
      const res = await fetch(`/api/cameras/${camId}`, { method: 'DELETE' });
      if (res.ok) {
        if (onRefreshCameras) onRefreshCameras();
      } else {
        alert(`Failed to delete camera ${camId}`);
      }
    } catch (err) {
      alert(`Error deleting camera: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const filteredCameras = selectedFilter === 'all'
    ? cameras
    : cameras.filter((c) => (c.camera_id || c.id) === selectedFilter);

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

        <div className="section-actions" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            className="button button-primary"
            onClick={() => setShowAddModal(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              fontSize: '0.85rem',
              background: '#2563eb',
              color: '#ffffff',
              borderRadius: '8px',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600
            }}
          >
            <Plus size={16} /> Add IP Camera
          </button>

          <select
            className="filter-select"
            value={selectedFilter}
            onChange={(e) => setSelectedFilter(e.target.value)}
          >
            <option value="all">All Channels ({cameras.length} Feeds)</option>
            {cameras.map((cam) => {
              const cid = cam.camera_id || cam.id;
              return (
                <option key={cid} value={cid}>
                  {cam.camera_name || cam.name || cid}
                </option>
              );
            })}
          </select>
        </div>
      </div>

      <div className="camera-grid">
        {filteredCameras.map((cam) => {
          const cid = cam.camera_id || cam.id;
          const streamUrl = `/api/cameras/${cid}/stream${streamKeys[cid] ? `?t=${streamKeys[cid]}` : ''}`;
          const isNight = cam.night_mode_active || cam.is_night;
          const isOffline = cam.is_connected === false;
          const camDisplayName = cam.camera_name || cam.name || cid;

          return (
            <div key={cid} className="camera-card">
              {/* Header */}
              <div className="camera-card-header">
                <div className="camera-name-box">
                  <Camera size={16} color="#2563eb" />
                  <span className="camera-name">{camDisplayName}</span>
                  <span className="camera-id-badge">{cid}</span>
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

                  {/* Delete button */}
                  <button
                    onClick={() => handleDeleteCamera(cid, camDisplayName)}
                    disabled={deletingId === cid}
                    title="Remove Camera Channel"
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: '#94a3b8',
                      cursor: 'pointer',
                      padding: '4px',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center'
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = '#ef4444')}
                    onMouseLeave={(e) => (e.currentTarget.style.color = '#94a3b8')}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {/* Video Player */}
              <div className="camera-video-container">
                <img
                  src={streamUrl}
                  alt={`Live Stream - ${cid}`}
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
                  <span>Connecting to {camDisplayName}...</span>
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ marginTop: '8px' }}
                    onClick={() => reloadStream(cid)}
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
                  <MapPin size={12} color="#64748b" />
                  <span className="telemetry-val" style={{ fontSize: '0.78rem', color: '#475569' }}>
                    {cam.location || 'Border Sector'}
                  </span>
                </div>

                <div className="telemetry-item">
                  <span style={{ color: '#64748b' }}>Latency:</span>
                  <span className="telemetry-val">{Math.round(cam.inference_time_ms || cam.inference_latency_ms || 0)} ms</span>
                </div>

                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => onSelectSnapshot && onSelectSnapshot({
                      image_url: `/api/cameras/${cid}/snapshot?t=${Date.now()}`,
                      event_type: 'live_snapshot',
                      camera_id: cid,
                      timestamp: new Date().toISOString(),
                      details: `Manual snapshot capture for ${camDisplayName}`
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

      {/* Add Camera Modal */}
      <AddCameraModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onCameraAdded={() => {
          if (onRefreshCameras) onRefreshCameras();
        }}
      />
    </div>
  );
}
