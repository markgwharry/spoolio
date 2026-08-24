import React from 'react';
import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import AdminDataManager from './AdminDataManager';

vi.mock('../../FirmwareReleaseAdmin', () => ({ default: function FirmwareReleaseAdminMock() {
  return <section aria-label="Firmware releases">Firmware releases</section>;
} }));

const handlers = {
  onClose: vi.fn(),
  onRefresh: vi.fn(),
  onUpdateSpoolType: vi.fn(),
  onDeleteSpoolType: vi.fn(),
  onDeleteManufacturer: vi.fn(),
  onClearSubtype: vi.fn(),
};

const metadata = {
  spool_types: [],
  manufacturers: [],
  subtypes: [],
};

test('hides dormant firmware controls unless the backend enables OTA', () => {
  const { rerender } = render(
    <AdminDataManager metadata={{ ...metadata, features: { firmware_ota: false } }} {...handlers} />,
  );
  expect(screen.queryByLabelText('Firmware releases')).not.toBeInTheDocument();

  rerender(
    <AdminDataManager metadata={{ ...metadata, features: { firmware_ota: true } }} {...handlers} />,
  );
  expect(screen.getByLabelText('Firmware releases')).toBeInTheDocument();
});
