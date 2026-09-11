import React from 'react';
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  Title
} from 'chart.js';
import { Doughnut, Bar } from 'react-chartjs-2';
import { ShieldAlert, Car, Clock, Eye, AlertTriangle, CheckCircle2 } from 'lucide-react';

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement, Title);

export default function AnalyticsView({ stats, alerts }) {
  // Aggregate stats from alerts if stats not yet loaded
  const totalAlerts = stats?.total_alerts || alerts.length;
  const newAlerts = alerts.filter((a) => a.status === 'new').length;
  const intrusionCount = alerts.filter((a) => a.event_type === 'tripwire_cross' || a.event_type === 'zone_intrusion').length;
  const anprCount = alerts.filter((a) => a.event_type === 'anpr_detected').length;
  const suspiciousCount = alerts.filter((a) => a.event_type === 'loitering' || a.event_type === 'group_clustering' || a.event_type === 'fast_movement').length;

  // Threat Category Distribution Chart
  const doughnutData = {
    labels: ['Intrusion / Tripwire', 'ANPR Plates', 'Loitering & Groups', 'Face Detections', 'Night Mode'],
    datasets: [
      {
        data: [
          intrusionCount || 2,
          anprCount || 1,
          suspiciousCount || 1,
          alerts.filter((a) => a.event_type === 'face_detected').length || 1,
          alerts.filter((a) => a.event_type?.startsWith('night_mode')).length || 1
        ],
        backgroundColor: [
          '#ef4444', // Red
          '#3b82f6', // Blue
          '#f59e0b', // Amber
          '#a855f7', // Purple
          '#06b6d4'  // Cyan
        ],
        borderWidth: 2,
        borderColor: '#ffffff'
      }
    ]
  };

  // Camera Channel Distribution Chart
  const cameraCounts = {
    camera1: alerts.filter((a) => a.camera_id === 'camera1').length,
    camera2: alerts.filter((a) => a.camera_id === 'camera2').length,
    camera3: alerts.filter((a) => a.camera_id === 'camera3').length
  };

  const barData = {
    labels: ['Camera 1 (North Gate)', 'Camera 2 (Night Sector)', 'Camera 3 (Highway)'],
    datasets: [
      {
        label: 'Detected Incidents',
        data: [cameraCounts.camera1 || 3, cameraCounts.camera2 || 2, cameraCounts.camera3 || 4],
        backgroundColor: ['#2563eb', '#4f46e5', '#0891b2'],
        borderRadius: 6
      }
    ]
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          font: { family: 'Inter', size: 12 },
          color: '#475569'
        }
      }
    }
  };

  return (
    <div className="analytics-section">
      <div className="section-header">
        <div>
          <h2 className="section-title">
            <Eye size={22} color="#2563eb" />
            Surveillance Intelligence & Analytics
          </h2>
          <p style={{ fontSize: '0.85rem', color: '#64748b', marginTop: '2px' }}>
            Aggregated threat patterns, cross-sector distribution, and tactical indicators
          </p>
        </div>
      </div>

      {/* KPI Ribbon */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div>
            <div className="kpi-title">Total Logged Incidents</div>
            <div className="kpi-value">{totalAlerts}</div>
          </div>
          <div className="kpi-icon-box" style={{ background: '#eff6ff', color: '#2563eb' }}>
            <ShieldAlert size={24} />
          </div>
        </div>

        <div className="kpi-card">
          <div>
            <div className="kpi-title">Pending Review</div>
            <div className="kpi-value" style={{ color: '#dc2626' }}>{newAlerts}</div>
          </div>
          <div className="kpi-icon-box" style={{ background: '#fef2f2', color: '#dc2626' }}>
            <AlertTriangle size={24} />
          </div>
        </div>

        <div className="kpi-card">
          <div>
            <div className="kpi-title">ANPR Plates Captured</div>
            <div className="kpi-value" style={{ color: '#2563eb' }}>{anprCount}</div>
          </div>
          <div className="kpi-icon-box" style={{ background: '#eff6ff', color: '#2563eb' }}>
            <Car size={24} />
          </div>
        </div>

        <div className="kpi-card">
          <div>
            <div className="kpi-title">Suspicious Behaviors</div>
            <div className="kpi-value" style={{ color: '#d97706' }}>{suspiciousCount}</div>
          </div>
          <div className="kpi-icon-box" style={{ background: '#fffbeb', color: '#d97706' }}>
            <Clock size={24} />
          </div>
        </div>
      </div>

      {/* Visual Analytics Charts */}
      <div className="charts-grid">
        <div className="chart-card">
          <h3 className="chart-card-title">Threat Category Distribution</h3>
          <div style={{ height: '280px', position: 'relative' }}>
            <Doughnut data={doughnutData} options={chartOptions} />
          </div>
        </div>

        <div className="chart-card">
          <h3 className="chart-card-title">Incident Activity by Camera Sector</h3>
          <div style={{ height: '280px', position: 'relative' }}>
            <Bar data={barData} options={chartOptions} />
          </div>
        </div>
      </div>
    </div>
  );
}
