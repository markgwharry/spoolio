import React from 'react';
import { Route, Routes, Link, NavLink, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, AuthContext } from './AuthContext';
import ErrorBoundary from './ErrorBoundary';
import Register from './Register';
import Login from './Login';
import Icons from './components/Icons';
import SpoolSpinner from './components/SpoolSpinner';
import CommandPalette from './components/CommandPalette';
import BrandLogo from './components/BrandLogo';
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
  const navItems = React.useMemo(() => (isAuthenticated ? [
    { to: '/dashboard', label: 'Dashboard', icon: Icons.Dashboard },
    { to: '/analytics', label: 'Analytics', icon: Icons.Analytics },
    { to: '/parts', label: 'Parts', icon: Icons.Bits },
    { to: '/hardware', label: 'Hardware', icon: Icons.Hardware },
  ] : [
    { to: '/', label: 'Home', icon: Icons.Home },
    { to: '/login', label: 'Log in', icon: Icons.LogIn },
  ]), [isAuthenticated]);
  return (
    <nav className={`app-nav ${isAuthenticated ? 'is-authenticated' : 'is-public'}`} aria-label="Primary">
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
      {!isAuthenticated && !loading && action !== 'closed' && (
        <NavLink to="/register" className={({ isActive }) => isActive ? 'active' : undefined}>
          <Icons.User />
          <span>{action === 'waitlist' ? 'Waitlist' : 'Join'}</span>
        </NavLink>
      )}
    </nav>
  );
}

function UserChip() {
  const { user, logout } = React.useContext(AuthContext);
  if (!user) return null;
  const initials = (user.username || user.email || '?')
    .split(' ')
    .slice(0, 2)
    .map(part => part[0])
    .join('')
    .toUpperCase();
  return (
    <details className="user-menu">
      <summary aria-label="Open account menu">
        <span className="avatar" aria-hidden="true">{initials}</span>
        <span className="user-menu-name">{user.username || user.email}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </summary>
      <div className="user-menu-popover">
        {user.email && <span className="user-menu-email">{user.email}</span>}
        <Link to="/account"><Icons.Settings /> Account settings</Link>
        <button type="button" onClick={logout}><Icons.LogIn /> Log out</button>
      </div>
    </details>
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

function HomeRoute() {
  const { user, token } = React.useContext(AuthContext);
  return (user || token) ? <Navigate to="/dashboard" replace /> : <Home />;
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
      type="button"
      className="theme-toggle"
      onClick={() => setIsDark(d => !d)}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
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
          <span className="theme-label">Light</span>
        </>
      ) : (
        <>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
          <span className="theme-label">Dark</span>
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
      <Link to={user ? '/dashboard' : '/'} className="brand" aria-label="Spoolio home">
        <BrandLogo />
      </Link>
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
              <Route path="/" element={<HomeRoute />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/projects/:id" element={<ProjectDetail />} />
              <Route path="/parts" element={<BitsInventory />} />
              <Route path="/bits" element={<Navigate to="/parts" replace />} />
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
