import React, { useState } from 'react';
import { Camera, Plus, X, Globe, MapPin, Shield, Moon, Car, UserCheck, AlertCircle, CheckCircle } from 'lucide-react';

export default function AddCameraModal({ isOpen, onClose, onCameraAdded }) {
  const [ipAddress, setIpAddress] = useState('');
  const [rtspUrl, setRtspUrl] = useState('');
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [enableFace, setEnableFace] = useState(true);
  const [enableAnpr, setEnableAnpr] = useState(true);
  const [enableNight, setEnableNight] = useState(true);
  const [confThreshold, setConfThreshold] = useState(0.25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  if (!isOpen) return null;

  // Auto-fill Name, Location, and Stream URL as user types IP address
  const handleIpChange = (e) => {
    const val = e.target.value;
    setIpAddress(val);

    const trimmed = val.trim();
    if (!trimmed) {
      return;
    }

    // Extract clean IP
    let extractedIp = trimmed;
    const ipMatch = trimmed.match(/(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/);
    if (ipMatch) {
      extractedIp = ipMatch[1];
    }

    // Auto-populate Name if user hasn't typed custom name
    if (!name || name.startsWith('Camera (')) {
      setName(`Camera (${extractedIp})`);
    }

    // Auto-populate Location if user hasn't typed custom location
    if (!location || location.startsWith('Sector -') || location.startsWith('North Perimeter')) {
      setLocation(`Sector - ${extractedIp}`);
    }

    // Auto-construct Stream URL if user hasn't customized it
    if (!rtspUrl || rtspUrl.startsWith('http://') || rtspUrl.startsWith('rtsp://')) {
      if (trimmed.startsWith('http://') || trimmed.startsWith('https://') || trimmed.startsWith('rtsp://')) {
        setRtspUrl(trimmed);
      } else if (trimmed.includes(':')) {
        setRtspUrl(`http://${trimmed}/video`);
      } else {
        setRtspUrl(`http://${trimmed}:8080/video`);
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!ipAddress.trim() && !rtspUrl.trim()) {
      setError('Please provide an IP address or direct stream URL.');
      return;
    }

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const res = await fetch('/api/cameras', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ip_address: ipAddress.trim(),
          rtsp_url: rtspUrl.trim() || undefined,
          name: name.trim() || undefined,
          location: location.trim() || undefined,
          enable_face_detection: enableFace,
          enable_anpr: enableAnpr,
          enable_night_mode: enableNight,
          conf_threshold: parseFloat(confThreshold)
        })
      });

      const data = await res.json();
      if (res.ok) {
        setSuccess(`Camera '${data.camera?.name || name}' added & started successfully!`);
        setTimeout(() => {
          if (onCameraAdded) onCameraAdded(data.camera);
          onClose();
        }, 800);
      } else {
        setError(data.detail || 'Failed to add camera.');
      }
    } catch (err) {
      setError('Network error while connecting camera: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-container" style={{ maxWidth: '580px' }} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ background: '#dbeafe', color: '#2563eb', padding: '6px', borderRadius: '8px' }}>
              <Plus size={20} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.15rem', color: '#1e293b' }}>Add IP Camera Channel</h3>
              <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                Connect an IP webcam, CCTV or RTSP stream for live AI security analytics
              </p>
            </div>
          </div>
          <button className="icon-button" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {error && (
            <div style={{ background: '#fee2e2', border: '1px solid #ef4444', color: '#991b1b', padding: '10px 14px', borderRadius: '8px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertCircle size={16} /> {error}
            </div>
          )}

          {success && (
            <div style={{ background: '#dcfce7', border: '1px solid #22c55e', color: '#166534', padding: '10px 14px', borderRadius: '8px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle size={16} /> {success}
            </div>
          )}

          {/* IP Address */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
              <Globe size={15} color="#2563eb" /> Camera IP Address / Host
            </label>
            <input
              type="text"
              className="filter-select"
              style={{ width: '100%', boxSizing: 'border-box', padding: '9px 12px', fontSize: '0.9rem' }}
              placeholder="e.g. 192.168.1.50 or 192.0.0.4:8080"
              value={ipAddress}
              onChange={handleIpChange}
              autoFocus
            />
            <span style={{ fontSize: '0.74rem', color: '#64748b', marginTop: '3px', display: 'block' }}>
              Tip: Enter IP or mobile IP Webcam address. Name and stream URL will auto-populate automatically.
            </span>
          </div>

          {/* Stream URL (Auto-Generated or Custom) */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
              <Camera size={15} color="#2563eb" /> Video Stream URL (RTSP / HTTP)
            </label>
            <input
              type="text"
              className="filter-select"
              style={{ width: '100%', boxSizing: 'border-box', padding: '9px 12px', fontSize: '0.88rem' }}
              placeholder="http://192.168.1.50:8080/video or rtsp://..."
              value={rtspUrl}
              onChange={(e) => setRtspUrl(e.target.value)}
            />
          </div>

          {/* Two-column: Label and Location */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '6px', display: 'block' }}>
                Camera Label / Name
              </label>
              <input
                type="text"
                className="filter-select"
                style={{ width: '100%', boxSizing: 'border-box', padding: '9px 12px', fontSize: '0.88rem' }}
                placeholder="e.g. Perimeter Camera 4"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.85rem', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                <MapPin size={14} color="#059669" /> Location / Sector
              </label>
              <input
                type="text"
                className="filter-select"
                style={{ width: '100%', boxSizing: 'border-box', padding: '9px 12px', fontSize: '0.88rem' }}
                placeholder="e.g. South Boundary Gate"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </div>
          </div>

          {/* AI Features Checklist */}
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '12px 14px' }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#475569', display: 'block', marginBottom: '8px' }}>
              Active AI Analytics Modules:
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.84rem', color: '#1e293b', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={enableFace}
                  onChange={(e) => setEnableFace(e.target.checked)}
                />
                <UserCheck size={16} color="#059669" />
                <span>Face Recognition & Database Watchlist Matching</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.84rem', color: '#1e293b', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={enableAnpr}
                  onChange={(e) => setEnableAnpr(e.target.checked)}
                />
                <Car size={16} color="#2563eb" />
                <span>Vehicle Detection & ANPR License Plate Reading</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.84rem', color: '#1e293b', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={enableNight}
                  onChange={(e) => setEnableNight(e.target.checked)}
                />
                <Moon size={16} color="#d97706" />
                <span>CLAHE Night Enhancement (Low-Light)</span>
              </label>
            </div>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
            <button
              type="button"
              className="button button-outline"
              onClick={onClose}
              disabled={loading}
              style={{ padding: '8px 16px', fontSize: '0.88rem' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="button button-primary"
              disabled={loading}
              style={{ padding: '8px 20px', fontSize: '0.88rem', background: '#2563eb', color: '#ffffff' }}
            >
              {loading ? 'Connecting Channel...' : 'Connect & Add Channel'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
