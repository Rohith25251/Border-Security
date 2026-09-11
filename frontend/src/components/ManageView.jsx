import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  Users, UserPlus, Trash2, Edit3, Check, X, Search, 
  RefreshCw, Calendar, Image as ImageIcon, Upload, 
  AlertCircle, Sparkles, ZoomIn, FileText, User, Camera, Plus, Globe, MapPin, Shield, Sun, Moon, AlertTriangle
} from 'lucide-react';
import AddCameraModal from './AddCameraModal';

export default function ManageView({ onOpenSnapshot, cameras = [], onRefreshCameras }) {
  const [activeSubTab, setActiveSubTab] = useState('persons'); // 'persons' | 'cameras'
  const [persons, setPersons] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  
  // Modal state for Add/Edit Person
  const [showModal, setShowModal] = useState(false);
  const [modalMode, setModalMode] = useState('add'); // 'add' | 'edit'
  const [formData, setFormData] = useState({
    id: '',
    name: '',
    dob: '',
    description: '',
    image_url: ''
  });
  const [fileInputKey, setFileInputKey] = useState(Date.now());
  const fileInputRef = useRef(null);

  // Modal state for Add Camera
  const [showAddCamModal, setShowAddCamModal] = useState(false);
  const [deletingCamId, setDeletingCamId] = useState(null);

  // Delete confirmation state
  const [deleteTarget, setDeleteTarget] = useState(null);

  // High-res image preview lightbox state
  const [lightboxImage, setLightboxImage] = useState(null);

  const [actionLoading, setActionLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // Fetch Persons List (instant caching)
  const fetchPersons = useCallback(async (showSpinner = false) => {
    try {
      if (showSpinner && persons.length === 0) setLoading(true);
      let url = '/api/persons?limit=100';
      if (searchQuery.trim()) {
        url += `&search=${encodeURIComponent(searchQuery.trim())}`;
      }
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setPersons(data);
        }
      }
    } catch (err) {
      console.error('Failed to fetch persons:', err);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, persons.length]);

  useEffect(() => {
    fetchPersons(true);
    const interval = setInterval(() => fetchPersons(false), 5000);
    return () => clearInterval(interval);
  }, [fetchPersons]);

  // Open Add Modal
  const handleOpenAddModal = () => {
    setModalMode('add');
    setFormData({
      id: '',
      name: '',
      dob: '',
      description: '',
      image_url: ''
    });
    setErrorMessage('');
    setFileInputKey(Date.now());
    setShowModal(true);
  };

  // Open Edit Modal
  const handleOpenEditModal = (person) => {
    setModalMode('edit');
    setFormData({
      id: person.id || person.person_id,
      name: person.name || '',
      dob: person.dob || '',
      description: person.description || person.notes || '',
      image_url: person.image_url || person.face_image_url || ''
    });
    setErrorMessage('');
    setFileInputKey(Date.now());
    setShowModal(true);
  };

  // Handle Image File Upload (Fast client-side compression to JPEG max 600x600)
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement('canvas');
          let width = img.width;
          let height = img.height;
          const maxDim = 600;
          if (width > maxDim || height > maxDim) {
            if (width > height) {
              height = Math.round((height * maxDim) / width);
              width = maxDim;
            } else {
              width = Math.round((width * maxDim) / height);
              height = maxDim;
            }
          }
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, width, height);
          const compressedBase64 = canvas.toDataURL('image/jpeg', 0.85);
          setFormData((prev) => ({ ...prev, image_url: compressedBase64 }));
        };
        img.src = event.target.result;
      };
      reader.readAsDataURL(file);
    }
  };

  // Save Person (Add or Edit)
  const handleSubmitForm = async (e) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setErrorMessage('Please enter the person\'s name.');
      return;
    }

    try {
      setActionLoading(true);
      setErrorMessage('');

      if (modalMode === 'add') {
        const res = await fetch('/api/persons', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: formData.name.trim(),
            dob: formData.dob || '',
            description: formData.description.trim(),
            image_url: formData.image_url || ''
          })
        });

        if (res.ok) {
          setShowModal(false);
          fetchPersons(true);
        } else {
          const errData = await res.json().catch(() => ({}));
          setErrorMessage(errData.detail || 'Failed to create person record.');
        }
      } else {
        // Edit Mode
        const res = await fetch(`/api/persons/${formData.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: formData.name.trim(),
            dob: formData.dob || '',
            description: formData.description.trim(),
            image_url: formData.image_url || ''
          })
        });

        if (res.ok) {
          setShowModal(false);
          fetchPersons(true);
        } else {
          const errData = await res.json().catch(() => ({}));
          setErrorMessage(errData.detail || 'Failed to update person record.');
        }
      }
    } catch (err) {
      console.error('Error saving person:', err);
      setErrorMessage('Network error occurred. Please try again.');
    } finally {
      setActionLoading(false);
    }
  };

  // Delete Person
  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;

    try {
      setActionLoading(true);
      const targetId = deleteTarget.id || deleteTarget.person_id;
      const res = await fetch(`/api/persons/${targetId}`, {
        method: 'DELETE'
      });

      if (res.ok) {
        setPersons(prev => prev.filter(p => p.id !== targetId && p.person_id !== targetId));
        setDeleteTarget(null);
      } else {
        console.error('Failed to delete person');
      }
    } catch (err) {
      console.error('Error deleting person:', err);
    } finally {
      setActionLoading(false);
    }
  };

  // Delete Camera
  const handleDeleteCamera = async (camId, camName) => {
    if (!window.confirm(`Are you sure you want to delete camera channel '${camName || camId}'?`)) {
      return;
    }
    setDeletingCamId(camId);
    try {
      const res = await fetch(`/api/cameras/${camId}`, { method: 'DELETE' });
      if (res.ok) {
        if (onRefreshCameras) onRefreshCameras();
      } else {
        alert(`Failed to delete camera ${camId}`);
      }
    } catch (err) {
      alert(`Error deleting camera: ${err.message}`);
    } finally {
      setDeletingCamId(null);
    }
  };

  // Helper to format DOB
  const formatDob = (dobString) => {
    if (!dobString) return 'Not Specified';
    try {
      const parts = dobString.split('-');
      if (parts.length === 3) {
        const date = new Date(parts[0], parts[1] - 1, parts[2]);
        if (!isNaN(date.getTime())) {
          return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
        }
      }
      return dobString;
    } catch {
      return dobString;
    }
  };

  // Image source resolver
  const getImageUrl = (url) => {
    if (!url) return null;
    if (url.startsWith('data:') || url.startsWith('http')) return url;
    if (url.startsWith('/')) return url;
    return `/api/persons/image/faces/${url.split('/').pop()}`;
  };

  return (
    <div className="manage-view-container">
      {/* Top Header Section */}
      <div className="manage-header-card">
        <div className="manage-header-left">
          <div className="manage-avatar-icon-wrap">
            {activeSubTab === 'persons' ? (
              <Users size={26} className="text-cyan" />
            ) : (
              <Camera size={26} className="text-cyan" />
            )}
          </div>
          <div>
            <h1 className="manage-title">
              {activeSubTab === 'persons' ? 'Person Records & Profiles' : 'IP & RTSP Camera Management'}
            </h1>
            <p className="manage-subtitle">
              {activeSubTab === 'persons' 
                ? 'Manage enrolled facial watchlist profiles and automatic recognition intelligence.' 
                : 'Configure IP video streams, auto-derived sector locations, and active AI analytics channels.'}
            </p>
          </div>
        </div>

        <div className="manage-header-actions">
          {activeSubTab === 'persons' ? (
            <>
              <button 
                className="btn-glass" 
                onClick={() => fetchPersons(true)} 
                disabled={loading}
                title="Refresh list"
              >
                <RefreshCw size={16} className={loading ? 'spin' : ''} />
                <span>Refresh</span>
              </button>
              
              <button 
                className="btn-cyan-primary"
                onClick={handleOpenAddModal}
              >
                <UserPlus size={16} />
                <span>Add Person</span>
              </button>
            </>
          ) : (
            <button 
              className="btn-cyan-primary"
              onClick={() => setShowAddCamModal(true)}
            >
              <Plus size={16} strokeWidth={2.5} />
              <span>Add IP Camera</span>
            </button>
          )}
        </div>
      </div>

      {/* Sub-Tab Navigation Bar */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <button
          onClick={() => setActiveSubTab('persons')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 18px',
            fontSize: '0.88rem',
            fontWeight: 600,
            borderRadius: '10px',
            cursor: 'pointer',
            border: 'none',
            background: activeSubTab === 'persons' ? '#2563eb' : '#f1f5f9',
            color: activeSubTab === 'persons' ? '#ffffff' : '#475569',
            boxShadow: activeSubTab === 'persons' ? '0 2px 6px rgba(37, 99, 235, 0.25)' : 'none'
          }}
        >
          <Users size={16} />
          <span>Persons of Interest & Watchlist ({persons.length})</span>
        </button>

        <button
          onClick={() => setActiveSubTab('cameras')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 18px',
            fontSize: '0.88rem',
            fontWeight: 600,
            borderRadius: '10px',
            cursor: 'pointer',
            border: 'none',
            background: activeSubTab === 'cameras' ? '#2563eb' : '#f1f5f9',
            color: activeSubTab === 'cameras' ? '#ffffff' : '#475569',
            boxShadow: activeSubTab === 'cameras' ? '0 2px 6px rgba(37, 99, 235, 0.25)' : 'none'
          }}
        >
          <Camera size={16} />
          <span>IP & RTSP Cameras ({cameras.length})</span>
        </button>
      </div>

      {/* SUB-TAB 1: PERSON RECORDS */}
      {activeSubTab === 'persons' && (
        <>
          {/* Search & Stats Bar */}
          <div className="manage-toolbar">
            <div className="manage-search-container">
              <Search size={18} className="search-icon-svg" />
              <input
                type="text"
                className="manage-search-box"
                placeholder="Search by name or description..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button className="search-clear-cross" onClick={() => setSearchQuery('')}>
                  <X size={15} />
                </button>
              )}
            </div>

            <div className="manage-stats-pill">
              <span className="stats-label">Total Registered:</span>
              <span className="stats-count">{persons.length}</span>
            </div>
          </div>

          {/* Person Cards Grid */}
          {persons.length === 0 && loading ? (
            <div className="manage-state-card">
              <RefreshCw size={36} className="spin text-cyan" />
              <p className="state-text">Loading person records...</p>
            </div>
          ) : persons.length === 0 ? (
            <div className="manage-state-card">
              <div className="empty-icon-circle">
                <Users size={40} className="text-muted" />
              </div>
              <h3 className="empty-title">No Person Records Found</h3>
              <p className="empty-desc">
                {searchQuery 
                  ? `No records match "${searchQuery}".` 
                  : 'There are no persons added yet. Click "+ Add Person" to create the first record.'}
              </p>
              <button className="btn-cyan-primary mt-2" onClick={handleOpenAddModal}>
                <UserPlus size={16} />
                <span>Add First Person</span>
              </button>
            </div>
          ) : (
            <div className="person-profiles-grid">
              {persons.map((person) => {
                const pid = person.id || person.person_id;
                const imgUrl = getImageUrl(person.image_url || person.face_image_url);

                return (
                  <div key={pid} className="person-card">
                    {/* Card Header Top */}
                    <div className="person-card-header">
                      <div className="person-badge-status">
                        <span className="person-status-dot"></span>
                        <span>Watchlist Enrolled</span>
                      </div>
                      <span className="person-id-chip" title={`Record ID: ${pid}`}>
                        {pid.slice(0, 8)}...
                      </span>
                    </div>

                    {/* Card Body: Photo & Info */}
                    <div className="person-card-body">
                      <div 
                        className="person-photo-wrap"
                        onClick={() => imgUrl && setLightboxImage({ url: imgUrl, name: person.name })}
                        title={imgUrl ? "Click to view full photo" : "No photo available"}
                      >
                        {imgUrl ? (
                          <>
                            <img 
                              src={imgUrl} 
                              alt={person.name} 
                              className="person-photo-img"
                              onError={(e) => {
                                e.target.style.display = 'none';
                                if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex';
                              }}
                            />
                            <div className="person-photo-fallback" style={{ display: 'none' }}>
                              <User size={36} />
                            </div>
                            <div className="photo-zoom-overlay">
                              <ZoomIn size={18} />
                            </div>
                          </>
                        ) : (
                          <div className="person-photo-fallback">
                            <User size={36} />
                          </div>
                        )}
                      </div>

                      <div className="person-info-main">
                        <h3 className="person-name" title={person.name}>{person.name}</h3>
                        
                        <div className="person-meta-row">
                          <div className="person-dob-badge">
                            <Calendar size={13} />
                            <span>DOB: {formatDob(person.dob)}</span>
                          </div>
                        </div>

                        {/* AI Detection Match Active Indicator */}
                        <div className="person-ai-badge">
                          <Sparkles size={12} color="#7c3aed" />
                          <span>Facial Vector Ready</span>
                        </div>
                      </div>
                    </div>

                    {/* Card Middle: Description & Notes */}
                    <div className="person-desc-section">
                      <div className="person-desc-header">
                        <FileText size={13} />
                        <span>Traits & Threat Notes</span>
                      </div>
                      <p className="person-desc-text">
                        {person.description || person.notes || 'No identifying traits or specific notes specified.'}
                      </p>
                    </div>

                    {/* Card Bottom: Action Buttons */}
                    <div className="person-card-actions">
                      <button 
                        type="button"
                        className="btn-card-action edit"
                        onClick={() => handleOpenEditModal(person)}
                        title="Edit person details"
                      >
                        <Edit3 size={14} />
                        <span>Edit</span>
                      </button>

                      <button 
                        type="button"
                        className="btn-card-action delete"
                        onClick={() => setDeleteTarget(person)}
                        title="Delete person from database"
                      >
                        <Trash2 size={14} />
                        <span>Delete</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* SUB-TAB 2: IP CAMERAS MANAGEMENT */}
      {activeSubTab === 'cameras' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
            {cameras.map((cam) => {
              const cid = cam.camera_id || cam.id;
              const isOffline = cam.is_connected === false;
              const isNight = cam.night_mode_active || cam.is_night;
              const cName = cam.camera_name || cam.name || cid;

              return (
                <div key={cid} style={{
                  background: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: '14px',
                  padding: '18px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px'
                }}>
                  {/* Top Bar */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{
                        width: '36px',
                        height: '36px',
                        borderRadius: '8px',
                        background: '#eff6ff',
                        color: '#2563eb',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}>
                        <Camera size={20} />
                      </div>
                      <div>
                        <h4 style={{ margin: 0, fontSize: '0.98rem', fontWeight: 700, color: '#0f172a' }}>{cName}</h4>
                        <span style={{ fontSize: '0.75rem', color: '#64748b' }}>ID: {cid}</span>
                      </div>
                    </div>

                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      padding: '3px 8px',
                      borderRadius: '12px',
                      background: isOffline ? '#fee2e2' : '#dcfce7',
                      color: isOffline ? '#991b1b' : '#166534'
                    }}>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: isOffline ? '#ef4444' : '#22c55e' }}></span>
                      {isOffline ? 'Offline' : 'Active Live'}
                    </span>
                  </div>

                  {/* Details */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.84rem', color: '#475569' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <MapPin size={14} color="#059669" />
                      <strong style={{ color: '#1e293b' }}>Location:</strong> {cam.location || 'Border Sector'}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Globe size={14} color="#2563eb" />
                      <strong style={{ color: '#1e293b' }}>IP Address:</strong> {cam.ip_address || 'Auto-Detected'}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', wordBreak: 'break-all' }}>
                      <Shield size={14} color="#64748b" />
                      <strong style={{ color: '#1e293b' }}>Stream URL:</strong> 
                      <span style={{ fontSize: '0.78rem', color: '#64748b' }}>{cam.rtsp_url || 'Default Stream'}</span>
                    </div>
                  </div>

                  {/* AI Status Badges */}
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', paddingTop: '4px' }}>
                    <span style={{ fontSize: '0.72rem', background: '#f1f5f9', color: '#334155', padding: '2px 8px', borderRadius: '6px', fontWeight: 500 }}>
                      👤 Face Match Active
                    </span>
                    <span style={{ fontSize: '0.72rem', background: '#f1f5f9', color: '#334155', padding: '2px 8px', borderRadius: '6px', fontWeight: 500 }}>
                      🚗 ANPR Plates Active
                    </span>
                    <span style={{ fontSize: '0.72rem', background: isNight ? '#fef3c7' : '#f1f5f9', color: isNight ? '#92400e' : '#334155', padding: '2px 8px', borderRadius: '6px', fontWeight: 500 }}>
                      🌙 CLAHE Night
                    </span>
                  </div>

                  {/* Action Delete Button */}
                  <div style={{ borderTop: '1px solid #f1f5f9', paddingTop: '10px', display: 'flex', justifyContent: 'flex-end' }}>
                    <button
                      onClick={() => handleDeleteCamera(cid, cName)}
                      disabled={deletingCamId === cid}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '6px 12px',
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        color: '#ef4444',
                        background: '#fef2f2',
                        border: '1px solid #fca5a5',
                        borderRadius: '6px',
                        cursor: 'pointer'
                      }}
                    >
                      <Trash2 size={14} />
                      <span>{deletingCamId === cid ? 'Deleting...' : 'Delete Camera'}</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Add Camera Modal */}
      <AddCameraModal
        isOpen={showAddCamModal}
        onClose={() => setShowAddCamModal(false)}
        onCameraAdded={() => {
          if (onRefreshCameras) onRefreshCameras();
        }}
      />

      {/* ADD / EDIT PERSON MODAL (LIGHT THEME) */}
      {showModal && (
        <div 
          className="modal-backdrop" 
          onClick={() => setShowModal(false)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(6px)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '16px'
          }}
        >
          <div 
            className="modal-card" 
            onClick={(e) => e.stopPropagation()}
            style={{
              background: '#ffffff',
              width: '100%',
              maxWidth: '540px',
              borderRadius: '16px',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25), 0 0 0 1px rgba(226, 232, 240, 0.8)',
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column'
            }}
          >
            {/* Modal Header */}
            <div style={{
              padding: '18px 24px',
              borderBottom: '1px solid #f1f5f9',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: '#f8fafc'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: '10px',
                  background: '#eff6ff',
                  border: '1px solid #dbeafe',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#2563eb'
                }}>
                  {modalMode === 'add' ? <UserPlus size={20} strokeWidth={2.5} /> : <Edit3 size={20} strokeWidth={2.5} />}
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.12rem', fontWeight: 700, color: '#0f172a' }}>
                    {modalMode === 'add' ? 'Add Person of Interest' : 'Edit Person Profile'}
                  </h3>
                  <p style={{ margin: '2px 0 0 0', fontSize: '0.8rem', color: '#64748b' }}>
                    Enroll identity photo and details for automatic facial recognition matching
                  </p>
                </div>
              </div>
              <button 
                type="button"
                onClick={() => setShowModal(false)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#64748b',
                  cursor: 'pointer',
                  padding: '6px',
                  borderRadius: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#e2e8f0')}
                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSubmitForm} style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {errorMessage && (
                <div style={{
                  background: '#fef2f2',
                  border: '1px solid #fca5a5',
                  color: '#991b1b',
                  padding: '10px 14px',
                  borderRadius: '10px',
                  fontSize: '0.86rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  <AlertCircle size={17} color="#dc2626" />
                  <span>{errorMessage}</span>
                </div>
              )}

              {/* Photo Upload Section */}
              <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.86rem', fontWeight: 600, color: '#1e293b', marginBottom: '8px' }}>
                  <ImageIcon size={15} color="#2563eb" /> Person Photo
                </label>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', background: '#f8fafc', padding: '12px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                  <div style={{
                    width: '74px',
                    height: '74px',
                    borderRadius: '12px',
                    overflow: 'hidden',
                    background: '#ffffff',
                    border: '1.5px dashed #cbd5e1',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0
                  }}>
                    {formData.image_url ? (
                      <img 
                        src={formData.image_url} 
                        alt="Preview" 
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', color: '#94a3b8' }}>
                        <User size={28} />
                        <span style={{ fontSize: '0.65rem', marginTop: '2px' }}>No Photo</span>
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <input
                      key={fileInputKey}
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      style={{ display: 'none' }}
                      onChange={handleFileChange}
                    />
                    
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '6px 14px',
                          fontSize: '0.82rem',
                          fontWeight: 600,
                          color: '#2563eb',
                          background: '#eff6ff',
                          border: '1px solid #bfdbfe',
                          borderRadius: '8px',
                          cursor: 'pointer'
                        }}
                      >
                        <Upload size={14} />
                        <span>Upload Photo File</span>
                      </button>

                      {formData.image_url && (
                        <button
                          type="button"
                          onClick={() => {
                            setFormData((prev) => ({ ...prev, image_url: '' }));
                            setFileInputKey(Date.now());
                          }}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            padding: '6px 10px',
                            fontSize: '0.82rem',
                            fontWeight: 600,
                            color: '#ef4444',
                            background: '#fef2f2',
                            border: '1px solid #fecaca',
                            borderRadius: '8px',
                            cursor: 'pointer'
                          }}
                        >
                          <Trash2 size={13} />
                          <span>Remove</span>
                        </button>
                      )}
                    </div>

                    <span style={{ fontSize: '0.74rem', color: '#64748b' }}>
                      Face embeddings are automatically pre-computed for instant matching.
                    </span>
                  </div>
                </div>
              </div>

              {/* Name Field */}
              <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.86rem', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
                  <User size={15} color="#2563eb" /> Full Name *
                </label>
                <input
                  type="text"
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '10px 14px',
                    fontSize: '0.92rem',
                    borderRadius: '8px',
                    border: '1.5px solid #cbd5e1',
                    background: '#ffffff',
                    color: '#0f172a',
                    outline: 'none'
                  }}
                  placeholder="e.g., Sujitha B"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  autoFocus
                />
              </div>

              {/* DOB Field */}
              <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.86rem', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
                  <Calendar size={15} color="#059669" /> Date of Birth
                </label>
                <input
                  type="date"
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '9px 14px',
                    fontSize: '0.9rem',
                    borderRadius: '8px',
                    border: '1.5px solid #cbd5e1',
                    background: '#ffffff',
                    color: '#0f172a',
                    outline: 'none'
                  }}
                  value={formData.dob}
                  onChange={(e) => setFormData({ ...formData, dob: e.target.value })}
                />
              </div>

              {/* Description Field */}
              <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.86rem', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
                  <FileText size={15} color="#64748b" /> Description & Notes
                </label>
                <textarea
                  rows="3"
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '10px 14px',
                    fontSize: '0.88rem',
                    borderRadius: '8px',
                    border: '1.5px solid #cbd5e1',
                    background: '#ffffff',
                    color: '#0f172a',
                    outline: 'none',
                    resize: 'vertical'
                  }}
                  placeholder="Enter identifying notes, physical traits, or watchlist category..."
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                />
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '6px' }}>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  disabled={actionLoading}
                  style={{
                    padding: '9px 18px',
                    fontSize: '0.88rem',
                    fontWeight: 600,
                    color: '#475569',
                    background: '#f1f5f9',
                    border: '1px solid #cbd5e1',
                    borderRadius: '8px',
                    cursor: 'pointer'
                  }}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={actionLoading}
                  style={{
                    padding: '9px 22px',
                    fontSize: '0.88rem',
                    fontWeight: 600,
                    color: '#ffffff',
                    background: '#2563eb',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    boxShadow: '0 2px 4px rgba(37, 99, 235, 0.2)'
                  }}
                >
                  {actionLoading ? (
                    <>
                      <RefreshCw size={15} className="spin" />
                      <span>Saving Profile...</span>
                    </>
                  ) : (
                    <>
                      <Check size={16} />
                      <span>{modalMode === 'add' ? 'Add Person' : 'Save Changes'}</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* DELETE CONFIRMATION DIALOG (LIGHT THEME) */}
      {deleteTarget && (
        <div 
          className="modal-backdrop" 
          onClick={() => setDeleteTarget(null)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(6px)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '16px'
          }}
        >
          <div 
            className="modal-card" 
            onClick={(e) => e.stopPropagation()}
            style={{
              background: '#ffffff',
              width: '100%',
              maxWidth: '440px',
              borderRadius: '16px',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
              border: '1px solid #e2e8f0',
              padding: '24px',
              textAlign: 'center'
            }}
          >
            <div style={{
              width: '54px',
              height: '54px',
              borderRadius: '50%',
              background: '#fee2e2',
              color: '#ef4444',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px auto'
            }}>
              <AlertCircle size={30} />
            </div>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '1.15rem', fontWeight: 700, color: '#0f172a' }}>
              Delete Person Record?
            </h3>
            <p style={{ margin: '0 0 20px 0', fontSize: '0.88rem', color: '#64748b', lineHeight: 1.5 }}>
              Are you sure you want to permanently delete <strong>"{deleteTarget.name}"</strong>? 
              This will remove their facial recognition profile from all live camera feeds.
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '12px' }}>
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                disabled={actionLoading}
                style={{
                  padding: '9px 18px',
                  fontSize: '0.88rem',
                  fontWeight: 600,
                  color: '#475569',
                  background: '#f1f5f9',
                  border: '1px solid #cbd5e1',
                  borderRadius: '8px',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={actionLoading}
                style={{
                  padding: '9px 20px',
                  fontSize: '0.88rem',
                  fontWeight: 600,
                  color: '#ffffff',
                  background: '#ef4444',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: 'pointer'
                }}
              >
                {actionLoading ? 'Deleting...' : 'Yes, Delete Record'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* FULL PHOTO LIGHTBOX */}
      {lightboxImage && (
        <div 
          className="lightbox-backdrop" 
          onClick={() => setLightboxImage(null)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            backdropFilter: 'blur(8px)',
            zIndex: 10000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px'
          }}
        >
          <div 
            className="lightbox-content" 
            onClick={(e) => e.stopPropagation()}
            style={{
              background: '#ffffff',
              borderRadius: '16px',
              overflow: 'hidden',
              maxWidth: '520px',
              width: '100%',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)'
            }}
          >
            <img 
              src={lightboxImage.url} 
              alt={lightboxImage.name} 
              style={{ width: '100%', maxHeight: '420px', objectFit: 'contain', background: '#000000', display: 'block' }}
            />
            <div style={{
              padding: '14px 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: '#ffffff'
            }}>
              <span style={{ fontWeight: 700, color: '#0f172a', fontSize: '1rem' }}>{lightboxImage.name}</span>
              <button 
                onClick={() => setLightboxImage(null)}
                style={{
                  background: '#f1f5f9',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '6px 12px',
                  color: '#475569',
                  cursor: 'pointer',
                  fontWeight: 600
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
