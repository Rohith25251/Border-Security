import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  Users, UserPlus, Trash2, Edit3, Check, X, Search, 
  RefreshCw, Calendar, Image as ImageIcon, Upload, 
  AlertCircle, Sparkles, ZoomIn, FileText, User
} from 'lucide-react';

export default function ManageView({ onOpenSnapshot }) {
  const [persons, setPersons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  
  // Modal state for Add/Edit
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

  // Delete confirmation state
  const [deleteTarget, setDeleteTarget] = useState(null);

  // High-res image preview lightbox state
  const [lightboxImage, setLightboxImage] = useState(null);

  const [actionLoading, setActionLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // Fetch Persons List
  const fetchPersons = useCallback(async (showSpinner = false) => {
    try {
      if (showSpinner) setLoading(true);
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
  }, [searchQuery]);

  useEffect(() => {
    fetchPersons(true);
    const interval = setInterval(() => fetchPersons(false), 4000);
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
          try {
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
            const compressed = canvas.toDataURL('image/jpeg', 0.85);
            setFormData(prev => ({ ...prev, image_url: compressed }));
            setErrorMessage('');
          } catch (err) {
            setFormData(prev => ({ ...prev, image_url: event.target.result }));
          }
        };
        img.onerror = () => {
          setErrorMessage('Could not load selected image.');
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
          fetchPersons();
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
          fetchPersons();
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
            <Users size={26} className="text-cyan" />
          </div>
          <div>
            <h1 className="manage-title">Person Records & Profiles</h1>
            <p className="manage-subtitle">
              Manage facial profiles, records, and identification information.
            </p>
          </div>
        </div>

        <div className="manage-header-actions">
          <button 
            className="btn-glass" 
            onClick={fetchPersons} 
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
        </div>
      </div>

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
      {loading && persons.length === 0 ? (
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
            const rawImg = person.image_url || person.face_image_url;
            const imgSrc = getImageUrl(rawImg);

            return (
              <div key={person.id || person.person_id} className="person-profile-card">
                {/* Photo & Main Header */}
                <div className="card-person-header">
                  <div 
                    className="person-photo-wrapper"
                    onClick={() => imgSrc && setLightboxImage({ url: imgSrc, name: person.name })}
                    title={imgSrc ? "Click to enlarge photo" : "No photo attached"}
                  >
                    {imgSrc ? (
                      <>
                        <img 
                          src={imgSrc} 
                          alt={person.name} 
                          className="person-photo-img"
                          onError={(e) => {
                            e.target.style.display = 'none';
                            e.target.nextSibling.style.display = 'flex';
                          }}
                        />
                        <div className="photo-fallback-icon" style={{ display: 'none' }}>
                          <User size={32} />
                        </div>
                        <div className="photo-zoom-overlay">
                          <ZoomIn size={18} />
                        </div>
                      </>
                    ) : (
                      <div className="photo-fallback-icon">
                        <User size={32} />
                      </div>
                    )}
                  </div>

                  <div className="person-main-info">
                    <h2 className="person-display-name" title={person.name}>
                      {person.name}
                    </h2>
                    
                    <div className="person-dob-badge">
                      <Calendar size={13} className="text-cyan flex-shrink-0" />
                      <span className="dob-prefix">DOB:</span>
                      <span className="dob-val">{formatDob(person.dob)}</span>
                    </div>
                  </div>
                </div>

                {/* Description Body */}
                <div className="person-description-section">
                  <div className="section-mini-header">
                    <FileText size={12} className="text-muted flex-shrink-0" />
                    <span>DESCRIPTION</span>
                  </div>
                  <p className="person-description-text">
                    {person.description || person.notes || (
                      <span className="text-dim italic">No description provided for this person.</span>
                    )}
                  </p>
                </div>

                {/* Action Buttons Footer */}
                <div className="person-card-actions">
                  <button 
                    className="btn-card-edit"
                    onClick={() => handleOpenEditModal(person)}
                    title="Edit name, DOB, description, or photo"
                  >
                    <Edit3 size={15} />
                    <span>Edit</span>
                  </button>

                  <button 
                    className="btn-card-delete"
                    onClick={() => setDeleteTarget(person)}
                    title="Delete person record"
                  >
                    <Trash2 size={15} />
                    <span>Delete</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add / Edit Person Modal */}
      {showModal && (
        <div className="custom-modal-backdrop" onClick={() => !actionLoading && setShowModal(false)}>
          <div className="custom-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="custom-modal-header">
              <div className="modal-title-with-icon">
                {modalMode === 'add' ? (
                  <UserPlus size={22} className="text-cyan" />
                ) : (
                  <Edit3 size={22} className="text-cyan" />
                )}
                <div>
                  <h2 className="modal-main-title">
                    {modalMode === 'add' ? 'Add Person Record' : 'Edit Person Details'}
                  </h2>
                  <p className="modal-subtitle-text">
                    {modalMode === 'add' 
                      ? 'Create a new person profile with name, DOB, description, and image.' 
                      : 'Update the person information and photo.'}
                  </p>
                </div>
              </div>
              <button 
                className="modal-btn-close" 
                onClick={() => setShowModal(false)}
                disabled={actionLoading}
              >
                <X size={18} />
              </button>
            </div>

            {errorMessage && (
              <div className="modal-error-banner">
                <AlertCircle size={16} />
                <span>{errorMessage}</span>
              </div>
            )}

            <form onSubmit={handleSubmitForm} className="modal-body-form">
              {/* Name Field */}
              <div className="modal-field-group">
                <label className="modal-field-label">
                  Full Name <span className="text-required">*</span>
                </label>
                <input
                  type="text"
                  required
                  className="modal-text-input"
                  placeholder="e.g. Vikram Malhotra / John Doe"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              {/* DOB Field */}
              <div className="modal-field-group">
                <label className="modal-field-label">
                  Date of Birth (DOB)
                </label>
                <input
                  type="date"
                  className="modal-date-input"
                  value={formData.dob}
                  onChange={(e) => setFormData({ ...formData, dob: e.target.value })}
                />
              </div>

              {/* Description Field */}
              <div className="modal-field-group">
                <label className="modal-field-label">
                  Description / Background Notes
                </label>
                <textarea
                  className="modal-textarea-input"
                  rows={3}
                  placeholder="Enter details, identification marks, background information, or notes..."
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                />
              </div>

              {/* Image Section */}
              <div className="modal-field-group">
                <label className="modal-field-label">
                  Person Image / Photo
                </label>
                
                <div className="photo-upload-zone">
                  {/* Photo Preview if Available */}
                  {formData.image_url ? (
                    <div className="modal-photo-preview-box">
                      <img 
                        src={getImageUrl(formData.image_url)} 
                        alt="Preview" 
                        className="modal-preview-img"
                      />
                      <button 
                        type="button" 
                        className="btn-remove-photo"
                        onClick={() => {
                          setFormData({ ...formData, image_url: '' });
                          if (fileInputRef.current) fileInputRef.current.value = '';
                        }}
                        title="Remove photo"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ) : (
                    <div 
                      className="photo-dropzone-placeholder"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <Upload size={24} className="text-cyan" />
                      <span className="dropzone-text">Click to choose image file</span>
                      <span className="dropzone-sub">PNG, JPG, WEBP up to 5MB</span>
                    </div>
                  )}

                  <input 
                    key={fileInputKey}
                    ref={fileInputRef}
                    type="file" 
                    accept="image/*" 
                    className="hidden-file-input"
                    onChange={handleFileChange}
                  />

                  {/* Or enter Image URL */}
                  <div className="url-input-container">
                    <span className="url-label">Or Image URL:</span>
                    <input
                      type="text"
                      className="modal-text-input small"
                      placeholder="https://example.com/photo.jpg"
                      value={formData.image_url.startsWith('data:') ? '' : formData.image_url}
                      onChange={(e) => setFormData({ ...formData, image_url: e.target.value })}
                    />
                  </div>
                </div>
              </div>

              {/* Modal Actions */}
              <div className="modal-actions-footer">
                <button 
                  type="button" 
                  className="btn-modal-cancel" 
                  onClick={() => setShowModal(false)}
                  disabled={actionLoading}
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="btn-modal-save" 
                  disabled={actionLoading || !formData.name.trim()}
                >
                  {actionLoading ? (
                    <>
                      <RefreshCw size={15} className="spin" />
                      <span>Saving...</span>
                    </>
                  ) : (
                    <>
                      <Check size={16} />
                      <span>{modalMode === 'add' ? 'Save Person' : 'Update Person'}</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog Modal */}
      {deleteTarget && (
        <div className="custom-modal-backdrop" onClick={() => !actionLoading && setDeleteTarget(null)}>
          <div className="custom-modal-card delete-card" onClick={(e) => e.stopPropagation()}>
            <div className="delete-modal-icon-wrap">
              <Trash2 size={28} className="text-red" />
            </div>

            <h2 className="delete-modal-title">Delete Person Record?</h2>
            <p className="delete-modal-desc">
              Are you sure you want to delete <strong className="text-primary">{deleteTarget.name}</strong>? 
              This will permanently remove their profile and photo from the database.
            </p>

            <div className="delete-modal-actions">
              <button 
                type="button" 
                className="btn-modal-cancel" 
                onClick={() => setDeleteTarget(null)}
                disabled={actionLoading}
              >
                Cancel
              </button>
              <button 
                type="button" 
                className="btn-danger-delete" 
                onClick={handleConfirmDelete}
                disabled={actionLoading}
              >
                {actionLoading ? (
                  <>
                    <RefreshCw size={15} className="spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 size={16} />
                    <span>Yes, Delete Record</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Lightbox Modal for Enlarge Image */}
      {lightboxImage && (
        <div className="custom-modal-backdrop" onClick={() => setLightboxImage(null)}>
          <div className="lightbox-content-card" onClick={(e) => e.stopPropagation()}>
            <div className="lightbox-header">
              <span className="lightbox-title">{lightboxImage.name}</span>
              <button className="modal-btn-close" onClick={() => setLightboxImage(null)}>
                <X size={20} />
              </button>
            </div>
            <div className="lightbox-img-wrapper">
              <img 
                src={lightboxImage.url} 
                alt={lightboxImage.name} 
                className="lightbox-full-img" 
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
