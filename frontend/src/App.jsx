import React, { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import CameraGrid from './components/CameraGrid';
import DirectCCTVView from './components/DirectCCTVView';
import ThreatFeed from './components/ThreatFeed';
import ManageView from './components/ManageView';
import AnalyticsView from './components/AnalyticsView';
import C2ConfigModal from './components/C2ConfigModal';
import SnapshotModal from './components/SnapshotModal';
import SuspectAlertModal from './components/SuspectAlertModal';

export default function App() {
  const [activeTab, setActiveTab] = useState('surveillance');
  const [cameras, setCameras] = useState([
    { camera_id: 'camera1', name: 'Camera 1 (North Gate)', current_fps: 1.0, active_tracks: 0, current_brightness: 110.0, night_mode_active: false },
    { camera_id: 'camera2', name: 'Camera 2 (Night Sector)', current_fps: 1.0, active_tracks: 0, current_brightness: 42.0, night_mode_active: true },
    { camera_id: 'camera3', name: 'Camera 3 (Highway)', current_fps: 1.0, active_tracks: 0, current_brightness: 125.0, night_mode_active: false }
  ]);
  const [alerts, setAlerts] = useState([]);
  const [persons, setPersons] = useState([]);
  const [stats, setStats] = useState(null);
  const [webhooks, setWebhooks] = useState([]);
  const [selectedSnapshot, setSelectedSnapshot] = useState(null);
  const [isConnected, setIsConnected] = useState(true);

  const [liveSuspects, setLiveSuspects] = useState([]);
  const [inspectedSuspectAlert, setInspectedSuspectAlert] = useState(null);

  // Fetch live suspects currently visible in camera frames
  const fetchLiveSuspects = useCallback(async () => {
    try {
      const res = await fetch('/api/live-suspects');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setLiveSuspects(data);
        }
      }
    } catch {
      // Silently pass
    }
  }, []);

  // Fetch telemetry and camera status
  const fetchCameras = useCallback(async () => {
    try {
      const res = await fetch('/api/cameras');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          setCameras(data);
        }
      }
      setIsConnected(true);
    } catch {
      setIsConnected(false);
    }
  }, []);

  // Fetch persons list
  const fetchPersons = useCallback(async () => {
    try {
      const res = await fetch('/api/persons?limit=100');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setPersons(data);
        }
      }
    } catch {
      // Silently pass
    }
  }, []);

  // Fetch alerts log
  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch('/api/alerts?limit=100');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setAlerts(data);
        }
      }
    } catch {
      // Keep existing alerts if fetch fails
    }
  }, []);

  // Fetch statistics
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch('/api/stats');
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch {
      // Silently pass
    }
  }, []);

  // Fetch C2 Webhooks
  const fetchWebhooks = useCallback(async () => {
    try {
      const res = await fetch('/api/c2/webhook-config');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setWebhooks(data);
        }
      }
    } catch {
      // Silently pass
    }
  }, []);

  // Initial load and periodic sub-second polling for 100% sync
  useEffect(() => {
    fetchCameras();
    fetchPersons();
    fetchAlerts();
    fetchStats();
    fetchWebhooks();
    fetchLiveSuspects();

    // Fast live suspect interval (600ms)
    const liveInterval = setInterval(fetchLiveSuspects, 600);

    // General telemetry & alerts interval (1000ms)
    const generalInterval = setInterval(() => {
      fetchAlerts();
      fetchCameras();
      fetchStats();
      fetchPersons();
    }, 1000);

    return () => {
      clearInterval(liveInterval);
      clearInterval(generalInterval);
    };
  }, [fetchCameras, fetchPersons, fetchAlerts, fetchStats, fetchWebhooks, fetchLiveSuspects]);

  // Update alert status
  const handleUpdateStatus = async (alertId, newStatus) => {
    if (!alertId) return;
    try {
      const res = await fetch(`/api/alerts/${alertId}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });

      if (res.ok) {
        setAlerts((prev) =>
          prev.map((a) => (a.id === alertId ? { ...a, status: newStatus } : a))
        );
        fetchStats();
      }
    } catch (err) {
      console.error('Failed to update alert status:', err);
    }
  };

  // Add C2 Webhook
  const handleAddWebhook = async (webhookData) => {
    try {
      const res = await fetch('/api/c2/webhook-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(webhookData)
      });
      if (res.ok) {
        fetchWebhooks();
      }
    } catch (err) {
      console.error('Failed to register webhook:', err);
    }
  };

  // Delete C2 Webhook
  const handleDeleteWebhook = async (webhookId) => {
    try {
      const res = await fetch(`/api/c2/webhook-config/${webhookId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchWebhooks();
      }
    } catch (err) {
      console.error('Failed to delete webhook:', err);
    }
  };

  // Pin alert when suspect is first detected — don't re-derive every poll tick (avoids flicker)
  const [pinnedSuspectAlert, setPinnedSuspectAlert] = useState(null);

  useEffect(() => {
    if (liveSuspects.length > 0) {
      // Only update pinned alert if person changed (avoid re-render on timestamp diff)
      const incoming = liveSuspects[0];
      const incomingKey = `${incoming.camera_id}_${incoming.track_id}_${incoming.metadata?.matched_person || incoming.person_name}`;
      const currentKey = pinnedSuspectAlert
        ? `${pinnedSuspectAlert.camera_id}_${pinnedSuspectAlert.track_id}_${pinnedSuspectAlert.metadata?.matched_person || pinnedSuspectAlert.person_name}`
        : null;
      if (incomingKey !== currentKey) {
        setPinnedSuspectAlert(incoming);
        // Audible alert beep
        try {
          const ctx = new (window.AudioContext || window.webkitAudioContext)();
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.frequency.value = 880;
          gain.gain.setValueAtTime(0.3, ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
          osc.start(ctx.currentTime);
          osc.stop(ctx.currentTime + 0.4);
        } catch (_) {}
      }
    } else {
      // Suspect left camera view — clear alert
      if (!inspectedSuspectAlert) {
        setPinnedSuspectAlert(null);
      }
    }
  }, [liveSuspects, inspectedSuspectAlert]);

  // Active suspect is derived in real time from live camera tracking
  const activeSuspectAlert = inspectedSuspectAlert || pinnedSuspectAlert;

  const handleNavigateSuspectToThreatFeed = (alertToNote) => {
    setInspectedSuspectAlert(null);
    setPinnedSuspectAlert(null);
    setActiveTab('threats');
  };

  const unreviewedCount = alerts.filter((a) => a.status === 'new').length;

  return (
    <div className="app-container">
      {/* Left Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        unreviewedCount={unreviewedCount}
        isConnected={isConnected}
        onRefresh={() => {
          fetchCameras();
          fetchAlerts();
          fetchStats();
          fetchWebhooks();
        }}
      />

      {/* Main Operations Content Area */}
      <div className="main-content-wrapper">
        <main className="main-content">
          {activeTab === 'surveillance' && (
            <CameraGrid
              cameras={cameras}
              onSelectSnapshot={(snapshot) => setSelectedSnapshot(snapshot)}
              onRefreshCameras={fetchCameras}
            />
          )}

          {activeTab === 'direct_cctv' && (
            <DirectCCTVView
              cameras={cameras}
              onSelectSnapshot={(snapshot) => setSelectedSnapshot(snapshot)}
            />
          )}

          {activeTab === 'manage' && (
            <ManageView
              onOpenSnapshot={(snapshot) => setSelectedSnapshot(snapshot)}
              cameras={cameras}
              onRefreshCameras={fetchCameras}
              initialPersons={persons}
              onRefreshPersons={fetchPersons}
            />
          )}

          {activeTab === 'threats' && (
            <ThreatFeed
              alerts={alerts}
              onSelectSnapshot={(snapshot) => setSelectedSnapshot(snapshot)}
              onInspectSuspect={(alert) => setInspectedSuspectAlert(alert)}
            />
          )}

          {activeTab === 'analytics' && (
            <AnalyticsView
              stats={stats}
              alerts={alerts}
            />
          )}

          {activeTab === 'c2' && (
            <C2ConfigModal
              webhooks={webhooks}
              onAddWebhook={handleAddWebhook}
              onDeleteWebhook={handleDeleteWebhook}
            />
          )}
        </main>
      </div>

      {/* Real-time Live Suspect Match Alert Popup (Auto-dismisses when wanted person leaves camera) */}
      {activeSuspectAlert && (
        <SuspectAlertModal
          alert={activeSuspectAlert}
          onNavigateToThreatFeed={handleNavigateSuspectToThreatFeed}
          onClose={() => setInspectedSuspectAlert(null)}
        />
      )}

      {/* Snapshot Inspector Modal */}
      {selectedSnapshot && (
        <SnapshotModal
          alert={selectedSnapshot}
          onClose={() => setSelectedSnapshot(null)}
        />
      )}
    </div>
  );
}
