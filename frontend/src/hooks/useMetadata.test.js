import { act, renderHook } from '@testing-library/react';
import { vi } from 'vitest';
import useMetadata from './useMetadata';

describe('useMetadata', () => {
  test('deduplicates concurrent resource loads and shares the cached result', async () => {
    const authFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ materials: [{ id: 1, name: 'PLA' }] }),
    });
    const first = renderHook(() => useMetadata(authFetch, ['materials']));
    const second = renderHook(() => useMetadata(authFetch, ['materials']));

    await act(async () => {
      await Promise.all([
        first.result.current.reload(),
        second.result.current.reload(),
      ]);
    });

    expect(authFetch).toHaveBeenCalledTimes(1);
    expect(first.result.current.materials).toEqual([{ id: 1, name: 'PLA' }]);
    expect(second.result.current.materials).toEqual([{ id: 1, name: 'PLA' }]);

    const cached = renderHook(() => useMetadata(authFetch, ['materials']));
    expect(cached.result.current.materials).toEqual([{ id: 1, name: 'PLA' }]);
  });
});
