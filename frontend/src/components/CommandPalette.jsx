import React, { useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthContext } from '../AuthContext';

/**
 * Global Cmd/Ctrl+K command palette. Self-gates to authenticated users.
 * Navigation + quick actions; built on the Workshop identity.
 */
export default function CommandPalette() {
  const { user, logout } = useContext(AuthContext);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);
  const [light, setLight] = useState(
    () => typeof document !== 'undefined' && document.documentElement.classList.contains('light')
  );

  const commands = useMemo(() => {
    const go = (to) => () => navigate(to);
    return [
      { id: 'add-spool', label: 'Add a spool', section: 'Actions', keywords: 'new create spool filament', run: () => navigate('/dashboard#add-spool') },
      { id: 'nav-dashboard', label: 'Go to Dashboard', section: 'Navigate', keywords: 'inventory spools rack home', run: go('/dashboard') },
      { id: 'nav-analytics', label: 'Go to Analytics', section: 'Navigate', keywords: 'usage projects stats charts cost', run: go('/analytics') },
      { id: 'nav-hardware', label: 'Go to Hardware', section: 'Navigate', keywords: 'devices nfc scale printer spoolman', run: go('/hardware') },
      { id: 'nav-bits', label: 'Go to Bits', section: 'Navigate', keywords: 'parts components inventory', run: go('/bits') },
      { id: 'nav-account', label: 'Go to Account', section: 'Navigate', keywords: 'settings profile password integration spoolman', run: go('/account') },
      { id: 'theme', label: light ? 'Switch to dark mode' : 'Switch to light mode', section: 'Actions', keywords: 'theme dark light appearance', run: () => window.dispatchEvent(new Event('spoolio:toggle-theme')) },
      { id: 'logout', label: 'Log out', section: 'Actions', keywords: 'sign out exit', run: () => logout() },
    ];
  }, [navigate, logout, light]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(c => (c.label + ' ' + c.keywords).toLowerCase().includes(q));
  }, [query, commands]);

  // Global open/close shortcut (only mounted for authed users).
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(o => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Allow other UI (e.g. the header hint button) to open the palette.
  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener('spoolio:open-cmdk', onOpen);
    return () => window.removeEventListener('spoolio:open-cmdk', onOpen);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery('');
      setActive(0);
      // refresh theme label to reflect the current mode each time we open
      setLight(document.documentElement.classList.contains('light'));
      // focus after the panel mounts
      const t = window.setTimeout(() => inputRef.current?.focus(), 20);
      return () => window.clearTimeout(t);
    }
  }, [open]);

  useEffect(() => { setActive(0); }, [query]);

  if (!user) return null;

  const run = (cmd) => {
    setOpen(false);
    cmd.run();
  };

  const onInputKeyDown = (e) => {
    if (e.key === 'Escape') { setOpen(false); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); if (results[active]) run(results[active]); }
  };

  if (!open) return null;

  return (
    <div className="cmdk-overlay" onClick={() => setOpen(false)}>
      <div
        className="cmdk-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="cmdk-input-row">
          <svg className="cmdk-search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            className="cmdk-input"
            placeholder="Type a command or search…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKeyDown}
            aria-label="Command palette search"
          />
          <kbd className="cmdk-kbd">esc</kbd>
        </div>
        <ul className="cmdk-list" ref={listRef} role="listbox" aria-label="Commands">
          {results.length === 0 && <li className="cmdk-empty">No matching commands</li>}
          {results.map((cmd, i) => (
            <li
              key={cmd.id}
              role="option"
              aria-selected={i === active}
              className={`cmdk-item${i === active ? ' is-active' : ''}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => run(cmd)}
            >
              <span className="cmdk-item-label">{cmd.label}</span>
              <span className="cmdk-item-section">{cmd.section}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
