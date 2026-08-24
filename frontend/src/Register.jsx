import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useRegistration } from './RegistrationContext';

export default function Register() {
  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    registration_token: '',
  });
  const [message, setMessage] = useState('');
  const [status, setStatus] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [accountCreated, setAccountCreated] = useState(false);
  const { action, loading, error: registrationError, refresh } = useRegistration();
  const createsOwner = action === 'create-owner';

  const handleChange = e => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async e => {
    e.preventDefault();
    setMessage('');
    setStatus(null);
    setSubmitting(true);
    try {
      const payload = {
        username: form.username,
        email: form.email,
        ...(createsOwner ? {
          password: form.password,
          registration_token: form.registration_token,
        } : {}),
      };
      const res = await fetch('/api/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      const { msg } = data;
      if (res.ok) {
        setStatus('success');
        setMessage(msg || (createsOwner
          ? 'Owner account created. You can now log in.'
          : 'Thanks for joining the Spoolio waitlist!'));
        setForm({ username: '', email: '', password: '', registration_token: '' });
        if (createsOwner) {
          setAccountCreated(true);
          await refresh();
        }
      } else {
        setStatus('error');
        setMessage(msg || 'We could not process your request. Please try again later.');
      }
    } catch (err) {
      console.error('Registration error:', err);
      setStatus('error');
      setMessage('Error connecting to server.');
    } finally {
      setSubmitting(false);
    }
  };

  if (accountCreated) {
    return (
      <section className="auth-card" aria-labelledby="register-title">
        <h2 id="register-title">Owner account created</h2>
        <div className="status-text success" role="status">
          {message || 'Your server is ready. You can now log in.'}
        </div>
        <Link to="/login" className="button primary-cta">Log in</Link>
      </section>
    );
  }

  if (loading) {
    return (
      <section className="auth-card" aria-labelledby="register-title">
        <h2 id="register-title">Checking registration…</h2>
      </section>
    );
  }

  if (registrationError || action === 'closed') {
    return (
      <section className="auth-card" aria-labelledby="register-title">
        <h2 id="register-title">Registration is closed</h2>
        <p className="form-note">
          {registrationError || 'This server already has an owner. Ask them for access.'}
        </p>
        <Link to="/login" className="button primary-cta">Log in</Link>
      </section>
    );
  }

  return (
    <section className="auth-card" aria-labelledby="register-title">
      <h2 id="register-title">
        {createsOwner ? 'Create the owner account' : 'Join the Spoolio waitlist'}
      </h2>
      <p className="form-note">
        {createsOwner
          ? 'This one-time account will administer your new Spoolio server. Registration closes after it is created.'
          : 'Reserve your spot for the next round of invites. We’ll email you as soon as we open access.'}
      </p>
      <form onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="register-username">Preferred username</label>
          <input
            id="register-username"
            name="username"
            placeholder="PrinterPro"
            value={form.username}
            onChange={handleChange}
            required
            autoComplete="username"
          />
          <small>We use this to personalize your workspace.</small>
        </div>
        <div className="form-field">
          <label htmlFor="register-email">Email address</label>
          <input
            id="register-email"
            name="email"
            placeholder="you@example.com"
            value={form.email}
            onChange={handleChange}
            required
            type="email"
            autoComplete="email"
          />
          <small>We&rsquo;ll only contact you about onboarding and major updates.</small>
        </div>
        {createsOwner && (
          <div className="form-field">
            <label htmlFor="register-token">Owner setup code</label>
            <input
              id="register-token"
              name="registration_token"
              value={form.registration_token}
              onChange={handleChange}
              required
              type="password"
              autoComplete="off"
            />
            <small>Find this code in the first container startup log.</small>
          </div>
        )}
        {createsOwner && (
          <div className="form-field">
            <label htmlFor="register-password">Password</label>
            <input
              id="register-password"
              name="password"
              value={form.password}
              onChange={handleChange}
              required
              type="password"
              minLength={8}
              autoComplete="new-password"
            />
            <small>Use at least 8 characters with upper-case, lower-case, and a number.</small>
          </div>
        )}
        <button type="submit" disabled={submitting}>
          {submitting ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5em' }}>
              <svg className="spool-spinner-svg" width="16" height="16" viewBox="0 0 64 64" aria-hidden="true">
                <circle cx="32" cy="32" r="22" fill="none" stroke="currentColor" strokeOpacity="0.3" strokeWidth="8" />
                <circle cx="32" cy="32" r="22" fill="none" stroke="currentColor" strokeWidth="8" strokeLinecap="round" strokeDasharray="50 140" />
              </svg>
              {createsOwner ? 'Creating…' : 'Joining…'}
            </span>
          ) : (createsOwner ? 'Create owner account' : 'Join waitlist')}
        </button>
      </form>
      {message && (
        <div className={`status-text ${status === 'error' ? 'error' : 'success'}`} role="status">
          {message}
        </div>
      )}
      <p className="form-note">
        Already invited? <Link to="/login">Log in</Link>
      </p>
    </section>
  );
}
