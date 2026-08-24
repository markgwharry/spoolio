import React, { createContext, useState, useCallback, useMemo, useRef } from 'react';

export const AuthContext = createContext();

export function AuthProvider({ children }) {
  // Always default to '' if no token is present
  const [token, setToken] = useState(() => localStorage.getItem('token') || '');
  const [refreshToken, setRefreshToken] = useState(() => localStorage.getItem('refreshToken') || '');
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  // Track if a refresh is in progress to avoid multiple simultaneous refreshes
  const refreshPromiseRef = useRef(null);

  const login = useCallback((accessToken, refreshTok, userData) => {
    if (typeof accessToken !== 'string') {
      accessToken = accessToken && accessToken.access_token ? accessToken.access_token : '';
    }
    setToken(accessToken);
    setRefreshToken(refreshTok || '');
    setUser(userData);
    localStorage.setItem('token', accessToken);
    localStorage.setItem('refreshToken', refreshTok || '');
    try {
      localStorage.setItem('user', JSON.stringify(userData));
    } catch {
      // Ignore storage failures (e.g. quota exceeded)
    }
  }, []);

  const logout = useCallback(async () => {
    const currentRefreshToken = localStorage.getItem('refreshToken');
    setToken('');
    setRefreshToken('');
    setUser(null);
    localStorage.removeItem('token');
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('user');

    if (currentRefreshToken) {
      try {
        await fetch('/api/logout', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${currentRefreshToken}`,
          },
        });
      } catch (error) {
        // Local logout still succeeds when the server cannot be reached.
        console.error('[AuthContext] Server logout failed:', error);
      }
    }
  }, []);

  const updateStoredUser = useCallback((nextUser) => {
    setUser(nextUser);
    if (nextUser) {
      try {
        localStorage.setItem('user', JSON.stringify(nextUser));
      } catch {
        // Ignore storage failures
      }
    } else {
      localStorage.removeItem('user');
    }
  }, []);

  // Attempt to refresh the access token using the refresh token
  const refreshAccessToken = useCallback(async () => {
    const currentRefreshToken = localStorage.getItem('refreshToken');
    if (!currentRefreshToken) {
      return null;
    }

    // If a refresh is already in progress, wait for it
    if (refreshPromiseRef.current) {
      return refreshPromiseRef.current;
    }

    refreshPromiseRef.current = (async () => {
      try {
        const response = await fetch('/api/refresh', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${currentRefreshToken}`,
            'Content-Type': 'application/json',
          },
        });

        if (response.ok) {
          const data = await response.json();
          const newToken = data.access_token;
          setToken(newToken);
          localStorage.setItem('token', newToken);
          return newToken;
        } else {
          // Refresh token is invalid or expired - logout
          logout();
          return null;
        }
      } catch (error) {
        console.error('[AuthContext] Token refresh failed:', error);
        logout();
        return null;
      } finally {
        refreshPromiseRef.current = null;
      }
    })();

    return refreshPromiseRef.current;
  }, [logout]);

  // Helper for authenticated API requests with automatic token refresh
  const authFetch = useCallback(async (url, options = {}) => {
    const makeRequest = (accessToken) => {
      const headers = { ...options.headers };
      if (accessToken && typeof accessToken === 'string') {
        headers['Authorization'] = `Bearer ${accessToken}`;
      }
      return fetch(url, { ...options, headers });
    };

    // Get current token from localStorage to ensure we have the latest
    let currentToken = localStorage.getItem('token') || token;
    let response = await makeRequest(currentToken);

    // If we get a 401, try to refresh the token and retry once
    if (response.status === 401) {
      const newToken = await refreshAccessToken();
      if (newToken) {
        // Retry the request with the new token
        response = await makeRequest(newToken);
      }
    }

    return response;
  }, [token, refreshAccessToken]);

  const contextValue = useMemo(
    () => ({ token, refreshToken, user, login, logout, authFetch, updateStoredUser }),
    [token, refreshToken, user, login, logout, authFetch, updateStoredUser]
  );

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}
