import React, { useState, useEffect, useContext, useCallback, useMemo } from 'react';
import { AuthContext } from './AuthContext';
import { useConfirmDialog } from './ConfirmDialog';
import SpoolSpinner from './components/SpoolSpinner';
import EmptyState from './components/EmptyState';
import useMetadata, { HARDWARE_METADATA } from './hooks/useMetadata';
import './HardwareManager.css';

const HardwareManager = () => {
  const { authFetch } = useContext(AuthContext);
  const { confirm, DialogComponent } = useConfirmDialog();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [showRegisterForm, setShowRegisterForm] = useState(false);
  const [newDevice, setNewDevice] = useState({
    device_id: '',
    name: '',
    location: '',
    hardware_type: ''
  });
  const [orphans, setOrphans] = useState([]);
  const [spools, setSpools] = useState([]);
  const [linking, setLinking] = useState({});
  const metadata = useMetadata(authFetch, HARDWARE_METADATA);
  const { materials, colors, manufacturers } = metadata;
  const reloadMetadata = metadata.reload;
  const [deviceSecrets, setDeviceSecrets] = useState({});
  const [focusedDeviceId, setFocusedDeviceId] = useState(null);
  const [wifiForms, setWifiForms] = useState({});
  const [wifiSaving, setWifiSaving] = useState({});
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const copyToClipboard = useCallback(async (value) => {
    if (!value) return false;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch (err) {
      // Fallback below
    }
    try {
      const textArea = document.createElement('textarea');
      textArea.value = value;
      textArea.setAttribute('readonly', '');
      textArea.style.position = 'absolute';
      textArea.style.left = '-9999px';
      document.body.appendChild(textArea);
      textArea.select();
      const successful = document.execCommand('copy');
      document.body.removeChild(textArea);
      return successful;
    } catch (err) {
      return false;
    }
  }, []);

  const fetchDevices = useCallback(async () => {
    try {
      const response = await authFetch('/api/hardware/devices', {
        headers: {
          'Content-Type': 'application/json'
        }
      });
      let data;
      try {
        data = await response.json();
      } catch (err) {
        data = [];
      }
      if (!response.ok) {
        const message = (data && data.error) ? data.error : 'Failed to fetch devices';
        throw new Error(message);
      }
      setDevices(Array.isArray(data) ? data : []);
      setLastRefreshedAt(new Date());
      return data;
    } catch (err) {
      setError(err.message);
      setFeedback(null);
      return null;
    }
  }, [authFetch]);

  const fetchOrphans = useCallback(async () => {
    try {
      const res = await authFetch('/api/hardware/orphans', {
        headers: {
          'Content-Type': 'application/json'
        }
      });
      if (!res.ok) throw new Error('Failed to fetch orphan tags');
      const data = await res.json();
      setOrphans(data.orphans || []);
      return data;
    } catch (err) {
      console.error('Failed to fetch orphans:', err);
      setOrphans([]);
      return null;
    }
  }, [authFetch]);

  const fetchSpools = useCallback(async () => {
    try {
      const res = await authFetch('/api/spools/', {
        headers: {
          'Content-Type': 'application/json'
        }
      });
      if (!res.ok) throw new Error('Failed to fetch spools');
      const data = await res.json();
      setSpools(data.spools || []);
      return data;
    } catch (err) {
      return null;
    }
  }, [authFetch]);

  const runFullRefresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) {
      setLoading(true);
    }
    setRefreshing(true);
    try {
      await Promise.all([
        fetchDevices(),
        fetchOrphans(),
        fetchSpools(),
        reloadMetadata({ force: !showSpinner }).catch(() => null),
      ]);
      setLastRefreshedAt(new Date());
    } finally {
      if (showSpinner) {
        setLoading(false);
      }
      setRefreshing(false);
    }
  }, [fetchDevices, fetchOrphans, fetchSpools, reloadMetadata]);

  useEffect(() => {
    let cancelled = false;
    const loadInitial = async () => {
      await runFullRefresh(true);
      if (cancelled) return;
    };
    loadInitial();
    return () => {
      cancelled = true;
    };
  }, [runFullRefresh]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchDevices();
      fetchOrphans();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchDevices, fetchOrphans]);

  useEffect(() => {
    setWifiForms(prev => {
      const next = {};
      (devices || []).forEach(device => {
        const backendSsid = device.wifi_ssid || '';
        const existing = prev[device.id] || {};
        const preserveDraft = existing.dirtySsid && existing.sourceSsid === backendSsid;
        next[device.id] = {
          ssid: preserveDraft ? existing.ssid : backendSsid,
          password: '',
          clearPassword: existing.clearPassword || false,
          dirtySsid: preserveDraft ? existing.dirtySsid : false,
          sourceSsid: backendSsid
        };
      });
      return next;
    });
  }, [devices]);

  const handleRegisterDevice = async (e) => {
    e.preventDefault();
    setError(null);
    setFeedback(null);
    try {
      const payload = {
        device_id: newDevice.device_id.trim(),
        name: newDevice.name.trim(),
        location: (newDevice.location || '').trim(),
        hardware_type: (newDevice.hardware_type || '').trim()
      };
      const response = await authFetch('/api/hardware/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Failed to register device');
      }
      setDeviceSecrets(prev => ({ ...prev, [data.device.id]: data.api_key }));
      const copied = await copyToClipboard(data.api_key);
      setFeedback(copied
        ? `Device "${data.device.name}" registered. API key copied to clipboard.`
        : `Device "${data.device.name}" registered. Copy the API key from the device card below.`
      );
      setNewDevice({ device_id: '', name: '', location: '', hardware_type: '' });
      setShowRegisterForm(false);
      await fetchDevices();
    } catch (err) {
      setFeedback(null);
      setError(err.message);
    }
  };

  const handleDeleteDevice = async (deviceId) => {
    const confirmed = await confirm({
      title: 'Delete Device',
      message: 'Are you sure you want to delete this device? This action cannot be undone.',
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      variant: 'danger'
    });
    if (!confirmed) return;
    setError(null);
    try {
      const response = await authFetch(`/api/hardware/devices/${deviceId}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || 'Failed to delete device');
      }
      setDeviceSecrets(prev => {
        const next = { ...prev };
        delete next[deviceId];
        return next;
      });
      setFeedback('Device deleted successfully.');
      await fetchDevices();
    } catch (err) {
      setFeedback(null);
      setError(err.message);
    }
  };

  const handleRegenerateKey = async (deviceId) => {
    const confirmed = await confirm({
      title: 'Regenerate API Key',
      message: 'Regenerating the API key will disconnect this device until it is updated. Continue?',
      confirmLabel: 'Regenerate',
      cancelLabel: 'Cancel',
      variant: 'default'
    });
    if (!confirmed) return;
    setError(null);
    try {
      const response = await authFetch(`/api/hardware/devices/${deviceId}/regenerate-key`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Failed to regenerate API key');
      }
      setDeviceSecrets(prev => ({ ...prev, [deviceId]: data.api_key }));
      const copied = await copyToClipboard(data.api_key);
      setFeedback(copied
        ? 'New API key generated and copied to clipboard.'
        : 'New API key generated. Copy it from the device card below.'
      );
      await fetchDevices();
    } catch (err) {
      setFeedback(null);
      setError(err.message);
    }
  };

  const handleCopyKey = async (deviceId) => {
    const apiKey = deviceSecrets[deviceId];
    if (!apiKey) {
      setFeedback(null);
      setError('API keys are only shown immediately after registration or regeneration. Generate a new key to copy it.');
      return;
    }
    const copied = await copyToClipboard(apiKey);
    if (copied) {
      setError(null);
      setFeedback('API key copied to clipboard.');
    } else {
      setFeedback(null);
      setError('Unable to copy API key automatically. Please copy it manually.');
    }
  };

  const linkOrphan = async (nfc_tag_id) => {
    const spool_id = linking[nfc_tag_id];
    if (!spool_id) return;
    try {
      const res = await authFetch('/api/hardware/orphans/link', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ nfc_tag_id, spool_id })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to link tag');
      await Promise.all([fetchOrphans(), fetchSpools(), fetchDevices()]);
      setLinking(l => ({ ...l, [nfc_tag_id]: '' }));
      setError(null);
      setFeedback('Tag linked successfully.');
    } catch (err) {
      setFeedback(null);
      setError(err.message);
    }
  };

  const deleteOrphan = async (nfc_tag_id) => {
    try {
      const res = await authFetch(`/api/hardware/orphans/${encodeURIComponent(nfc_tag_id)}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || 'Failed to delete orphan tag');
      }
      await fetchOrphans();
      setFeedback('Orphan tag deleted.');
    } catch (err) {
      setFeedback(null);
      setError(err.message);
    }
  };

  const focusOnDevice = (deviceId) => {
    setFocusedDeviceId(deviceId);
    const section = document.getElementById('orphan-section');
    if (section && section.scrollIntoView) {
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const handleConfirmAssociation = (device) => {
    if (!device || !device.last_linked_spool) {
      setFeedback(null);
      setError('No linked spool to confirm yet for this device.');
      return;
    }
    setError(null);
    setFeedback(`Confirmed ${device.name} is paired with spool #${device.last_linked_spool.id}.`);
  };

  const handleWifiFieldChange = (deviceId, field, value) => {
    setWifiForms(prev => {
      const current = prev[deviceId] || { ssid: '', password: '', clearPassword: false, dirtySsid: false, sourceSsid: '' };
      const updated = {
        ...current,
        [field]: value
      };
      if (field === 'ssid') {
        updated.dirtySsid = true;
      }
      return { ...prev, [deviceId]: updated };
    });
  };

  const toggleWifiClearPassword = (deviceId) => {
    setWifiForms(prev => {
      const current = prev[deviceId] || { ssid: '', password: '', clearPassword: false, dirtySsid: false, sourceSsid: '' };
      const nextValue = !current.clearPassword;
      return {
        ...prev,
        [deviceId]: {
          ...current,
          clearPassword: nextValue,
          password: nextValue ? '' : current.password
        }
      };
    });
  };

  const handleWifiSubmit = async (event, deviceId) => {
    event.preventDefault();
    const formState = wifiForms[deviceId] || {};
    const ssid = (formState.ssid || '').trim();

    if (!ssid) {
      setFeedback(null);
      setError('SSID is required to store Wi-Fi credentials.');
      return;
    }

    const payload = { ssid };
    if (formState.clearPassword) {
      payload.clear_password = true;
    } else if (formState.password) {
      payload.password = formState.password;
    }

    setWifiSaving(prev => ({ ...prev, [deviceId]: true }));
    setError(null);
    setFeedback(null);

    try {
      const response = await authFetch(`/api/hardware/devices/${deviceId}/wifi`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || 'Failed to update Wi-Fi settings');
      }

      setFeedback(data.message || 'Wi-Fi settings saved. Devices can securely fetch the updated credentials.');
      setWifiForms(prev => ({
        ...prev,
        [deviceId]: {
          ssid: data.wifi_ssid || '',
          password: '',
          clearPassword: false,
          dirtySsid: false,
          sourceSsid: data.wifi_ssid || ''
        }
      }));
      await fetchDevices();
    } catch (err) {
      setFeedback(null);
      setError(err.message);
    } finally {
      setWifiSaving(prev => ({ ...prev, [deviceId]: false }));
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'online':
        return '#4CAF50';
      case 'offline':
        return '#f44336';
      default:
        return '#ff9800';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleString();
  };

  const deviceNameById = useMemo(() => {
    const map = {};
    (devices || []).forEach(device => {
      map[device.id] = device.name;
    });
    return map;
  }, [devices]);

  const orphansByDevice = useMemo(() => {
    const grouped = {};
    (orphans || []).forEach(orphan => {
      if (!orphan.hardware_device_id) return;
      if (!grouped[orphan.hardware_device_id]) {
        grouped[orphan.hardware_device_id] = [];
      }
      grouped[orphan.hardware_device_id].push(orphan);
    });
    return grouped;
  }, [orphans]);

  const connectedDevices = useMemo(() => (
    (devices || []).filter(device => (device.connection_state || device.status) === 'online')
  ), [devices]);

  if (loading && !lastRefreshedAt) {
    return <div className="hardware-manager"><SpoolSpinner label="Loading devices…" /></div>;
  }

  return (
    <>
    {DialogComponent}
    <div className="hardware-manager">
      <div className="hardware-header">
        <h2>Hardware Devices</h2>
        <button
          className="btn btn-primary"
          onClick={() => setShowRegisterForm(true)}
        >
          Register New Device
        </button>
      </div>
      <div className="hardware-summary">
        <div className="summary-card">
          <span className="summary-label">Online devices</span>
          <strong>{connectedDevices.length}</strong>
        </div>
        <div className="summary-card">
          <span className="summary-label">Offline devices</span>
          <strong>{Math.max(0, devices.length - connectedDevices.length)}</strong>
        </div>
        <div className="summary-card">
          <span className="summary-label">Orphan tags</span>
          <strong>{orphans.length}</strong>
        </div>
        <div className="summary-card">
          <span className="summary-label">Last refresh</span>
          <strong>{lastRefreshedAt ? lastRefreshedAt.toLocaleTimeString() : '—'}</strong>
        </div>
        <button
          className="btn btn-outline"
          onClick={() => runFullRefresh()}
          disabled={refreshing}
          style={{ minWidth: 140 }}
        >
          {refreshing ? 'Refreshing…' : 'Refresh now'}
        </button>
      </div>

      {error && (
        <div className="error-message" role="alert" aria-live="assertive">
          {error}
          <button onClick={() => setError(null)} aria-label="Dismiss error">×</button>
        </div>
      )}

      {feedback && (
        <div className="success-message" role="status" aria-live="polite">
          {feedback}
          <button onClick={() => setFeedback(null)} aria-label="Dismiss message">×</button>
        </div>
      )}

      {showRegisterForm && (
        <div className="register-form-overlay">
          <div className="register-form">
            <h3>Register New Hardware Device</h3>
            <form onSubmit={handleRegisterDevice}>
              <div className="form-group">
                <label htmlFor="device_id">Device ID:</label>
                <input
                  type="text"
                  id="device_id"
                  value={newDevice.device_id}
                  onChange={(e) => setNewDevice({...newDevice, device_id: e.target.value})}
                  placeholder="e.g., ESP8266_SPOOL_TRACKER_001"
                  required
                />
                <small>Unique identifier for your hardware device</small>
              </div>

              <div className="form-group">
                <label htmlFor="name">Device Name:</label>
                <input
                  type="text"
                  id="name"
                  value={newDevice.name}
                  onChange={(e) => setNewDevice({...newDevice, name: e.target.value})}
                  placeholder="e.g., Workshop Scale"
                  required
                />
                <small>Human-readable name for the device</small>
              </div>

              <div className="form-group">
                <label htmlFor="location">Location:</label>
                <input
                  type="text"
                  id="location"
                  value={newDevice.location}
                  onChange={(e) => setNewDevice({...newDevice, location: e.target.value})}
                  placeholder="e.g., 3D Printer Room"
                />
                <small>Optional location description</small>
              </div>

              <div className="form-group">
                <label htmlFor="hardware_type">Hardware Type:</label>
                <input
                  type="text"
                  id="hardware_type"
                  value={newDevice.hardware_type}
                  onChange={(e) => setNewDevice({ ...newDevice, hardware_type: e.target.value })}
                  placeholder="e.g., esp8266"
                  required
                />
                <small>Used to target OTA firmware releases (match the value your device reports).</small>
              </div>

              <div className="form-actions">
                <button type="submit" className="btn btn-primary">
                  Register Device
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowRegisterForm(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <section className="connected-hardware">
        <h3>Connected hardware</h3>
        {connectedDevices.length === 0 ? (
          <p className="connected-empty">No devices are currently online.</p>
        ) : (
          <div className="connected-grid">
            {connectedDevices.map(device => {
              const pendingTags = (orphansByDevice[device.id] || []).length;
              const lastSpool = device.last_linked_spool;
              const connectionState = device.connection_state || device.status || 'unknown';
              const spoolLabelParts = [];
              if (lastSpool?.material_name) spoolLabelParts.push(lastSpool.material_name);
              if (lastSpool?.color_name) spoolLabelParts.push(lastSpool.color_name);
              if (lastSpool?.manufacturer_name) spoolLabelParts.push(lastSpool.manufacturer_name);
              const spoolLabel = spoolLabelParts.length ? ` ${spoolLabelParts.join(' • ')}` : '';
              return (
                <div key={`connected-${device.id}`} className="connected-card">
                  <div className="connected-card-header">
                    <h4>{device.name}</h4>
                    <span className={`state-pill ${connectionState}`}>
                      {connectionState}
                    </span>
                  </div>
                  {device.location && (
                    <p><strong>Location:</strong> {device.location}</p>
                  )}
                  <p><strong>Hardware:</strong> {device.hardware_type || '—'}</p>
                  <p><strong>Last heartbeat:</strong> {formatDate(device.last_seen)}</p>
                  {lastSpool ? (
                    <div className="connected-spool">
                      <p><strong>Last linked spool:</strong> #{lastSpool.id}{spoolLabel}</p>
                      <p><strong>Tag:</strong> {lastSpool.nfc_tag_id || '—'}</p>
                      <p><strong>Linked:</strong> {formatDate(lastSpool.hardware_last_update)}</p>
                    </div>
                  ) : (
                    <p>No spool link recorded yet.</p>
                  )}
                  <p><strong>Pending tags:</strong> {pendingTags}</p>
                  <div className="connected-actions">
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => focusOnDevice(device.id)}
                      disabled={pendingTags === 0}
                    >
                      Link pending tag
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleCopyKey(device.id)}
                      disabled={!deviceSecrets[device.id]}
                    >
                      Copy API key
                    </button>
                    <button
                      className="btn btn-tertiary btn-sm"
                      onClick={() => handleRegenerateKey(device.id)}
                    >
                      Regenerate key
                    </button>
                    <button
                      className="btn btn-outline btn-sm"
                      onClick={() => handleConfirmAssociation(device)}
                      disabled={!device.last_linked_spool}
                    >
                      Confirm association
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <div className="devices-grid">
        {devices.length === 0 ? (
          <EmptyState
            title="No devices yet"
            message="Register your first device to start tracking spool weights automatically."
          />
        ) : (
          devices.map(device => {
            const pendingTags = (orphansByDevice[device.id] || []).length;
            const lastSpool = device.last_linked_spool;
            const connectionState = device.connection_state || device.status || 'unknown';
            const spoolParts = [];
            if (lastSpool?.material_name) spoolParts.push(lastSpool.material_name);
            if (lastSpool?.color_name) spoolParts.push(lastSpool.color_name);
            if (lastSpool?.manufacturer_name) spoolParts.push(lastSpool.manufacturer_name);
            const spoolSummary = spoolParts.length ? ` ${spoolParts.join(' • ')}` : '';
            const wifiForm = wifiForms[device.id] || { ssid: device.wifi_ssid || '', password: '', clearPassword: false };
            const wifiStatusSummary = device.wifi_ssid
              ? `SSID "${device.wifi_ssid}"${device.wifi_password_set ? ' with encrypted password' : ' (no password stored)'}`
              : 'No Wi-Fi credentials stored yet';
            const wifiUpdatedAt = device.wifi_credentials_updated_at ? formatDate(device.wifi_credentials_updated_at) : null;
            return (
              <div key={device.id} className="device-card">
                <div className="device-header">
                  <h3>{device.name}</h3>
                  <div
                    className="status-indicator"
                    style={{ backgroundColor: getStatusColor(connectionState) }}
                    title={connectionState}
                  ></div>
                </div>

                <div className="device-info">
                  <p><strong>Device ID:</strong> {device.device_id}</p>
                  {device.location && (
                    <p><strong>Location:</strong> {device.location}</p>
                  )}
                  <p><strong>Hardware:</strong> {device.hardware_type || '—'}</p>
                  <p><strong>Status:</strong> {connectionState}</p>
                  <p><strong>Last Seen:</strong> {formatDate(device.last_seen)}</p>
                  <p><strong>Registered:</strong> {formatDate(device.created_at)}</p>
                  {lastSpool ? (
                    <>
                      <p><strong>Last Linked Spool:</strong> #{lastSpool.id}{spoolSummary}</p>
                      <p><strong>Linked Tag:</strong> {lastSpool.nfc_tag_id || '—'}</p>
                      <p><strong>Linked At:</strong> {formatDate(lastSpool.hardware_last_update)}</p>
                    </>
                  ) : (
                    <p><strong>Last Linked Spool:</strong> Not yet linked</p>
                  )}
                  {typeof lastSpool?.weight_remaining === 'number' && (
                    <p><strong>Last Recorded Weight:</strong> {Math.round(lastSpool.weight_remaining)} g</p>
                  )}
                  {deviceSecrets[device.id] && (
                    <div className="device-secret">
                      <p><strong>API Key:</strong> <code>{deviceSecrets[device.id]}</code></p>
                    </div>
                  )}
                </div>

                <div className="wifi-section">
                  <h4>Wi-Fi Credentials</h4>
                  <p className="wifi-warning">
                    Wi-Fi passwords are encrypted at rest and are never displayed after saving. Store new credentials here when onboarding hardware or rotating networks.
                  </p>
                  <p className="wifi-status"><strong>Current:</strong> {wifiStatusSummary}</p>
                  {wifiUpdatedAt && (
                    <p className="wifi-status"><strong>Last updated:</strong> {wifiUpdatedAt}</p>
                  )}
                  <form onSubmit={(event) => handleWifiSubmit(event, device.id)}>
                    <div className="form-group">
                      <label htmlFor={`wifi-ssid-${device.id}`}>Network name (SSID)</label>
                      <input
                        id={`wifi-ssid-${device.id}`}
                        type="text"
                        value={wifiForm.ssid || ''}
                        onChange={(e) => handleWifiFieldChange(device.id, 'ssid', e.target.value)}
                        placeholder="Wi-Fi network name"
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor={`wifi-password-${device.id}`}>Wi-Fi password</label>
                      <input
                        id={`wifi-password-${device.id}`}
                        type="password"
                        value={wifiForm.password || ''}
                        onChange={(e) => handleWifiFieldChange(device.id, 'password', e.target.value)}
                        placeholder={device.wifi_password_set ? 'Enter a new password to rotate' : 'Enter the network password'}
                        disabled={wifiForm.clearPassword}
                        autoComplete="new-password"
                      />
                      <small>Passwords are encrypted immediately and cannot be recovered. Provide a new value to rotate them.</small>
                    </div>
                    <div className="form-group wifi-clear-option">
                      <label>
                        <input
                          type="checkbox"
                          checked={wifiForm.clearPassword || false}
                          onChange={() => toggleWifiClearPassword(device.id)}
                        />{' '}
                        Remove stored password
                      </label>
                      <small>Only select this for open networks. Hardware will receive no password when fetching the config.</small>
                    </div>
                    <div className="form-actions wifi-actions">
                      <button
                        type="submit"
                        className="btn btn-primary btn-sm"
                        disabled={wifiSaving[device.id]}
                      >
                        {wifiSaving[device.id] ? 'Saving…' : 'Save Wi-Fi settings'}
                      </button>
                    </div>
                  </form>
                </div>

                <div className="device-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => focusOnDevice(device.id)}
                    disabled={pendingTags === 0}
                  >
                    Link pending tag
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleCopyKey(device.id)}
                    disabled={!deviceSecrets[device.id]}
                  >
                    Copy API key
                  </button>
                  <button
                    className="btn btn-tertiary btn-sm"
                    onClick={() => handleRegenerateKey(device.id)}
                  >
                    Regenerate key
                  </button>
                  <button
                    className="btn btn-danger btn-sm"
                    onClick={() => handleDeleteDevice(device.id)}
                  >
                    Delete Device
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="hardware-info" id="orphan-section">
        <h3>Unlinked NFC Tags</h3>
        {orphans.length === 0 ? (
          <p>No orphan tags detected yet. When your hardware scans a new tag, it will appear here to link to a spool.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>NFC Tag</th>
                <th style={{ textAlign: 'left' }}>Device</th>
                <th style={{ textAlign: 'left' }}>Last Gross Weight</th>
                <th style={{ textAlign: 'left' }}>Last Seen</th>
                <th style={{ textAlign: 'left' }}>Link To Spool</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {orphans.map(o => (
                <tr
                  key={o.id}
                  className={o.hardware_device_id === focusedDeviceId ? 'orphan-row-focused' : ''}
                >
                  <td>{o.nfc_tag_id}</td>
                  <td>{deviceNameById[o.hardware_device_id] || (o.hardware_device_id ? `Device #${o.hardware_device_id}` : 'Unknown')}</td>
                  <td>{typeof o.last_weight === 'number' ? Math.round(o.last_weight) : o.last_weight ?? '-'}</td>
                  <td>{o.last_seen ? new Date(o.last_seen).toLocaleString() : '-'}</td>
                  <td>
                    <select
                      value={linking[o.nfc_tag_id] || ''}
                      onChange={e => setLinking(l => ({ ...l, [o.nfc_tag_id]: e.target.value }))}
                    >
                      <option value="">Select spool…</option>
                      {(() => {
                        const materialMap = Object.fromEntries(materials.map(m => [m.id, m.name]));
                        const colorMap = Object.fromEntries(colors.map(c => [c.id, c.name]));
                        const manufacturerMap = Object.fromEntries(manufacturers.map(m => [m.id, m.name]));
                        // Only list spools that do not currently have an NFC tag associated
                        const untagged = (spools || []).filter(s => !s.nfc_tag_id);
                        return untagged.map(s => {
                          const mfr = manufacturerMap[s.manufacturer_id] || 'Unknown';
                          const mat = materialMap[s.material_id] || 'Unknown';
                          const col = colorMap[s.color_id] || 'Unknown';
                          const grams = typeof s.weight_remaining === 'number' ? Math.round(s.weight_remaining) : s.weight_remaining;
                          return (
                            <option key={s.id} value={s.id}>
                              {`${mfr} ${mat} ${col} - ${grams}g`}
                            </option>
                          );
                        });
                      })()}
                    </select>
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button className="btn btn-primary btn-sm" onClick={() => linkOrphan(o.nfc_tag_id)} disabled={!linking[o.nfc_tag_id]}>Link</button>
                    <button className="btn btn-secondary btn-sm" style={{ marginLeft: 8 }} onClick={() => deleteOrphan(o.nfc_tag_id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="hardware-info">
        <h3>Hardware Integration Guide</h3>
        <div className="info-grid">
          <div className="info-card">
            <h4>Setup Instructions</h4>
            <ol>
              <li>Register your device above to get an API key</li>
              <li>Update your ESP8266 code with the API key</li>
              <li>Configure WiFi settings in the code</li>
              <li>Upload the code to your ESP8266</li>
              <li>Attach NFC tags to your spools</li>
            </ol>
          </div>

          <div className="info-card">
            <h4>Required Components</h4>
            <ul>
              <li>ESP8266 microcontroller</li>
              <li>HX711 load cell amplifier</li>
              <li>PN532 NFC reader</li>
              <li>NeoPixel LED strip</li>
              <li>Load cell sensor</li>
              <li>NFC tags for spools</li>
            </ul>
          </div>

          <div className="info-card">
            <h4>How It Works</h4>
            <ol>
              <li>Place spool on scale</li>
              <li>Scan NFC tag on spool</li>
              <li>Device measures weight</li>
              <li>Data sent to API automatically</li>
              <li>Spool weight updated in database</li>
            </ol>
          </div>
        </div>
      </div>
    </div>
    </>
  );
};

export default HardwareManager;
