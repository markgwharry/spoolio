import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { vi } from 'vitest';
import { AuthContext } from './AuthContext';
import Dashboard from './Dashboard';

const mocks = vi.hoisted(() => ({
  data: null,
  mutations: null,
  view: null,
  controller: null,
}));

vi.mock('./hooks/useDashboardData', () => ({ default: () => mocks.data }));
vi.mock('./hooks/useSpoolMutations', () => ({ default: () => mocks.mutations }));
vi.mock('./hooks/useDashboardView', () => ({ default: () => mocks.view }));
vi.mock('./hooks/useDashboardController', () => ({ default: () => mocks.controller }));

const filters = {
  materialId: '',
  colorId: '',
  manufacturerId: '',
  subtypeMode: 'all',
  lowStockOnly: false,
  includeRefills: true,
  sortMode: 'rainbow',
};

const refill = {
  id: 21,
  material_id: 1,
  color_id: 2,
  manufacturer_id: 3,
  weight_total: 1000,
  weight_remaining: 750,
};

const spool = {
  id: 7,
  material_id: 1,
  color_id: 2,
  manufacturer_id: 3,
  spool_type_id: 4,
  weight_start: 1000,
  weight_remaining: 10,
  low_stock_threshold: 100,
  is_empty: false,
};

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.hash}`}</output>;
}

function renderDashboard(initialEntry = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuthContext.Provider value={{ user: { username: 'maker', is_admin: false }, authFetch: vi.fn() }}>
        <Dashboard />
        <LocationProbe />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocks.data = {
    spools: [],
    refills: [refill],
    emptySpools: [],
    materials: [{ id: 1, name: 'PLA' }],
    colors: [{ id: 2, name: 'Orange' }],
    manufacturers: [{ id: 3, name: 'Example Filament' }],
    spoolTypes: [{ id: 4, name: 'Cardboard 1 kg' }],
    subtypes: [],
    loading: false,
    error: '',
    setSpools: vi.fn(),
    setRefills: vi.fn(),
    setEmptySpools: vi.fn(),
    setMaterials: vi.fn(),
    setColors: vi.fn(),
    setManufacturers: vi.fn(),
    setSpoolTypes: vi.fn(),
    reloadSpools: vi.fn(),
    reloadEmptySpools: vi.fn(),
  };
  mocks.mutations = {
    addRefill: vi.fn(),
    addEmptySpool: vi.fn(),
  };
  mocks.view = {
    filters: { ...filters },
    hideEmpty: false,
    visibleSpools: [],
    visibleRefills: [refill],
    groupedSpools: { PLA: { Orange: [] } },
    setHideEmpty: vi.fn(),
    updateFilter: vi.fn(),
    resetFilters: vi.fn(),
  };
  mocks.controller = {
    selectedSpool: null,
    spoolHistory: [],
    loadingHistory: false,
    showAddSpool: false,
    showReport: false,
    showDataManager: false,
    adminMetadata: null,
    expanded: { 'PLA-Orange': true },
    collapsed: {},
    highlightedSpoolId: null,
    setShowAddSpool: vi.fn(),
    setSelectedSpool: vi.fn(),
    setShowReport: vi.fn(),
    setShowDataManager: vi.fn(),
    jumpToSpoolGroup: vi.fn(),
    toggleGroup: vi.fn(),
    toggleMaterial: vi.fn(),
    openSpoolDetail: vi.fn(),
    updateSpool: vi.fn(),
    assembleRefill: vi.fn(),
    deleteRefill: vi.fn(),
    updateHistory: vi.fn(),
    recordUsage: vi.fn(),
    openDataManager: vi.fn(),
    refreshAdminMetadata: vi.fn(),
    runAdminMutation: vi.fn(),
  };
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
    callback();
    return 1;
  });
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

test('keeps refill-only inventory and inventory entry tools accessible', () => {
  renderDashboard();

  expect(screen.getByRole('heading', { name: 'PLA' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Bring into use' })).toBeInTheDocument();
  expect(screen.getByText('Manage refills and empty spools')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Add Refill' })).toBeInTheDocument();
});

test('clears filters before jumping from a global low-stock alert', () => {
  mocks.data.spools = [spool];
  mocks.view.filters = { ...filters, materialId: '999' };
  mocks.view.visibleSpools = [];
  mocks.view.groupedSpools = {};

  renderDashboard();
  fireEvent.click(screen.getByText(/10g left/).closest('li'));

  expect(mocks.view.resetFilters).toHaveBeenCalledOnce();
  expect(mocks.controller.jumpToSpoolGroup).toHaveBeenCalledWith(spool);
  expect(mocks.view.resetFilters.mock.invocationCallOrder[0])
    .toBeLessThan(mocks.controller.jumpToSpoolGroup.mock.invocationCallOrder[0]);
});

test('retains find-spool until loading finishes and the controls are mounted', async () => {
  mocks.data.loading = true;
  mocks.data.spools = [spool];
  mocks.view.visibleSpools = [spool];
  mocks.view.groupedSpools = { PLA: { Orange: [spool] } };

  const view = renderDashboard('/dashboard#find-spool');
  expect(screen.getByTestId('location')).toHaveTextContent('/dashboard#find-spool');

  mocks.data.loading = false;
  view.rerender(
    <MemoryRouter initialEntries={['/dashboard#find-spool']}>
      <AuthContext.Provider value={{ user: { username: 'maker', is_admin: false }, authFetch: vi.fn() }}>
        <Dashboard />
        <LocationProbe />
      </AuthContext.Provider>
    </MemoryRouter>,
  );

  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/dashboard'));
  expect(screen.getByLabelText('Filter by material')).toHaveFocus();
});
