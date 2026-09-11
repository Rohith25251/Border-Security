import React from 'react';
import { X, ShieldAlert, Download, Camera } from 'lucide-react';

export default function SnapshotModal({ alert, onClose }) {
  if (!alert) return null;

  const rawImage = alert.image_path || alert.image_url;
  const imageUrl = rawImage
    ? (rawImage.startsWith('http') || rawImage.startsWith('/api')
        ? rawImage
        : `/api/alerts/image/${rawImage}`)
    : null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-title">
            <ShieldAlert size={18} color="#2563eb" />
            <span>Incident Frame Inspection — {alert.camera_name || alert.camera_id}</span>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body">
          {imageUrl ? (
            <div style={{ background: '#090d16', borderRadius: '8px', overflow: 'hidden', textAlign: 'center', marginBottom: '16px', position: 'relative' }}>
              <img
                src={imageUrl}
                alt="High-Res Incident Screenshot"
                style={{ maxWidth: '100%', maxHeight: '440px', objectFit: 'contain' }}
                onError={(e) => {
                  e.target.style.display = 'none';
                  if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex';
                }}
              />
              <div
                style={{
                  display: 'none',
                  padding: '48px',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexDirection: 'column',
                  gap: '8px',
                  color: '#94a3b8'
                }}
              >
                <Camera size={32} />
                <span>Screenshot loading or syncing with storage...</span>
              </div>
            </div>
          ) : (
            <div style={{ padding: '48px', textAlign: 'center', color: '#94a3b8', background: '#090d16', borderRadius: '8px', marginBottom: '16px' }}>
              <Camera size={36} style={{ marginBottom: '8px', opacity: 0.6 }} />
              <div>No snapshot image available for this event record</div>
            </div>
          )}

          {/* Metadata Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', fontSize: '0.85rem' }}>
            <div style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 600 }}>Threat Event</div>
              <div style={{ fontWeight: 700, marginTop: '2px', textTransform: 'capitalize' }}>
                {alert.event_type?.replace(/_/g, ' ')}
              </div>
            </div>

            <div style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 600 }}>Target Classification</div>
              <div style={{ fontWeight: 700, marginTop: '2px' }}>
                {(alert.object_type || alert.target_class || 'TARGET').toUpperCase()}
                {alert.track_id !== undefined && alert.track_id !== null && ` (#TRK-${alert.track_id})`}
              </div>
            </div>

            <div style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 600 }}>Timestamp</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', marginTop: '2px' }}>
                {alert.timestamp ? new Date(alert.timestamp).toLocaleString() : 'N/A'}
              </div>
            </div>

            <div style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 600 }}>Confidence</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, marginTop: '2px', color: '#2563eb' }}>
                {Math.round((alert.confidence || 0.85) * 100)}%
              </div>
            </div>
          </div>

          {alert.license_plate && (
            <div style={{ marginTop: '12px', background: '#eff6ff', border: '1px solid #bfdbfe', padding: '10px 14px', borderRadius: '6px', fontSize: '0.85rem' }}>
              <span style={{ fontWeight: 600, color: '#1e40af' }}>License Plate: </span>
              <span className="plate-tag" style={{ marginLeft: '6px' }}>{alert.license_plate}</span>
            </div>
          )}

          {(alert.details || alert.location) && (
            <div style={{ marginTop: '12px', background: '#f1f5f9', padding: '10px 14px', borderRadius: '6px', fontSize: '0.82rem' }}>
              <span style={{ fontWeight: 600, color: '#334155' }}>Sector Location / Details: </span>
              <span style={{ color: '#475569' }}>{alert.details || alert.location}</span>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="modal-footer">
          {imageUrl && (
            <a
              href={imageUrl}
              download={`snapshot_${alert.camera_id}_${alert.id || 'event'}.jpg`}
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary"
            >
              <Download size={14} /> Open Full Resolution
            </a>
          )}
          <button className="btn btn-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
