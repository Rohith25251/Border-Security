import React, { useState } from 'react';
import {
  ShieldAlert,
  Car,
  Clock,
  UserCheck,
  Moon,
  Users,
  CheckCircle,
  AlertCircle,
  Eye,
  Camera,
  Maximize2
} from 'lucide-react';

export default function ThreatFeed({ alerts = [], onSelectSnapshot }) {
  const [cameraFilter, setCameraFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');

  // Filter alerts
  const filteredAlerts = alerts.filter((alert) => {
    if (cameraFilter !== 'all' && alert.camera_id !== cameraFilter) return false;
    if (typeFilter !== 'all' && alert.event_type !== typeFilter) return false;
    return true;
  });

  const getThreatBadge = (eventType, itemAlert) => {
    switch (eventType) {
      case 'tripwire_cross':
      case 'zone_intrusion':
      case 'intrusion':
        return (
          <span className="threat-badge intrusion">
            <ShieldAlert size={12} /> Intrusion
          </span>
        );
      case 'anpr':
      case 'anpr_detected':
        return (
          <span className="threat-badge anpr">
            <Car size={12} /> ANPR Plate
          </span>
        );
      case 'loitering':
        return (
          <span className="threat-badge loitering">
            <Clock size={12} /> Loitering
          </span>
        );
      case 'fast_movement':
        return (
          <span className="threat-badge speed">
            <AlertCircle size={12} /> Fast Speed
          </span>
        );
      case 'group_clustering':
        return (
          <span className="threat-badge loitering">
            <Users size={12} /> Group ({itemAlert?.metadata?.cluster_size || itemAlert?.metadata?.group_size || 3})
          </span>
        );
      case 'face_detected':
        return (
          <span className="threat-badge face">
            <UserCheck size={12} /> Face Crop
          </span>
        );
      case 'night_mode_change':
      case 'night_mode_on':
      case 'night_mode_off':
        return (
          <span className="threat-badge night">
            <Moon size={12} /> Night Switch
          </span>
        );
      default:
        return (
          <span className="threat-badge safe">
            <AlertCircle size={12} /> {eventType}
          </span>
        );
    }
  };

  const formatTimestamp = (ts) => {
    if (!ts) return 'N/A';
    try {
      const date = new Date(ts);
      return date.toLocaleTimeString([], { hour12: false }) + ' (' + date.toLocaleDateString() + ')';
    } catch {
      return ts;
    }
  };

  const getImageUrl = (alert) => {
    const raw = alert.image_path || alert.image_url;
    if (!raw) return null;
    if (raw.startsWith('http') || raw.startsWith('/api')) return raw;
    return `/api/alerts/image/${raw}`;
  };

  return (
    <div className="threat-feed-section">
      <div className="section-header">
        <div>
          <h2 className="section-title">
            <ShieldAlert size={22} color="#dc2626" />
            Security Threat Incident Logs
          </h2>
          <p style={{ fontSize: '0.85rem', color: '#64748b', marginTop: '2px' }}>
            Live stream of synchronized perimeter intrusions, vehicle plates, and behavioral threats
          </p>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="filter-toolbar">
        <div className="filter-group">
          <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569' }}>Filter By:</label>

          <select
            className="filter-select"
            value={cameraFilter}
            onChange={(e) => setCameraFilter(e.target.value)}
          >
            <option value="all">All Cameras</option>
            <option value="camera1">Camera 1 (North Gate)</option>
            <option value="camera2">Camera 2 (Night Sector)</option>
            <option value="camera3">Camera 3 (Highway)</option>
          </select>

          <select
            className="filter-select"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="all">All Threat Types</option>
            <option value="intrusion">Perimeter Intrusion</option>
            <option value="tripwire_cross">Tripwire Crossing</option>
            <option value="zone_intrusion">Zone Intrusion</option>
            <option value="anpr">ANPR License Plate</option>
            <option value="face_detected">Face Detection</option>
            <option value="loitering">Loitering</option>
            <option value="fast_movement">Fast Movement</option>
            <option value="group_clustering">Group Clustering</option>
          </select>
        </div>

        <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#64748b' }}>
          Showing <span style={{ color: '#0f172a' }}>{filteredAlerts.length}</span> of {alerts.length} Incidents
        </div>
      </div>

      {/* Threats Table */}
      <div className="threat-table-card">
        {filteredAlerts.length === 0 ? (
          <div className="empty-state">
            <CheckCircle className="empty-state-icon" style={{ color: '#10b981' }} />
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a' }}>Perimeter Secure</h3>
            <p style={{ fontSize: '0.82rem', color: '#64748b' }}>No threats match the current filter criteria</p>
          </div>
        ) : (
          <table className="threat-table">
            <thead>
              <tr>
                <th style={{ width: '80px' }}>Snapshot</th>
                <th>Threat Category</th>
                <th>Camera & Sector</th>
                <th>Target & Details</th>
                <th>Confidence</th>
                <th>Timestamp</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredAlerts.map((alert) => {
                const plateText = alert.license_plate || alert.metadata?.plate_text || (alert.event_type === 'anpr_detected' && alert.details);
                const imgUrl = getImageUrl(alert);

                return (
                  <tr key={alert.id || alert.timestamp + alert.camera_id}>
                    {/* Thumbnail */}
                    <td>
                      {imgUrl ? (
                        <img
                          src={imgUrl}
                          alt="Threat Snapshot"
                          className="threat-thumb"
                          onClick={() => onSelectSnapshot({ ...alert, image_url: imgUrl })}
                          onError={(e) => {
                            e.target.style.display = 'none';
                            if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex';
                          }}
                        />
                      ) : null}
                      <div
                        className="threat-thumb"
                        style={{
                          display: imgUrl ? 'none' : 'flex',
                          background: '#f1f5f9',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: '#94a3b8',
                          fontSize: '0.65rem'
                        }}
                        onClick={() => onSelectSnapshot({ ...alert, image_url: imgUrl })}
                      >
                        <Camera size={14} color="#94a3b8" />
                      </div>
                    </td>

                    {/* Threat Type Badge */}
                    <td>{getThreatBadge(alert.event_type, alert)}</td>

                    {/* Camera */}
                    <td>
                      <div style={{ fontWeight: 600 }}>{alert.camera_name || alert.camera_id}</div>
                      <div style={{ fontSize: '0.72rem', color: '#64748b' }}>{alert.location || 'Sector Perimeter'}</div>
                    </td>

                    {/* Target & Details */}
                    <td>
                      {plateText ? (
                        <span className="plate-tag">{plateText}</span>
                      ) : (
                        <div>
                          <div style={{ fontWeight: 600 }}>
                            {alert.object_type ? alert.object_type.toUpperCase() : (alert.target_class ? alert.target_class.toUpperCase() : 'TARGET')}
                            {alert.track_id !== undefined && alert.track_id !== null && (
                              <span style={{ color: '#64748b', fontSize: '0.75rem', marginLeft: '6px' }}>
                                #TRK-{alert.track_id}
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: '0.72rem', color: '#64748b', maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {alert.details || (alert.metadata?.fence_name ? `Breached ${alert.metadata.fence_name}` : 'Intrusion threshold breached')}
                          </div>
                        </div>
                      )}
                    </td>

                    {/* Confidence */}
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <div style={{ width: '48px', height: '6px', background: '#e2e8f0', borderRadius: '4px', overflow: 'hidden' }}>
                          <div
                            style={{
                              width: `${Math.round((alert.confidence || 0.85) * 100)}%`,
                              height: '100%',
                              background: '#2563eb'
                            }}
                          />
                        </div>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 600 }}>
                          {Math.round((alert.confidence || 0.85) * 100)}%
                        </span>
                      </div>
                    </td>

                    {/* Timestamp */}
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: '#475569' }}>
                      {formatTimestamp(alert.timestamp)}
                    </td>

                    {/* Actions */}
                    <td style={{ textAlign: 'right' }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => onSelectSnapshot({ ...alert, image_url: imgUrl })}
                        title="Inspect Incident Snapshot Frame"
                      >
                        <Eye size={13} /> Preview
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
