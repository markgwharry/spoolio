import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { vi } from 'vitest';
import { AuthContext } from './AuthContext';
import HardwareManager from './HardwareManager';

const metadata = vi.hoisted(() => ({
  value: {
    materials: [],
    colors: [],
    manufacturers: [],
    reload: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('./hooks/useMetadata', () => ({
  default: () => metadata.value,
  HARDWARE_METADATA: [],
}));

function Harness({ authFetch }) {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <AuthContext.Provider value={{ authFetch }}>
      <button type="button" onClick={() => navigate('/hardware#register-device')}>
        Launch registration
      </button>
      <output data-testid="location">{`${location.pathname}${location.hash}`}</output>
      <HardwareManager />
    </AuthContext.Provider>
  );
}

test('clears the registration hash through the router so the action can reopen', async () => {
  const authFetch = vi.fn(async (url) => ({
    ok: true,
    json: async () => {
      if (url === '/api/hardware/orphans') return { orphans: [] };
      if (url === '/api/spools/') return { spools: [] };
      return [];
    },
  }));

  render(
    <MemoryRouter initialEntries={['/hardware#register-device']}>
      <Harness authFetch={authFetch} />
    </MemoryRouter>,
  );

  expect(await screen.findByRole('dialog', { name: 'Register a hardware device' })).toBeInTheDocument();
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/hardware'));

  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.queryByRole('dialog', { name: 'Register a hardware device' })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Launch registration' }));
  expect(await screen.findByRole('dialog', { name: 'Register a hardware device' })).toBeInTheDocument();
});

test('creates a spool from a decoded Bambu Lab tag', async () => {
  const orphan = {
    id: 7,
    nfc_tag_id: 'A1B2C3D4E5F60718293A4B5C6D7E8F90',
    hardware_device_id: 1,
    last_weight: 1250,
    last_seen: '2026-09-25T10:00:00',
    tag_format: 'bambu',
    tag_metadata: {
      format: 'bambu',
      material: 'PLA',
      variant: 'PLA Basic',
      variant_id: 'A00-W1',
      color_hex: '#FFFFFF',
      spool_weight: 1000,
    },
    suggestions: {
      material: 'PLA',
      subtype: 'Basic',
      color: 'white',
      manufacturer: 'Bambu Lab',
      weight_start: 1000,
    },
  };
  let orphans = [orphan];
  metadata.value = {
    ...metadata.value,
    spoolTypes: [
      { id: 3, name: 'Sunlu refill' },
      { id: 4, name: 'Bambu spool' },
    ],
  };
  const authFetch = vi.fn(async (url, options = {}) => {
    if (url === '/api/hardware/orphans/create-spool') {
      orphans = [];
      return { ok: true, json: async () => ({ spool: { id: 11 } }) };
    }
    return {
      ok: true,
      json: async () => {
        if (url === '/api/hardware/orphans') return { orphans };
        if (url === '/api/spools/') return { spools: [] };
        if (url === '/api/hardware/devices') {
          return [{ id: 1, name: 'Bench scale', device_id: 'scale-1', status: 'online' }];
        }
        return [];
      },
    };
  });

  render(
    <MemoryRouter initialEntries={['/hardware']}>
      <Harness authFetch={authFetch} />
    </MemoryRouter>,
  );

  expect(await screen.findByText('PLA Basic')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Create spool' }));

  const dialog = await screen.findByRole('dialog', { name: 'Create spool from tag' });
  expect(dialog).toBeInTheDocument();
  expect(screen.getByLabelText('Material')).toHaveValue('PLA');
  expect(screen.getByLabelText('Subtype')).toHaveValue('Basic');
  expect(screen.getByLabelText('Spool type')).toHaveValue('4');
  fireEvent.change(screen.getByLabelText('Colour name'), { target: { value: 'Jade White' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Create spool' }));

  await waitFor(() => expect(screen.getByText('Spool created and tag linked.')).toBeInTheDocument());
  const createCall = authFetch.mock.calls.find(([url]) => url === '/api/hardware/orphans/create-spool');
  expect(JSON.parse(createCall[1].body)).toEqual({
    nfc_tag_id: orphan.nfc_tag_id,
    material: 'PLA',
    subtype: 'Basic',
    color: 'Jade White',
    manufacturer: 'Bambu Lab',
    weight_start: 1000,
    spool_type_id: 4,
  });
  expect(screen.queryByRole('dialog', { name: 'Create spool from tag' })).not.toBeInTheDocument();
});
