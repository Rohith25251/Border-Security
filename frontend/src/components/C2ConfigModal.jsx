import React, { useState, useEffect } from 'react';
import { Globe, Plus, Trash2, Send, CheckCircle2, AlertCircle } from 'lucide-react';

export default function C2ConfigModal({ webhooks, onAddWebhook, onDeleteWebhook }) {
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [secret, setSecret] = useState('');
  const [statusMsg, setStatusMsg] = useState(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!url.trim()) return;

    onAddWebhook({
      webhook_url: url.trim(),
      description: description.trim() || 'C2 Dispatch Endpoint',
      secret_token: secret.trim() || undefined
    });

    setUrl('');
    setDescription('');
    setSecret('');
    setStatusMsg({ type: 'success', text: 'C2 Webhook destination registered successfully.' });
    setTimeout(() => setStatusMsg(null), 3500);
  };

  return (
    <div className="c2-section">
      <div className="section-header">
        <div>
          <h2 className="section-title">
            <Globe size={22} color="#4f46e5" />
            Command & Control (C2) Integration
          </h2>
          <p style={{ fontSize: '0.85rem', color: '#64748b', marginTop: '2px' }}>
            Forward real-time threat events and license plate logs to external military / tactical sector C2 systems
          </p>
        </div>
      </div>

      {statusMsg && (
        <div
          style={{
            padding: '12px 16px',
            borderRadius: '8px',
            marginBottom: '16px',
            background: statusMsg.type === 'success' ? '#f0fdf4' : '#fef2f2',
            color: statusMsg.type === 'success' ? '#15803d' : '#b91c1c',
            border: `1px solid ${statusMsg.type === 'success' ? '#bbf7d0' : '#fecaca'}`,
            fontSize: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <CheckCircle2 size={16} /> {statusMsg.text}
        </div>
      )}

      {/* Register New Webhook Card */}
      <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '14px', color: '#0f172a' }}>
          Register New C2 Webhook Destination
        </h3>

        <form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '12px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
              Destination Webhook URL *
            </label>
            <input
              type="url"
              required
              placeholder="https://c2.borderdefense.gov/api/v1/alerts"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="filter-select"
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
              Sector / Description
            </label>
            <input
              type="text"
              placeholder="Sector 4 Command Center"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="filter-select"
              style={{ width: '100%' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button type="submit" className="btn btn-primary" style={{ height: '36px' }}>
              <Plus size={15} /> Add Endpoint
            </button>
          </div>
        </form>
      </div>

      {/* Active Webhooks List */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', background: '#f8fafc', borderBottom: '1px solid #e2e8f0', fontWeight: 700, fontSize: '0.85rem', color: '#475569' }}>
          Active C2 Webhook Endpoints ({webhooks.length})
        </div>

        {webhooks.length === 0 ? (
          <div className="empty-state">
            <Globe className="empty-state-icon" />
            <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#0f172a' }}>No External C2 Webhooks Configured</div>
            <p style={{ fontSize: '0.8rem', color: '#64748b' }}>
              Add a webhook URL above to automatically broadcast detected incidents to external systems.
            </p>
          </div>
        ) : (
          <table className="threat-table">
            <thead>
              <tr>
                <th>Destination URL</th>
                <th>Sector Name</th>
                <th>Registered At</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {webhooks.map((wh) => (
                <tr key={wh.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: '#2563eb' }}>
                    {wh.webhook_url}
                  </td>
                  <td>{wh.description || 'Command Center'}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: '#64748b' }}>
                    {wh.created_at ? new Date(wh.created_at).toLocaleString() : 'Active'}
                  </td>
                  <td>
                    <span className="status-tag acknowledged">Active Dispatch</span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      className="btn btn-secondary btn-sm"
                      style={{ color: '#dc2626', borderColor: '#fecaca' }}
                      onClick={() => onDeleteWebhook(wh.id)}
                    >
                      <Trash2 size={13} /> Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
