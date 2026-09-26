import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import AddSpoolModal from './AddSpoolModal';

const baseProps = () => ({
  open: true,
  materials: [{ id: 1, name: 'PLA' }],
  colors: [{ id: 2, name: 'Orange' }],
  manufacturers: [{ id: 3, name: 'Example Filament' }],
  spoolTypes: [{ id: 4, name: 'Cardboard 1 kg' }],
  subtypes: ['Matte'],
  mutations: {
    createMetadata: vi.fn(),
    addSpool: vi.fn().mockResolvedValue({ id: 99 }),
  },
  onMaterialAdded: vi.fn(),
  onColorAdded: vi.fn(),
  onManufacturerAdded: vi.fn(),
  onSpoolTypeAdded: vi.fn(),
  onSpoolAdded: vi.fn(),
  onMessage: vi.fn(),
  onClose: vi.fn(),
});

test('adds a spool through three focused steps', async () => {
  const props = baseProps();
  render(<AddSpoolModal {...props} />);

  expect(screen.getByRole('dialog', { name: 'Add a spool' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'What is it?' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Who made the spool?' })).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Material'), { target: { value: '1' } });
  fireEvent.change(screen.getByLabelText('Colour'), { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

  fireEvent.change(screen.getByLabelText('Manufacturer'), { target: { value: '3' } });
  fireEvent.change(screen.getByLabelText('Spool type'), { target: { value: '4' } });
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

  expect(screen.getAllByDisplayValue('1000')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: 'Add spool' }));

  await waitFor(() => expect(props.mutations.addSpool).toHaveBeenCalledWith(expect.objectContaining({
    material_id: '1',
    color_id: '2',
    manufacturer_id: '3',
    spool_type_id: '4',
    weight_start: 1000,
    weight_remaining: 1000,
  })));
  expect(props.onSpoolAdded).toHaveBeenCalledWith({ id: 99 });
  expect(props.onClose).toHaveBeenCalled();
});

test('creates missing metadata only after explicit confirmation', async () => {
  const props = baseProps();
  props.mutations.createMetadata.mockResolvedValue({ id: 8, name: 'ASA' });
  render(<AddSpoolModal {...props} />);

  fireEvent.change(screen.getByLabelText('Material'), { target: { value: '__new__' } });
  const input = screen.getByLabelText('New material');
  fireEvent.change(input, { target: { value: 'ASA' } });
  fireEvent.blur(input);
  expect(props.mutations.createMetadata).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Create' }));
  await waitFor(() => expect(props.mutations.createMetadata).toHaveBeenCalledWith('materials', { name: 'ASA' }));
  expect(props.onMaterialAdded).toHaveBeenCalledWith({ id: 8, name: 'ASA' });
});

test('keeps focus stable when the parent supplies a new close callback', () => {
  const props = baseProps();
  const nextOnClose = vi.fn();
  const requestFrame = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    callback();
    return 1;
  });
  const view = render(<AddSpoolModal {...props} />);
  const material = screen.getByLabelText('Material');
  material.focus();
  const initialFrameCount = requestFrame.mock.calls.length;

  view.rerender(<AddSpoolModal {...props} onClose={nextOnClose} />);

  expect(requestFrame).toHaveBeenCalledTimes(initialFrameCount);
  expect(material).toHaveFocus();
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(nextOnClose).toHaveBeenCalledOnce();
});
