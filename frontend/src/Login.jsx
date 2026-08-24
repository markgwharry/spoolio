import React, { useState, useContext } from 'react';
import { AuthContext } from './AuthContext';
import logo from './logo-cropped.webp';
import { useNavigate, Link } from 'react-router-dom';
import { useRegistration } from './RegistrationContext';

export default function Login() {
  const { login } = useContext(AuthContext);
  const [form, setForm] = useState({ username: '', password: '' });
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [showResend, setShowResend] = useState(false);
  const [resendMsg, setResendMsg] = useState('');
  const [resendEmail, setResendEmail] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();
  const { action, loading } = useRegistration();

  const handleChange = e => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async e => {
    e.preventDefault();
    setError('');
    setMessage('');
    setShowResend(false);
    setResendMsg('');
    setSubmitting(true);
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (res.ok && data.access_token && data.user) {
        login(data.access_token, data.refresh_token, data.user);
        setMessage('Login successful! Redirecting…');
        navigate('/dashboard', { replace: true });
      } else {
        setError(data.msg || 'Invalid username or password');
        if (data.email_verification_required) {
          setShowResend(true);
          const inferredEmail = data.email || (form.username.includes('@') ? form.username : '');
          setResendEmail(inferredEmail);
        }
      }
    } catch (err) {
      setError('Error connecting to server.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (!resendEmail) {
      setResendMsg('Enter the email associated with your account.');
      return;
    }
    setResendMsg('');
    const res = await fetch('/api/resend-verification', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: resendEmail }),
    });
    const data = await res.json();
    setResendMsg(data.msg || 'Request processed.');
  };

  return (
    <section className="auth-card" aria-labelledby="login-title">
      <div className="auth-logo">
        <img src={logo} alt="Spoolio logo" />
      </div>
      <h2 id="login-title">Welcome back</h2>
      <p className="form-note">Enter your credentials to reach your dashboard.</p>
      <form onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="login-username">Username or email</label>
          <input
            id="login-username"
            name="username"
            value={form.username}
            onChange={handleChange}
            autoComplete="username"
            required
          />
        </div>
        <div className="form-field password-field">
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            name="password"
            type={showPassword ? 'text' : 'password'}
            value={form.password}
            onChange={handleChange}
            autoComplete="current-password"
            required
            minLength={8}
          />
          <button
            type="button"
            onClick={() => setShowPassword(v => !v)}
            className="ghost-button"
            aria-label={showPassword ? 'Hide password' : 'Show password'}
          >
            {showPassword ? 'Hide' : 'Show'}
          </button>
        </div>
        <button type="submit" disabled={submitting}>
          {submitting ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5em' }}>
              <svg className="spool-spinner-svg" width="16" height="16" viewBox="0 0 64 64" aria-hidden="true">
                <circle cx="32" cy="32" r="22" fill="none" stroke="currentColor" strokeOpacity="0.3" strokeWidth="8" />
                <circle cx="32" cy="32" r="22" fill="none" stroke="currentColor" strokeWidth="8" strokeLinecap="round" strokeDasharray="50 140" />
              </svg>
              Logging in…
            </span>
          ) : 'Login'}
        </button>
      </form>
      {error && <div className="status-text error" role="status">{error}</div>}
      {message && <div className="status-text success" role="status">{message}</div>}
      {showResend && (
        <div className="form-field" style={{ marginTop: '1em' }}>
          <label htmlFor="resend-email">Verify your email</label>
          <input
            id="resend-email"
            type="email"
            value={resendEmail}
            onChange={e => setResendEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <div style={{ display: 'flex', gap: '0.5em', flexWrap: 'wrap', marginTop: '0.5em' }}>
            <button type="button" onClick={handleResend} className="button ghost">
              Resend verification link
            </button>
            {resendMsg && <span className="status-text success" role="status">{resendMsg}</span>}
          </div>
        </div>
      )}
      {!loading && action !== 'closed' && (
        <p className="form-note">
          Need an account?{' '}
          <Link to="/register">
            {action === 'waitlist' ? 'Join the waitlist' : 'Create the owner account'}
          </Link>
        </p>
      )}
    </section>
  );
}
