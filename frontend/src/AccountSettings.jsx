import React, { useContext, useEffect, useRef, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { AuthContext } from './AuthContext';

export default function AccountSettings() {
  const { token, authFetch, updateStoredUser, login, logout, user } = useContext(AuthContext);
  const authFetchRef = useRef(authFetch);
  const [account, setAccount] = useState(user);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState(null);
  const [emailForm, setEmailForm] = useState({
    email: user?.email || '',
    currentPassword: ''
  });
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: '',
    newPassword: ''
  });
  const [deleteForm, setDeleteForm] = useState({
    currentPassword: '',
    confirmText: ''
  });
  const [emailSaving, setEmailSaving] = useState(false);
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletePending, setDeletePending] = useState(false);
  const [integration, setIntegration] = useState(null);
  const [integrationLoading, setIntegrationLoading] = useState(true);
  const [integrationBusy, setIntegrationBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    authFetchRef.current = authFetch;
  }, [authFetch]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    let isMounted = true;
    const fetchAccount = async () => {
      setLoading(true);
      try {
        const response = await authFetchRef.current('/api/account');
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          if (isMounted) {
            setStatus({ type: 'error', message: body.msg || 'Unable to load account details.' });
          }
          return;
        }
        const body = await response.json();
        if (isMounted && body.user) {
          setAccount(body.user);
          setEmailForm(prev => ({ ...prev, email: body.user.email || '' }));
          updateStoredUser(body.user);
        }
      } catch (err) {
        if (isMounted) {
          setStatus({ type: 'error', message: 'Unable to load account details. Please try again.' });
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };
    fetchAccount();
    return () => {
      isMounted = false;
    };
  }, [token, updateStoredUser]);

  const showStatus = (type, message) => {
    setStatus({ type, message });
    window.setTimeout(() => {
      setStatus(prev => (prev && prev.type === type && prev.message === message ? null : prev));
    }, 5000);
  };

  useEffect(() => {
    if (!token) {
      setIntegrationLoading(false);
      return;
    }
    let isMounted = true;
    (async () => {
      setIntegrationLoading(true);
      try {
        const res = await authFetchRef.current('/api/integrations/spoolman');
        if (res.ok) {
          const body = await res.json();
          if (isMounted) setIntegration(body);
        }
      } catch (err) {
        /* non-fatal: integration card simply shows as unavailable */
      } finally {
        if (isMounted) setIntegrationLoading(false);
      }
    })();
    return () => { isMounted = false; };
  }, [token]);

  const callIntegration = async (method, query = '') => {
    setIntegrationBusy(true);
    try {
      const res = await authFetch(`/api/integrations/spoolman${query}`, { method });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        showStatus('error', body.message || 'Unable to update the integration.');
        return;
      }
      setIntegration(body);
      return body;
    } catch (err) {
      showStatus('error', 'Unable to update the integration. Please try again.');
    } finally {
      setIntegrationBusy(false);
    }
  };

  const handleEnableIntegration = async () => {
    const body = await callIntegration('POST');
    if (body) showStatus('success', 'Spoolman integration enabled.');
  };

  const handleRotateIntegration = async () => {
    if (!window.confirm('Rotate the token? Your current Spoolman URL will stop working immediately.')) return;
    const body = await callIntegration('POST', '?rotate=true');
    if (body) showStatus('success', 'Token rotated. Update your printer/slicer with the new URL.');
  };

  const handleDisableIntegration = async () => {
    if (!window.confirm('Disable the Spoolman integration? The URL will stop working.')) return;
    const body = await callIntegration('DELETE');
    if (body) showStatus('success', 'Spoolman integration disabled.');
  };

  const handleCopyUrl = async () => {
    const url = integration?.spoolman_url;
    if (!url) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        const ta = document.createElement('textarea');
        ta.value = url;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      showStatus('error', 'Could not copy to clipboard. Copy it manually.');
    }
  };

  const handleEmailSubmit = async (event) => {
    event.preventDefault();
    setEmailSaving(true);
    setStatus(null);
    try {
      const payload = {
        email: emailForm.email.trim(),
        current_password: emailForm.currentPassword
      };
      const response = await authFetch('/api/account/email', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        showStatus('error', body.msg || 'Unable to update email address.');
        return;
      }
      if (body.user) {
        setAccount(body.user);
        updateStoredUser(body.user);
      }
      showStatus('success', body.msg || 'Email updated.');
      setEmailForm(form => ({ ...form, currentPassword: '' }));
    } catch (err) {
      showStatus('error', 'Unable to update email address. Please try again.');
    } finally {
      setEmailSaving(false);
    }
  };

  const handlePasswordSubmit = async (event) => {
    event.preventDefault();
    setPasswordSaving(true);
    setStatus(null);
    try {
      const payload = {
        current_password: passwordForm.currentPassword,
        new_password: passwordForm.newPassword
      };
      const response = await authFetch('/api/account/password', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        showStatus('error', body.msg || 'Unable to update password.');
        return;
      }
      if (body.access_token && body.refresh_token) {
        login(body.access_token, body.refresh_token, body.user || user);
      }
      showStatus('success', body.msg || 'Password updated successfully.');
      setPasswordForm({ currentPassword: '', newPassword: '' });
    } catch (err) {
      showStatus('error', 'Unable to update password. Please try again.');
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleImageUpload = async (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) {
      return;
    }
    setUploading(true);
    setStatus(null);
    const formData = new FormData();
    formData.append('image', file);
    try {
      const response = await authFetch('/api/account/profile-image', {
        method: 'POST',
        body: formData
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        showStatus('error', body.msg || 'Unable to upload profile image.');
        return;
      }
      if (body.user) {
        setAccount(body.user);
        updateStoredUser(body.user);
      }
      showStatus('success', body.msg || 'Profile image updated.');
    } catch (err) {
      showStatus('error', 'Unable to upload profile image. Please try again.');
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  const handleImageRemove = async () => {
    if (!account?.profile_image_url) {
      return;
    }
    setUploading(true);
    setStatus(null);
    try {
      const response = await authFetch('/api/account/profile-image', {
        method: 'DELETE'
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        showStatus('error', body.msg || 'Unable to remove profile image.');
        return;
      }
      if (body.user) {
        setAccount(body.user);
        updateStoredUser(body.user);
      }
      showStatus('success', body.msg || 'Profile image removed.');
    } catch (err) {
      showStatus('error', 'Unable to remove profile image. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteAccount = async (event) => {
    event.preventDefault();
    if (deleteForm.confirmText.trim().toUpperCase() !== 'DELETE') {
      showStatus('error', 'Type DELETE to confirm account removal.');
      return;
    }
    setDeletePending(true);
    setStatus(null);
    try {
      const payload = {
        current_password: deleteForm.currentPassword,
        confirm: true
      };
      const response = await authFetch('/api/account', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        showStatus('error', body.msg || 'Unable to delete account.');
        return;
      }
      showStatus('success', body.msg || 'Account deleted. Logging you out.');
      logout();
      window.setTimeout(() => {
        window.location.href = '/';
      }, 1200);
    } catch (err) {
      showStatus('error', 'Unable to delete account. Please try again.');
    } finally {
      setDeletePending(false);
    }
  };

  if (!token && !loading) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="settings-wrapper">
      <h1>Account Settings</h1>
      {status && (
        <div className={`status-banner status-${status.type}`}>
          {status.message}
        </div>
      )}
      {loading ? (
        <div className="card">Loading account details...</div>
      ) : (
        <div className="settings-grid">
          <section className="card settings-card">
            <h2>Profile</h2>
            <p className="muted">
              Manage the basics tied to your Spoolio identity.
            </p>
            <div className="profile-preview">
              {account?.profile_image_url ? (
                <img src={account.profile_image_url} alt="Profile" />
              ) : (
                <div className="placeholder-avatar">{(account?.username || 'U').slice(0, 1).toUpperCase()}</div>
              )}
            </div>
            <div className="profile-meta">
              <div><strong>Username:</strong> {account?.username}</div>
              <div><strong>Email:</strong> {account?.email}</div>
              <div>
                <strong>Email status:</strong>{' '}
                {account?.email_verified ? 'Verified' : 'Verification pending'}
              </div>
              <div><strong>Member since:</strong> {account?.created_at ? new Date(account.created_at).toLocaleDateString() : '--'}</div>
            </div>
            <div className="profile-actions">
              <label className="upload-button">
                <input type="file" accept="image/png,image/jpeg,image/jpg,image/gif,image/webp" onChange={handleImageUpload} disabled={uploading} />
                {uploading ? 'Uploading...' : 'Upload Image'}
              </label>
              {account?.profile_image_url && (
                <button type="button" className="link-button" onClick={handleImageRemove} disabled={uploading}>
                  Remove image
                </button>
              )}
            </div>
          </section>

          <section className="card settings-card">
            <h2>Update Email</h2>
            <form className="settings-form" onSubmit={handleEmailSubmit}>
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                type="email"
                value={emailForm.email}
                onChange={(e) => setEmailForm(form => ({ ...form, email: e.target.value }))}
                required
              />
              <label htmlFor="email-password">Current password</label>
              <input
                id="email-password"
                type="password"
                value={emailForm.currentPassword}
                onChange={(e) => setEmailForm(form => ({ ...form, currentPassword: e.target.value }))}
                required
              />
              <button type="submit" disabled={emailSaving}>
                {emailSaving ? 'Saving...' : 'Save changes'}
              </button>
            </form>
          </section>

          <section className="card settings-card">
            <h2>Update Password</h2>
            <form className="settings-form" onSubmit={handlePasswordSubmit}>
              <label htmlFor="current-password">Current password</label>
              <input
                id="current-password"
                type="password"
                value={passwordForm.currentPassword}
                onChange={(e) => setPasswordForm(form => ({ ...form, currentPassword: e.target.value }))}
                required
              />
              <label htmlFor="new-password">New password</label>
              <input
                id="new-password"
                type="password"
                value={passwordForm.newPassword}
                onChange={(e) => setPasswordForm(form => ({ ...form, newPassword: e.target.value }))}
                required
                minLength={8}
              />
              <button type="submit" disabled={passwordSaving}>
                {passwordSaving ? 'Updating...' : 'Update password'}
              </button>
            </form>
          </section>

          <section className="card settings-card">
            <h2>Printer &amp; Slicer Integration</h2>
            <p className="muted">
              Spoolio speaks the <strong>Spoolman</strong> API, so Moonraker,
              OctoPrint-Spoolman, OrcaSlicer and NFC scales like FilaMan can read
              your inventory and decrement spools automatically as you print.
            </p>

            {integrationLoading ? (
              <p className="muted">Loading integration status...</p>
            ) : integration?.enabled ? (
              <>
                <p style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', margin: '0.25rem 0 0.75rem' }}>
                  <span aria-hidden="true" style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--success)', display: 'inline-block' }} />
                  <strong>Connected.</strong>
                  <span className="muted">Paste this URL as your “Spoolman server”:</span>
                </p>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'stretch' }}>
                  <input
                    type="text"
                    readOnly
                    value={integration.spoolman_url || ''}
                    onFocus={(e) => e.target.select()}
                    aria-label="Spoolman server URL"
                    style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}
                  />
                  <button type="button" onClick={handleCopyUrl} style={{ whiteSpace: 'nowrap' }}>
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                </div>
                <p className="muted" style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>
                  Keep this URL private — anyone with it can read and adjust your spools.
                </p>
                <div className="profile-actions" style={{ marginTop: '0.75rem' }}>
                  <button type="button" className="link-button" onClick={handleRotateIntegration} disabled={integrationBusy}>
                    Rotate token
                  </button>
                  <button type="button" className="link-button" onClick={handleDisableIntegration} disabled={integrationBusy}>
                    Disable
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="muted" style={{ marginBottom: '0.75rem' }}>
                  Not connected. Enable to get a private URL for your printer or slicer.
                </p>
                <button type="button" onClick={handleEnableIntegration} disabled={integrationBusy}>
                  {integrationBusy ? 'Enabling...' : 'Enable integration'}
                </button>
              </>
            )}
          </section>

          <section className="card settings-card danger-zone">
            <h2>Danger Zone</h2>
            <p>
              Delete your account and associated data. This cannot be undone.
            </p>
            <form className="settings-form" onSubmit={handleDeleteAccount}>
              <label htmlFor="delete-password">Current password</label>
              <input
                id="delete-password"
                type="password"
                value={deleteForm.currentPassword}
                onChange={(e) => setDeleteForm(form => ({ ...form, currentPassword: e.target.value }))}
                required
              />
              <label htmlFor="delete-confirm">Type DELETE to confirm</label>
              <input
                id="delete-confirm"
                type="text"
                value={deleteForm.confirmText}
                onChange={(e) => setDeleteForm(form => ({ ...form, confirmText: e.target.value }))}
                placeholder="DELETE"
                required
              />
              <button type="submit" className="danger" disabled={deletePending}>
                {deletePending ? 'Deleting...' : 'Delete account'}
              </button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
