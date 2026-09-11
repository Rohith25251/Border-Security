import React, { useState, useEffect } from 'react';
import { Shield, Video, Tv, Bell, BarChart3, Globe, RefreshCw, Activity, CheckCircle2, AlertTriangle } from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, unreviewedCount, isConnected, onRefresh }) {
  const [timeUtc, setTimeUtc] = useState('');
  const [timeLocal, setTimeLocal] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTimeUtc(now.toTimeString().split(' ')[0] + ' UTC');
      setTimeLocal(now.toLocaleTimeString([], { hour12: false }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleRefreshClick = () => {
    setIsRefreshing(true);
    if (onRefresh) onRefresh();
    setTimeout(() => setIsRefreshing(false), 800);
  };

  const navItems = [
    {
      id: 'surveillance',
      label: 'Live Detection',
      icon: Video,
      description: 'AI analytics & HUD'
    },
    {
      id: 'direct_cctv',
      label: 'Direct CCTV',
      icon: Tv,
      description: 'Raw high-FPS feeds'
    },
    {
      id: 'threats',
      label: 'Threat Feed',
      icon: Bell,
      badge: unreviewedCount > 0 ? unreviewedCount : null,
      description: 'Incidents & intrusion'
    },
    {
      id: 'analytics',
      label: 'Analytics',
      icon: BarChart3,
      description: 'Telemetry & statistics'
    },
    {
      id: 'c2',
      label: 'C2 Integration',
      icon: Globe,
      description: 'Command & dispatch'
    }
  ];

  return (
    <aside className="sidebar">
      {/* Brand Header */}
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <div className="sidebar-logo">
            <Shield size={24} />
          </div>
          <div className="sidebar-brand-text">
            <div className="sidebar-brand-title">
              IBVAP <span className="sidebar-brand-badge">OPS</span>
            </div>
            <div className="sidebar-brand-subtitle">Border Surveillance Platform</div>
          </div>
        </div>
      </div>

      {/* Navigation Menu */}
      <div className="sidebar-nav-container">
        <div className="sidebar-nav-heading">OPERATIONS MENU</div>
        <nav className="sidebar-nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
                onClick={() => setActiveTab(item.id)}
                title={item.label}
              >
                <div className="sidebar-nav-item-icon">
                  <Icon size={18} />
                </div>
                <div className="sidebar-nav-item-content">
                  <span className="sidebar-nav-item-label">{item.label}</span>
                  <span className="sidebar-nav-item-desc">{item.description}</span>
                </div>
                {item.badge && (
                  <span className="sidebar-badge">{item.badge}</span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* System Status & Footer Info */}
      <div className="sidebar-footer">
        {/* Status Card */}
        <div className="sidebar-status-card">
          <div className="sidebar-status-header">
            <div className={`status-pill ${isConnected ? 'live' : 'error'}`}>
              <span className="pulse-dot"></span>
              <span>{isConnected ? 'SYSTEM LIVE' : 'OFFLINE'}</span>
            </div>
            <button
              className={`sidebar-refresh-btn ${isRefreshing ? 'spinning' : ''}`}
              onClick={handleRefreshClick}
              title="Refresh Feeds & Telemetry"
              aria-label="Refresh Feeds"
            >
              <RefreshCw size={14} />
            </button>
          </div>

          <div className="sidebar-clock-box">
            <div className="sidebar-clock-row">
              <span className="clock-label">LOCAL</span>
              <span className="clock-value">{timeLocal}</span>
            </div>
            <div className="sidebar-clock-row">
              <span className="clock-label">TIME</span>
              <span className="clock-subvalue">24-HR OPS</span>
            </div>
          </div>
        </div>

        {/* System Meta */}
        <div className="sidebar-system-meta">
          <span>IBVAP DEFENSE SUITE</span>
          <span className="version-pill">v1.2.0</span>
        </div>
      </div>
    </aside>
  );
}
