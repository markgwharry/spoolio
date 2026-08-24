import React, { useCallback, useEffect, useMemo, useState, useContext } from 'react';
import { AuthContext } from './AuthContext';

function ManualInstructions({ release }) {
  const fallback = useMemo(() => {
    if (!release) return '';
    const base = release.download_url || '';
    const checksum = release.checksum || 'unknown';
    const signed = release.signed_download_url || base;
    return [
      '1. Download the firmware binary from the signed link below.',
      signed ? `   ${signed}` : base ? `   ${base}` : '',
      '2. Verify the SHA256 checksum matches:',
      `   ${checksum}`,
      '3. Flash the binary using esptool (replace PORT as needed):',
      '   esptool.py --port /dev/ttyUSB0 --baud 921600 write_flash 0x0 firmware.bin',
      '4. Power-cycle the device and verify its heartbeat and hardware functions.'
    ].filter(Boolean).join('\n');
  }, [release]);

  const text = release?.manual_instructions?.trim() ? release.manual_instructions.trim() : fallback;

  const handleCopy = () => {
    if (!text) return;
    navigator.clipboard.writeText(text).catch(() => {});
  };

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>Manual / USB flashing instructions</strong>
        <button type="button" onClick={handleCopy} style={{ fontSize: 12, padding: '4px 8px' }}>Copy</button>
      </div>
      <pre style={{
        background: 'var(--muted, #0f172a)',
        color: 'var(--muted-foreground, #e2e8f0)',
        padding: 12,
        borderRadius: 8,
        whiteSpace: 'pre-wrap',
        marginTop: 8,
        fontSize: 12,
        maxHeight: 220,
        overflowY: 'auto'
      }}>{text || 'No instructions provided yet.'}</pre>
    </div>
  );
}

export default function FirmwareReleaseAdmin() {
  const { authFetch } = useContext(AuthContext);
  const [releases, setReleases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [form, setForm] = useState({
    version: '',
    hardware_type: '',
    release_notes: '',
    manual_instructions: '',
    is_active: true
  });
  const [binaryFile, setBinaryFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const fetchReleases = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await authFetch('/api/admin/firmware');
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to load firmware releases');
      }
      setReleases(Array.isArray(data.releases) ? data.releases : []);
    } catch (err) {
      setError(err.message || 'Unable to load firmware releases');
    }
    setLoading(false);
  }, [authFetch]);

  useEffect(() => {
    fetchReleases();
  }, [fetchReleases]);

  const handleFormChange = (event) => {
    const { name, value, type, checked } = event.target;
    setForm(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleFileChange = (event) => {
    setBinaryFile(event.target.files?.[0] || null);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setMessage('');
    if (!binaryFile) {
      setError('Please choose a firmware binary before publishing.');
      return;
    }
    if (!form.version.trim() || !form.hardware_type.trim()) {
      setError('Version and hardware type are required.');
      return;
    }
    const payload = new FormData();
    payload.append('version', form.version.trim());
    payload.append('hardware_type', form.hardware_type.trim());
    payload.append('is_active', form.is_active ? 'true' : 'false');
    payload.append('release_notes', form.release_notes);
    payload.append('manual_instructions', form.manual_instructions);
    payload.append('binary', binaryFile);

    setSubmitting(true);
    try {
      const res = await authFetch('/api/admin/firmware', {
        method: 'POST',
        body: payload
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to create firmware release');
      }
      setMessage(`Firmware ${data.release?.version || form.version} published.`);
      setForm({
        version: '',
        hardware_type: '',
        release_notes: '',
        manual_instructions: '',
        is_active: true
      });
      setBinaryFile(null);
      try {
        if (event.target && event.target.reset) event.target.reset();
      } catch (_) {}
      await fetchReleases();
    } catch (err) {
      setError(err.message || 'Upload failed');
    }
    setSubmitting(false);
  };

  const handleActivate = async (releaseId) => {
    setError('');
    setMessage('');
    try {
      const res = await authFetch(`/api/admin/firmware/${releaseId}/activate`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Unable to activate release');
      }
      setMessage(`Release ${data.release?.version || ''} set active.`);
      setReleases(prev => prev.map(r => r.id === data.release.id ? data.release : { ...r, is_active: false }));
    } catch (err) {
      setError(err.message || 'Failed to update release status');
    }
  };

  const handleNotify = async (release) => {
    const extra = window.prompt('Optional note to include in the email announcement:', '');
    setError('');
    setMessage('');
    try {
      const res = await authFetch(`/api/admin/firmware/${release.id}/notify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: extra || undefined })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to send firmware announcement');
      }
      setMessage(`Email sent to ${data.notified} of ${data.requested} recipients.`);
      if (data.release) {
        setReleases(prev => prev.map(r => r.id === data.release.id ? data.release : r));
      }
    } catch (err) {
      setError(err.message || 'Unable to send email notification');
    }
  };

  return (
    <div style={{
      gridColumn: '1 / -1',
      border: '1px solid var(--border)',
      borderRadius: 12,
      padding: 16,
      background: 'var(--background, #fff)',
      color: 'var(--foreground, #111827)'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>Firmware Releases</h3>
        <button type="button" onClick={fetchReleases} style={{ fontSize: 12 }}>Refresh</button>
      </div>
      <p style={{ marginTop: 0, fontSize: 14, color: 'var(--muted-foreground, #4b5563)' }}>
        Publish firmware binaries, email device owners, and share manual flashing instructions. This opt-in tool does not make a device OTA-capable; maintained Spoolio sketches still require USB flashing.
      </p>

      <form onSubmit={handleSubmit} style={{ marginTop: 12, background: 'var(--card, #f8fafc)', padding: 16, borderRadius: 12 }}>
        <h4 style={{ marginTop: 0 }}>Publish firmware</h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
          <label style={{ display: 'flex', flexDirection: 'column', fontSize: 14 }}>
            Version
            <input name="version" value={form.version} onChange={handleFormChange} required placeholder="e.g. 1.2.0" />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', fontSize: 14 }}>
            Hardware type
            <input name="hardware_type" value={form.hardware_type} onChange={handleFormChange} required placeholder="e.g. esp8266" />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
            <input type="checkbox" name="is_active" checked={form.is_active} onChange={handleFormChange} /> Activate immediately
          </label>
        </div>
        <label style={{ display: 'flex', flexDirection: 'column', marginTop: 12, fontSize: 14 }}>
          Release notes
          <textarea name="release_notes" value={form.release_notes} onChange={handleFormChange} rows={3} placeholder="Key changes, bug fixes, etc." />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', marginTop: 12, fontSize: 14 }}>
          Manual instructions (optional)
          <textarea name="manual_instructions" value={form.manual_instructions} onChange={handleFormChange} rows={4} placeholder="Provide USB flashing steps, checksum commands, recovery notes…" />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', marginTop: 12, fontSize: 14 }}>
          Firmware binary
          <input type="file" onChange={handleFileChange} accept=".bin,.uf2,.hex,.zip" required />
        </label>
        <button type="submit" disabled={submitting} style={{ marginTop: 12 }}>
          {submitting ? 'Publishing…' : 'Publish firmware'}
        </button>
      </form>

      {error && <div style={{ marginTop: 12, color: 'var(--destructive, #b91c1c)' }}>{error}</div>}
      {message && <div style={{ marginTop: 12, color: 'var(--success, #15803d)' }}>{message}</div>}

      <div style={{ marginTop: 16 }}>
        <h4>Existing releases</h4>
        {loading ? (
          <div>Loading firmware releases…</div>
        ) : releases.length === 0 ? (
          <div>No firmware releases yet.</div>
        ) : (
          <div style={{ display: 'grid', gap: 16 }}>
            {releases.map(release => (
              <div key={release.id} style={{
                border: '1px solid var(--border)',
                borderRadius: 12,
                padding: 16,
                background: 'var(--popover, #ffffff)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <strong>{release.version}</strong> — {release.hardware_type}
                    {release.is_active && <span style={{ marginLeft: 8, padding: '2px 8px', borderRadius: 999, background: 'var(--primary, #0ea5e9)', color: '#fff', fontSize: 12 }}>Active</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {!release.is_active && (
                      <button type="button" onClick={() => handleActivate(release.id)}>Mark active</button>
                    )}
                    <button type="button" onClick={() => handleNotify(release)}>Email owners</button>
                  </div>
                </div>
                <div style={{ marginTop: 8, fontSize: 13, color: 'var(--muted-foreground, #4b5563)' }}>
                  Uploaded {release.created_at ? new Date(release.created_at).toLocaleString() : '—'} • SHA256 {release.checksum?.slice(0, 10)}…
                </div>
                {release.release_notes && (
                  <div style={{ marginTop: 8 }}>
                    <strong>Release notes</strong>
                    <p style={{ marginTop: 4 }}>{release.release_notes}</p>
                  </div>
                )}
                <div style={{ marginTop: 12 }}>
                  <div><strong>Signed download</strong></div>
                  <code style={{ display: 'block', wordBreak: 'break-all', marginTop: 4 }}>{release.signed_download_url || release.download_url}</code>
                  <small style={{ color: 'var(--muted-foreground, #64748b)' }}>Links expire after a few minutes. Refresh to mint a new signed URL.</small>
                </div>
                <ManualInstructions release={release} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
