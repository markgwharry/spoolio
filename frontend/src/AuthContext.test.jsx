import React, { useContext } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import { AuthContext, AuthProvider } from './AuthContext';


function SessionHarness() {
  const { user, logout } = useContext(AuthContext);
  return (
    <div>
      <span>{user ? user.username : 'signed out'}</span>
      <button type="button" onClick={logout}>Log out</button>
    </div>
  );
}


beforeEach(() => {
  localStorage.clear();
  global.fetch = vi.fn().mockResolvedValue({ ok: true });
});


afterEach(() => {
  vi.restoreAllMocks();
});


test('logout clears local state and revokes the refresh token on the server', async () => {
  localStorage.setItem('token', 'access-token');
  localStorage.setItem('refreshToken', 'refresh-token');
  localStorage.setItem('user', JSON.stringify({ username: 'alice' }));

  render(
    <AuthProvider>
      <SessionHarness />
    </AuthProvider>
  );

  fireEvent.click(screen.getByRole('button', { name: /log out/i }));

  expect(await screen.findByText('signed out')).toBeInTheDocument();
  expect(localStorage.getItem('token')).toBeNull();
  expect(localStorage.getItem('refreshToken')).toBeNull();
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    '/api/logout',
    {
      method: 'POST',
      headers: { Authorization: 'Bearer refresh-token' },
    }
  ));
});
