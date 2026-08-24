import { requestJson } from '../../api/request';
import { buildSuppliesReportRows } from './SuppliesReport';
import { sortGroupedSpools } from '../../hooks/useDashboardView';
import { vi } from 'vitest';

describe('dashboard data contracts', () => {
  test('requestJson preserves API error messages and status', async () => {
    const authFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ msg: 'Already exists' }),
    });

    await expect(requestJson(authFetch, '/api/example', undefined, 'Fallback'))
      .rejects.toMatchObject({ message: 'Already exists', status: 409 });
  });

  test('supplies report combines active and refill weight under the same key', () => {
    const rows = buildSuppliesReportRows({
      spools: [{
        id: 1,
        material_id: 10,
        color_id: 20,
        manufacturer_id: 30,
        subtype: 'Matte',
        weight_remaining: 250,
        low_stock_threshold: 100,
        is_empty: false,
      }],
      refills: [{
        id: 2,
        material_id: 10,
        color_id: 20,
        manufacturer_id: 30,
        subtype: 'Matte',
        weight_total: 1000,
      }],
      materials: [{ id: 10, name: 'PLA' }],
      colors: [{ id: 20, name: 'Black' }],
      filters: {
        materialId: '',
        colorId: '',
        manufacturerId: '',
        subtypeMode: 'all',
        lowStockOnly: false,
        includeRefills: true,
      },
    });

    expect(rows).toEqual([expect.objectContaining({
      material: 'PLA',
      color: 'Black',
      subtype: 'Matte',
      activeCount: 1,
      activeWeight: 250,
      reserveCount: 1,
      reserveWeight: 1000,
      totalWeight: 1250,
    })]);
  });

  test('low-stock sorting prioritizes both material and color groups', () => {
    const grouped = {
      PETG: {
        Blue: [{ id: 1, weight_remaining: 500, low_stock_threshold: 100 }],
      },
      PLA: {
        Green: [{ id: 2, weight_remaining: 400, low_stock_threshold: 100 }],
        Red: [{ id: 3, weight_remaining: 50, low_stock_threshold: 100 }],
      },
    };

    const sorted = sortGroupedSpools(grouped, 'low-stock');

    expect(Object.keys(sorted)).toEqual(['PLA', 'PETG']);
    expect(Object.keys(sorted.PLA)).toEqual(['Red', 'Green']);
  });
});
