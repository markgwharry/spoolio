import React from 'react';
import { Route, Routes, Link, NavLink, useLocation } from 'react-router-dom';
import { AuthProvider, AuthContext } from './AuthContext';
import ErrorBoundary from './ErrorBoundary';
import Register from './Register';
import Login from './Login';
import Icons from './components/Icons';
import SpoolSpinner from './components/SpoolSpinner';
import CommandPalette from './components/CommandPalette';
import logo from './logo-cropped.webp';
import { RegistrationProvider, useRegistration } from './RegistrationContext';

const Dashboard = React.lazy(() => import('./Dashboard'));
const Analytics = React.lazy(() => import('./Analytics'));
const HardwareManager = React.lazy(() => import('./HardwareManager'));
const AccountSettings = React.lazy(() => import('./AccountSettings'));
const ProjectDetail = React.lazy(() => import('./ProjectDetail'));
const BitsInventory = React.lazy(() => import('./BitsInventory'));
function AppNavigation() {
  const { user, token } = React.useContext(AuthContext);
  const { action, loading } = useRegistration();
  const isAuthenticated = Boolean(user) || Boolean(token);
  const navItems = React.useMemo(() => ([
    { to: '/', label: 'Home', icon: Icons.Home },
    { to: '/dashboard', label: 'Dashboard', icon: Icons.Dashboard },
    { to: '/analytics', label: 'Analytics', icon: Icons.Analytics },
    { to: '/bits', label: 'Bits', icon: Icons.Bits },
    { to: '/hardware', label: 'Hardware', icon: Icons.Hardware },
  ]), []);
  return (
    <nav className="app-nav" aria-label="Primary">
      {navItems.map(item => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) => isActive ? 'active' : undefined}
          end={item.to === '/'}
        >
          <item.icon />
          <span>{item.label}</span>
        </NavLink>
      ))}
      {isAuthenticated ? (
        <NavLink to="/account" className={({ isActive }) => isActive ? 'active' : undefined}>
          <Icons.Settings />
          <span>Account</span>
        </NavLink>
      ) : (
        <>
          <NavLink to="/login" className={({ isActive }) => isActive ? 'active' : undefined}>
            <Icons.LogIn />
            <span>Login</span>
          </NavLink>
          {!loading && action !== 'closed' && (
            <NavLink to="/register" className={({ isActive }) => isActive ? 'active' : undefined}>
              <Icons.User />
              <span>{action === 'waitlist' ? 'Waitlist' : 'Create account'}</span>
            </NavLink>
          )}
        </>
      )}
    </nav>
  );
}

function UserChip() {
  const { user, logout } = React.useContext(AuthContext);
  if (!user) {
    return (
      <div className="user-chip">
        <span className="user-meta">
          Need an account?
        </span>
        <Link to="/login">Login</Link>
      </div>
    );
  }
  const initials = (user.username || user.email || '?')
    .split(' ')
    .slice(0, 2)
    .map(part => part[0])
    .join('')
    .toUpperCase();
  return (
    <div className="user-chip" aria-label="Account menu">
      <div className="avatar" aria-hidden="true">{initials}</div>
      <div className="user-meta">
        <span>{user.username}</span>
        {user.email && <span className="muted">{user.email}</span>}
      </div>
      <button type="button" onClick={logout} className="ghost-button">Logout</button>
    </div>
  );
}

function Home() {
  const { user } = React.useContext(AuthContext);
  const { action, loading } = useRegistration();
  return (
    <div className="home-wrapper">
      <section className="hero">
        <div>
          <p className="eyebrow">Spoolio</p>
          <h1>Know exactly what filament is ready before every print.</h1>
          <p className="hero-copy">
            Track active, reserve, and empty spools, connect your own scale hardware, and get usage insights for every project.
          </p>
          <div className="hero-actions">
            {user ? (
              <Link to="/dashboard#add-spool" className="button primary-cta">
                Add a spool
              </Link>
            ) : (
              <>
                {!loading && action !== 'closed' && (
                  <Link to="/register" className="button primary-cta">
                    {action === 'waitlist' ? 'Join the waitlist' : 'Create owner account'}
                  </Link>
                )}
                <Link to="/login" className={action === 'closed' ? 'button primary-cta' : 'button ghost'}>Log in</Link>
              </>
            )}
          </div>
        </div>
        <ul className="hero-points" aria-label="Highlights">
          <li>Low-stock alerts help you restock before a print stalls.</li>
          <li>Analytics tie grams consumed to projects and material types.</li>
          <li>Optional hardware devices can report NFC scans and live spool weights.</li>
        </ul>
      </section>
    </div>
  );
}

function DarkModeToggle() {
  // Default to dark mode (matches current UI), user can switch to light
  const [isDark, setIsDark] = React.useState(() => {
    try {
      const stored = localStorage.getItem('theme');
      // If no preference stored, default to dark (current state)
      return stored ? stored !== 'light' : true;
    } catch { return true; }
  });
  React.useEffect(() => {
    const root = document.documentElement;
    const body = document.body;

    // Briefly disable transitions during mode switch
    root.classList.add('no-transitions');
    body.classList.add('no-transitions');

    if (isDark) {
      root.classList.remove('light');
      body.classList.remove('light');
      try { localStorage.setItem('theme', 'dark'); } catch {}
    } else {
      root.classList.add('light');
      body.classList.add('light');
      try { localStorage.setItem('theme', 'light'); } catch {}
    }

    // Re-enable transitions after a brief delay
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        root.classList.remove('no-transitions');
        body.classList.remove('no-transitions');
      });
    });
  }, [isDark]);

  // The command palette toggles theme through this single source of truth so
  // the header label/icon stay in sync.
  React.useEffect(() => {
    const onToggle = () => setIsDark(d => !d);
    window.addEventListener('spoolio:toggle-theme', onToggle);
    return () => window.removeEventListener('spoolio:toggle-theme', onToggle);
  }, []);

  return (
    <button
      onClick={() => setIsDark(d => !d)}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.5em',
        minWidth: 'auto',
        padding: '0.5em 1em'
      }}
    >
      {isDark ? (
        <>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="5"/>
            <line x1="12" y1="1" x2="12" y2="3"/>
            <line x1="12" y1="21" x2="12" y2="23"/>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
            <line x1="1" y1="12" x2="3" y2="12"/>
            <line x1="21" y1="12" x2="23" y2="12"/>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
          </svg>
          Light
        </>
      ) : (
        <>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
          Dark
        </>
      )}
    </button>
  );
}

function AppHeader() {
  const { user } = React.useContext(AuthContext);
  React.useEffect(() => {
    const onScroll = () => {
      const shadow = window.scrollY > 2 ? '0 2px 10px rgba(0,0,0,0.08)' : '0 0 0 rgba(0,0,0,0)';
      document.documentElement.style.setProperty('--header-shadow', shadow);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return (
    <header className="app-header">
      <div className="brand">
        <img src={logo} alt="Spoolio logo" loading="lazy" decoding="async" width="120" height="40" />
      </div>
      <div className="header-actions">
        {user && (
          <button
            type="button"
            className="cmdk-hint"
            onClick={() => window.dispatchEvent(new Event('spoolio:open-cmdk'))}
            aria-label="Open command palette"
            title="Command palette"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
            </svg>
            <kbd>{(typeof navigator !== 'undefined' && /Mac/i.test(navigator.platform || navigator.userAgent)) ? '⌘K' : 'Ctrl K'}</kbd>
          </button>
        )}
        <DarkModeToggle />
        <UserChip />
      </div>
    </header>
  );
}

function AppShell() {
  const location = useLocation();
  const showChrome = !['/login', '/register'].includes(location.pathname);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <CommandPalette />
      {showChrome && (
        <>
          <AppHeader />
          <AppNavigation />
        </>
      )}
      {/* Aria-live region for announcements */}
      <div
        id="announcements"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      />
      <main id="main" className="app-main">
        <ErrorBoundary>
          <React.Suspense fallback={<div className="page-loading"><SpoolSpinner label="Loading…" /></div>}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/projects/:id" element={<ProjectDetail />} />
              <Route path="/bits" element={<BitsInventory />} />
              <Route path="/hardware" element={<HardwareManager />} />
              <Route path="/account" element={<AccountSettings />} />
            </Routes>
          </React.Suspense>
        </ErrorBoundary>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <RegistrationProvider>
        <AppShell />
      </RegistrationProvider>
    </AuthProvider>
  );
}
