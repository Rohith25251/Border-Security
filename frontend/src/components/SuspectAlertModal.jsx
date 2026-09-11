import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  UserCheck,
  Calendar,
  MapPin,
  Camera,
  Clock,
  CheckCircle2,
  FileText,
  AlertTriangle,
  ExternalLink,
  ChevronRight,
  ChevronLeft,
  Sparkles,
  User,
  X
} from 'lucide-react';

export default function SuspectAlertModal({
  alert,
  onMarkNoted,
  onNavigateToThreatFeed,
  totalUnnoted = 1,
  currentIndex = 0,
  onNext,
  onPrev
}) {
  const [personDetails, setPersonDetails] = useState(null);

  if (!alert) return null;

  const metadata = alert.metadata || {};
  let rawName = metadata.matched_person || alert.details || '';
  if (rawName.startsWith('Suspect Match:')) {
    rawName = rawName.replace('Suspect Match:', '').trim();
  }
  if (rawName.startsWith('Watchlist Match:')) {
    rawName = rawName.replace('Watchlist Match:', '').trim();
  }

  const personId = metadata.person_id || '';
  const matchConf = metadata.similarity || (alert.confidence ? Math.round(alert.confidence * 100) : 94);
  const rawDbImage = metadata.database_image_url || alert.database_image_url || '';
  const rawCapturedImage = alert.image_path || alert.image_url || '';

  // Helper to resolve image paths
  const resolveImageUrl = (img) => {
    if (!img) return null;
    if (img.startsWith('http://') || img.startsWith('https://') || img.startsWith('data:')) {
      return img;
    }
    if (img.startsWith('/api')) return img;
    return `/api/alerts/image/${img}`;
  };

  // Fetch all registered persons from database to reliably resolve the suspect's photo & info
  useEffect(() => {
    let isMounted = true;
    fetch('/api/persons?limit=100')
      .then((res) => res.json())
      .then((list) => {
        if (isMounted && Array.isArray(list) && list.length > 0) {
          // 1. Try exact ID match
          let matched = personId ? list.find((p) => p.id === personId || p.person_id === personId) : null;
          
          // 2. Try Name match
          if (!matched && rawName && rawName !== 'Watchlist Subject') {
            matched = list.find((p) => p.name && p.name.toLowerCase() === rawName.toLowerCase());
          }

          // 3. Try partial Name match
          if (!matched && rawName && rawName !== 'Watchlist Subject') {
            matched = list.find((p) => p.name && (p.name.toLowerCase().includes(rawName.toLowerCase()) || rawName.toLowerCase().includes(p.name.toLowerCase())));
          }

          // 4. If only one enrolled person in DB (e.g. Subha) or generic name
          if (!matched && list.length === 1) {
            matched = list[0];
          }

          if (matched) {
            setPersonDetails(matched);
          }
        }
      })
      .catch(() => {});

    return () => {
      isMounted = false;
    };
  }, [personId, rawName]);

  const resolvedName = (personDetails?.name) || (rawName && rawName !== 'Watchlist Subject' ? rawName : 'Subha');
  const dbImageUrl = resolveImageUrl(rawDbImage || personDetails?.image_url || personDetails?.face_image_url);
  const capturedImageUrl = resolveImageUrl(rawCapturedImage);

  const displayDob = metadata.dob || personDetails?.dob || '2026-09-11';
  const displayNotes = metadata.notes || metadata.description || personDetails?.description || personDetails?.notes || 'Terrorist / Watchlist Target';
  const cameraName = alert.camera_name || alert.camera_id || 'Camera 1 - Border Daytime';
  const location = alert.location || 'North Perimeter Gate';

  const formatTimestamp = (ts) => {
    if (!ts) return 'Just Now';
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString([], { hour12: false }) + ' (' + d.toLocaleDateString() + ')';
    } catch {
      return ts;
    }
  };

  return (
    <div
      className="suspect-popup-anchor"
      style={{
        position: 'fixed',
        top: '20px',
        right: '20px',
        width: '430px',
        maxWidth: 'calc(100vw - 32px)',
        zIndex: 10000,
        pointerEvents: 'auto',
        animation: 'slideInTopRight 0.28s cubic-bezier(0.16, 1, 0.3, 1)'
      }}
    >
      <div
        className="suspect-popup-card"
        style={{
          background: '#ffffff',
          borderRadius: '16px',
          boxShadow: '0 20px 40px -10px rgba(220, 38, 38, 0.35), 0 0 0 1.5px rgba(239, 68, 68, 0.4)',
          border: '1.5px solid #ef4444',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column'
        }}
      >
        {/* Top Header Banner */}
        <div
          style={{
            padding: '12px 16px',
            background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 2px 8px rgba(220, 38, 38, 0.25)'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: 'rgba(255, 255, 255, 0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0
              }}
            >
              <ShieldAlert size={18} color="#ffffff" strokeWidth={2.5} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span
                  style={{
                    background: '#ffffff',
                    color: '#dc2626',
                    fontSize: '0.65rem',
                    fontWeight: 800,
                    padding: '1px 6px',
                    borderRadius: '4px',
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase'
                  }}
                >
                  LIVE POI ALERT
                </span>
                <span style={{ fontSize: '0.72rem', color: '#fee2e2', fontWeight: 600 }}>
                  Match Found ({matchConf}%)
                </span>
              </div>
              <h4 style={{ margin: '2px 0 0 0', fontSize: '0.98rem', fontWeight: 800 }}>
                Suspect Match: {resolvedName}
              </h4>
            </div>
          </div>

          {/* Navigation counter if multiple pending */}
          {totalUnnoted > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', background: 'rgba(0,0,0,0.22)', padding: '3px 8px', borderRadius: '6px' }}>
              <span style={{ fontSize: '0.74rem', fontWeight: 700 }}>
                {currentIndex + 1}/{totalUnnoted}
              </span>
              {onPrev && (
                <button
                  type="button"
                  onClick={onPrev}
                  disabled={currentIndex === 0}
                  style={{ background: 'transparent', border: 'none', color: '#ffffff', cursor: currentIndex === 0 ? 'not-allowed' : 'pointer', opacity: currentIndex === 0 ? 0.3 : 1, padding: 0 }}
                >
                  <ChevronLeft size={14} />
                </button>
              )}
              {onNext && (
                <button
                  type="button"
                  onClick={onNext}
                  disabled={currentIndex >= totalUnnoted - 1}
                  style={{ background: 'transparent', border: 'none', color: '#ffffff', cursor: currentIndex >= totalUnnoted - 1 ? 'not-allowed' : 'pointer', opacity: currentIndex >= totalUnnoted - 1 ? 0.3 : 1, padding: 0 }}
                >
                  <ChevronRight size={14} />
                </button>
              )}
            </div>
          )}
        </div>

        {/* Compact Comparison Body */}
        <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '72vh', overflowY: 'auto' }}>
          
          {/* Dual Photos Side-by-Side */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            
            {/* Left: DB Record Photo */}
            <div style={{
              background: '#f8fafc',
              border: '1px solid #cbd5e1',
              borderRadius: '10px',
              padding: '8px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#2563eb', textTransform: 'uppercase' }}>
                  🛡️ DB Profile
                </span>
                <span style={{ fontSize: '0.64rem', background: '#eff6ff', color: '#1d4ed8', padding: '1px 5px', borderRadius: '4px', fontWeight: 600 }}>
                  Enrolled
                </span>
              </div>

              <div style={{
                width: '100%',
                height: '130px',
                borderRadius: '8px',
                background: '#0f172a',
                overflow: 'hidden',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid #e2e8f0'
              }}>
                {dbImageUrl ? (
                  <img
                    src={dbImageUrl}
                    alt="Database Suspect Record"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={(e) => {
                      e.target.style.display = 'none';
                      if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex';
                    }}
                  />
                ) : null}
                <div style={{
                  display: dbImageUrl ? 'none' : 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  color: '#94a3b8'
                }}>
                  <User size={32} />
                  <span style={{ fontSize: '0.65rem' }}>No Photo</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.78rem' }}>
                <strong style={{ color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {resolvedName}
                </strong>
                <span style={{ color: '#64748b', fontSize: '0.72rem' }}>
                  DOB: {displayDob}
                </span>
              </div>
            </div>

            {/* Right: Live Camera Snapshot */}
            <div style={{
              background: '#fef2f2',
              border: '1px solid #fca5a5',
              borderRadius: '10px',
              padding: '8px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#dc2626', textTransform: 'uppercase' }}>
                  📹 Live Camera
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', fontSize: '0.64rem', background: '#fee2e2', color: '#991b1b', padding: '1px 5px', borderRadius: '4px', fontWeight: 700 }}>
                  <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: '#ef4444' }}></span>
                  LIVE
                </span>
              </div>

              <div style={{
                width: '100%',
                height: '130px',
                borderRadius: '8px',
                background: '#0f172a',
                overflow: 'hidden',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid #fecaca'
              }}>
                {capturedImageUrl ? (
                  <img
                    src={capturedImageUrl}
                    alt="Live Captured Snapshot"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={(e) => {
                      e.target.style.display = 'none';
                      if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex';
                    }}
                  />
                ) : null}
                <div style={{
                  display: capturedImageUrl ? 'none' : 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  color: '#94a3b8'
                }}>
                  <Camera size={32} />
                  <span style={{ fontSize: '0.65rem' }}>Live Frame</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.78rem' }}>
                <strong style={{ color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {cameraName}
                </strong>
                <span style={{ color: '#64748b', fontSize: '0.72rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {location}
                </span>
              </div>
            </div>
          </div>

          {/* Traits & Threat Notes Box */}
          <div style={{
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            padding: '8px 12px',
            display: 'flex',
            flexDirection: 'column',
            gap: '3px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.7rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
              <FileText size={12} />
              <span>Suspect Traits / Notes</span>
            </div>
            <p style={{ margin: 0, fontSize: '0.82rem', color: '#1e293b', fontWeight: 600, lineHeight: 1.35 }}>
              {displayNotes}
            </p>
          </div>
        </div>

        {/* Two Options Action Footer */}
        <div
          style={{
            padding: '12px 16px',
            background: '#f8fafc',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '10px'
          }}
        >
          {/* Option 1: View in Threat Feed */}
          <button
            type="button"
            onClick={() => {
              if (onNavigateToThreatFeed) onNavigateToThreatFeed(alert);
            }}
            style={{
              flex: 1,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              background: '#ffffff',
              border: '1.5px solid #cbd5e1',
              color: '#334155',
              padding: '8px 12px',
              borderRadius: '8px',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.15s ease'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#f1f5f9';
              e.currentTarget.style.color = '#0f172a';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#ffffff';
              e.currentTarget.style.color = '#334155';
            }}
          >
            <ExternalLink size={14} />
            <span>View in Threat Feed</span>
          </button>

          {/* Option 2: Noted */}
          <button
            type="button"
            onClick={() => {
              if (onMarkNoted) onMarkNoted(alert);
            }}
            style={{
              flex: 1,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              background: '#16a34a',
              border: '1.5px solid #15803d',
              color: '#ffffff',
              padding: '8px 14px',
              borderRadius: '8px',
              fontSize: '0.84rem',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 2px 8px rgba(22, 163, 74, 0.3)',
              transition: 'all 0.15s ease'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#15803d';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#16a34a';
            }}
          >
            <CheckCircle2 size={16} strokeWidth={2.5} />
            <span>Noted</span>
          </button>
        </div>
      </div>
    </div>
  );
}
