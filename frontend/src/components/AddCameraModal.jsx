import React, { useState, useEffect } from 'react';
import { 
  Camera, Plus, X, Globe, MapPin, Shield, Moon, Car, 
  UserCheck, AlertCircle, CheckCircle, Sparkles, Sliders, Zap
} from 'lucide-react';

// Smart IP to Location Derivation Helper
function deriveLocationFromIp(input) {
  const trimmed = (input || '').trim();
  if (!trimmed) return { name: '', location: '', url: '' };

  let ip = '';
  const ipMatch = trimmed.match(/(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/);
  if (ipMatch) {
    ip = ipMatch[1];
  } else if (trimmed.includes('localhost') || trimmed.includes('127.0.0.1')) {
    ip = '127.0.0.1';
  }

  let location = 'Border Sector Zone';
  let name = 'Camera Channel';
  let streamUrl = trimmed;

  if (ip) {
    const octets = ip.split('.');
    const last = octets[3] || '1';
    const third = parseInt(octets[2] || '0', 10);

    if (ip === '192.0.0.4') {
      location = 'North Perimeter Gate (192.0.0.4)';
      name = 'Camera 1 - Border Daytime';
    } else if (octets[0] === '192' && octets[1] === '0') {
      location = `North Perimeter Gate (${ip})`;
      name = `Camera ${last} - Perimeter Gate`;
    } else if (octets[0] === '192' && octets[1] === '168' && third === 0) {
      location = `Sector Alpha Main Entrance (${ip})`;
      name = `Camera ${last} - Alpha Gate`;
    } else if (octets[0] === '192' && octets[1] === '168' && third === 1) {
      location = `Sector Bravo Wire (${ip})`;
      name = `Camera ${last} - Bravo Wire`;
    } else if (octets[0] === '192' && octets[1] === '168' && third >= 2) {
      location = `Sector Charlie Highway Checkpoint (${ip})`;
      name = `Camera ${last} - Checkpoint`;
    } else if (octets[0] === '10') {
      location = `Eastern Low-Light Sector (${ip})`;
      name = `Camera ${last} - Night Sector`;
    } else if (ip === '127.0.0.1') {
      location = `Local Sector Corridor (${ip})`;
      name = `Camera Local (${ip})`;
    } else {
      location = `Border Sector ${octets[1]}.${octets[2]} (${ip})`;
      name = `Camera (${ip})`;
    }

    // Auto-construct Stream URL
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://') || trimmed.startsWith('rtsp://')) {
      streamUrl = trimmed;
    } else if (trimmed.includes(':')) {
      streamUrl = `http://${trimmed}/video`;
    } else {
      streamUrl = `http://${ip}:8080/video`;
    }
  }

  return { name, location, url: streamUrl, ip };
}

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

  const handleIpChange = (e) => {
    const val = e.target.value;
    setIpAddress(val);

    const derived = deriveLocationFromIp(val);
    if (derived.ip) {
      setName(derived.name);
      setLocation(derived.location);
      setRtspUrl(derived.url);
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
        setSuccess(`Camera '${data.camera?.name || name}' added & live inference active!`);
        setTimeout(() => {
          if (onCameraAdded) onCameraAdded(data.camera);
          onClose();
        }, 700);
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
    <div 
      className="modal-backdrop" 
      onClick={onClose}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.65)',
        backdropFilter: 'blur(6px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px'
      }}
    >
      <div 
        className="modal-card" 
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#ffffff',
          width: '100%',
          maxWidth: '560px',
          borderRadius: '16px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25), 0 0 0 1px rgba(226, 232, 240, 0.8)',
          border: '1px solid #e2e8f0',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          animation: 'fadeInScale 0.2s cubic-bezier(0.16, 1, 0.3, 1)'
        }}
      >
        {/* Header */}
        <div style={{
          padding: '18px 24px',
          borderBottom: '1px solid #f1f5f9',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#f8fafc'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: '38px',
              height: '38px',
              borderRadius: '10px',
              background: '#eff6ff',
              border: '1px solid #dbeafe',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#2563eb'
            }}>
              <Plus size={22} strokeWidth={2.5} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.12rem', fontWeight: 700, color: '#0f172a' }}>
                Add IP Camera Channel
              </h3>
              <p style={{ margin: '2px 0 0 0', fontSize: '0.8rem', color: '#64748b' }}>
                Connect an IP camera, mobile CCTV or RTSP stream for real-time AI surveillance
              </p>
            </div>
          </div>
          <button 
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#64748b',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#e2e8f0')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
          >
            <X size={20} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {error && (
            <div style={{
              background: '#fef2f2',
              border: '1px solid #fca5a5',
              color: '#991b1b',
              padding: '10px 14px',
              borderRadius: '10px',
              fontSize: '0.86rem',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              <AlertCircle size={17} color="#dc2626" />
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div style={{
              background: '#f0fdf4',
              border: '1px solid #86efac',
              color: '#166534',
              padding: '10px 14px',
              borderRadius: '10px',
              fontSize: '0.86rem',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              <CheckCircle size={17} color="#16a34a" />
              <span>{success}</span>
            </div>
          )}



          {/* Camera IP Address */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.86rem', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
              <Globe size={15} color="#2563eb" /> Camera IP Address / Host
            </label>
            <input
              type="text"
              style={{
                width: '100%',
                boxSizing: 'border-box',
                padding: '10px 14px',
                fontSize: '0.92rem',
                borderRadius: '8px',
                border: '1.5px solid #cbd5e1',
                background: '#ffffff',
                color: '#0f172a',
                outline: 'none',
                transition: 'border-color 0.15s'
              }}
              placeholder="e.g. 192.168.1.50 or 192.0.0.4:8080"
              value={ipAddress}
              onChange={handleIpChange}
              autoFocus
            />
          </div>

          {/* Stream URL */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.86rem', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
              <Camera size={15} color="#2563eb" /> Video Stream URL (Auto-Constructed)
            </label>
            <input
              type="text"
              style={{
                width: '100%',
                boxSizing: 'border-box',
                padding: '9px 14px',
                fontSize: '0.88rem',
                borderRadius: '8px',
                border: '1.5px solid #cbd5e1',
                background: '#f8fafc',
                color: '#0f172a',
                outline: 'none'
              }}
              placeholder="http://192.168.1.50:8080/video or rtsp://..."
              value={rtspUrl}
              onChange={(e) => setRtspUrl(e.target.value)}
            />
          </div>

          {/* Label and Location (Auto-derived) */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '0.84rem', fontWeight: 600, color: '#1e293b', marginBottom: '6px', display: 'block' }}>
                Camera Label (Auto-Derived)
              </label>
              <input
                type="text"
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  padding: '9px 12px',
                  fontSize: '0.88rem',
                  borderRadius: '8px',
                  border: '1.5px solid #cbd5e1',
                  background: '#ffffff',
                  color: '#0f172a',
                  outline: 'none'
                }}
                placeholder="e.g. Camera 1 - Border Daytime"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.84rem', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
                <MapPin size={14} color="#059669" /> Location (Auto-Derived)
              </label>
              <input
                type="text"
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  padding: '9px 12px',
                  fontSize: '0.88rem',
                  borderRadius: '8px',
                  border: '1.5px solid #cbd5e1',
                  background: '#ffffff',
                  color: '#0f172a',
                  outline: 'none'
                }}
                placeholder="e.g. North Perimeter Gate"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </div>
          </div>

          {/* Active AI Modules */}
          <div style={{
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '12px',
            padding: '14px 16px'
          }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#334155', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
              <Shield size={14} color="#2563eb" /> Active AI Surveillance Engines:
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.86rem', color: '#1e293b', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={enableFace}
                  onChange={(e) => setEnableFace(e.target.checked)}
                  style={{ width: '16px', height: '16px', accentColor: '#2563eb' }}
                />
                <UserCheck size={16} color="#059669" />
                <span style={{ fontWeight: 500 }}>Face Recognition & Watchlist Database Matching</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.86rem', color: '#1e293b', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={enableAnpr}
                  onChange={(e) => setEnableAnpr(e.target.checked)}
                  style={{ width: '16px', height: '16px', accentColor: '#2563eb' }}
                />
                <Car size={16} color="#2563eb" />
                <span style={{ fontWeight: 500 }}>Vehicle Detection & ANPR License Plate Reading</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.86rem', color: '#1e293b', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={enableNight}
                  onChange={(e) => setEnableNight(e.target.checked)}
                  style={{ width: '16px', height: '16px', accentColor: '#2563eb' }}
                />
                <Moon size={16} color="#d97706" />
                <span style={{ fontWeight: 500 }}>CLAHE Night Enhancement (Low-Light)</span>
              </label>
            </div>
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '6px' }}>
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              style={{
                padding: '9px 18px',
                fontSize: '0.88rem',
                fontWeight: 600,
                color: '#475569',
                background: '#f1f5f9',
                border: '1px solid #cbd5e1',
                borderRadius: '8px',
                cursor: 'pointer'
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '9px 22px',
                fontSize: '0.88rem',
                fontWeight: 600,
                color: '#ffffff',
                background: '#2563eb',
                border: 'none',
                borderRadius: '8px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                boxShadow: '0 2px 4px rgba(37, 99, 235, 0.2)'
              }}
            >
              {loading ? <Zap size={16} className="spin" /> : <Plus size={16} strokeWidth={2.5} />}
              {loading ? 'Connecting Channel...' : 'Connect & Add Channel'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
