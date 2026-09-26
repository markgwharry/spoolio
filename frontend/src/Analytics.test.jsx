import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { AuthContext } from './AuthContext';
import Analytics from './Analytics';

const metadata = vi.hoisted(() => ({
  value: {
    materials: [{ id: 1, name: 'PLA' }],
    colors: [{ id: 2, name: 'Orange' }],
    loading: false,
  },
}));

vi.mock('./hooks/useMetadata', () => ({
  default: () => metadata.value,
  ANALYTICS_METADATA: [],
}));

test('shows a valid zero-day average depletion forecast', async () => {
  const authFetch = vi.fn(async (url) => ({
    ok: true,
    json: async () => {
      if (url === '/api/spoolhistory/') {
        return {
          history: [{
            id: 10,
            spool_id: 7,
            weight_used: 1000,
            date: new Date().toISOString(),
          }],
        };
      }
      if (url === '/api/projects/') return { projects: [] };
      if (url === '/api/spools/') {
        return {
          spools: [{
            id: 7,
            material_id: 1,
            color_id: 2,
            weight_start: 1000,
            weight_remaining: 1,
          }],
        };
      }
      throw new Error(`Unexpected request: ${url}`);
    },
  }));

  render(
    <MemoryRouter>
      <AuthContext.Provider value={{ authFetch }}>
        <Analytics />
      </AuthContext.Provider>
    </MemoryRouter>,
  );

  const label = await screen.findByText('Avg remaining');
  expect(label.previousElementSibling).toHaveTextContent('0 days');
});
