import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import App from './App';

beforeEach(() => {
  localStorage.clear();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      mode: 'waitlist',
      action: 'waitlist',
      registration_enabled: false,
      waitlist_enabled: true,
      password_required: false,
    }),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

test('renders the logged-out login route', async () => {
  render(
    <MemoryRouter initialEntries={['/login']}>
      <App />
    </MemoryRouter>
  );

  expect(screen.getByRole('img', { name: /spoolio logo/i })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /welcome back/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^login$/i })).toBeInTheDocument();
  expect(await screen.findByRole('link', { name: /join the waitlist/i })).toBeInTheDocument();
});

test('renders the hosted waitlist from the registration contract', async () => {
  render(
    <MemoryRouter initialEntries={['/register']}>
      <App />
    </MemoryRouter>
  );

  expect(await screen.findByRole('heading', { name: /join the spoolio waitlist/i })).toBeInTheDocument();
  expect(screen.queryByLabelText(/^password$/i)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /join waitlist/i })).toBeInTheDocument();
});

test('creates the one-time self-hosted owner account and then closes registration', async () => {
  let statusRequests = 0;
  global.fetch = vi.fn(async (url, options = {}) => {
    if (url === '/api/registration') {
      statusRequests += 1;
      return {
        ok: true,
        json: async () => statusRequests === 1 ? ({
          mode: 'first-user',
          action: 'create-owner',
          registration_enabled: true,
          waitlist_enabled: false,
          password_required: true,
        }) : ({
          mode: 'first-user',
          action: 'closed',
          registration_enabled: false,
          waitlist_enabled: false,
          password_required: false,
        }),
      };
    }
    if (url === '/api/register' && options.method === 'POST') {
      return {
        ok: true,
        status: 201,
        json: async () => ({
          msg: 'Owner account created. You can now log in.',
          account_created: true,
        }),
      };
    }
    throw new Error(`Unexpected request: ${url}`);
  });

  render(
    <MemoryRouter initialEntries={['/register']}>
      <App />
    </MemoryRouter>
  );

  expect(await screen.findByRole('heading', { name: /create the owner account/i })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/preferred username/i), {
    target: { value: 'owner' },
  });
  fireEvent.change(screen.getByLabelText(/email address/i), {
    target: { value: 'owner@example.com' },
  });
  fireEvent.change(screen.getByLabelText(/^password$/i), {
    target: { value: 'OwnerPass1' },
  });
  fireEvent.change(screen.getByLabelText(/owner setup code/i), {
    target: { value: 'setup-token-from-container' },
  });
  fireEvent.click(screen.getByRole('button', { name: /create owner account/i }));

  expect(await screen.findByRole('heading', { name: /owner account created/i })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /log in/i })).toBeInTheDocument();
  await waitFor(() => expect(statusRequests).toBe(2));

  const registrationCall = global.fetch.mock.calls.find(
    ([url, options]) => url === '/api/register' && options?.method === 'POST'
  );
  expect(JSON.parse(registrationCall[1].body)).toEqual({
    username: 'owner',
    email: 'owner@example.com',
    password: 'OwnerPass1',
    registration_token: 'setup-token-from-container',
  });
});

test('shows a closed state without an account form', async () => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      mode: 'closed',
      action: 'closed',
      registration_enabled: false,
      waitlist_enabled: false,
      password_required: false,
    }),
  });

  render(
    <MemoryRouter initialEntries={['/register']}>
      <App />
    </MemoryRouter>
  );

  expect(await screen.findByRole('heading', { name: /registration is closed/i })).toBeInTheDocument();
  expect(screen.queryByLabelText(/preferred username/i)).not.toBeInTheDocument();
});
