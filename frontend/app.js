/**
 * IBVAP — Defense Surveillance Dashboard Client Logic
 * Handles real-time video stream rendering, Supabase Realtime alert subscriptions,
 * threat log updates, analytics charts, and C2 webhook integrations.
 */

// Configuration
const API_BASE_URL = window.location.origin.includes("localhost") || window.location.origin.includes("127.0.0.1")
  ? window.location.origin
  : "http://localhost:8000";

// Supabase Realtime Config
const SUPABASE_URL = "https://tqglzsucamaqdllvntor.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRxZ2x6c3VjYW1hcWRsbHZudG9yIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODgxNzM2OSwiZXhwIjoyMTA0MzkzMzY5fQ.w6JmXZX41ihrDMU8t4q0QJgTVy3ZuN7-qyrgpSMq1us";

let supabaseClient = null;
let chartEventTypes = null;
let chartCameras = null;
let currentAlerts = [];
let telemetryInterval = null;
let alertsPollingInterval = null;
let seenFaceAlertIds = new Set();
let isInitialAlertsLoaded = false;

function playFacialMatchBuzzerSound() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    if (ctx.state === 'suspended') ctx.resume();

    const pulses = [0, 0.2, 0.4];
    const pulseLen = 0.14;

    pulses.forEach((offset) => {
      const startTime = ctx.currentTime + offset;
      const stopTime = startTime + pulseLen;

      const osc1 = ctx.createOscillator();
      osc1.type = 'sawtooth';
      osc1.frequency.setValueAtTime(580, startTime);
      osc1.frequency.linearRampToValueAtTime(460, stopTime);

      const osc2 = ctx.createOscillator();
      osc2.type = 'square';
      osc2.frequency.setValueAtTime(870, startTime);
      osc2.frequency.linearRampToValueAtTime(690, stopTime);

      const gain = ctx.createGain();
      gain.gain.setValueAtTime(0.001, startTime);
      gain.gain.exponentialRampToValueAtTime(0.45, startTime + 0.015);
      gain.gain.setValueAtTime(0.45, stopTime - 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, stopTime);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(ctx.destination);

      osc1.start(startTime);
      osc2.start(startTime);
      osc1.stop(stopTime);
      osc2.stop(stopTime);
    });
  } catch (err) {
    console.warn('Buzzer sound playback error:', err);
  }
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  initClock();
  initSupabaseRealtime();
  fetchCameras();
  fetchAlerts();
  fetchStats();
  fetchC2Webhooks();

  // Background polling loops
  telemetryInterval = setInterval(fetchCameras, 2000);
  alertsPollingInterval = setInterval(fetchAlerts, 3000);
  setInterval(fetchStats, 5000);
});

// ==============================================================================
// 1. Navigation & Tab Switching
// ==============================================================================
function switchTab(tabId) {
  document.querySelectorAll(".nav-tab").forEach(tab => tab.classList.remove("active"));
  document.querySelectorAll(".tab-pane").forEach(pane => pane.classList.remove("active"));

  const targetTabBtn = document.getElementById(`tab-btn-${tabId}`);
  const targetPane = document.getElementById(`pane-${tabId}`);

  if (targetTabBtn) targetTabBtn.classList.add("active");
  if (targetPane) targetPane.classList.add("active");

  if (tabId === "analytics") {
    fetchStats();
  }
}

// Live Clock
function initClock() {
  const clockEl = document.getElementById("clock-display");
  function update() {
    const now = new Date();
    const utcStr = now.toISOString().substring(11, 19) + " UTC";
    const localStr = now.toLocaleTimeString();
    clockEl.textContent = `${localStr} (${utcStr})`;
  }
  update();
  setInterval(update, 1000);
}

// ==============================================================================
// 2. Camera Grid & Live MJPEG Video Feeds
// ==============================================================================
async function fetchCameras() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/cameras`);
    if (!res.ok) return;
    const cameras = await res.json();
    renderCameraGrid(cameras);
  } catch (err) {
    console.error("Error fetching cameras:", err);
  }
}

function renderCameraGrid(cameras) {
  const grid = document.getElementById("camera-grid");
  const activePill = document.getElementById("active-cams-pill");

  const activeCount = cameras.filter(c => c.is_connected).length;
  activePill.textContent = `${activeCount} / ${cameras.length} Channels Streaming`;

  cameras.forEach(cam => {
    let card = document.getElementById(`cam-card-${cam.camera_id}`);
    const streamUrl = `${API_BASE_URL}/api/cameras/${cam.camera_id}/stream`;

    if (!card) {
      card = document.createElement("div");
      card.id = `cam-card-${cam.camera_id}`;
      card.className = "camera-card";
      card.innerHTML = `
        <div class="camera-card-header">
          <div class="cam-meta">
            <h4>${cam.camera_name}</h4>
            <p>${cam.location}</p>
          </div>
          <span class="cam-status-pill ${cam.is_night ? 'night' : ''}" id="pill-${cam.camera_id}">
            <span class="status-dot"></span>
            ${cam.is_night ? 'NIGHT (CLAHE)' : 'LIVE STREAM'}
          </span>
        </div>

        <div class="video-container">
          <div class="video-overlay-telemetry">
            <span class="telemetry-chip" id="fps-${cam.camera_id}">${cam.fps} FPS</span>
            <span class="telemetry-chip" id="lat-${cam.camera_id}">${Math.round(cam.inference_time_ms)} ms</span>
            <span class="telemetry-chip" id="tracks-${cam.camera_id}">${cam.active_tracks} Targets</span>
          </div>
          <img id="stream-img-${cam.camera_id}" src="${streamUrl}" alt="${cam.camera_name}" loading="lazy" onerror="handleStreamError('${cam.camera_id}')">
        </div>

        <div class="camera-card-footer">
          <div class="footer-stats">
            <span>Processed: <b id="frames-${cam.camera_id}">${cam.total_frames_processed}</b></span>
            <span>Alerts: <b id="alerts-${cam.camera_id}">${cam.total_alerts}</b></span>
          </div>
          <button class="btn-action" onclick="captureSnapshot('${cam.camera_id}')">Snapshot</button>
        </div>
      `;
      grid.appendChild(card);
    } else {
      // Update telemetry badges
      const fpsEl = document.getElementById(`fps-${cam.camera_id}`);
      const latEl = document.getElementById(`lat-${cam.camera_id}`);
      const tracksEl = document.getElementById(`tracks-${cam.camera_id}`);
      const framesEl = document.getElementById(`frames-${cam.camera_id}`);
      const alertsEl = document.getElementById(`alerts-${cam.camera_id}`);
      const pillEl = document.getElementById(`pill-${cam.camera_id}`);

      if (fpsEl) fpsEl.textContent = `${cam.fps} FPS`;
      if (latEl) latEl.textContent = `${Math.round(cam.inference_time_ms)} ms`;
      if (tracksEl) tracksEl.textContent = `${cam.active_tracks} Targets`;
      if (framesEl) framesEl.textContent = cam.total_frames_processed;
      if (alertsEl) alertsEl.textContent = cam.total_alerts;

      if (pillEl) {
        pillEl.className = `cam-status-pill ${cam.is_night ? 'night' : ''}`;
        pillEl.innerHTML = `<span class="status-dot"></span> ${cam.is_night ? 'NIGHT (CLAHE)' : (cam.is_connected ? 'LIVE STREAM' : 'OFFLINE')}`;
      }
    }
  });
}

function handleStreamError(camId) {
  const img = document.getElementById(`stream-img-${camId}`);
  if (img) {
    setTimeout(() => {
      img.src = `${API_BASE_URL}/api/cameras/${camId}/stream?t=${Date.now()}`;
    }, 2000);
  }
}

function refreshAllFeeds() {
  document.querySelectorAll(".video-container img").forEach(img => {
    const src = img.src.split("?")[0];
    img.src = `${src}?t=${Date.now()}`;
  });
}

function captureSnapshot(camId) {
  const snapUrl = `${API_BASE_URL}/api/cameras/${camId}/snapshot?t=${Date.now()}`;
  openImageModal(snapUrl, `Live Snapshot — ${camId}`, { Camera: camId, Timestamp: new Date().toISOString() });
}

// ==============================================================================
// 3. Alerts Feed & Threat Log
// ==============================================================================
async function fetchAlerts() {
  try {
    const cam = document.getElementById("filter-camera")?.value || "";
    const eventType = document.getElementById("filter-event")?.value || "";
    const status = document.getElementById("filter-status")?.value || "";

    const params = new URLSearchParams({ limit: "50" });
    if (cam) params.append("camera_id", cam);
    if (eventType) params.append("event_type", eventType);
    if (status) params.append("status", status);

    const res = await fetch(`${API_BASE_URL}/api/alerts?${params.toString()}`);
    if (!res.ok) return;
    currentAlerts = await res.json();
    if (Array.isArray(currentAlerts)) {
      if (isInitialAlertsLoaded) {
        const hasNewFaceMatch = currentAlerts.some(
          a => a.event_type === "face_detected" && !seenFaceAlertIds.has(a.id)
        );
        if (hasNewFaceMatch) playFacialMatchBuzzerSound();
      }
      currentAlerts.forEach(a => {
        if (a.event_type === "face_detected") seenFaceAlertIds.add(a.id);
      });
      isInitialAlertsLoaded = true;
    }
    renderAlertsTable(currentAlerts);
  } catch (err) {
    console.error("Error fetching alerts:", err);
  }
}

function applyAlertFilters() {
  fetchAlerts();
}

function renderAlertsTable(alerts) {
  const tbody = document.getElementById("alerts-table-body");
  const headerCount = document.getElementById("header-alert-count");
  if (!tbody) return;

  if (headerCount) {
    const newCount = alerts.filter(a => a.status === "new").length;
    headerCount.textContent = newCount;
  }

  // Update quick stats in sidebar
  const intrusionCount = alerts.filter(a => a.event_type === "intrusion").length;
  const anprCount = alerts.filter(a => a.event_type === "anpr").length;
  const suspiciousCount = alerts.filter(a => ["loitering", "fast_movement", "group_clustering"].includes(a.event_type)).length;

  document.getElementById("qstat-intrusion").textContent = intrusionCount;
  document.getElementById("qstat-anpr").textContent = anprCount;
  document.getElementById("qstat-suspicious").textContent = suspiciousCount;

  if (alerts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2rem;">No security threats matching current criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = alerts.map(a => {
    const dateStr = new Date(a.timestamp).toLocaleString();
    const plateMarkup = a.license_plate ? `<span class="plate-tag">${a.license_plate}</span>` : `<span style="color:var(--text-dim);">-</span>`;
    const targetMarkup = a.track_id ? `ID: <b>#${a.track_id}</b> (${a.object_type})` : a.object_type;
    const imgUrl = a.image_path || "https://placehold.co/120x90/e2e8f0/475569?text=Snapshot";

    return `
      <tr id="alert-row-${a.id}">
        <td>
          <img src="${imgUrl}" class="alert-thumb" alt="Threat" onclick="openImageModal('${imgUrl}', '${a.event_type.toUpperCase()} — ${a.camera_name}', { ID: '${a.id.substring(0,8)}', Location: '${a.location}', Confidence: '${Math.round(a.confidence * 100)}%', Time: '${dateStr}', Plate: '${a.license_plate || 'N/A'}' })">
        </td>
        <td>
          <span class="event-badge ${a.event_type}">${formatEventType(a.event_type)}</span>
        </td>
        <td>
          <div><b>${a.camera_name}</b></div>
          <div style="font-size:0.72rem; color:var(--text-muted);">${a.location}</div>
        </td>
        <td>
          ${targetMarkup}
          ${a.license_plate ? `<div style="margin-top:0.25rem;">${plateMarkup}</div>` : ''}
        </td>
        <td><b>${Math.round(a.confidence * 100)}%</b></td>
        <td style="font-family: var(--font-mono); font-size:0.75rem;">${dateStr}</td>
        <td>
          <span class="status-pill ${a.status}">${a.status}</span>
        </td>
        <td>
          <div style="display:flex; gap:0.35rem;">
            ${a.status === 'new' ? `<button class="btn-action" onclick="updateAlertStatus('${a.id}', 'acknowledged')">Acknowledge</button>` : ''}
            ${a.status !== 'resolved' ? `<button class="btn-action resolve" onclick="updateAlertStatus('${a.id}', 'resolved')">Resolve</button>` : `<span style="color:var(--color-success); font-weight:600; font-size:0.75rem;">Done</span>`}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function formatEventType(type) {
  return type.replace(/_/g, " ");
}

async function updateAlertStatus(alertId, newStatus) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/alerts/${alertId}/status`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus })
    });
    if (res.ok) {
      fetchAlerts();
      fetchStats();
    }
  } catch (err) {
    console.error("Failed to update status:", err);
  }
}

// ==============================================================================
// 4. Supabase Realtime Subscription
// ==============================================================================
function initSupabaseRealtime() {
  if (typeof supabase === "undefined") {
    console.warn("Supabase JS client not loaded. Falling back to HTTP polling.");
    return;
  }

  try {
    supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
    
    // Subscribe to `alerts` table changes
    supabaseClient
      .channel("public:alerts")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "alerts" },
        (payload) => {
          console.log("[Supabase Realtime] Alert Change Event:", payload);
          fetchAlerts();
          fetchStats();
        }
      )
      .subscribe((status) => {
        console.log("[Supabase Realtime] Connection Status:", status);
        const sysBadge = document.getElementById("sys-status-text");
        if (sysBadge && status === "SUBSCRIBED") {
          sysBadge.textContent = "SYSTEM OPERATIONAL (REALTIME SYNC)";
        }
      });
  } catch (err) {
    console.error("Supabase Realtime initialization error:", err);
  }
}

// ==============================================================================
// 5. Analytics & Charts View
// ==============================================================================
async function fetchStats() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/stats`);
    if (!res.ok) return;
    const stats = await res.json();
    renderAnalytics(stats);
  } catch (err) {
    console.error("Error fetching stats:", err);
  }
}

function renderAnalytics(stats) {
  document.getElementById("kpi-total-alerts").textContent = stats.total_alerts || 0;
  document.getElementById("kpi-pending-alerts").textContent = stats.by_status?.new || 0;
  document.getElementById("kpi-anpr-count").textContent = stats.by_event_type?.anpr || 0;

  // Render Charts
  renderEventTypesChart(stats.by_event_type || {});
  renderCamerasChart(stats.by_camera || {});
}

function renderEventTypesChart(byEventType) {
  const ctx = document.getElementById("chart-event-types");
  if (!ctx) return;

  const labels = Object.keys(byEventType).map(formatEventType);
  const data = Object.values(byEventType);

  const colors = [
    "#dc2626", // intrusion
    "#2563eb", // anpr
    "#d97706", // loitering
    "#ea580c", // clustering
    "#7c3aed", // face
    "#0891b2"  // night
  ];

  if (chartEventTypes) {
    chartEventTypes.data.labels = labels;
    chartEventTypes.data.datasets[0].data = data;
    chartEventTypes.update();
  } else {
    chartEventTypes = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [{
          data: data,
          backgroundColor: colors.slice(0, labels.length),
          borderWidth: 2,
          borderColor: "#ffffff"
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" }
        }
      }
    });
  }
}

function renderCamerasChart(byCamera) {
  const ctx = document.getElementById("chart-cameras");
  if (!ctx) return;

  const labels = Object.keys(byCamera).map(k => k.toUpperCase());
  const data = Object.values(byCamera);

  if (chartCameras) {
    chartCameras.data.labels = labels;
    chartCameras.data.datasets[0].data = data;
    chartCameras.update();
  } else {
    chartCameras = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          label: "Threat Count",
          data: data,
          backgroundColor: "#3b82f6",
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          y: { beginAtZero: true, grid: { color: "#f1f5f9" } },
          x: { grid: { display: false } }
        }
      }
    });
  }
}

// ==============================================================================
// 6. C2 Command & Control Integration
// ==============================================================================
async function fetchC2Webhooks() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/c2/webhook-config`);
    if (!res.ok) return;
    const hooks = await res.json();
    renderC2List(hooks);
  } catch (err) {
    console.error("Error fetching C2 webhooks:", err);
  }
}

function renderC2List(hooks) {
  const list = document.getElementById("c2-webhooks-list");
  if (!list) return;

  if (hooks.length === 0) {
    list.innerHTML = `<p style="color:var(--text-muted); font-size:0.85rem;">No external C2 webhooks currently registered.</p>`;
    return;
  }

  list.innerHTML = hooks.map(h => `
    <div class="c2-item">
      <div class="c2-item-info">
        <h5>${h.description}</h5>
        <p>${h.webhook_url}</p>
      </div>
      <button class="btn-del" onclick="deleteC2Webhook('${h.id}')" title="Remove Webhook">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
      </button>
    </div>
  `).join("");
}

async function handleRegisterWebhook(e) {
  e.preventDefault();
  const url = document.getElementById("c2-url").value;
  const desc = document.getElementById("c2-desc").value;
  const token = document.getElementById("c2-token").value;

  try {
    const res = await fetch(`${API_BASE_URL}/api/c2/webhook-config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ webhook_url: url, description: desc, secret_token: token || null })
    });
    if (res.ok) {
      document.getElementById("form-c2-webhook").reset();
      fetchC2Webhooks();
    }
  } catch (err) {
    console.error("Failed to register webhook:", err);
  }
}

async function deleteC2Webhook(hookId) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/c2/webhook-config/${hookId}`, {
      method: "DELETE"
    });
    if (res.ok) {
      fetchC2Webhooks();
    }
  } catch (err) {
    console.error("Failed to delete webhook:", err);
  }
}

// ==============================================================================
// 7. Image Inspection Modal
// ==============================================================================
function openImageModal(imgSrc, title, metaObj) {
  const modal = document.getElementById("image-modal");
  const modalImg = document.getElementById("modal-img");
  const modalTitle = document.getElementById("modal-title");
  const modalMeta = document.getElementById("modal-meta");

  modalImg.src = imgSrc;
  modalTitle.textContent = title;

  modalMeta.innerHTML = Object.entries(metaObj).map(([k, v]) => `
    <span>${k}: <b>${v}</b></span>
  `).join("");

  modal.classList.add("open");
}

function closeImageModal() {
  const modal = document.getElementById("image-modal");
  modal.classList.remove("open");
}
