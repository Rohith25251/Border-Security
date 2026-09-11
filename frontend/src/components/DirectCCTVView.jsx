import React, { useState, useEffect, useRef } from 'react';
import {
  Tv,
  Camera,
  Maximize2,
  Minimize2,
  RefreshCw,
  Play,
  Pause,
  Grid,
  Square,
  Columns,
  LayoutTemplate,
  ZoomIn,
  ZoomOut,
  ChevronLeft,
  ChevronRight,
  Eye,
  Activity,
  Radio,
  Clock,
  ShieldAlert
} from 'lucide-react';

export default function DirectCCTVView({ cameras = [], onSelectSnapshot }) {
  const [layout, setLayout] = useState('grid-2x2'); // 'grid-2x2', 'focus-1x1', 'hero-pip', 'split-1x2'
  const [selectedChannel, setSelectedChannel] = useState('all');
  const [focusedCamId, setFocusedCamId] = useState(cameras[0]?.camera_id || 'camera1');
  const [streamKeys, setStreamKeys] = useState({});
  const [fullscreenCam, setFullscreenCam] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [isNativeFullscreen, setIsNativeFullscreen] = useState(false);
  const theaterRef = useRef(null);

  // Auto-Tour / Patrol Mode
  const [isPatrolActive, setIsPatrolActive] = useState(false);
  const [patrolIntervalSec, setPatrolIntervalSec] = useState(5);
  const [patrolProgress, setPatrolProgress] = useState(100);
  const patrolTimerRef = useRef(null);
  const patrolAnimRef = useRef(null);

  // Live Clock
  const [liveTime, setLiveTime] = useState(new Date().toLocaleTimeString());
  const [liveDate, setLiveDate] = useState(new Date().toISOString().slice(0, 10));

  useEffect(() => {
    const clockInt = setInterval(() => {
      const now = new Date();
      setLiveTime(now.toLocaleTimeString());
      setLiveDate(now.toISOString().slice(0, 10));
    }, 1000);
    return () => clearInterval(clockInt);
  }, []);

  // Sync focused camera when cameras load
  useEffect(() => {
    if (cameras.length > 0 && !cameras.some((c) => c.camera_id === focusedCamId)) {
      setFocusedCamId(cameras[0].camera_id);
    }
  }, [cameras, focusedCamId]);

  const reloadStream = (cameraId) => {
    setStreamKeys((prev) => ({
      ...prev,
      [cameraId]: Date.now()
    }));
  };

  // Auto-Tour Patrol Logic
  useEffect(() => {
    if (!isPatrolActive || cameras.length <= 1) {
      if (patrolTimerRef.current) clearInterval(patrolTimerRef.current);
      if (patrolAnimRef.current) clearInterval(patrolAnimRef.current);
      setPatrolProgress(100);
      return;
    }

    const totalSteps = patrolIntervalSec * 10;
    let currentStep = 0;

    patrolAnimRef.current = setInterval(() => {
      currentStep = (currentStep + 1) % totalSteps;
      setPatrolProgress(100 - (currentStep / totalSteps) * 100);
    }, 100);

    patrolTimerRef.current = setInterval(() => {
      setFocusedCamId((prevId) => {
        const nextIdx = (cameras.findIndex((c) => c.camera_id === prevId) + 1) % cameras.length;
        const nextCam = cameras[nextIdx];
        if (fullscreenCam) {
          setFullscreenCam(nextCam);
        }
        return nextCam.camera_id;
      });
      currentStep = 0;
    }, patrolIntervalSec * 1000);

    return () => {
      if (patrolTimerRef.current) clearInterval(patrolTimerRef.current);
      if (patrolAnimRef.current) clearInterval(patrolAnimRef.current);
    };
  }, [isPatrolActive, patrolIntervalSec, cameras, fullscreenCam]);

  // Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (fullscreenCam) setFullscreenCam(null);
      } else if (e.key === 'f' || e.key === 'F') {
        if (fullscreenCam) {
          toggleNativeFullscreen();
        } else if (cameras.length > 0) {
          const target = cameras.find((c) => c.camera_id === focusedCamId) || cameras[0];
          setFullscreenCam(target);
        }
      } else if (e.key === 't' || e.key === 'T') {
        setIsPatrolActive((prev) => !prev);
      } else if (e.key >= '1' && e.key <= '9') {
        const idx = parseInt(e.key, 10) - 1;
        if (idx < cameras.length) {
          const cam = cameras[idx];
          setFocusedCamId(cam.camera_id);
          if (fullscreenCam) setFullscreenCam(cam);
        }
      } else if (fullscreenCam && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
        const currIdx = cameras.findIndex((c) => c.camera_id === fullscreenCam.camera_id);
        const nextIdx = e.key === 'ArrowRight'
          ? (currIdx + 1) % cameras.length
          : (currIdx - 1 + cameras.length) % cameras.length;
        setFullscreenCam(cameras[nextIdx]);
        setFocusedCamId(cameras[nextIdx].camera_id);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [fullscreenCam, cameras, focusedCamId]);

  const toggleNativeFullscreen = () => {
    if (!document.fullscreenElement) {
      if (theaterRef.current?.requestFullscreen) {
        theaterRef.current.requestFullscreen();
        setIsNativeFullscreen(true);
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
        setIsNativeFullscreen(false);
      }
    }
  };

  const handleNextPrevCam = (direction) => {
    if (!fullscreenCam || cameras.length === 0) return;
    const currIdx = cameras.findIndex((c) => c.camera_id === fullscreenCam.camera_id);
    const nextIdx = direction === 'next'
      ? (currIdx + 1) % cameras.length
      : (currIdx - 1 + cameras.length) % cameras.length;
    setFullscreenCam(cameras[nextIdx]);
    setFocusedCamId(cameras[nextIdx].camera_id);
    setZoomLevel(1);
  };

  // Filtered cameras based on section selection
  const displayedCameras = (() => {
    if (selectedChannel !== 'all') {
      return cameras.filter((c) => c.camera_id === selectedChannel);
    }
    if (layout === 'focus-1x1') {
      const target = cameras.find((c) => c.camera_id === focusedCamId);
      return target ? [target] : cameras.slice(0, 1);
    }
    return cameras;
  })();

  const focusedCam = cameras.find((c) => c.camera_id === focusedCamId) || cameras[0];

  return (
    <div className="direct-cctv-section">
      {/* Top Header & Toolbar */}
      <div className="section-header cctv-ops-header">
        <div>
          <h2 className="section-title">
            <Tv size={22} color="#2563eb" />
            Direct CCTV Operations
            <span className="direct-feed-badge">RAW NATIVE STREAM</span>
          </h2>
          <p className="section-subtitle">
            Dedicated uncompressed high-FPS video pipeline decoupled from AI inference
          </p>
        </div>

        <div className="cctv-toolbar">
          {/* Auto-Tour / Patrol Mode */}
          <div className="patrol-control-box">
            <button
              className={`btn btn-sm ${isPatrolActive ? 'btn-patrol-active' : 'btn-secondary'}`}
              onClick={() => setIsPatrolActive(!isPatrolActive)}
              title="Auto-Tour Patrol Mode (Cycles through camera feeds automatically)"
            >
              {isPatrolActive ? <Pause size={13} /> : <Play size={13} />}
              <span>{isPatrolActive ? 'Patrol Active' : 'Auto-Tour'}</span>
              {isPatrolActive && (
                <span className="patrol-progress-badge">
                  {Math.round((patrolProgress / 100) * patrolIntervalSec)}s
                </span>
              )}
            </button>

            {isPatrolActive && (
              <select
                className="patrol-interval-select"
                value={patrolIntervalSec}
                onChange={(e) => setPatrolIntervalSec(Number(e.target.value))}
                title="Tour cycle interval"
              >
                <option value={3}>3s</option>
                <option value={5}>5s</option>
                <option value={10}>10s</option>
                <option value={15}>15s</option>
                <option value={30}>30s</option>
              </select>
            )}
          </div>

          {/* Layout Mode Selector */}
          <div className="layout-selector-group">
            <button
              className={`layout-btn ${layout === 'grid-2x2' ? 'active' : ''}`}
              onClick={() => {
                setLayout('grid-2x2');
                setSelectedChannel('all');
              }}
              title="Quad Grid 2x2 View"
            >
              <Grid size={15} />
              <span className="layout-tooltip">2x2 Quad</span>
            </button>

            <button
              className={`layout-btn ${layout === 'focus-1x1' ? 'active' : ''}`}
              onClick={() => setLayout('focus-1x1')}
              title="Single Focused 1x1 View"
            >
              <Square size={15} />
              <span className="layout-tooltip">1x1 Focus</span>
            </button>

            <button
              className={`layout-btn ${layout === 'hero-pip' ? 'active' : ''}`}
              onClick={() => {
                setLayout('hero-pip');
                setSelectedChannel('all');
              }}
              title="1+3 Hero Main & PIP Sidebars View"
            >
              <LayoutTemplate size={15} />
              <span className="layout-tooltip">1+3 Hero</span>
            </button>

            <button
              className={`layout-btn ${layout === 'split-1x2' ? 'active' : ''}`}
              onClick={() => {
                setLayout('split-1x2');
                setSelectedChannel('all');
              }}
              title="1x2 Split Dual Channel View"
            >
              <Columns size={15} />
              <span className="layout-tooltip">1x2 Split</span>
            </button>
          </div>

          {/* Theater Fullscreen Button */}
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setFullscreenCam(focusedCam || cameras[0])}
            title="Open Focused Camera in Fullscreen Theater (Shortcut: F)"
          >
            <Maximize2 size={13} /> Fullscreen
          </button>
        </div>
      </div>

      {/* Camera Channel / Section Chooser Tabs */}
      <div className="camera-channel-switcher">
        <button
          className={`channel-tab ${selectedChannel === 'all' && layout !== 'focus-1x1' ? 'active' : ''}`}
          onClick={() => {
            setSelectedChannel('all');
            if (layout === 'focus-1x1') setLayout('grid-2x2');
          }}
        >
          <Radio size={13} />
          <span>All Channels ({cameras.length})</span>
        </button>

        {cameras.map((cam, idx) => {
          const isSelected = selectedChannel === cam.camera_id || (layout === 'focus-1x1' && focusedCamId === cam.camera_id);
          const isLive = cam.is_connected !== false;
          return (
            <button
              key={cam.camera_id}
              className={`channel-tab ${isSelected ? 'active' : ''}`}
              onClick={() => {
                setFocusedCamId(cam.camera_id);
                setSelectedChannel(layout === 'focus-1x1' ? 'all' : cam.camera_id);
              }}
            >
              <span className="channel-number-key">[{idx + 1}]</span>
              <span className="channel-tab-name">{cam.name || cam.camera_id}</span>
              <span className="channel-badge-status">
                <span className="pulse-dot" style={{ backgroundColor: isLive ? '#10b981' : '#ef4444' }}></span>
                <span>{isLive ? 'LIVE' : 'OFFLINE'}</span>
              </span>
            </button>
          );
        })}
      </div>

      {/* Main Video Viewport Layouts */}
      {layout === 'hero-pip' && cameras.length > 1 ? (
        <div className="hero-pip-layout">
          {/* Main Hero View */}
          <div className="hero-viewport">
            {focusedCam && (
              <DirectCameraCard
                cam={focusedCam}
                streamKeys={streamKeys}
                reloadStream={reloadStream}
                onSelectSnapshot={onSelectSnapshot}
                onEnterFullscreen={() => setFullscreenCam(focusedCam)}
                isHero={true}
                currentDate={liveDate}
                currentTime={liveTime}
              />
            )}
          </div>

          {/* PIP Sidebar */}
          <div className="pip-sidebar">
            <div className="pip-sidebar-title">
              <span>Secondary Feeds (Click to focus)</span>
            </div>
            {cameras
              .filter((c) => c.camera_id !== focusedCamId)
              .map((cam) => (
                <div
                  key={cam.camera_id}
                  className="pip-card"
                  onClick={() => setFocusedCamId(cam.camera_id)}
                  title={`Click to switch ${cam.name} into Hero View`}
                >
                  <DirectCameraCard
                    cam={cam}
                    streamKeys={streamKeys}
                    reloadStream={reloadStream}
                    onSelectSnapshot={onSelectSnapshot}
                    onEnterFullscreen={() => setFullscreenCam(cam)}
                    isPip={true}
                    currentDate={liveDate}
                    currentTime={liveTime}
                  />
                </div>
              ))}
          </div>
        </div>
      ) : (
        /* Standard Quad / Split / Grid Layout */
        <div className={`camera-grid cctv-grid layout-${layout}`}>
          {displayedCameras.map((cam) => (
            <DirectCameraCard
              key={cam.camera_id}
              cam={cam}
              streamKeys={streamKeys}
              reloadStream={reloadStream}
              onSelectSnapshot={onSelectSnapshot}
              onEnterFullscreen={() => setFullscreenCam(cam)}
              onFocus={() => setFocusedCamId(cam.camera_id)}
              isFocused={focusedCamId === cam.camera_id}
              currentDate={liveDate}
              currentTime={liveTime}
            />
          ))}
        </div>
      )}

      {/* Fullscreen Theater Modal */}
      {fullscreenCam && (
        <div className="cctv-fullscreen-backdrop" ref={theaterRef}>
          <div className="cctv-fullscreen-theater">
            {/* Top OSD Bar */}
            <div className="theater-osd-top">
              <div className="theater-cam-info">
                <div className="rec-indicator">
                  <span className="rec-dot"></span>
                  <span>DIRECT CCTV</span>
                </div>
                <h3 className="theater-cam-title">{fullscreenCam.name || fullscreenCam.camera_id}</h3>
                <span className="theater-cam-id">{fullscreenCam.camera_id}</span>
                <span className="theater-location">{fullscreenCam.location || 'Border Sector'}</span>
              </div>

              <div className="theater-osd-controls">
                <div className="osd-clock-badge">
                  <Clock size={13} />
                  <span>{liveDate} {liveTime}</span>
                </div>

                <select
                  className="filter-select theater-cam-select"
                  value={fullscreenCam.camera_id}
                  onChange={(e) => {
                    const found = cameras.find((c) => c.camera_id === e.target.value);
                    if (found) {
                      setFullscreenCam(found);
                      setFocusedCamId(found.camera_id);
                      setZoomLevel(1);
                    }
                  }}
                >
                  {cameras.map((c, i) => (
                    <option key={c.camera_id} value={c.camera_id}>
                      CH {i + 1}: {c.name || c.camera_id}
                    </option>
                  ))}
                </select>

                <button
                  className="btn btn-secondary btn-sm"
                  onClick={toggleNativeFullscreen}
                  title="Toggle Browser Native Fullscreen (F)"
                >
                  {isNativeFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                </button>

                <button
                  className="modal-close-btn theater-close-btn"
                  onClick={() => {
                    if (document.fullscreenElement) {
                      document.exitFullscreen().catch(() => {});
                    }
                    setFullscreenCam(null);
                    setZoomLevel(1);
                  }}
                  title="Exit Fullscreen (Esc)"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Video Canvas Stage */}
            <div className="theater-video-stage">
              <button
                className="theater-nav-btn nav-prev"
                onClick={() => handleNextPrevCam('prev')}
                title="Previous Camera (Left Arrow)"
              >
                <ChevronLeft size={32} />
              </button>

              <div className="theater-video-wrapper" onDoubleClick={toggleNativeFullscreen}>
                <img
                  src={`/api/cameras/${fullscreenCam.camera_id}/raw-stream${streamKeys[fullscreenCam.camera_id] ? `?t=${streamKeys[fullscreenCam.camera_id]}` : ''}`}
                  alt={`Direct CCTV - ${fullscreenCam.camera_id}`}
                  className="theater-video-element"
                  style={{
                    transform: `scale(${zoomLevel})`,
                    transformOrigin: 'center center',
                    transition: zoomLevel === 1 ? 'transform 0.2s ease' : 'none'
                  }}
                />

                {/* CCTV Corner Watermark */}
                <div className="cctv-osd-stamp top-left">
                  <span>IBVAP DIRECT CCTV</span>
                  <span>{fullscreenCam.name}</span>
                </div>
                <div className="cctv-osd-stamp bottom-right">
                  <span>{liveDate} {liveTime}</span>
                  <span>FULL NATIVE STREAM</span>
                </div>
              </div>

              <button
                className="theater-nav-btn nav-next"
                onClick={() => handleNextPrevCam('next')}
                title="Next Camera (Right Arrow)"
              >
                <ChevronRight size={32} />
              </button>
            </div>

            {/* Bottom Telemetry & Controls */}
            <div className="theater-osd-bottom">
              <div className="theater-telemetry-row">
                <div className="theater-stat-chip">
                  <span className="chip-label">FEED:</span>
                  <span className="chip-val blue">Direct Native Feed</span>
                </div>
                <div className="theater-stat-chip">
                  <span className="chip-label">LOCATION:</span>
                  <span className="chip-val">{fullscreenCam.location || 'Border Sector'}</span>
                </div>
                <div className="theater-stat-chip">
                  <span className="chip-label">STATUS:</span>
                  <span className="chip-val green">TRANSMITTING</span>
                </div>
              </div>

              <div className="theater-actions-row">
                {/* PTZ Zoom Controls */}
                <div className="ptz-zoom-group">
                  <button
                    className="btn btn-secondary btn-sm ptz-btn"
                    onClick={() => setZoomLevel((z) => Math.max(1, z - 0.5))}
                    disabled={zoomLevel <= 1}
                    title="Zoom Out"
                  >
                    <ZoomOut size={14} />
                  </button>
                  <span className="ptz-zoom-display">{zoomLevel.toFixed(1)}x</span>
                  <button
                    className="btn btn-secondary btn-sm ptz-btn"
                    onClick={() => setZoomLevel((z) => Math.min(3, z + 0.5))}
                    disabled={zoomLevel >= 3}
                    title="Zoom In"
                  >
                    <ZoomIn size={14} />
                  </button>
                  {zoomLevel > 1 && (
                    <button
                      className="btn btn-secondary btn-sm ptz-btn"
                      onClick={() => setZoomLevel(1)}
                      title="Reset Zoom to 1.0x"
                    >
                      <RefreshCw size={13} />
                    </button>
                  )}
                </div>

                <button
                  className="btn btn-primary btn-sm"
                  onClick={() =>
                    onSelectSnapshot &&
                    onSelectSnapshot({
                      image_url: `/api/cameras/${fullscreenCam.camera_id}/snapshot?mode=raw&t=${Date.now()}`,
                      event_type: 'direct_cctv_snapshot',
                      camera_id: fullscreenCam.camera_id,
                      timestamp: new Date().toISOString(),
                      details: `Direct high-resolution CCTV snapshot captured from ${fullscreenCam.name || fullscreenCam.camera_id}`
                    })
                  }
                  title="Capture High-Resolution Snapshot"
                >
                  <Eye size={14} /> Capture Snapshot
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Individual Camera Feed Card for Direct CCTV
 */
function DirectCameraCard({
  cam,
  streamKeys,
  reloadStream,
  onSelectSnapshot,
  onEnterFullscreen,
  onFocus,
  isHero = false,
  isPip = false,
  isFocused = false,
  currentDate,
  currentTime
}) {
  const streamUrl = `/api/cameras/${cam.camera_id}/raw-stream${streamKeys[cam.camera_id] ? `?t=${streamKeys[cam.camera_id]}` : ''}`;
  const isLive = cam.is_connected !== false;

  return (
    <div
      className={`camera-card direct-cctv-card ${isHero ? 'hero-card' : ''} ${isPip ? 'pip-card-inner' : ''} ${isFocused ? 'focused-active' : ''}`}
      onClick={onFocus}
    >
      {/* Header */}
      <div className="camera-card-header">
        <div className="camera-name-box">
          <Camera size={16} color="#2563eb" />
          <span className="camera-name">{cam.name || cam.camera_id}</span>
          <span className="camera-id-badge">{cam.camera_id}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className={`threat-badge ${isLive ? 'safe' : 'intrusion'}`} style={{ fontSize: '0.68rem', padding: '2px 6px' }}>
            <Radio size={11} /> {isLive ? 'LIVE DIRECT' : 'OFFLINE'}
          </span>
          <button
            className="cam-header-action-btn"
            onClick={(e) => {
              e.stopPropagation();
              onEnterFullscreen();
            }}
            title="Open Fullscreen (F)"
          >
            <Maximize2 size={13} />
          </button>
        </div>
      </div>

      {/* Video Container */}
      <div
        className="camera-video-container"
        onDoubleClick={(e) => {
          e.stopPropagation();
          onEnterFullscreen();
        }}
        title="Double-click to open full screen"
      >
        <img
          src={streamUrl}
          alt={`Direct CCTV - ${cam.camera_id}`}
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
          <span>Direct CCTV: Connecting to {cam.name || cam.camera_id}...</span>
          <button
            className="btn btn-secondary btn-sm"
            style={{ marginTop: '8px' }}
            onClick={(e) => {
              e.stopPropagation();
              reloadStream(cam.camera_id);
            }}
          >
            Retry Connection
          </button>
        </div>

        {/* Live HUD Overlay */}
        <div className="video-hud-overlay">
          <div className="hud-pill">
            <span className="pulse-dot hud-live-tag" style={{ backgroundColor: isLive ? '#10b981' : '#ef4444' }}></span>
            <span>{isLive ? 'DIRECT LIVE' : 'OFFLINE'}</span>
          </div>
        </div>

        {/* Date / Time Stamp */}
        <div className="card-cctv-osd-stamp">
          <span>{currentDate} {currentTime}</span>
        </div>

        {/* Hover Action Overlay */}
        <div className="video-hover-actions">
          <button
            className="video-action-pill"
            onClick={(e) => {
              e.stopPropagation();
              onEnterFullscreen();
            }}
            title="Expand Full Screen"
          >
            <Maximize2 size={13} /> Expand
          </button>
        </div>
      </div>

      {/* Footer */}
      <div className="camera-card-footer">
        <div className="telemetry-item">
          <span style={{ color: '#64748b' }}>Location:</span>
          <span className="telemetry-val" style={{ fontSize: '0.78rem' }}>{cam.location || 'Border Sector'}</span>
        </div>

        <div style={{ display: 'flex', gap: '4px' }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={(e) => {
              e.stopPropagation();
              onSelectSnapshot &&
                onSelectSnapshot({
                  image_url: `/api/cameras/${cam.camera_id}/snapshot?mode=raw&t=${Date.now()}`,
                  event_type: 'direct_cctv_snapshot',
                  camera_id: cam.camera_id,
                  timestamp: new Date().toISOString(),
                  details: `Direct CCTV manual snapshot for ${cam.name || cam.camera_id}`
                });
            }}
            title="Capture Instant Raw Snapshot"
          >
            <Eye size={13} /> Snapshot
          </button>
        </div>
      </div>
    </div>
  );
}
