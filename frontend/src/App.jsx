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
  const [stats, setStats] = useState(null);
  const [webhooks, setWebhooks] = useState([]);
  const [selectedSnapshot, setSelectedSnapshot] = useState(null);
  const [isConnected, setIsConnected] = useState(true);

  // Mandatory Suspect Alert Popup State
  const [notedSuspectIds, setNotedSuspectIds] = useState(() => {
    try {
      const stored = localStorage.getItem('ibvap_noted_suspects');
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch {
      return new Set();
    }
  });
  const [inspectedSuspectAlert, setInspectedSuspectAlert] = useState(null);
  const [suspectIndex, setSuspectIndex] = useState(0);

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

  // Initial load and periodic polling
  useEffect(() => {
    fetchCameras();
    fetchAlerts();
    fetchStats();
    fetchWebhooks();

    const interval = setInterval(() => {
      fetchCameras();
      fetchAlerts();
      fetchStats();
    }, 2500);

    return () => clearInterval(interval);
  }, [fetchCameras, fetchAlerts, fetchStats, fetchWebhooks]);

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

  // Find all unnoted suspect/facial recognition alerts
  const unnotedSuspectAlerts = alerts.filter((a) => {
    const isSuspect = a.event_type === 'face_detected' || a.metadata?.matched_person;
    if (!isSuspect) return false;
    const alertKey = a.id || `${a.camera_id}_${a.timestamp}`;
    return !notedSuspectIds.has(alertKey) && a.status !== 'resolved';
  });

  const activeSuspectAlert = inspectedSuspectAlert || (unnotedSuspectAlerts.length > 0 ? unnotedSuspectAlerts[suspectIndex] || unnotedSuspectAlerts[0] : null);

  // Mark Suspect Alert as Noted / Acknowledged
  const handleMarkSuspectNoted = async (alertToNote) => {
    if (!alertToNote) return;
    const alertKey = alertToNote.id || `${alertToNote.camera_id}_${alertToNote.timestamp}`;

    setNotedSuspectIds((prev) => {
      const next = new Set(prev);
      next.add(alertKey);
      try {
        localStorage.setItem('ibvap_noted_suspects', JSON.stringify(Array.from(next)));
      } catch {}
      return next;
    });

    if (alertToNote.id) {
      handleUpdateStatus(alertToNote.id, 'acknowledged');
    }

    setInspectedSuspectAlert(null);
    setSuspectIndex(0);
  };

  const handleNavigateSuspectToThreatFeed = (alertToNote) => {
    handleMarkSuspectNoted(alertToNote);
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

      {/* Real-time Mandatory Suspect Match Alert Popup (Persistent until marked noted) */}
      {activeSuspectAlert && (
        <SuspectAlertModal
          alert={activeSuspectAlert}
          totalUnnoted={unnotedSuspectAlerts.length}
          currentIndex={suspectIndex}
          onNext={() => setSuspectIndex((prev) => Math.min(unnotedSuspectAlerts.length - 1, prev + 1))}
          onPrev={() => setSuspectIndex((prev) => Math.max(0, prev - 1))}
          onMarkNoted={handleMarkSuspectNoted}
          onNavigateToThreatFeed={handleNavigateSuspectToThreatFeed}
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
